using System;
using System.Collections.Concurrent;
using System.Threading;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace RobotFramework.UnityBridge
{
    [DisallowMultipleComponent]
    [AddComponentMenu("Unity Bridge/SDK Host")]
    public sealed class UnityBridgeHost : MonoBehaviour
    {
        [SerializeField, Range(1, 65535)] private int serverPort = 13000;
        [SerializeField, Range(0.016f, 1f)] private float sampleIntervalSeconds = 0.1f;
        private static UnityBridgeHost instance;
        private readonly object gate = new object();
        private readonly ConcurrentQueue<string> diagnostics = new ConcurrentQueue<string>();
        private int diagnosticCount;
        private RpcWork slot;
        private PendingOperation operation;
        private TcpServer server;
        private bool stopping;
        private bool previousRunInBackground;

        public int ServerPort => serverPort;
        public bool IsRunning => server != null;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetStatic() { instance = null; }

        private void Awake()
        {
            if (instance != null && instance != this) { Destroy(this); return; }
            if (transform.parent != null)
            {
                Debug.LogError("[Unity Bridge] SDK Host must be on a root GameObject", this);
                enabled = false;
                return;
            }
            instance = this;
            DontDestroyOnLoad(gameObject);
            SceneManager.sceneLoaded += SceneLoaded;
            SceneManager.sceneUnloaded += SceneUnloaded;
            ElementRegistry.ScanLoadedScenes();
        }

        private void OnEnable() { if (instance == this) StartServer(); }
        private void OnDisable() { if (instance == this) StopServer(); }

        public void StartServer()
        {
            if (instance != this || !isActiveAndEnabled || server != null) return;
#if UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_BRIDGE_ENABLED
            lock (gate) { stopping = false; }
            previousRunInBackground = Application.runInBackground;
            Application.runInBackground = true;
            try
            {
                server = new TcpServer(serverPort, Application.unityVersion, Submit, QueueDiagnostic);
                server.Start();
                Debug.Log("[Unity Bridge] Listening on 127.0.0.1:" + serverPort, this);
            }
            catch (Exception error)
            {
                server?.Dispose();
                server = null;
                Application.runInBackground = previousRunInBackground;
                Debug.LogError("[Unity Bridge] Could not start SDK: " + error.Message, this);
            }
#endif
        }

        public void StopServer()
        {
            lock (gate) { stopping = true; slot?.Cancel(); slot = null; }
            operation = null;
            if (server == null) return;
            server.Dispose();
            server = null;
#if UNITY_EDITOR || DEVELOPMENT_BUILD || UNITY_BRIDGE_ENABLED
            Application.runInBackground = previousRunInBackground;
#endif
        }

        private void SceneLoaded(Scene scene, LoadSceneMode mode) { ElementRegistry.ScanLoadedScenes(); }
        private void SceneUnloaded(Scene scene) { ElementRegistry.Prune(); }

        private void QueueDiagnostic(string message)
        {
            if (Interlocked.Increment(ref diagnosticCount) <= 32) diagnostics.Enqueue(message);
            else Interlocked.Decrement(ref diagnosticCount);
        }

        // Called from a network worker. This lock protects only ordinary CLR state.
        private bool Submit(RpcWork work)
        {
            lock (gate)
            {
                if (stopping || (slot != null && !slot.Cancelled && !slot.Completion.Task.IsCompleted)) return false;
                slot = work;
                return true;
            }
        }

        private void LateUpdate()
        {
            for (int i = 0; i < 8 && diagnostics.TryDequeue(out var message); i++)
            {
                Interlocked.Decrement(ref diagnosticCount);
                Debug.LogWarning("[Unity Bridge] " + message, this);
            }
            RpcWork current;
            lock (gate) { current = slot; }
            if (current == null || current.Cancelled || current.Completion.Task.IsCompleted)
            {
                operation = null;
                return;
            }
            if (operation == null || !ReferenceEquals(operation.Work, current))
                operation = new PendingOperation(current, sampleIntervalSeconds);
            if (!operation.Due) return;
            // One refresh per sampling tick, never one full-scene scan per element.
            Canvas.ForceUpdateCanvases();
            operation.Tick();
            if (current.Completion.Task.IsCompleted)
            {
                lock (gate) { if (ReferenceEquals(slot, current)) slot = null; }
                operation = null;
            }
        }

        private void OnDestroy()
        {
            if (instance != this) return;
            StopServer();
            SceneManager.sceneLoaded -= SceneLoaded;
            SceneManager.sceneUnloaded -= SceneUnloaded;
            instance = null;
        }
    }

    internal sealed class PendingOperation
    {
        internal readonly RpcWork Work;
        private readonly double sampleInterval;
        private double nextSample;
        private ElementSnapshot last;
        private string lastReason = "not_sampled";
        private string clickEffect = "not_started";
        private RpcRequest Request => Work.Request;
        internal bool Due => BridgeClock.Now >= Math.Min(nextSample, Request.Deadline);

        internal PendingOperation(RpcWork work, double sampleInterval)
        {
            Work = work;
            this.sampleInterval = sampleInterval;
        }

        internal void Tick()
        {
            if (Work.Cancelled || Work.Completion.Task.IsCompleted) return;
            try
            {
                if (BridgeClock.Now >= Request.Deadline) { Timeout(); return; }
                nextSample = BridgeClock.Now + sampleInterval;
                last = UguiElementAdapter.Snapshot(Request.ElementId, out var element);
                if (Request.Method == "element.get")
                {
                    Complete(new JObject { ["snapshot"] = last.Json(), ["elapsed_ms"] = Elapsed });
                    return;
                }
                if (Request.Method == "element.wait")
                {
                    if (last.Matches(Request.State)) Complete(new JObject
                    { ["snapshot"] = last.Json(), ["matched_state"] = Request.State, ["elapsed_ms"] = Elapsed });
                    return;
                }
                if (!last.Exists) { lastReason = "not_found"; return; }
                if (!last.Visible) { lastReason = "not_visible"; return; }
                if (last.Enabled != true) { lastReason = "disabled"; return; }
                if (!UguiElementAdapter.PrepareClick(element, Request, out var pointer, out lastReason)) return;
                if (Work.Cancelled) return;
                if (BridgeClock.Now >= Request.Deadline) { Timeout(); return; }
                clickEffect = "started";
                UguiElementAdapter.DispatchClick(element, Request, pointer, () => Work.Cancelled);
                clickEffect = "completed";
                Complete(new JObject { ["dispatched"] = true, ["snapshot_before"] = last.Json(), ["elapsed_ms"] = Elapsed });
            }
            catch (BridgeFault fault)
            {
                JObject details = Context();
                details.Merge(fault.Details);
                if (Request.Method == "element.click" && details["effect"] == null) details["effect"] = "not_started";
                Fail(fault.Code, fault.Message, details);
            }
            catch (Exception error)
            {
                Debug.LogException(error);
                var details = Context();
                details["effect"] = clickEffect;
                Fail("INTERNAL_ERROR", "Unexpected SDK error: " + error.Message, details);
            }
        }

        private double Elapsed => Math.Max(0, (BridgeClock.Now - Request.ReceivedAt) * 1000);
        private JObject Context() => new JObject
        {
            ["selector"] = new JObject { ["id"] = Request.ElementId },
            ["expected_state"] = Request.State == null ? JValue.CreateNull() : new JValue(Request.State),
            ["last_snapshot"] = last == null ? (JToken)JValue.CreateNull() : last.Json(),
            ["elapsed_ms"] = Elapsed, ["reason"] = lastReason
        };

        private void Timeout()
        {
            string code = last == null ? "DEADLINE_EXCEEDED"
                : Request.Method == "element.click" ? "ELEMENT_CLICK_TIMEOUT" : "ELEMENT_WAIT_TIMEOUT";
            var details = Context();
            details["effect"] = "not_started";
            Fail(code, "Element " + Request.ElementId + " did not satisfy " + (Request.State ?? "click conditions")
                + " within " + Request.TimeoutMs + " ms", details);
        }

        private void Complete(JObject result) { Work.Completion.TrySetResult(RpcReply.Success(Request.Id, result)); }
        private void Fail(string code, string message, JObject details)
        { Work.Completion.TrySetResult(RpcReply.Error(Request.Id, code, message, details)); }
    }
}
