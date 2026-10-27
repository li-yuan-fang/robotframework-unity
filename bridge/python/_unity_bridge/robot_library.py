from .client import UnityBridgeClient

try:
    from robot.api.deco import keyword
    from robot.utils import timestr_to_secs
except ImportError:
    def keyword(name):
        def decorate(function):
            function.robot_name = name
            return function
        return decorate

    def timestr_to_secs(value):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError("Install the [robot] extra to parse Robot time strings such as '5s'") from exc


def _time(value):
    if isinstance(value, bool):
        raise ValueError("timeout cannot be a boolean")
    return timestr_to_secs(value) if isinstance(value, str) else value


class UnityBridge:
    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_AUTO_KEYWORDS = False
    ROBOT_LIBRARY_VERSION = "0.1.0"

    def __init__(self, default_timeout=5.0, adb_path="adb", transport_grace=2.0):
        self.client = UnityBridgeClient(adb_path, _time(default_timeout), _time(transport_grace))

    @keyword("Connect To Unity")
    def connect_to_unity(self, serial=None, server_port=13000, host_port="auto", timeout="10s"):
        """Create an owned ADB forward, connect, and negotiate the protocol."""
        local_port = None if host_port is None or str(host_port).lower() == "auto" else host_port
        return self.client.connect(serial, server_port, local_port, _time(timeout))

    @keyword("Connect To Unity Editor")
    def connect_to_unity_editor(self, server_port=13000, timeout="10s"):
        """Connect to a running Editor/demo player directly, without ADB."""
        return self.client.connect_local(server_port=server_port, timeout=_time(timeout))

    @keyword("Close Unity Connection")
    def close_unity_connection(self):
        self.client.close()

    @keyword("Get Unity Element State")
    def get_unity_element_state(self, element_id, timeout=None):
        return self.client.get_state(element_id, None if timeout is None else _time(timeout))

    @keyword("Wait For Unity Element State")
    def wait_for_unity_element_state(self, element_id, state, timeout=None):
        return self.client.wait_for_state(element_id, str(state).strip().lower(),
                                          None if timeout is None else _time(timeout))

    @keyword("Click Unity Element")
    def click_unity_element(self, element_id, timeout=None, point=None):
        return self.client.click(element_id, None if timeout is None else _time(timeout), point)
