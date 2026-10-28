"""One frame per scan, optional diagnostics, stable success/error contracts."""

from copy import deepcopy
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .diagnostics import export_debug
from .element import ImageElement
from .errors import (
    AmbiguousImageMatchError, CoordinateMappingError, ImageNotFoundError,
    ImageReadError, InvalidArgumentError, VisionError,
)
from .matching import center, decode, grayscale, image_size, match
from .options import MatchOptions


def load_template(template):
    if isinstance(template, bytes):
        return template, None
    if not isinstance(template, (str, os.PathLike)):
        raise InvalidArgumentError("template must be an image path or PNG/JPEG bytes")
    try:
        path = Path(template).expanduser().resolve()
        return path.read_bytes(), str(path)
    except (OSError, ValueError) as exc:
        raise ImageReadError(f"cannot read template: {template}") from exc


def _map_coordinates(result, coordinate_mode):
    window, image = result["window_size"], result["image_size"]
    if window is None or coordinate_mode == "screenshot":
        return
    sx, sy = window["width"] / image["width"], window["height"] / image["height"]
    if abs(sx / sy - 1) > 0.005:
        raise CoordinateMappingError("screenshot/window scales disagree; full-window mapping is invalid")
    result["coordinate_mapping"] = "identity" if window == image else "scaled"
    result["window_scale"] = {"x": sx, "y": sy}
    if result["rect"] is not None:
        rect = result["rect"]
        result["window_rect"] = {"x": rect["x"] * sx, "y": rect["y"] * sy,
                                 "width": rect["width"] * sx, "height": rect["height"] * sy}
        result["window_center"] = center(result["window_rect"])


def execute_scan(template_loader, source_provider, options, debug_dir=None,
                 coordinate_mode="screenshot"):
    """Providers supply bytes; only the opt-in diagnostic exporter writes files.

    source_provider(receive) must call receive(bytes, window_size_or_none) once.
    Capturing into receive before checking screen stability preserves the exact
    frame for optional diagnostics even if the capture's post-check fails.
    """
    if coordinate_mode not in ("screenshot", "full_window"):
        raise InvalidArgumentError("coordinate_mode must be screenshot or full_window")
    if options.debug != "none" and debug_dir is None:
        raise InvalidArgumentError("debug_dir is required when diagnostics are enabled outside Robot")
    started = perf_counter()
    result = {
        "scan_id": uuid4().hex, "status": "error", "rect": None, "center": None,
        "score": None, "scale": None, "best_candidate": None, "second_candidate": None,
        "image_size": None, "template_size": None, "template_path": None, "roi": None,
        "parameters": dict(options.metadata(), coordinate_mode=coordinate_mode), "scales": [],
        "coordinate_mapping": "not_applicable", "window_size": None,
        "window_rect": None, "window_center": None, "window_scale": None,
        "elapsed_ms": 0.0, "debug_paths": {}, "diagnostic_error": None,
    }
    buffers = {"source": None, "template": None}
    source_image = None
    error = None

    def receive(data, window=None):
        if buffers["source"] is not None:
            raise InvalidArgumentError("a scan must receive exactly one screenshot")
        buffers["source"] = data
        result["window_size"] = deepcopy(window)
        if window is not None:
            result["coordinate_mapping"] = "unverified"

    try:
        buffers["template"], result["template_path"] = template_loader()
        template = decode(buffers["template"], "template")
        result["template_size"] = image_size(template)
        grayscale(template, template=True)
        source_provider(receive)
        source_image = decode(buffers["source"], "source_bytes")
        match(source_image, template, options, result)
        _map_coordinates(result, coordinate_mode)
        if result["status"] == "not_found":
            raise ImageNotFoundError(f"no candidate reached threshold {options.threshold:g}")
        if result["status"] == "ambiguous":
            raise AmbiguousImageMatchError("different screen positions have similar matching scores")
    except VisionError as exc:
        error = exc
    except Exception as exc:
        error = VisionError(f"image scan failed: {type(exc).__name__}: {exc}")
        error.__cause__ = exc
    result["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)

    if options.debug == "always" or (options.debug == "on_failure" and error is not None):
        if source_image is None and buffers["source"] is not None:
            try:
                source_image = decode(buffers["source"], "source_bytes")
                result["image_size"] = image_size(source_image)
            except VisionError:
                pass
        export_debug(debug_dir, result, buffers["source"], buffers["template"], source_image, error)
    if error is not None:
        error.details.update(deepcopy(result))
        raise error
    return ImageElement(result)


def find_image_in_memory(source_bytes, template_bytes, *, threshold=0.80,
                         scale_min=0.50, scale_max=2.00, scale_step=0.05,
                         roi=None, score_margin=0.05, debug="none", debug_dir=None):
    """Find a single template in encoded PNG/JPEG bytes without device or file input.

    Returns a read-only ImageElement. Raises ImageNotFoundError or
    AmbiguousImageMatchError for unsuccessful matches. Files are written only
    when debug is explicitly enabled and debug_dir is supplied.
    """
    options = MatchOptions.parse(threshold, scale_min, scale_max, scale_step, roi, score_margin, debug)
    return execute_scan(lambda: (template_bytes, None),
                        lambda receive: receive(source_bytes), options, debug_dir)
