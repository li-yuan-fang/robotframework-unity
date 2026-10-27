using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using RobotFramework.UnityBridge;

// Tests the ACTUAL SDK transport/protocol, but substitutes element execution.
// It does not load Unity and is not a substitute for the PlayMode tests.
internal static class Program
{
    private static int clicks;

    private static bool Submit(RpcWork work)
    {
        _ = Task.Run(async () =>
        {
            var request = work.Request;
            var snapshot = new JObject { ["id"] = request.ElementId, ["exists"] = true, ["visible"] = true, ["enabled"] = true };
            if (request.ElementId == "missing")
                snapshot = new JObject { ["id"] = "missing", ["exists"] = false, ["visible"] = false, ["enabled"] = JValue.CreateNull() };
            if (request.ElementId == "disabled") snapshot["enabled"] = false;
            bool matches = request.State == "visible" && snapshot["visible"].Value<bool>()
                || request.State == "not visible" && !snapshot["visible"].Value<bool>()
                || request.State == "enabled" && snapshot["enabled"].Type == JTokenType.Boolean && snapshot["enabled"].Value<bool>()
                || request.State == "disabled" && snapshot["exists"].Value<bool>() && snapshot["enabled"].Type == JTokenType.Boolean
                    && !snapshot["enabled"].Value<bool>();
            bool waiting = request.Method == "element.wait" && !matches
                || request.Method == "element.click" && !snapshot["exists"].Value<bool>();
            if (waiting)
            {
                while (!work.Cancelled && BridgeClock.Now < request.Deadline) await Task.Delay(5);
                if (work.Cancelled) return;
                work.Completion.TrySetResult(RpcReply.Error(request.Id,
                    request.Method == "element.click" ? "ELEMENT_CLICK_TIMEOUT" : "ELEMENT_WAIT_TIMEOUT", "Contract fixture timeout",
                    new JObject { ["last_snapshot"] = snapshot, ["effect"] = "not_started" }));
                return;
            }
            if (work.Cancelled) return;
            double elapsed = (BridgeClock.Now - request.ReceivedAt) * 1000;
            JObject result;
            if (request.Method == "element.click")
            {
                Interlocked.Increment(ref clicks);
                result = new JObject { ["dispatched"] = true, ["snapshot_before"] = snapshot, ["elapsed_ms"] = elapsed };
            }
            else
            {
                result = new JObject { ["snapshot"] = snapshot, ["elapsed_ms"] = elapsed };
                if (request.Method == "element.wait") result["matched_state"] = request.State;
            }
            work.Completion.TrySetResult(RpcReply.Success(request.Id, result));
        });
        return true;
    }

    private static JObject Request(int id, string method = "bridge.hello", string target = "button", int timeout = 1000, string state = null)
    {
        var args = new JObject();
        if (method != "bridge.hello") args["selector"] = new JObject { ["id"] = target };
        if (state != null) args["state"] = state;
        return new JObject { ["v"] = 1, ["id"] = id, ["method"] = method, ["params"] = args, ["timeout_ms"] = timeout };
    }

    private static void Check(bool condition, string message)
    { if (!condition) throw new Exception("FAILED: " + message); }

    private static void ExpectFault(JObject request, string expected)
    {
        try { RpcRequest.Parse(request, request["id"].Value<int>(), BridgeClock.Now); }
        catch (BridgeFault fault) { Check(fault.Code == expected, "expected " + expected + ", got " + fault.Code); return; }
        throw new Exception("Expected fault " + expected);
    }

    private static void ProtocolTests()
    {
        Check(RpcRequest.Parse(Request(1), 1, BridgeClock.Now).Method == "bridge.hello", "valid hello");
        var request = Request(2, "element.click");
        request["params"]["point"] = new JArray(0.2, 0.8);
        Check(RpcRequest.Parse(request, 2, BridgeClock.Now).Y == 0.8, "normalized point");
        request["params"]["point"] = new JArray(true, 0);
        ExpectFault(request, "INVALID_PARAMS");
        request = Request(3); request["timeout_ms"] = 0; ExpectFault(request, "INVALID_PARAMS");
        request = Request(4); request["v"] = true; ExpectFault(request, "UNSUPPORTED_VERSION");
        request = Request(5); request["params"]["typo"] = 1; ExpectFault(request, "INVALID_PARAMS");
        request = Request(6, "execute_arbitrary_code"); ExpectFault(request, "METHOD_NOT_FOUND");
        Check(!RpcRequest.ReadId(new JObject { ["id"] = true }).HasValue, "boolean id rejected");
        Check(!RpcRequest.ValidElementId("a\nb"), "control character rejected");
        Check(RpcRequest.ValidElementId(new string('x', 128)), "128-char id accepted");
        try { RpcRequest.ReadObject("{\"id\":1,\"id\":2}"); throw new Exception("Duplicate JSON accepted"); }
        catch (Newtonsoft.Json.JsonReaderException) { }
        Console.WriteLine("PASS: C# protocol validation");
    }

    private static void SyntaxTests()
    {
        string package = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,
            "../../../../../unity/com.robotframework.unitybridge"));
        int count = 0;
        foreach (string file in Directory.GetFiles(package, "*.cs", SearchOption.AllDirectories))
        {
            foreach (var symbols in new[] { new[] { "UNITY_EDITOR", "ENABLE_LEGACY_INPUT_MANAGER" },
                new[] { "DEVELOPMENT_BUILD", "UNITY_2022_2_OR_NEWER", "ENABLE_INPUT_SYSTEM" }, new string[0] })
            {
                var tree = CSharpSyntaxTree.ParseText(File.ReadAllText(file),
                    new CSharpParseOptions(LanguageVersion.CSharp9, preprocessorSymbols: symbols), file);
                var errors = tree.GetDiagnostics().Where(diagnostic => diagnostic.Severity == DiagnosticSeverity.Error).ToArray();
                Check(errors.Length == 0, string.Join(Environment.NewLine, errors.Select(error => error.ToString())));
            }
            count++;
        }
        Console.WriteLine("PASS: C# syntax (" + count + " SDK/sample/test files, 3 build symbol configurations; no Unity type checking)");
    }

    private sealed class Peer : IDisposable
    {
        internal readonly TcpClient Client = new TcpClient();
        internal readonly StreamReader Reader;
        internal Peer(int port)
        {
            Client.Connect("127.0.0.1", port);
            Client.GetStream().ReadTimeout = 4000;
            Reader = new StreamReader(Client.GetStream(), new UTF8Encoding(false, true), false, 1024, true);
        }
        internal void Send(JObject request, bool fragmented = false)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(request.ToString(Newtonsoft.Json.Formatting.None) + "\n");
            if (fragmented)
            {
                Client.GetStream().Write(bytes, 0, 7);
                Thread.Sleep(10);
                Client.GetStream().Write(bytes, 7, bytes.Length - 7);
            }
            else Client.GetStream().Write(bytes, 0, bytes.Length);
        }
        internal JObject Read() => JObject.Parse(Reader.ReadLine() ?? throw new Exception("Unexpected EOF"));
        public void Dispose() { Reader.Dispose(); Client.Dispose(); }
    }

    private static void NetworkTests(TcpServer server)
    {
        using (var peer = new Peer(server.Port))
        {
            peer.Send(Request(1), true);
            Check(peer.Read()["ok"].Value<bool>(), "fragmented handshake");
            peer.Send(Request(2, "element.click")); Check(peer.Read()["ok"].Value<bool>(), "click reply");
            peer.Send(Request(2, "element.click"));
            Check(peer.Read()["error"]["code"].Value<string>() == "DUPLICATE_REQUEST_ID", "duplicate rejected");
            Check(clicks == 1, "duplicate click did not execute");
            using (var busy = new Peer(server.Port))
            {
                busy.Send(Request(1));
                Check(busy.Read()["error"]["code"].Value<string>() == "SERVER_BUSY", "second client rejected");
            }
            peer.Send(Request(3, "element.wait", "missing", 150, "disabled"));
            peer.Send(Request(4, "element.get"));
            var a = peer.Read(); var b = peer.Read();
            var errors = new HashSet<string> { a["error"]["code"].Value<string>(), b["error"]["code"].Value<string>() };
            Check(errors.SetEquals(new[] { "REQUEST_IN_PROGRESS", "ELEMENT_WAIT_TIMEOUT" }), "single in-flight operation");
            peer.Send(Request(5, "element.get", "missing"));
            Check(!peer.Read()["result"]["snapshot"]["exists"].Value<bool>(), "missing element snapshot");
        }
        Thread.Sleep(100);
        using (var malformed = new Peer(server.Port))
        {
            byte[] bytes = Encoding.UTF8.GetBytes("not json\n");
            malformed.Client.GetStream().Write(bytes);
            Check(malformed.Reader.ReadLine() == null, "bad frame closes session");
        }
        Thread.Sleep(100);
        using (var oversized = new Peer(server.Port))
        {
            var bytes = new byte[65538]; Array.Fill(bytes, (byte)'x');
            oversized.Client.GetStream().Write(bytes);
            Check(oversized.Reader.ReadLine() == null, "oversized unterminated frame closes session");
        }
        Console.WriteLine("PASS: C# TCP framing, duplicate prevention, busy handling, timeout, invalid streams");
    }

    private static int Main(string[] args)
    {
        try
        {
            using var server = new TcpServer(0, "contract-test-no-unity", Submit);
            server.Start();
            if (args.Length == 1 && args[0] == "--serve")
            {
                Console.WriteLine(server.Port); Console.Out.Flush();
                Console.ReadLine();
            }
            else { SyntaxTests(); ProtocolTests(); NetworkTests(server); }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
