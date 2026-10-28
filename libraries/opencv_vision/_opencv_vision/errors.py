"""Stable error codes with JSON-compatible diagnostic metadata."""

from copy import deepcopy


class VisionError(RuntimeError):
    code = "VISION_ERROR"

    def __init__(self, message, details=None):
        super().__init__(f"{self.code}: {message}")
        self.details = deepcopy(details or {})


class ImageNotFoundError(VisionError):
    code = "IMAGE_NOT_FOUND"


class AmbiguousImageMatchError(VisionError):
    code = "AMBIGUOUS_IMAGE_MATCH"


class InvalidArgumentError(VisionError):
    code = "INVALID_ARGUMENT"


class ImageReadError(VisionError):
    code = "IMAGE_READ_ERROR"


class UnsupportedTemplateError(VisionError):
    code = "UNSUPPORTED_TEMPLATE"


class DegenerateTemplateError(VisionError):
    code = "DEGENERATE_TEMPLATE"


class NoValidScaleError(VisionError):
    code = "NO_VALID_SCALE"


class AppiumSessionError(VisionError):
    code = "APPIUM_SESSION_ERROR"


class ScreenChangedError(VisionError):
    code = "SCREEN_CHANGED"


class ContextRestoreError(VisionError):
    code = "CONTEXT_RESTORE_ERROR"


class CoordinateMappingError(VisionError):
    code = "COORDINATE_MAPPING_ERROR"
