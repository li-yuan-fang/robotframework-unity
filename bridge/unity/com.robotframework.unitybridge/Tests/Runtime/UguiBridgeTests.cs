using System;
using System.Collections;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace RobotFramework.UnityBridge.Tests
{
    public sealed class DisableOnPointerDown : MonoBehaviour, IPointerDownHandler
    {
        public void OnPointerDown(PointerEventData data) { GetComponent<Button>().interactable = false; }
    }

    public sealed class UguiBridgeTests
    {
        private GameObject root;
        private EventSystem previousSystem;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            root = new GameObject("Bridge test root");
            previousSystem = EventSystem.current;
            var system = new GameObject("Test EventSystem", typeof(EventSystem));
            system.transform.SetParent(root.transform);
            EventSystem.current = system.GetComponent<EventSystem>();
            var canvas = new GameObject("Canvas", typeof(RectTransform), typeof(Canvas), typeof(GraphicRaycaster));
            canvas.transform.SetParent(root.transform);
            canvas.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.GetComponent<Canvas>().sortingOrder = 32000;
            yield return null;
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            Time.timeScale = 1;
            UnityEngine.Object.Destroy(root);
            yield return null;
            EventSystem.current = previousSystem;
            ElementRegistry.Prune();
        }

        private BridgeElement MakeButton(string id)
        {
            var obj = new GameObject(id, typeof(RectTransform), typeof(Image), typeof(Button));
            obj.transform.SetParent(root.GetComponentInChildren<Canvas>().transform, false);
            var rect = obj.GetComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
            rect.sizeDelta = new Vector2(200, 80);
            obj.GetComponent<Button>().targetGraphic = obj.GetComponent<Image>();
            var element = obj.AddComponent<BridgeElement>();
            element.Configure(id);
            return element;
        }

        private static RpcRequest ClickRequest(string id) => new RpcRequest
        { Id = 1, Method = "element.click", ElementId = id, TimeoutMs = 1000, ReceivedAt = BridgeClock.Now };

        [Test]
        public void MissingIsHiddenButNotDisabled()
        {
            var snapshot = UguiElementAdapter.Snapshot("test.missing", out _);
            Assert.IsTrue(snapshot.Matches("not visible"));
            Assert.IsFalse(snapshot.Matches("disabled"));
            Assert.IsNull(snapshot.Enabled);
        }

        [UnityTest]
        public IEnumerator InactiveAndDisabledAreDifferent()
        {
            var element = MakeButton("test.inactive");
            yield return null;
            element.gameObject.SetActive(false);
            var snapshot = UguiElementAdapter.Snapshot(element.ElementId, out _);
            Assert.IsFalse(snapshot.Visible);
            Assert.IsTrue(snapshot.Enabled);
            element.GetComponent<Button>().interactable = false;
            Assert.IsTrue(UguiElementAdapter.Snapshot(element.ElementId, out _).Matches("disabled"));
        }

        [UnityTest]
        public IEnumerator ButtonDispatchRunsOnce()
        {
            var element = MakeButton("test.button");
            int count = 0;
            element.GetComponent<Button>().onClick.AddListener(() => count++);
            yield return null;
            Canvas.ForceUpdateCanvases();
            var request = ClickRequest(element.ElementId);
            Assert.IsTrue(UguiElementAdapter.PrepareClick(element, request, out var pointer, out _));
            UguiElementAdapter.DispatchClick(element, request, pointer, () => false);
            Assert.AreEqual(1, count);
        }

        [UnityTest]
        public IEnumerator OverlayPreventsClick()
        {
            var element = MakeButton("test.blocked");
            var overlay = new GameObject("Blocker", typeof(RectTransform), typeof(Image));
            overlay.transform.SetParent(element.transform.parent, false);
            overlay.GetComponent<RectTransform>().sizeDelta = new Vector2(220, 100);
            yield return null;
            Canvas.ForceUpdateCanvases();
            Assert.IsFalse(UguiElementAdapter.PrepareClick(element, ClickRequest(element.ElementId), out _, out var reason));
            Assert.AreEqual("blocked", reason);
        }

        [UnityTest]
        public IEnumerator DisableDuringDownDoesNotClick()
        {
            var element = MakeButton("test.interrupted");
            element.gameObject.AddComponent<DisableOnPointerDown>();
            int count = 0;
            element.GetComponent<Button>().onClick.AddListener(() => count++);
            yield return null;
            Canvas.ForceUpdateCanvases();
            var request = ClickRequest(element.ElementId);
            Assert.IsTrue(UguiElementAdapter.PrepareClick(element, request, out var pointer, out _));
            var fault = Assert.Throws<BridgeFault>(() => UguiElementAdapter.DispatchClick(element, request, pointer, () => false));
            Assert.AreEqual("CLICK_INTERRUPTED", fault.Code);
            Assert.AreEqual("started", fault.Details["effect"].Value<string>());
            Assert.AreEqual(0, count);
        }

        [Test]
        public void DuplicateIdFailsInsteadOfPickingOne()
        {
            MakeButton("test.duplicate");
            MakeButton("test.duplicate");
            Assert.AreEqual("AMBIGUOUS_ELEMENT", Assert.Throws<BridgeFault>(() => ElementRegistry.Resolve("test.duplicate")).Code);
        }

        [UnityTest]
        public IEnumerator TimeoutStillExpiresAtTimeScaleZero()
        {
            Time.timeScale = 0;
            var request = new RpcRequest { Id = 1, Method = "element.wait", ElementId = "test.missing",
                State = "disabled", TimeoutMs = 40, ReceivedAt = BridgeClock.Now };
            var work = new RpcWork(request);
            var operation = new PendingOperation(work, 0.01);
            operation.Tick();
            yield return new WaitForSecondsRealtime(0.06f);
            operation.Tick();
            Assert.IsTrue(work.Completion.Task.IsCompleted);
            Assert.AreEqual("ELEMENT_WAIT_TIMEOUT", work.Completion.Task.Result["error"]["code"].Value<string>());
        }
    }
}
