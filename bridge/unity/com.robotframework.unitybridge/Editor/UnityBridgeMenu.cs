using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

namespace RobotFramework.UnityBridge.Editor
{
    internal static class UnityBridgeMenu
    {
        [MenuItem("GameObject/Unity Bridge/SDK Host", false, 10)]
        private static void AddHost()
        {
            if (Object.FindObjectOfType<UnityBridgeHost>(true) != null)
            {
                EditorUtility.DisplayDialog("Unity Bridge", "This scene already contains an SDK Host.", "OK");
                return;
            }
            var root = new GameObject("Unity Bridge SDK");
            Undo.RegisterCreatedObjectUndo(root, "Create Unity Bridge SDK");
            root.AddComponent<UnityBridgeHost>();
            Selection.activeGameObject = root;
        }

        [MenuItem("Tools/Unity Bridge/Add Element To Selected UI")]
        private static void AddElement()
        {
            foreach (var gameObject in Selection.gameObjects)
            {
                if (gameObject.GetComponent<Button>() == null && gameObject.GetComponent<Toggle>() == null) continue;
                var element = gameObject.GetComponent<BridgeElement>();
                if (element == null) element = Undo.AddComponent<BridgeElement>(gameObject);
                Selection.activeGameObject = gameObject;
                EditorGUIUtility.PingObject(element);
            }
        }
    }
}
