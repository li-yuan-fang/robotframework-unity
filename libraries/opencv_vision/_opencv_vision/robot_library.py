"""Robot boundary: one explicit keyword, no session creation or implicit click.

Robot converts keyword arguments from their defaults unless types are declared.
Every optional argument of ``find_image_element`` defaults to ``None``, which
Robot resolves to a single-parameter tuple: ``roi=${region}`` then reached this
module as the string "[800, 450, 800, 450]" and failed as a float conversion.
The ``@keyword(types=...)`` table declares the intended types instead.
"""

from contextlib import nullcontext

from .appium_adapter import capture_screen, freeze_current_context
from .core import execute_scan, load_template
from .errors import AppiumSessionError, VisionError
from .options import MatchOptions

try:
    from robot.api import logger
    from robot.api.deco import keyword
    from robot.libraries.BuiltIn import BuiltIn
except ImportError:
    logger = None
    BuiltIn = None

    def keyword(name, **kwargs):
        def decorate(function):
            function.robot_name = name
            return function
        return decorate

KEYWORD = "CV Find Image Element"
# Robot converts each argument using these types. Without them, the shared None
# default of the optional arguments turns roi=${region} into a string.
TYPES = {
    "template": "Union[str, bytes]",
    "threshold": float,
    "scale_min": float,
    "scale_max": float,
    "scale_step": float,
    "roi": "Union[tuple, list, None]",
    "score_margin": float,
    "debug": str,
    "debug_dir": "Union[str, None]",
    "appium_library": str,
    "coordinate_mode": str,
}


class OpenCVVision:
    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_AUTO_KEYWORDS = False
    ROBOT_LIBRARY_VERSION = "0.1.0"

    @keyword(KEYWORD, types=TYPES)
    def cv_find_image_element(self, template, threshold=0.90, scale_min=0.50,
                           scale_max=5.00, scale_step=0.05, roi=None,
                           score_margin=0.01, debug="none", debug_dir=None,
                           appium_library="AppiumLibrary", coordinate_mode="screenshot"):
        """Find a template in one in-memory screenshot from the active application.

        ``template`` is a PNG/JPEG path or bytes. ``roi`` is an optional list
        [x, y, width, height] in screenshot pixels; ``roi=800,450,300,200`` is
        accepted as well. Unsuccessful/ambiguous matches raise distinct errors.
        Diagnostics are disabled by default. The returned ImageElement exposes
        rect, location, size, center, score, and scale; it is a snapshot and does
        not click or retain a session.

        If the AppiumLibrary is not imported, a frozen ``appium_library`` session
        is used and left on NATIVE_APP until this keyword ends.
        """
        if isinstance(roi, (list, tuple)) and not roi:
            roi = None
        options = MatchOptions.parse(threshold, scale_min, scale_max, scale_step,
                                     roi, score_margin, debug)
        library, freeze = self._session(appium_library)
        try:
            with freeze():
                element = execute_scan(lambda: load_template(template),
                                       lambda receive: capture_screen(library, receive),
                                       options, debug_dir, coordinate_mode)
        except VisionError as exc:
            self._log_diagnostic_error(exc.details)
            raise
        self._log_diagnostic_error(element.to_dict())
        if logger is not None:
            logger.info(repr(element))
        return element

    @staticmethod
    def _session(appium_library):
        """Return the AppiumLibrary instance and the context manager wrapping the scan."""
        try:
            library = BuiltIn().get_library_instance(appium_library)
        except Exception as exc:
            name = appium_library if isinstance(appium_library, str) else ""
            if not name.isidentifier():
                raise AppiumSessionError(
                    f"cannot access Robot library {appium_library!r}") from exc
            # The library is not imported, so Robot is not running this keyword:
            # let an outer freeze supervise the session before giving up.
            return None, _frozen(name)
        if not callable(getattr(library, "_current_application", None)):
            raise AppiumSessionError(
                f"Robot library {appium_library!r} is not an AppiumLibrary instance")
        return library, nullcontext

    @staticmethod
    def _log_diagnostic_error(metadata):
        if logger is not None and metadata.get("diagnostic_error"):
            logger.warn(f"OpenCVVision diagnostic export failed: {metadata['diagnostic_error']}")


def _frozen(name):
    """Freeze an outer library's context, or fail with the usual error."""
    try:
        library = BuiltIn().get_library_instance(name)
    except Exception as exc:
        raise AppiumSessionError(f"cannot access Robot library {name!r}") from exc
    return freeze_current_context(library)
