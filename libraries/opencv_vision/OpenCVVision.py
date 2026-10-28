"""Public Python API and Robot library entry point.

Robot: Library    /path/to/libraries/opencv_vision/OpenCVVision.py
Python: from OpenCVVision import find_image_in_memory, ImageElement
"""

from _opencv_vision.core import find_image_in_memory
from _opencv_vision.element import ImageElement
from _opencv_vision.errors import (
    AmbiguousImageMatchError, AppiumSessionError, ContextRestoreError,
    CoordinateMappingError, DegenerateTemplateError, ImageNotFoundError,
    ImageReadError, InvalidArgumentError, NoValidScaleError,
    ScreenChangedError, UnsupportedTemplateError, VisionError,
)
from _opencv_vision.robot_library import OpenCVVision

__all__ = [
    "OpenCVVision", "ImageElement", "find_image_in_memory", "VisionError",
    "ImageNotFoundError", "AmbiguousImageMatchError", "InvalidArgumentError",
    "ImageReadError", "UnsupportedTemplateError", "DegenerateTemplateError",
    "NoValidScaleError", "AppiumSessionError", "ScreenChangedError",
    "ContextRestoreError", "CoordinateMappingError",
]
