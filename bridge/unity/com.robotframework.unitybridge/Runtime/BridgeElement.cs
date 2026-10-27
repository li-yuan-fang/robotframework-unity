using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace RobotFramework.UnityBridge
{
    [DisallowMultipleComponent]
    [AddComponentMenu("Unity Bridge/Bridge Element")]
    public sealed class BridgeElement : MonoBehaviour
    {
        [SerializeField, Tooltip("Unique, stable test ID, for example login.submit")]
        private string elementId;
        [SerializeField, Tooltip("Optional graphics used for visibility; empty means this element's UI subtree")]
        private Graphic[] visibilityGraphics;

        public string ElementId => elementId;
        internal Selectable Selectable => GetComponent<Selectable>();

        /// <summary>Call after instantiating UI, including initially inactive objects.</summary>
        public void Configure(string id)
        {
            if (!RpcRequest.ValidElementId(id)) throw new ArgumentException("Invalid bridge element ID", nameof(id));
            ElementRegistry.Remove(this);
            elementId = id;
            ElementRegistry.Register(this);
        }

        public static void RegisterHierarchy(GameObject root)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            foreach (var element in root.GetComponentsInChildren<BridgeElement>(true)) ElementRegistry.Register(element);
        }

        internal IEnumerable<Graphic> Graphics()
        {
            if (visibilityGraphics != null && visibilityGraphics.Length > 0)
                return visibilityGraphics.Where(graphic => graphic != null);
            return GetComponentsInChildren<Graphic>(true).Where(graphic =>
                graphic != null && graphic.GetComponentInParent<BridgeElement>(true) == this);
        }

        private void Awake() { ElementRegistry.Register(this); }
        private void OnEnable() { ElementRegistry.Register(this); }
        // Do not unregister on OnDisable: hidden elements must still be queryable.
        private void OnDestroy() { ElementRegistry.Remove(this); }
    }

    internal static class ElementRegistry
    {
        private static readonly Dictionary<string, HashSet<BridgeElement>> Elements =
            new Dictionary<string, HashSet<BridgeElement>>(StringComparer.Ordinal);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void Reset() { Elements.Clear(); }

        internal static void Register(BridgeElement element)
        {
            if (element == null || !RpcRequest.ValidElementId(element.ElementId)) return;
            if (!Elements.TryGetValue(element.ElementId, out var matches))
                Elements[element.ElementId] = matches = new HashSet<BridgeElement>();
            matches.Add(element);
        }

        internal static void Remove(BridgeElement element)
        {
            // Configure can change the ID; remove by identity, including an old entry.
            foreach (var id in Elements.Keys.ToArray())
            {
                Elements[id].Remove(element);
                if (Elements[id].Count == 0) Elements.Remove(id);
            }
        }

        internal static void ScanLoadedScenes()
        {
            // Includes inactive scene objects and DontDestroyOnLoad objects; excludes prefab assets.
            foreach (var element in Resources.FindObjectsOfTypeAll<BridgeElement>())
                if (element.gameObject.scene.IsValid() && element.gameObject.scene.isLoaded) Register(element);
            Prune();
        }

        internal static void Prune()
        {
            foreach (var id in Elements.Keys.ToArray())
            {
                Elements[id].RemoveWhere(element => element == null);
                if (Elements[id].Count == 0) Elements.Remove(id);
            }
        }

        internal static BridgeElement Resolve(string id)
        {
            if (!Elements.TryGetValue(id, out var matches)) return null;
            matches.RemoveWhere(element => element == null);
            if (matches.Count > 1) throw new BridgeFault("AMBIGUOUS_ELEMENT", "Duplicate element ID: " + id);
            if (matches.Count > 0) return matches.First();
            Elements.Remove(id);
            return null;
        }
    }
}
