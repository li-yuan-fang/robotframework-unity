"""Explicit, optional exports; these files are never inputs to matching."""

import importlib.metadata
import json
from pathlib import Path

import cv2

from .matching import encoding


def export_debug(directory, result, source_bytes, template_bytes, source_image, error):
    """Best effort: annotate the exact frame already in memory, preserve primary errors."""
    try:
        target = Path(directory).resolve() / result["scan_id"]
        target.mkdir(parents=True, exist_ok=False)
        for name, data in (("source", source_bytes), ("template", template_bytes)):
            extension = encoding(data)
            if extension:
                path = target / f"{name}.{extension}"
                path.write_bytes(data)
                result["debug_paths"][name] = str(path)
        if source_image is not None:
            if source_image.ndim == 2:
                marked = cv2.cvtColor(source_image, cv2.COLOR_GRAY2BGR)
            elif source_image.shape[2] == 4:
                marked = cv2.cvtColor(source_image, cv2.COLOR_BGRA2BGR)
            else:
                marked = source_image.copy()
            if result["roi"] is not None:
                x, y, w, h = result["roi"]
                cv2.rectangle(marked, (x, y), (x + w - 1, y + h - 1), (255, 180, 0), 1)
            accepted = result["status"] == "matched" and error is None
            for index, key in enumerate(("best_candidate", "second_candidate")):
                candidate = result[key]
                if candidate is None:
                    continue
                rect = candidate["rect"]
                x, y, w, h = (rect[name] for name in ("x", "y", "width", "height"))
                color = (0, 200, 0) if accepted and index == 0 else (0, 100, 255)
                cv2.rectangle(marked, (x, y), (x + w - 1, y + h - 1), color, 2)
                label = (f"{'accepted' if accepted and index == 0 else 'candidate'} "
                         f"{candidate['score']:.4f} scale={candidate['scale']:g}")
                cv2.putText(marked, label, (x, max(12, y - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            status = error.code if error is not None else result["status"]
            cv2.putText(marked, status, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 100, 255), 1)
            success, encoded = cv2.imencode(".png", marked)
            if not success:
                raise OSError("could not encode the annotated image")
            path = target / "annotated.png"
            path.write_bytes(encoded.tobytes())
            result["debug_paths"]["annotated"] = str(path)
        versions = {"opencv": cv2.__version__}
        for package in ("numpy", "robotframework", "robotframework-appiumlibrary"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                pass
        path = target / "metadata.json"
        result["debug_paths"]["metadata"] = str(path)
        metadata = dict(result, versions=versions,
                        error={"code": error.code, "message": str(error),
                               "details": error.details} if error else None)
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False),
                        encoding="utf-8")
    except Exception as exc:
        result["diagnostic_error"] = f"{type(exc).__name__}: {exc}"
