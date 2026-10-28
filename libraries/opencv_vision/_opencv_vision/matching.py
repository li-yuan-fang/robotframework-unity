"""OpenCV computation only: no device calls or filesystem operations."""

import math

import cv2
import numpy as np

from .errors import (
    DegenerateTemplateError, ImageReadError, InvalidArgumentError,
    NoValidScaleError, UnsupportedTemplateError,
)


def encoding(data):
    if isinstance(data, bytes):
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if data.startswith(b"\xff\xd8\xff"):
            return "jpg"
    return None


def decode(data, name):
    if not isinstance(data, bytes):
        raise InvalidArgumentError(f"{name} must be encoded PNG/JPEG bytes")
    if not encoding(data):
        raise ImageReadError(f"{name} is not an encoded PNG/JPEG image")
    try:
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except cv2.error as exc:
        raise ImageReadError(f"cannot decode {name}") from exc
    if image is None or image.size == 0 or image.dtype != np.uint8:
        raise ImageReadError(f"{name} must be a nonempty 8-bit image")
    return image


def grayscale(image, template=False):
    if image.ndim == 2:
        result = image
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        if template and image.shape[2] == 4 and np.any(image[:, :, 3] != 255):
            raise UnsupportedTemplateError("template must be opaque; crop it from a screenshot")
        result = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY if image.shape[2] == 4
                              else cv2.COLOR_BGR2GRAY)
    else:
        raise ImageReadError("unsupported image channel layout")
    if template and float(result.std()) < 1.0:
        raise DegenerateTemplateError("template grayscale standard deviation must be at least 1")
    return result


def image_size(image):
    return {"width": int(image.shape[1]), "height": int(image.shape[0])}


def center(rect):
    return {"x": rect["x"] + rect["width"] / 2,
            "y": rect["y"] + rect["height"] / 2}


def _candidate(row):
    x, y, width, height, score, scale = row
    return {"rect": {"x": int(x), "y": int(y), "width": int(width), "height": int(height)},
            "score": float(score), "scale": float(scale)}


def _top_two(rows):
    if not rows:
        return None, None
    candidates = np.concatenate(rows)
    # Highest score, then nearest to original size, then top-to-bottom/left-to-right.
    order = np.lexsort((candidates[:, 0], candidates[:, 1],
                        np.abs(candidates[:, 5] - 1), -candidates[:, 4]))
    first = candidates[order[0]]
    other = candidates[order[1:]]
    if not len(other):
        return _candidate(first), None
    overlap_w = np.maximum(0, np.minimum(first[0] + first[2], other[:, 0] + other[:, 2])
                           - np.maximum(first[0], other[:, 0]))
    overlap_h = np.maximum(0, np.minimum(first[1] + first[3], other[:, 1] + other[:, 3])
                           - np.maximum(first[1], other[:, 1]))
    intersection = overlap_w * overlap_h
    union = first[2] * first[3] + other[:, 2] * other[:, 3] - intersection
    different = np.flatnonzero(intersection / union < 0.30)
    second = _candidate(other[different[0]]) if len(different) else None
    return _candidate(first), second


def match(source, template, options, result):
    """Populate metadata, retaining all above-threshold spatial peaks for ambiguity."""
    source_gray = grayscale(source)
    template_gray = grayscale(template, template=True)
    result.update(image_size=image_size(source), template_size=image_size(template))
    source_h, source_w = source_gray.shape
    roi = options.roi or (0, 0, source_w, source_h)
    x, y, width, height = roi
    if x + width > source_w or y + height > source_h:
        raise InvalidArgumentError("roi must fit completely inside the source image")
    result["roi"] = list(roi)
    search = np.ascontiguousarray(source_gray[y:y + height, x:x + width])
    template_h, template_w = template_gray.shape
    rows, seen = [], set()
    valid = 0
    for scale in options.scales:
        record = {"scale": scale}
        result["scales"].append(record)
        scaled_w, scaled_h = template_w * scale, template_h * scale
        if not math.isfinite(scaled_w) or not math.isfinite(scaled_h):
            record["skipped"] = "larger_than_roi"
            continue
        w, h = math.floor(scaled_w + 0.5), math.floor(scaled_h + 0.5)
        record.update(width=w, height=h)
        if w < 3 or h < 3:
            record["skipped"] = "smaller_than_3_pixels"
            continue
        if w > width or h > height:
            record["skipped"] = "larger_than_roi"
            continue
        if (w, h) in seen:
            record["skipped"] = "duplicate_dimensions"
            continue
        seen.add((w, h))
        resized = cv2.resize(template_gray, (w, h), interpolation=(
            cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC))
        if float(resized.std()) < 1.0:
            record["skipped"] = "degenerate_grayscale"
            continue
        valid += 1
        response = cv2.matchTemplate(search, resized, cv2.TM_CCOEFF_NORMED)
        finite = np.isfinite(response)
        if not np.any(finite):
            record["skipped"] = "no_finite_scores"
            continue
        response = np.where(finite, np.clip(response, -1, 1), -np.inf)
        local_max = cv2.dilate(response, np.ones((3, 3), dtype=np.uint8))
        peaks = finite & (response == local_max) & (response >= options.threshold)
        # Retain a rejected best candidate as well, to explain not-found failures.
        best_index = np.unravel_index(int(np.argmax(response)), response.shape)
        peaks[best_index] = True
        ys, xs = np.nonzero(peaks)
        rows.append(np.column_stack((xs + x, ys + y,
                                     np.full(len(xs), w), np.full(len(xs), h),
                                     response[ys, xs], np.full(len(xs), scale))))
    if not valid:
        raise NoValidScaleError("all requested template sizes are invalid for this ROI")

    best, second = _top_two(rows)
    # Only above-threshold alternatives matter to the ambiguity contract.
    if second is not None and second["score"] < options.threshold:
        second = None
    result.update(best_candidate=best, second_candidate=second)
    if best is None:
        result["status"] = "not_found"
        return
    result.update(score=best["score"], scale=best["scale"])
    if best["score"] < options.threshold:
        result["status"] = "not_found"
    elif (second is not None and second["score"] >= options.threshold
          and best["score"] - second["score"] < options.score_margin):
        result["status"] = "ambiguous"
    else:
        result.update(status="matched", rect=best["rect"], center=center(best["rect"]))
