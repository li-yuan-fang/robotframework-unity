import json
import socket
import threading
import time

from .errors import (
    BridgeClickOutcomeUnknown, BridgeClickTimeout, BridgeError, BridgeProtocolError,
    BridgeRpcError, BridgeTransportError, BridgeWaitTimeout,
)
from .validation import MAX_FRAME


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate JSON property {key!r}")
        obj[key] = value
    return obj


class TcpTransport:
    def __init__(self, sock):
        self.socket = sock
        self.buffer = bytearray()

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BridgeTransportError("RPC transport deadline exceeded")
        return remaining

    def exchange(self, payload, deadline):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_FRAME:
            raise BridgeProtocolError("Request exceeds 64 KiB")
        try:
            self.socket.settimeout(self._remaining(deadline))
            self.socket.sendall(encoded + b"\n")
            while True:
                newline = self.buffer.find(b"\n")
                if newline >= 0:
                    raw = bytes(self.buffer[:newline]).removesuffix(b"\r")
                    del self.buffer[:newline + 1]
                    if len(raw) > MAX_FRAME:
                        raise BridgeProtocolError("Response exceeds 64 KiB")
                    try:
                        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                          parse_constant=lambda n: (_ for _ in ()).throw(ValueError(n)))
                    except (UnicodeError, ValueError) as exc:
                        raise BridgeProtocolError(f"Invalid JSON response: {exc}") from exc
                if len(self.buffer) > MAX_FRAME + (1 if self.buffer.endswith(b"\r") else 0):
                    raise BridgeProtocolError("Unterminated response exceeds 64 KiB")
                self.socket.settimeout(self._remaining(deadline))
                block = self.socket.recv(8192)
                if not block:
                    raise BridgeTransportError("Unity closed the TCP connection")
                self.buffer.extend(block)
        except OSError as exc:
            raise BridgeTransportError(f"TCP exchange failed: {exc}") from exc

    def close(self):
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        finally:
            self.socket.close()
            self.buffer.clear()


class RpcClient:
    def __init__(self, sock, grace=2.0):
        self.transport = TcpTransport(sock)
        self.grace = grace
        self._id = 0
        self._lock = threading.Lock()
        self.connected = True

    def request(self, method, params, timeout, validator=None, deadline=None):
        if not self._lock.acquire(blocking=False):
            raise BridgeError("Concurrent RPC calls on one client are unsupported")
        started = time.monotonic()
        try:
            if not self.connected:
                raise BridgeTransportError("Not connected to Unity")
            self._id += 1
            if self._id > 2147483647:
                raise BridgeProtocolError("Request IDs exhausted; close and reconnect")
            payload = {"v": 1, "id": self._id, "method": method, "params": params,
                       "timeout_ms": max(1, int(timeout * 1000))}
            try:
                response = self.transport.exchange(
                    payload, min(deadline, started + timeout + self.grace)
                    if deadline is not None else started + timeout + self.grace)
                result = self._validate_response(response, method)
                return validator(result) if validator else result
            except (BridgeTransportError, BridgeProtocolError) as exc:
                self.close()
                context = f"{method} params={params!r}, elapsed={time.monotonic() - started:.3f}s: {exc}"
                if method == "element.click":
                    raise BridgeClickOutcomeUnknown(
                        f"Click outcome unknown; do not retry automatically. {context}") from exc
                raise type(exc)(context) from exc
        finally:
            self._lock.release()

    def _validate_response(self, response, method):
        if (not isinstance(response, dict) or type(response.get("v")) is not int
                or response["v"] != 1 or type(response.get("id")) is not int
                or response["id"] != self._id or type(response.get("ok")) is not bool):
            raise BridgeProtocolError(f"Invalid response envelope or mismatched id: {response!r}")
        if response["ok"]:
            if "error" in response or not isinstance(response.get("result"), dict):
                raise BridgeProtocolError("Successful response must contain only an object result")
            return response["result"]
        error = response.get("error")
        if ("result" in response or not isinstance(error, dict)
                or not isinstance(error.get("code"), str)
                or not isinstance(error.get("message"), str)
                or not isinstance(error.get("data", {}), dict)):
            raise BridgeProtocolError("Invalid RPC error envelope")
        if method == "element.click" and error.get("data", {}).get("effect") not in (
                "not_started", "started", "completed"):
            raise BridgeProtocolError("Click error omitted a reliable execution stage")
        cls = {"ELEMENT_WAIT_TIMEOUT": BridgeWaitTimeout,
               "ELEMENT_CLICK_TIMEOUT": BridgeClickTimeout}.get(error["code"], BridgeRpcError)
        raise cls(error["code"], error["message"], error.get("data"))

    def close(self):
        if self.connected:
            self.connected = False
            self.transport.close()
