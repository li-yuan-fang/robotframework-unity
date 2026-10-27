using System;
using RobotFramework.UnityBridge;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace RobotFramework.UnityBridge.Demo
{
    public sealed class BridgeDemoScene : MonoBehaviour
    {
        private Font font;
        private Text status;
        private int clickCount;

        private void Awake()
        {
#if UNITY_2022_2_OR_NEWER
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
#else
            font = Resources.GetBuiltinResource<Font>("Arial.ttf");
#endif
            if (FindObjectOfType<UnityBridgeHost>() == null)
                new GameObject("Unity Bridge SDK").AddComponent<UnityBridgeHost>();
            if (EventSystem.current == null)
            {
                var system = new GameObject("EventSystem", typeof(EventSystem));
#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
                // Avoid a hard dependency on the optional Input System package.
                var module = Type.GetType("UnityEngine.InputSystem.UI.InputSystemUIInputModule, Unity.InputSystem");
                if (module != null) system.AddComponent(module);
#else
                system.AddComponent<StandaloneInputModule>();
#endif
            }
            var canvasObject = new GameObject("Bridge Demo Canvas", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(GraphicRaycaster));
            Canvas canvas = canvasObject.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080, 720);
            var root = canvasObject.transform;
            Label(root, "Unity Bridge - UGUI Demo", new Vector2(0, 285), new Vector2(950, 55), 32);
            status = Label(root, "Waiting for Robot / Python", new Vector2(0, 225), new Vector2(950, 50), 22);

            Button home = MakeButton(root, "demo.home", "Home is ready", new Vector2(0, 145));
            home.gameObject.SetActive(false);
            Button login = MakeButton(root, "demo.login", "Login", new Vector2(0, 145));
            login.onClick.AddListener(() =>
            {
                login.gameObject.SetActive(false);
                home.gameObject.SetActive(true);
                status.text = "Login clicked; home visible";
            });

            Button purchase = MakeButton(root, "demo.purchase", "Purchase (initially disabled)", new Vector2(0, -15));
            purchase.interactable = false;
            purchase.onClick.AddListener(() => status.text = "Purchase clicked");
            Toggle toggle = MakeToggle(root, "demo.toggle", new Vector2(0, 65));
            toggle.onValueChanged.AddListener(value =>
            {
                purchase.interactable = value;
                status.text = "Toggle=" + value + "; purchase enabled=" + value;
            });
            Button once = MakeButton(root, "demo.once", "Click once", new Vector2(0, -95));
            once.onClick.AddListener(() =>
            {
                clickCount++;
                once.interactable = false;
                status.text = "Click-once callbacks: " + clickCount;
            });
            Button hidden = MakeButton(root, "demo.hidden", "Initially inactive", new Vector2(0, -175));
            hidden.gameObject.SetActive(false);
            Button blocked = MakeButton(root, "demo.blocked", "Blocked by raycast overlay", new Vector2(0, -245));
            var overlay = new GameObject("Blocking overlay", typeof(RectTransform), typeof(Image));
            overlay.transform.SetParent(root, false);
            SetRect(overlay.GetComponent<RectTransform>(), new Vector2(0, -245), new Vector2(510, 62));
            overlay.GetComponent<Image>().color = new Color(1, 0, 0, 0.15f);
            blocked.onClick.AddListener(() => status.text = "ERROR: blocked button clicked");
            BridgeElement.RegisterHierarchy(canvasObject);
        }

        private Button MakeButton(Transform root, string id, string text, Vector2 position)
        {
            var obj = new GameObject(id, typeof(RectTransform), typeof(Image), typeof(Button));
            obj.transform.SetParent(root, false);
            SetRect(obj.GetComponent<RectTransform>(), position, new Vector2(510, 62));
            var image = obj.GetComponent<Image>();
            image.color = new Color(0.22f, 0.40f, 0.68f);
            var button = obj.GetComponent<Button>();
            button.targetGraphic = image;
            Label(obj.transform, text, Vector2.zero, new Vector2(500, 60), 21);
            obj.AddComponent<BridgeElement>().Configure(id);
            return button;
        }

        private Toggle MakeToggle(Transform root, string id, Vector2 position)
        {
            var obj = new GameObject(id, typeof(RectTransform), typeof(Image), typeof(Toggle));
            obj.transform.SetParent(root, false);
            SetRect(obj.GetComponent<RectTransform>(), position, new Vector2(510, 62));
            var toggle = obj.GetComponent<Toggle>();
            toggle.targetGraphic = obj.GetComponent<Image>();
            toggle.targetGraphic.color = new Color(0.18f, 0.22f, 0.30f);
            var check = new GameObject("Check", typeof(RectTransform), typeof(Image));
            check.transform.SetParent(obj.transform, false);
            SetRect(check.GetComponent<RectTransform>(), new Vector2(-215, 0), new Vector2(25, 25));
            check.GetComponent<Image>().color = Color.green;
            check.GetComponent<Image>().raycastTarget = false;
            toggle.graphic = check.GetComponent<Image>();
            toggle.isOn = false;
            Label(obj.transform, "Enable purchase", new Vector2(30, 0), new Vector2(420, 60), 21);
            obj.AddComponent<BridgeElement>().Configure(id);
            return toggle;
        }

        private Text Label(Transform root, string text, Vector2 position, Vector2 size, int fontSize)
        {
            var obj = new GameObject("Label", typeof(RectTransform), typeof(Text));
            obj.transform.SetParent(root, false);
            SetRect(obj.GetComponent<RectTransform>(), position, size);
            Text label = obj.GetComponent<Text>();
            label.font = font;
            label.text = text;
            label.fontSize = fontSize;
            label.alignment = TextAnchor.MiddleCenter;
            label.color = Color.white;
            label.raycastTarget = false;
            return label;
        }

        private static void SetRect(RectTransform rect, Vector2 position, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
        }
    }
}
