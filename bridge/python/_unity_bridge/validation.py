import math
import unicodedata

STATES = ("visible", "not visible", "enabled", "disabled")
MAX_FRAME = 64 * 1024
MAX_TIMEOUT = 120.0


def seconds(value, name="timeout", maximum=MAX_TIMEOUT):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive number of seconds")
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise ValueError(f"{name} must be in (0, {maximum}] seconds")
    # The wire format has millisecond precision.
    if number < 0.001:
        raise ValueError(f"{name} must be at least 0.001 seconds")
    return number


def port(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer TCP port")
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} must be an integer TCP port") from exc
    if str(number) != str(value) or not 1 <= number <= 65535:
        raise ValueError(f"{name} must be an integer in [1, 65535]")
    return number


def element_id(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 128
            or any(unicodedata.category(ch) in ("Cc", "Cs") for ch in value)):
        raise ValueError("element_id must be nonblank, at most 128 characters, without control characters")
    return value


def point(value):
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("point must be a two-item list/tuple of normalized coordinates")
    if any(isinstance(n, bool) or not isinstance(n, (int, float))
           or not math.isfinite(n) or not 0 <= n <= 1 for n in value):
        raise ValueError("point coordinates must be finite numbers in [0, 1]")
    return list(value)
