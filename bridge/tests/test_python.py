"""Standard-library checks; no Unity, ADB, Robot Framework or network downloads.

Optionally set UNITY_BRIDGE_CSHARP_HARNESS to the locally built contract DLL.
That fixture runs the SDK's real C# TCP/protocol with substitute elements.
"""
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from UnityBridge import (  # noqa: E402
    BridgeClickOutcomeUnknown, BridgeClickTimeout, BridgeCleanupError, BridgeError, BridgeProtocolError,
    BridgeWaitTimeout, DeviceSelectionError, UnityBridge, UnityBridgeClient,
)
from _unity_bridge.adb import AdbForwardManager, Forward
from _unity_bridge.transport import RpcClient


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


def success(request, result):
    return {"v": 1, "id": request["id"], "ok": True, "result": result}


def hello(request):
    return success(request, {"protocol_version": 1, "session_id": "test-session", "unity_version": "fixture",
                             "methods": ["bridge.hello", "element.get", "element.wait", "element.click"],
                             "states": ["visible", "not visible", "enabled", "disabled"],
                             "click_delivery": "ugui_pointer_events", "max_timeout_ms": 120000})


class FixtureServer:
    """One-connection fake peer, only used to exercise client error paths."""
    def __init__(self, handler):
        self.handler = handler
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(3)
        self.port = self.listener.getsockname()[1]
        self.requests = []
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def run(self):
        try:
            with self.listener.accept()[0] as connection:
                connection.settimeout(3)
                with connection.makefile("rb") as reader:
                    while True:
                        line = reader.readline()
                        if not line:
                            break
                        request = json.loads(line)
                        self.requests.append(request)
                        if self.handler(connection, request) is False:
                            break
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as exc:
            self.error = exc

    def __exit__(self, *args):
        self.listener.close()
        self.thread.join(4)
        if self.thread.is_alive():
            raise AssertionError("Fixture server leaked a thread")
        if self.error is not None:
            raise self.error


class PythonClientTests(unittest.TestCase):
    def test_public_entry_and_python_syntax(self):
        self.assertEqual([p.name for p in (ROOT / "python").glob("*.py")], ["UnityBridge.py"])
        for path in (ROOT / "python").rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_no_connection_is_an_explicit_error(self):
        with UnityBridgeClient() as client:
            with self.assertRaisesRegex(BridgeError, "Not connected"):
                client.get_state("button")
        client.close()

    def test_numeric_and_locator_validation(self):
        for value in (True, 0, -1, float("inf"), float("nan"), 121, "5s"):
            with self.subTest(timeout=value), self.assertRaises(ValueError):
                UnityBridgeClient(default_timeout=value)
        client = UnityBridgeClient()
        for target in ("", " ", "x\ny", "x" * 129, None):
            with self.subTest(target=target), self.assertRaises(ValueError):
                client.get_state(target)
        for position in ((-1, 0), (True, 0), (1,), "0.5,0.5"):
            with self.subTest(point=position), self.assertRaises(ValueError):
                client.click("button", point=position)

    def test_fragmented_response_and_state_read(self):
        def handler(connection, request):
            response = hello(request) if request["method"] == "bridge.hello" else success(request, {
                "snapshot": {"id": "button", "exists": True, "visible": True, "enabled": False}, "elapsed_ms": 1})
            frame = encode(response)
            for part in (frame[:3], frame[3:17], frame[17:]):
                connection.sendall(part)
        with FixtureServer(handler) as server, UnityBridgeClient() as client:
            client.connect_local(server_port=server.port)
            self.assertFalse(client.get_state(element_id="button")["enabled"])
            self.assertEqual([r["id"] for r in server.requests], [1, 2])

    def test_wait_error_keeps_session_and_diagnostics(self):
        def handler(connection, request):
            if request["method"] == "bridge.hello":
                connection.sendall(encode(hello(request)))
            else:
                connection.sendall(encode({"v": 1, "id": request["id"], "ok": False, "error": {
                    "code": "ELEMENT_WAIT_TIMEOUT", "message": "Timed out", "data": {
                        "selector": {"id": "missing"}, "expected_state": "disabled", "elapsed_ms": 50,
                        "last_snapshot": {"id": "missing", "exists": False, "visible": False, "enabled": None}}}}))
        with FixtureServer(handler) as server, UnityBridgeClient() as client:
            client.connect_local(server_port=server.port)
            with self.assertRaises(BridgeWaitTimeout) as caught:
                client.wait_for_state("missing", "disabled", timeout=0.05)
            self.assertTrue(client.connected)
            self.assertEqual(caught.exception.data["expected_state"], "disabled")

    def test_missing_is_not_disabled_even_if_server_claims_success(self):
        def handler(connection, request):
            response = hello(request) if request["method"] == "bridge.hello" else success(request, {
                "snapshot": {"id": "missing", "exists": False, "visible": False, "enabled": None},
                "matched_state": "disabled", "elapsed_ms": 1})
            connection.sendall(encode(response))
        with FixtureServer(handler) as server, UnityBridgeClient() as client:
            client.connect_local(server_port=server.port)
            with self.assertRaises(BridgeProtocolError):
                client.wait_for_state("missing", "disabled")
            self.assertFalse(client.connected)

    def test_click_disconnect_is_unknown_and_never_retried(self):
        def handler(connection, request):
            if request["method"] == "bridge.hello":
                connection.sendall(encode(hello(request)))
            else:
                return False  # Simulate the reply being lost after the click ran.
        with FixtureServer(handler) as server, UnityBridgeClient() as client:
            client.connect_local(server_port=server.port)
            with self.assertRaises(BridgeClickOutcomeUnknown):
                client.click("button", timeout=0.1)
            self.assertFalse(client.connected)
            self.assertEqual([r["method"] for r in server.requests].count("element.click"), 1)

    def test_click_wrong_response_id_is_unknown(self):
        def handler(connection, request):
            response = hello(request)
            if request["method"] == "element.click":
                response["id"] += 1
            connection.sendall(encode(response))
        with FixtureServer(handler) as server, UnityBridgeClient() as client:
            client.connect_local(server_port=server.port)
            with self.assertRaises(BridgeClickOutcomeUnknown):
                client.click("button")

    def test_tcp_coalescing_preserves_remaining_frame(self):
        left, right = socket.socketpair()
        rpc = RpcClient(left, grace=0.1)
        try:
            right.sendall(encode({"v": 1, "id": 1, "ok": True, "result": {"n": 1}})
                          + encode({"v": 1, "id": 2, "ok": True, "result": {"n": 2}}))
            self.assertEqual(rpc.request("fixture", {}, 1)["n"], 1)
            self.assertEqual(rpc.request("fixture", {}, 1)["n"], 2)
        finally:
            rpc.close()
            right.close()

    def test_rpc_total_timeout_is_not_reset_for_each_chunk(self):
        def handler(connection, request):
            if request["method"] == "bridge.hello":
                connection.sendall(encode(hello(request)))
                return
            for _ in range(20):
                connection.sendall(b" ")
                time.sleep(0.03)
        with FixtureServer(handler) as server, UnityBridgeClient(transport_grace=0.05) as client:
            client.connect_local(server_port=server.port)
            started = time.monotonic()
            with self.assertRaises(BridgeClickOutcomeUnknown):
                client.click("button", timeout=0.05)
            self.assertLess(time.monotonic() - started, 0.4)

    def test_unterminated_frame_is_bounded(self):
        def handler(connection, request):
            connection.sendall(b"x" * (65536 + 2))
        with FixtureServer(handler) as server, UnityBridgeClient() as client:
            with self.assertRaises(BridgeProtocolError):
                client.connect_local(server_port=server.port)
            self.assertFalse(client.connected)

    def test_robot_keywords_delegate_without_exposing_transport(self):
        library = UnityBridge()
        with patch.object(library.client, "click", return_value={"dispatched": True}) as click:
            self.assertTrue(library.click_unity_element("button", timeout=2)["dispatched"])
            click.assert_called_once_with("button", 2, None)
        self.assertFalse(library.ROBOT_AUTO_KEYWORDS)
        self.assertEqual(library.ROBOT_LIBRARY_SCOPE, "SUITE")


class AdbTests(unittest.TestCase):
    def runner(self, command, **kwargs):
        self.commands.append(command)
        self.assertFalse(kwargs["shell"])
        self.assertLessEqual(kwargs["timeout"], 3)
        args = command[1:]
        output = ""
        if args == ["devices", "-l"]:
            output = self.devices
        elif args[-1] == "get-state":
            output = "device"
        elif "--list" in args:
            output = self.mappings
        elif "tcp:0" in args:
            output = str(self.allocated)
            self.mappings = f"serial-one tcp:{self.allocated} tcp:13000"
        elif "--remove" in args:
            self.mappings = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    def setUp(self):
        self.commands = []
        self.devices = "List of devices attached\nserial-one device product:test\n"
        self.mappings = ""
        self.allocated = 23456
        self.manager = AdbForwardManager(runner=self.runner)

    def test_dynamic_forward_and_idempotent_owned_cleanup(self):
        forward = self.manager.create(None, 13000, None, time.monotonic() + 5)
        self.assertEqual(forward, Forward("serial-one", 23456, 13000))
        self.manager.close()
        self.manager.close()
        removes = [c for c in self.commands if "--remove" in c]
        self.assertEqual(removes, [["adb", "-s", "serial-one", "forward", "--remove", "tcp:23456"]])
        self.assertFalse(any("--remove-all" in c for c in self.commands))

    def test_ambiguous_devices_do_not_create_forward(self):
        self.devices += "serial-two device\n"
        with self.assertRaises(DeviceSelectionError):
            self.manager.create(None, 13000, None, time.monotonic() + 5)
        self.assertFalse(any("forward" in command for command in self.commands))

    def test_replaced_mapping_is_not_removed(self):
        self.manager.create("serial-one", 13000, None, time.monotonic() + 5)
        self.mappings = "serial-one tcp:23456 tcp:9999"
        with self.assertRaises(BridgeCleanupError):
            self.manager.close()
        self.assertFalse(any("--remove" in c for c in self.commands))

    def test_failed_handshake_cleans_forward(self):
        def handler(connection, request):
            connection.sendall(encode(success(request, {"protocol_version": 99})))
        with FixtureServer(handler) as server:
            self.allocated = server.port
            client = UnityBridgeClient()
            client._adb = self.manager
            with self.assertRaises(BridgeProtocolError):
                client.connect(serial="serial-one")
            self.assertIsNone(self.manager.owned)
            self.assertFalse(client.connected)

    def test_fixed_port_uses_no_rebind(self):
        self.manager.create("serial-one", 13000, 23000, time.monotonic() + 5)
        self.assertIn(["adb", "-s", "serial-one", "forward", "--no-rebind", "tcp:23000", "tcp:13000"], self.commands)


@unittest.skipUnless(os.environ.get("UNITY_BRIDGE_CSHARP_HARNESS"), "optional C# contract harness not selected")
class CrossLanguageTests(unittest.TestCase):
    def test_python_calls_actual_csharp_transport(self):
        process = subprocess.Popen(["dotnet", os.environ["UNITY_BRIDGE_CSHARP_HARNESS"], "--serve"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            port = int(process.stdout.readline().strip())
            with UnityBridgeClient() as client:
                client.connect_local(server_port=port)
                self.assertTrue(client.get_state("button")["visible"])
                self.assertFalse(client.get_state("missing")["exists"])
                client.wait_for_state("missing", "not visible")
                client.wait_for_state("disabled", "disabled")
                self.assertTrue(client.click("button")["dispatched"])
                with self.assertRaises(BridgeWaitTimeout):
                    client.wait_for_state("missing", "disabled", timeout=0.05)
                with self.assertRaises(BridgeClickTimeout) as caught:
                    client.click("missing", timeout=0.05)
                self.assertEqual(caught.exception.data["effect"], "not_started")
        finally:
            try:
                process.communicate("stop\n", timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            self.assertEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
