import subprocess
import time
from dataclasses import dataclass

from .errors import AdbError, BridgeCleanupError, DeviceSelectionError
from .validation import port


@dataclass(frozen=True)
class Forward:
    serial: str
    local: int
    remote: int


class AdbForwardManager:
    def __init__(self, adb_path="adb", runner=None):
        self.adb_path = str(adb_path)
        self._run_process = runner or subprocess.run
        self.owned = None

    def _run(self, args, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AdbError("ADB deadline exceeded")
        command = [self.adb_path, *args]
        try:
            result = self._run_process(command, capture_output=True, text=True,
                                       encoding="utf-8", errors="replace",
                                       timeout=min(3.0, remaining), shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdbError(f"ADB command {command!r} failed: {exc}") from exc
        if result.returncode:
            raise AdbError(f"ADB command {command!r} exited {result.returncode}: "
                           f"stdout={result.stdout!r}, stderr={result.stderr!r}")
        return result.stdout.strip()

    def create(self, serial, server_port, host_port, deadline):
        if self.owned is not None:
            raise AdbError("A forward is still owned; close it before connecting again")
        if serial is None:
            devices = self._run(["devices", "-l"], deadline)
            ready = [line.split()[0] for line in devices.splitlines()
                     if len(line.split()) >= 2 and line.split()[1] == "device"]
            if len(ready) != 1:
                raise DeviceSelectionError(
                    f"Expected exactly one authorized device, got {ready}; specify serial. {devices}")
            serial = ready[0]
        if not isinstance(serial, str) or not serial.strip():
            raise DeviceSelectionError("serial must be a nonblank string")
        state = self._run(["-s", serial, "get-state"], deadline)
        if state != "device":
            raise DeviceSelectionError(f"Device {serial!r} is not ready: {state!r}")
        remote = port(server_port, "server_port")
        if host_port is None:
            output = self._run(["-s", serial, "forward", "tcp:0", f"tcp:{remote}"], deadline)
            try:
                local = port(output, "allocated host_port")
            except ValueError as exc:
                raise AdbError(f"ADB did not return its allocated port: {output!r}") from exc
        else:
            local = port(host_port, "host_port")
            self._run(["-s", serial, "forward", "--no-rebind",
                       f"tcp:{local}", f"tcp:{remote}"], deadline)
        self.owned = Forward(serial, local, remote)
        return self.owned

    def close(self, timeout=3.0):
        owned = self.owned
        if owned is None:
            return
        deadline = time.monotonic() + timeout
        try:
            output = self._run(["-s", owned.serial, "forward", "--list"], deadline)
            mappings = [line.split() for line in output.splitlines()]
            same_local = [parts for parts in mappings if len(parts) == 3
                          and parts[0] == owned.serial and parts[1] == f"tcp:{owned.local}"]
            if not same_local:
                self.owned = None
                return
            if same_local != [[owned.serial, f"tcp:{owned.local}", f"tcp:{owned.remote}"]]:
                self.owned = None
                raise BridgeCleanupError(f"Forward {owned} was replaced; skipped removal")
            self._run(["-s", owned.serial, "forward", "--remove", f"tcp:{owned.local}"], deadline)
            self.owned = None
        except AdbError as exc:
            if isinstance(exc, BridgeCleanupError):
                raise
            # Preserve ownership so the caller can retry cleanup after ADB recovers.
            raise BridgeCleanupError(f"Could not clean up forward {owned}: {exc}") from exc
