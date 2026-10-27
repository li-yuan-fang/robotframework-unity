using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace RobotFramework.UnityBridge
{
    internal sealed class ElementSnapshot
    {
        internal string Id;
        internal bool Exists;
        internal bool Visible;
        internal bool? Enabled;

        internal JObject Json() => new JObject
        {
            ["id"] = Id, ["exists"] = Exists, ["visible"] = Visible,
            ["enabled"] = Enabled.HasValue ? new JValue(Enabled.Value) : JValue.CreateNull()
        };

        internal bool Matches(string state)
        {
            switch (state)
            {
                case "visible": return Exists && Visible;
                case "not visible": return !Exists || !Visible;
                case "enabled": return Exists && Enabled == true;
                case "disabled": return Exists && Enabled == false;
                default: return false;
            }
        }
    }

    internal static class UguiElementAdapter
    {
        internal static ElementSnapshot Snapshot(string id, out BridgeElement element)
        {
            element = ElementRegistry.Resolve(id);
            if (element == null) return new ElementSnapshot { Id = id, Exists = false, Visible = false, Enabled = null };
            Selectable selectable = Supported(element);
            return new ElementSnapshot { Id = id, Exists = true, Visible = IsVisible(element), Enabled = IsEnabled(selectable) };
        }

        private static Selectable Supported(BridgeElement element)
        {
            var selectable = element.Selectable;
            if (!(selectable is Button) && !(selectable is Toggle))
                throw new BridgeFault("UNSUPPORTED_ELEMENT", "Attach BridgeElement to the same GameObject as Button or Toggle");
            return selectable;
        }

        internal static bool IsEnabled(Selectable selectable)
        {
            if (!selectable.enabled || !selectable.interactable) return false;
            // Recompute instead of using Selectable's potentially stale cache on inactive UI.
            for (Transform current = selectable.transform; current != null; current = current.parent)
            {
                bool stop = false;
                foreach (var group in current.GetComponents<CanvasGroup>())
                {
                    if (!group.interactable) return false;
                    if (group.ignoreParentGroups) stop = true;
                }
                if (stop) break;
            }
            return true;
        }

        private static Camera EventCamera(Canvas canvas)
        {
            Canvas root = canvas.rootCanvas;
            if (root.targetDisplay != 0 || root.renderMode == RenderMode.WorldSpace)
                throw new BridgeFault("UNSUPPORTED_CANVAS", "Only display 0 screen-space canvases are supported");
            if (root.renderMode == RenderMode.ScreenSpaceOverlay) return null;
            if (root.worldCamera == null || root.worldCamera.targetTexture != null)
                throw new BridgeFault("UNSUPPORTED_CANVAS", "Screen Space Camera requires a camera without RenderTexture output");
            return root.worldCamera;
        }

        private static bool IsVisible(BridgeElement element)
        {
            if (!element.gameObject.activeInHierarchy) return false;
            bool visible = false;
            foreach (var graphic in element.Graphics())
            {
                Canvas canvas = graphic.canvas;
                if (canvas == null) continue;
                Camera camera = EventCamera(canvas);
                if (!graphic.isActiveAndEnabled || !canvas.isActiveAndEnabled || !canvas.rootCanvas.isActiveAndEnabled
                    || (camera != null && !camera.isActiveAndEnabled) || graphic.canvasRenderer.cull) continue;
                // Native inherited alpha follows CanvasGroup inheritance for this Unity version.
                float alpha = graphic.color.a * graphic.canvasRenderer.GetAlpha() * graphic.canvasRenderer.GetInheritedAlpha();
                if (alpha <= 0.01f) continue;
                Rect rect = graphic.rectTransform.rect;
                if (rect.width <= 0 || rect.height <= 0) continue;
                var corners = new Vector3[4];
                graphic.rectTransform.GetWorldCorners(corners);
                Vector2 min = new Vector2(float.PositiveInfinity, float.PositiveInfinity);
                Vector2 max = new Vector2(float.NegativeInfinity, float.NegativeInfinity);
                bool inFront = camera == null;
                foreach (var corner in corners)
                {
                    if (camera != null && camera.WorldToScreenPoint(corner).z > 0) inFront = true;
                    Vector2 screen = RectTransformUtility.WorldToScreenPoint(camera, corner);
                    min = Vector2.Min(min, screen);
                    max = Vector2.Max(max, screen);
                }
                Rect viewport = camera == null ? new Rect(0, 0, Screen.width, Screen.height) : camera.pixelRect;
                visible |= inFront && Rect.MinMaxRect(min.x, min.y, max.x, max.y).Overlaps(viewport);
            }
            return visible;
        }

        internal static bool PrepareClick(BridgeElement element, RpcRequest request,
            out PointerEventData pointer, out string reason)
        {
            pointer = null;
            var system = EventSystem.current;
            if (system == null || !system.isActiveAndEnabled) { reason = "no_event_system"; return false; }
            var rect = element.transform as RectTransform;
            var canvas = element.GetComponentInParent<Canvas>();
            if (rect == null || canvas == null) { reason = "not_visible"; return false; }
            Vector3 local = new Vector3(Mathf.Lerp(rect.rect.xMin, rect.rect.xMax, (float)request.X),
                Mathf.Lerp(rect.rect.yMin, rect.rect.yMax, (float)request.Y), 0);
            Vector2 position = RectTransformUtility.WorldToScreenPoint(EventCamera(canvas), rect.TransformPoint(local));
            pointer = new PointerEventData(system)
            {
                pointerId = -1, button = PointerEventData.InputButton.Left, position = position,
                pressPosition = position, eligibleForClick = true, clickCount = 1, clickTime = Time.unscaledTime
            };
            if (!HitTarget(element, pointer, out var hit)) { reason = "blocked"; return false; }
            GameObject downOwner = ExecuteEvents.GetEventHandler<IPointerDownHandler>(hit.gameObject);
            if (downOwner != null && downOwner != element.gameObject) { reason = "pointer_press_mismatch"; return false; }
            pointer.pointerCurrentRaycast = hit;
            pointer.pointerPressRaycast = hit;
            pointer.pointerEnter = hit.gameObject;
            reason = null;
            return true;
        }

        private static bool HitTarget(BridgeElement element, PointerEventData pointer, out RaycastResult hit)
        {
            hit = default;
            var results = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointer, results);
            foreach (var result in results)
            {
                if (result.gameObject == null) continue;
                hit = result;
                return ExecuteEvents.GetEventHandler<IPointerClickHandler>(result.gameObject) == element.gameObject;
            }
            return false;
        }

        internal static void DispatchClick(BridgeElement element, RpcRequest request,
            PointerEventData pointer, Func<bool> cancelled)
        {
            var system = EventSystem.current;
            GameObject press = null;
            bool started = false;
            bool upSent = false;
            try
            {
                if (cancelled() || BridgeClock.Now >= request.Deadline)
                    throw new BridgeFault("ELEMENT_CLICK_TIMEOUT", "Click cancelled or expired before dispatch",
                        new JObject { ["effect"] = "not_started" });
                // Selection callbacks may have side effects too, so record the stage first.
                started = true;
                GameObject select = ExecuteEvents.GetEventHandler<ISelectHandler>(pointer.pointerCurrentRaycast.gameObject);
                if (select != system.currentSelectedGameObject) system.SetSelectedGameObject(null, pointer);
                EnsureStillValid(element, request, system, pointer, cancelled);
                press = ExecuteEvents.ExecuteHierarchy(pointer.pointerCurrentRaycast.gameObject, pointer, ExecuteEvents.pointerDownHandler);
                if (press == null) press = element.gameObject;
                pointer.pointerPress = press;
                pointer.rawPointerPress = pointer.pointerCurrentRaycast.gameObject;
                EnsureStillValid(element, request, system, pointer, cancelled);
                upSent = true;
                ExecuteEvents.Execute(press, pointer, ExecuteEvents.pointerUpHandler);
                EnsureStillValid(element, request, system, pointer, cancelled);
                if (press != element.gameObject || !pointer.eligibleForClick)
                    throw new BridgeFault("CLICK_INTERRUPTED", "Pointer press lost click eligibility");
                ExecuteEvents.Execute(element.gameObject, pointer, ExecuteEvents.pointerClickHandler);
            }
            catch (BridgeFault fault)
            {
                fault.Details["effect"] = started ? "started" : "not_started";
                throw;
            }
            catch (Exception error)
            {
                throw new BridgeFault("CLICK_INTERRUPTED", "Exception during pointer dispatch: " + error.Message,
                    new JObject { ["effect"] = started ? "started" : "not_started" });
            }
            finally
            {
                if (!upSent && press != null) ExecuteEvents.Execute(press, pointer, ExecuteEvents.pointerUpHandler);
                pointer.eligibleForClick = false;
                pointer.pointerPress = null;
                pointer.rawPointerPress = null;
            }
        }

        private static void EnsureStillValid(BridgeElement element, RpcRequest request, EventSystem system,
            PointerEventData pointer, Func<bool> cancelled)
        {
            if (cancelled() || element == null || EventSystem.current != system || !system.isActiveAndEnabled)
                throw new BridgeFault("CLICK_INTERRUPTED", "Target or event system was removed/cancelled");
            var snapshot = Snapshot(request.ElementId, out var resolved);
            if (resolved != element || !snapshot.Visible || snapshot.Enabled != true || !HitTarget(element, pointer, out _))
                throw new BridgeFault("CLICK_INTERRUPTED", "Target changed or lost interaction eligibility during dispatch");
        }
    }
}
