"""Small, read-only snapshot: no session or image buffers escape the call."""

from copy import deepcopy


class ImageElement:
    __slots__ = ("_metadata",)
    _fields = frozenset((
        "rect", "center", "score", "scale", "image_size", "template_size",
        "scan_id", "coordinate_mapping", "window_size", "window_rect",
        "window_center", "window_scale", "debug_paths", "diagnostic_error",
        "elapsed_ms", "parameters", "roi",
    ))

    def __init__(self, metadata):
        if metadata.get("status") != "matched" or metadata.get("rect") is None:
            raise ValueError("ImageElement requires an accepted match")
        object.__setattr__(self, "_metadata", deepcopy(metadata))

    def __setattr__(self, name, value):
        raise AttributeError("ImageElement is a read-only screenshot snapshot")

    def __getattr__(self, name):
        if name in self._fields:
            return deepcopy(self._metadata[name])
        raise AttributeError(name)

    @property
    def location(self):
        rect = self._metadata["rect"]
        return {"x": rect["x"], "y": rect["y"]}

    @property
    def size(self):
        rect = self._metadata["rect"]
        return {"width": rect["width"], "height": rect["height"]}

    def to_dict(self):
        result = deepcopy(self._metadata)
        result.update(location=self.location, size=self.size)
        return result

    def __repr__(self):
        return (f"ImageElement(rect={self._metadata['rect']}, "
                f"score={self._metadata['score']:.4f}, scale={self._metadata['scale']})")
