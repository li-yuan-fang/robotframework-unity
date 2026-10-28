"""Validate once at the boundary, including a bounded, stable scale grid."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
import math

import numpy as np

from .errors import InvalidArgumentError


def number(value, name):
    if isinstance(value, (bool, np.bool_)):
        raise InvalidArgumentError(f"{name} must be a finite number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidArgumentError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise InvalidArgumentError(f"{name} must be finite")
    return result


def integer(value, name):
    result = number(value, name)
    if not result.is_integer():
        raise InvalidArgumentError(f"{name} must be an integer")
    return int(result)


@dataclass(frozen=True)
class MatchOptions:
    threshold: float
    scales: tuple
    roi: object
    score_margin: float
    debug: str
    scale_min: float
    scale_max: float
    scale_step: float

    @classmethod
    def parse(cls, threshold=0.80, scale_min=0.50, scale_max=2.00,
              scale_step=0.05, roi=None, score_margin=0.05, debug="none"):
        threshold = number(threshold, "threshold")
        low = number(scale_min, "scale_min")
        high = number(scale_max, "scale_max")
        step = number(scale_step, "scale_step")
        margin = number(score_margin, "score_margin")
        if not 0 < threshold <= 1:
            raise InvalidArgumentError("threshold must be in (0, 1]")
        if not 0 < low <= high or step <= 0:
            raise InvalidArgumentError("require 0 < scale_min <= scale_max and scale_step > 0")
        if not 0 <= margin <= 1:
            raise InvalidArgumentError("score_margin must be in [0, 1]")
        if debug not in ("none", "on_failure", "always"):
            raise InvalidArgumentError("debug must be none, on_failure, or always")
        if roi is not None:
            if not isinstance(roi, (list, tuple)) or len(roi) != 4:
                raise InvalidArgumentError("roi must be a list/tuple of x, y, width, height")
            roi = tuple(integer(value, "roi component") for value in roi)
            if roi[0] < 0 or roi[1] < 0 or roi[2] <= 0 or roi[3] <= 0:
                raise InvalidArgumentError("roi requires nonnegative x/y and positive width/height")

        start, stop, increment = (Decimal(str(value)) for value in (low, high, step))
        count = int(((stop - start) / increment).to_integral_value(rounding=ROUND_FLOOR)) + 1
        if count > 101:
            raise InvalidArgumentError("a scan may request at most 101 scales")
        scales = [start + k * increment for k in range(count)]
        if scales[-1] != stop:
            scales.append(stop)
        if len(scales) > 101:
            raise InvalidArgumentError("a scan may request at most 101 scales")
        return cls(threshold, tuple(float(value) for value in scales), roi,
                   margin, debug, low, high, step)

    def metadata(self):
        return {"threshold": self.threshold, "scale_min": self.scale_min,
                "scale_max": self.scale_max, "scale_step": self.scale_step,
                "score_margin": self.score_margin, "debug": self.debug,
                "algorithm": "TM_CCOEFF_NORMED", "nms_iou": 0.30}
