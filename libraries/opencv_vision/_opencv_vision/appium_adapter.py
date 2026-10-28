"""The sole dependency on AppiumLibrary's private current-session accessor."""

import weakref
from contextlib import contextmanager

from .errors import (
    AppiumSessionError, ContextRestoreError, ScreenChangedError, VisionError,
)
from .options import integer

# Drivers whose context a frozen keyword keeps on NATIVE_APP, with nesting depth.
_frozen_contexts = weakref.WeakKeyDictionary()


def _window(driver):
    raw = driver.get_window_size()
    size = {name: integer(raw[name], f"window {name}") for name in ("width", "height")}
    if min(size.values()) <= 0:
        raise ValueError("window dimensions must be positive")
    return size


def _acquire_frozen_context(driver):
    """Increase the freeze depth; True tells the caller it owes a matching release."""
    if not _frozen_contexts.get(driver, 0):
        return False
    _frozen_contexts[driver] += 1
    return True


def _release_frozen_context(driver):
    remaining = _frozen_contexts.get(driver, 1) - 1
    if remaining:
        _frozen_contexts[driver] = remaining
        return
    _frozen_contexts.pop(driver, None)
    try:
        driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass


def capture_screen(library, receive):
    """Capture once into receive, check geometry, always restore original context.

    When the caller froze the context with freeze_current_context, the switch is
    borrowed instead of performed, and restoring it stays the caller's job.
    """
    try:
        driver = library._current_application()
        original_context = driver.current_context
        if not isinstance(original_context, str) or not original_context:
            raise ValueError("Appium returned no current context")
    except Exception as exc:
        raise AppiumSessionError("cannot access the active Appium session") from exc
    restore = original_context != "NATIVE_APP" and not _acquire_frozen_context(driver)
    error = None
    try:
        if restore:
            driver.switch_to.context("NATIVE_APP")
        before = _window(driver)
        orientation = driver.orientation
        if not isinstance(orientation, str) or not orientation:
            raise AppiumSessionError("Appium returned no screen orientation")
        data = driver.get_screenshot_as_png()
        if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AppiumSessionError("get_screenshot_as_png did not return PNG bytes")
        receive(data, before)
        if _window(driver) != before or driver.orientation != orientation:
            raise ScreenChangedError("window size or orientation changed during screenshot capture")
    except VisionError as exc:
        error = exc
    except Exception as exc:
        error = AppiumSessionError(f"could not capture screen: {type(exc).__name__}: {exc}")
        error.__cause__ = exc
    finally:
        if restore:
            try:
                driver.switch_to.context(original_context)
            except Exception as exc:
                if error is None:
                    error = ContextRestoreError("could not restore the original Appium context")
                    error.__cause__ = exc
                else:
                    error.details["context_restore_error"] = {
                        "code": ContextRestoreError.code, "message": f"{type(exc).__name__}: {exc}",
                    }
    if error is not None:
        raise error


@contextmanager
def freeze_current_context(library):
    """Pin the active Appium context to NATIVE_APP until the with-block exits.

    Used when a keyword cannot start its own session and the caller decides how
    long the freeze lasts. A frozen driver stays on NATIVE_APP; on exit the
    library switches back to whatever NATIVE_APP covers, the frozen library's
    default context, because the original OCR context cannot be recovered.
    """
    try:
        driver = library._current_application()
    except Exception as exc:
        raise AppiumSessionError("cannot access the active Appium session") from exc
    try:
        if driver.current_context != "NATIVE_APP":
            driver.switch_to.context("NATIVE_APP")
    except Exception as exc:
        raise AppiumSessionError("cannot switch to the NATIVE_APP context") from exc
    if not _acquire_frozen_context(driver):
        _frozen_contexts[driver] = 1
    try:
        yield
    finally:
        _release_frozen_context(driver)
