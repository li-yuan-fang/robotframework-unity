using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace RobotFramework.UnityBridge
{
    internal static class BridgeClock
    {
        internal static double Now => (double)Stopwatch.GetTimestamp() / Stopwatch.Frequency;
    }

    internal sealed class BridgeFault : Exception
    {
        internal readonly string Code;
        internal readonly JObject Details;
        internal BridgeFault(string code, string message, JObject details = null) : base(message)
        {
            Code = code;
            Details = details ?? new JObject();
        }
    }

    internal sealed class RpcRequest
    {
        internal int Id;
        internal string Method;
        internal string ElementId;
        internal string State;
        internal double X = 0.5;
        internal double Y = 0.5;
        internal int TimeoutMs;
        internal double ReceivedAt;
        internal double Deadline => ReceivedAt + TimeoutMs / 1000.0;

        internal static readonly string[] States = { "visible", "not visible", "enabled", "disabled" };
        internal static readonly string[] Methods = { "bridge.hello", "element.get", "element.wait", "element.click" };

        internal static JObject ReadObject(string line)
        {
            return JObject.Parse(line, new JsonLoadSettings
            {
                DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error
            });
        }

        internal static int? ReadId(JObject obj)
        {
            var token = obj["id"];
            if (token == null || token.Type != JTokenType.Integer) return null;
            try
            {
                long value = token.Value<long>();
                return value >= 1 && value <= int.MaxValue ? (int?)value : null;
            }
            catch (Exception) { return null; }
        }

        internal static RpcRequest Parse(JObject obj, int id, double receivedAt)
        {
            CheckKeys(obj, "v", "id", "method", "params", "timeout_ms");
            if (obj["v"]?.Type != JTokenType.Integer || obj["v"].ToString() != "1")
                throw new BridgeFault("UNSUPPORTED_VERSION", "Expected integer protocol version 1");
            if (obj["method"]?.Type != JTokenType.String)
                throw new BridgeFault("INVALID_REQUEST", "method must be a string");
            string method = obj["method"].Value<string>();
            if (!Methods.Contains(method)) throw new BridgeFault("METHOD_NOT_FOUND", "Unknown method: " + method);
            if (!(obj["params"] is JObject args)) throw new BridgeFault("INVALID_PARAMS", "params must be an object");
            if (obj["timeout_ms"]?.Type != JTokenType.Integer)
                throw new BridgeFault("INVALID_PARAMS", "timeout_ms must be an integer");
            long timeout;
            if (!long.TryParse(obj["timeout_ms"].ToString(), out timeout) || timeout < 1 || timeout > 120000)
                throw new BridgeFault("INVALID_PARAMS", "timeout_ms must be in [1, 120000]");
            var request = new RpcRequest { Id = id, Method = method, TimeoutMs = (int)timeout, ReceivedAt = receivedAt };
            if (method == "bridge.hello") { CheckKeys(args); return request; }
            CheckKeys(args, method == "element.wait" ? new[] { "selector", "state" }
                : method == "element.click" ? new[] { "selector", "point" } : new[] { "selector" });
            if (!(args["selector"] is JObject selector)) throw new BridgeFault("INVALID_PARAMS", "selector must be an object");
            CheckKeys(selector, "id");
            if (selector["id"]?.Type != JTokenType.String || !ValidElementId(selector["id"].Value<string>()))
                throw new BridgeFault("INVALID_PARAMS", "selector.id must be nonblank, at most 128 characters, without controls");
            request.ElementId = selector["id"].Value<string>();
            if (method == "element.wait")
            {
                if (args["state"]?.Type != JTokenType.String || !States.Contains(args["state"].Value<string>()))
                    throw new BridgeFault("INVALID_PARAMS", "Unsupported state");
                request.State = args["state"].Value<string>();
            }
            if (args["point"] != null)
            {
                if (!(args["point"] is JArray coordinates) || coordinates.Count != 2)
                    throw new BridgeFault("INVALID_PARAMS", "point must contain two normalized coordinates");
                request.X = Coordinate(coordinates[0]);
                request.Y = Coordinate(coordinates[1]);
            }
            return request;
        }

        private static double Coordinate(JToken token)
        {
            if (token.Type != JTokenType.Integer && token.Type != JTokenType.Float)
                throw new BridgeFault("INVALID_PARAMS", "Coordinates must be numbers");
            double value = token.Value<double>();
            if (double.IsNaN(value) || double.IsInfinity(value) || value < 0 || value > 1)
                throw new BridgeFault("INVALID_PARAMS", "Coordinates must be finite and in [0, 1]");
            return value;
        }

        internal static bool ValidElementId(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return false;
            int count = 0;
            for (int i = 0; i < value.Length; i++, count++)
            {
                if (char.IsControl(value[i])) return false;
                if (char.IsHighSurrogate(value[i]))
                {
                    if (i + 1 >= value.Length || !char.IsLowSurrogate(value[++i])) return false;
                }
                else if (char.IsLowSurrogate(value[i])) return false;
            }
            return count <= 128;
        }

        private static void CheckKeys(JObject obj, params string[] allowed)
        {
            var known = new HashSet<string>(allowed, StringComparer.Ordinal);
            if (obj.Properties().Any(property => !known.Contains(property.Name)))
                throw new BridgeFault("INVALID_PARAMS", "Unknown parameter or envelope field");
        }
    }

    internal static class RpcReply
    {
        internal static JObject Success(int id, JObject result) => new JObject
        { ["v"] = 1, ["id"] = id, ["ok"] = true, ["result"] = result };

        internal static JObject Error(int id, string code, string message, JObject details = null) => new JObject
        {
            ["v"] = 1, ["id"] = id, ["ok"] = false,
            ["error"] = new JObject { ["code"] = code, ["message"] = message, ["data"] = details ?? new JObject() }
        };

        internal static JObject Hello(string sessionId, string unityVersion) => new JObject
        {
            ["protocol_version"] = 1, ["session_id"] = sessionId, ["unity_version"] = unityVersion,
            ["methods"] = new JArray(RpcRequest.Methods), ["states"] = new JArray(RpcRequest.States),
            ["click_delivery"] = "ugui_pointer_events", ["max_timeout_ms"] = 120000
        };
    }
}
