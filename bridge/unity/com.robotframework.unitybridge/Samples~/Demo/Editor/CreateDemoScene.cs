using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace RobotFramework.UnityBridge.Demo.Editor
{
    internal static class CreateDemoScene
    {
        [MenuItem("Tools/Unity Bridge/Create Demo Scene")]
        private static void Create()
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            new GameObject("Bridge Demo").AddComponent<BridgeDemoScene>();
            string path = AssetDatabase.GenerateUniqueAssetPath("Assets/UnityBridgeDemo.unity");
            EditorSceneManager.SaveScene(scene, path);
            Selection.activeGameObject = GameObject.Find("Bridge Demo");
        }
    }
}
