"""Errors preserve the distinction between a failed condition and lost delivery."""


class BridgeError(RuntimeError):
    pass


class AdbError(BridgeError):
    pass


class DeviceSelectionError(AdbError):
    pass


class BridgeCleanupError(AdbError):
    pass


class BridgeConnectError(BridgeError):
    pass


class BridgeProtocolError(BridgeError):
    pass


class BridgeTransportError(BridgeError):
    pass


class BridgeClickOutcomeUnknown(BridgeTransportError):
    """The click may have run. Reconnect and inspect state before another click."""


class BridgeRpcError(BridgeError):
    def __init__(self, code, message, data=None):
        self.code = code
        self.data = data or {}
        super().__init__(f"{code}: {message}; details={self.data}")


class BridgeWaitTimeout(BridgeRpcError, AssertionError):
    pass


class BridgeClickTimeout(BridgeRpcError, AssertionError):
    pass
