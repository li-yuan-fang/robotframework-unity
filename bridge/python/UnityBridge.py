"""Public entry point: Robot's UnityBridge library and the plain Python client.

Robot:   Library    /path/to/UnityBridge.py
Python:  from UnityBridge import UnityBridgeClient
"""

from _unity_bridge.client import UnityBridgeClient
from _unity_bridge.errors import (
    AdbError, BridgeCleanupError, BridgeClickOutcomeUnknown, BridgeClickTimeout,
    BridgeConnectError, BridgeError, BridgeProtocolError, BridgeRpcError,
    BridgeTransportError, BridgeWaitTimeout, DeviceSelectionError,
)
from _unity_bridge.robot_library import UnityBridge

__all__ = [
    "UnityBridge", "UnityBridgeClient", "BridgeError", "AdbError",
    "DeviceSelectionError", "BridgeCleanupError", "BridgeConnectError",
    "BridgeProtocolError", "BridgeTransportError", "BridgeRpcError",
    "BridgeWaitTimeout", "BridgeClickTimeout", "BridgeClickOutcomeUnknown",
]
