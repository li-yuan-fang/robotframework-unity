import socket
import time

from .adb import AdbForwardManager
from .errors import BridgeConnectError, BridgeError, BridgeProtocolError
from .transport import RpcClient
from .validation import STATES, element_id as validate_element_id, point as validate_point, port, seconds


class UnityBridgeClient:
    """Synchronous, single-operation client. Numeric timeouts are seconds.

    connect() manages Android/ADB; connect_local() connects to a Unity Editor
    or desktop player without needing ADB. close() is required in either mode.
    """

    def __init__(self, adb_path="adb", default_timeout=5.0, transport_grace=2.0):
        self.default_timeout = seconds(default_timeout)
        self.transport_grace = seconds(transport_grace, "transport_grace")
        self._adb = AdbForwardManager(adb_path)
        self._rpc = None
        self.connection_info = None

    @property
    def connected(self):
        return self._rpc is not None and self._rpc.connected

    def _before_connect(self):
        if self._rpc is not None or self._adb.owned is not None:
            raise BridgeError("A session or forward already exists; call close() before connecting")

    def connect(self, serial=None, server_port=13000, host_port=None, timeout=10.0):
        self._before_connect()
        server_port = port(server_port, "server_port")
        host_port = None if host_port is None else port(host_port, "host_port")
        deadline = time.monotonic() + seconds(timeout, "connect timeout")
        try:
            forward = self._adb.create(serial, server_port, host_port, deadline)
            hello = self._open("127.0.0.1", forward.local, deadline)
            self.connection_info = {"mode": "adb", "serial": forward.serial,
                                    "host_port": forward.local, "server_port": server_port, **hello}
            return dict(self.connection_info)
        except BaseException as exc:
            self._cleanup_after_failure(exc)
            raise

    def connect_local(self, host="127.0.0.1", server_port=13000, timeout=10.0):
        self._before_connect()
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("The demo supports loopback hosts only")
        server_port = port(server_port, "server_port")
        deadline = time.monotonic() + seconds(timeout, "connect timeout")
        try:
            hello = self._open(host, server_port, deadline)
            self.connection_info = {"mode": "local", "host": host, "server_port": server_port, **hello}
            return dict(self.connection_info)
        except BaseException as exc:
            self._cleanup_after_failure(exc)
            raise

    def _open(self, host, server_port, deadline):
        last_error = None
        while time.monotonic() < deadline:
            sock = None
            try:
                sock = socket.create_connection((host, server_port),
                                                timeout=min(1.0, deadline - time.monotonic()))
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._rpc = RpcClient(sock, self.transport_grace)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeConnectError("Connection deadline exceeded before handshake")
                return self._rpc.request("bridge.hello", {}, min(5.0, remaining),
                                         validator=self._hello, deadline=deadline)
            except OSError as exc:
                last_error = exc
                if sock is not None:
                    sock.close()
                time.sleep(max(0.0, min(0.1, deadline - time.monotonic())))
        raise BridgeConnectError(f"Could not connect to {host}:{server_port}: {last_error}")

    @staticmethod
    def _hello(result):
        required = {"bridge.hello", "element.get", "element.wait", "element.click"}
        if (type(result.get("protocol_version")) is not int or result["protocol_version"] != 1
                or not isinstance(result.get("session_id"), str) or not result["session_id"]
                or not isinstance(result.get("unity_version"), str)
                or not isinstance(result.get("methods"), list)
                or not all(isinstance(x, str) for x in result["methods"])
                or not required.issubset(result["methods"])
                or not isinstance(result.get("states"), list)
                or not all(isinstance(x, str) for x in result["states"])
                or not set(STATES).issubset(result["states"])
                or result.get("click_delivery") != "ugui_pointer_events"
                or type(result.get("max_timeout_ms")) is not int
                or result["max_timeout_ms"] != 120000):
            raise BridgeProtocolError(f"Incompatible hello response: {result!r}")
        return result

    def _cleanup_after_failure(self, original):
        try:
            self.close()
        except Exception as cleanup:
            original.cleanup_error = cleanup
            if hasattr(original, "add_note"):
                original.add_note(f"Additional cleanup failure: {cleanup}")

    def _timeout(self, timeout):
        return self.default_timeout if timeout is None else seconds(timeout)

    def _call(self, method, params, timeout, validator):
        if not self.connected:
            raise BridgeError("Not connected; call connect() or connect_local() first")
        return self._rpc.request(method, params, self._timeout(timeout), validator)

    @staticmethod
    def _snapshot(result, target, key="snapshot"):
        snapshot = result.get(key)
        elapsed = result.get("elapsed_ms")
        if (not isinstance(snapshot, dict) or not {"id", "exists", "visible", "enabled"}.issubset(snapshot)
                or snapshot.get("id") != target
                or type(snapshot.get("exists")) is not bool
                or type(snapshot.get("visible")) is not bool
                or (snapshot["exists"] and type(snapshot.get("enabled")) is not bool)
                or (not snapshot["exists"] and
                    (snapshot["visible"] or snapshot.get("enabled") is not None))
                or type(elapsed) not in (int, float) or elapsed < 0):
            raise BridgeProtocolError(f"Invalid {key} for {target!r}: {result!r}")
        return snapshot

    def get_state(self, element_id, timeout=None):
        target = validate_element_id(element_id)
        return self._call("element.get", {"selector": {"id": target}}, timeout,
                          lambda result: self._snapshot(result, target))

    def wait_for_state(self, element_id, state, timeout=None):
        target = validate_element_id(element_id)
        if state not in STATES:
            raise ValueError(f"state must be one of {STATES}")

        def validate(result):
            snapshot = self._snapshot(result, target)
            matches = {"visible": snapshot["visible"], "not visible": not snapshot["visible"],
                       "enabled": snapshot["exists"] and snapshot["enabled"] is True,
                       "disabled": snapshot["exists"] and snapshot["enabled"] is False}
            if result.get("matched_state") != state or not matches[state]:
                raise BridgeProtocolError(f"Server returned an unmatched state: {result!r}")
            return snapshot

        return self._call("element.wait", {"selector": {"id": target}, "state": state}, timeout, validate)

    def click(self, element_id, timeout=None, point=None):
        target = validate_element_id(element_id)
        position = validate_point(point)
        params = {"selector": {"id": target}}
        if position is not None:
            params["point"] = position

        def validate(result):
            snapshot = self._snapshot(result, target, "snapshot_before")
            if result.get("dispatched") is not True or not (
                    snapshot["exists"] and snapshot["visible"] and snapshot["enabled"]):
                raise BridgeProtocolError(f"Invalid click result: {result!r}")
            return result

        return self._call("element.click", params, timeout, validate)

    def close(self):
        if self._rpc is not None:
            self._rpc.close()
            self._rpc = None
        self.connection_info = None
        self._adb.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None:
            self._cleanup_after_failure(exc)
        else:
            self.close()
