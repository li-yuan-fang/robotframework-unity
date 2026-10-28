"""Offline acceptance checks using real OpenCV and a substitute Appium session."""

from contextlib import contextmanager
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from OpenCVVision import (  # noqa: E402
    AmbiguousImageMatchError, AppiumSessionError, ContextRestoreError,
    CoordinateMappingError, DegenerateTemplateError, ImageElement,
    ImageNotFoundError, ImageReadError, InvalidArgumentError, NoValidScaleError,
    OpenCVVision, ScreenChangedError, UnsupportedTemplateError, find_image_in_memory,
)
from _opencv_vision.appium_adapter import capture_screen, freeze_current_context  # noqa: E402
from _opencv_vision.core import execute_scan  # noqa: E402
from _opencv_vision.options import MatchOptions  # noqa: E402


def encoded(image, extension=".png"):
    ok, buffer = cv2.imencode(extension, image)
    if not ok:
        raise AssertionError("fixture could not be encoded")
    return buffer.tobytes()


def fixture(scale=1.0, position=(81, 63), duplicate=False):
    rng = np.random.default_rng(21)
    template = rng.integers(40, 240, size=(32, 48, 3), dtype=np.uint8)
    template = cv2.GaussianBlur(template, (3, 3), 0)
    cv2.rectangle(template, (1, 1), (46, 30), (220, 30, 180), 2)
    cv2.circle(template, (15, 14), 7, (20, 240, 50), -1)
    resized = cv2.resize(template, (int(48 * scale + .5), int(32 * scale + .5)),
                         interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    screen = rng.integers(0, 60, size=(230, 330, 3), dtype=np.uint8)
    h, w = resized.shape[:2]
    x, y = position
    screen[y:y + h, x:x + w] = resized
    # A similar-looking but different pattern should not win over the true target.
    distractor = cv2.flip(resized, 1)
    screen[8:8 + h, 220:220 + w] = distractor
    if duplicate:
        screen[150:150 + h, 210:210 + w] = resized
    return screen, template


@contextmanager
def workdir():
    parent = ROOT / "test-results"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as directory:
        yield Path(directory)


class MatchingTests(unittest.TestCase):
    def test_all_required_scales_find_correct_location_and_size(self):
        for scale in (.5, .75, 1., 1.25, 1.5, 2.):
            with self.subTest(scale=scale):
                screen, template = fixture(scale)
                element = find_image_in_memory(encoded(screen), encoded(template))
                self.assertIsInstance(element, ImageElement)
                self.assertEqual(element.location, {"x": 81, "y": 63})
                self.assertEqual(element.size, {"width": round(48 * scale), "height": round(32 * scale)})
                self.assertEqual(element.scale, scale)
                self.assertGreater(element.score, .98)

    def test_finer_step_recovers_scale_between_default_samples(self):
        screen, template = fixture(1.23)
        fine = find_image_in_memory(encoded(screen), encoded(template),
                                    scale_min=1.20, scale_max=1.25, scale_step=.01)
        self.assertEqual(fine.location, {"x": 81, "y": 63})
        self.assertEqual(fine.size, {"width": 59, "height": 39})
        # 1.22 and 1.23 round to the same 59x39 template; size dedup keeps 1.22.
        self.assertEqual(fine.scale, 1.22)
        self.assertGreater(fine.score, .98)
        with self.assertRaises(ImageNotFoundError):
            find_image_in_memory(encoded(screen), encoded(template), threshold=.98,
                                 scale_min=1.20, scale_max=1.20)

    def test_roi_offsets_and_excludes_other_copy(self):
        screen, template = fixture(duplicate=True)
        element = find_image_in_memory(encoded(screen), encoded(template), roi=[60, 40, 120, 100])
        self.assertEqual(element.rect, {"x": 81, "y": 63, "width": 48, "height": 32})
        self.assertEqual(element.center, {"x": 105.0, "y": 79.0})

    def test_duplicate_locations_are_ambiguous_even_at_one_scale(self):
        screen, template = fixture(duplicate=True)
        with self.assertRaises(AmbiguousImageMatchError) as caught:
            find_image_in_memory(encoded(screen), encoded(template), scale_min=1, scale_max=1)
        self.assertEqual(caught.exception.details["status"], "ambiguous")
        self.assertIsNone(caught.exception.details["rect"])
        self.assertIsNotNone(caught.exception.details["second_candidate"])

    def test_zero_margin_explicitly_allows_best_of_repeated_targets(self):
        screen, template = fixture(duplicate=True)
        element = find_image_in_memory(encoded(screen), encoded(template), score_margin=0)
        self.assertIn(element.location, ({"x": 81, "y": 63}, {"x": 210, "y": 150}))

    def test_not_found_keeps_rejected_candidate_and_serializable_metadata(self):
        screen, template = fixture()
        screen[:] = np.random.default_rng(4).integers(0, 255, screen.shape, dtype=np.uint8)
        with self.assertRaises(ImageNotFoundError) as caught:
            find_image_in_memory(encoded(screen), encoded(template))
        details = caught.exception.details
        self.assertEqual(details["status"], "not_found")
        self.assertLess(details["score"], .8)
        self.assertIsNotNone(details["best_candidate"])
        json.dumps(details, allow_nan=False)

    def test_element_is_read_only_and_has_no_image_or_session(self):
        screen, template = fixture()
        element = find_image_in_memory(encoded(screen), encoded(template))
        copy = element.rect
        copy["x"] = -100
        self.assertEqual(element.location["x"], 81)
        data = element.to_dict()
        data["rect"]["x"] = -200
        self.assertEqual(element.rect["x"], 81)
        with self.assertRaises(AttributeError):
            element.score = 0
        for name in ("click", "id", "driver", "source_bytes"):
            self.assertFalse(hasattr(element, name))
        json.dumps(element.to_dict(), allow_nan=False)

    def test_memory_scan_performs_no_file_io_including_failure(self):
        screen, template = fixture()
        source_bytes, template_bytes = encoded(screen), encoded(template)
        with patch("builtins.open", side_effect=AssertionError("file IO")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("file read")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("file write")), \
                patch("tempfile.mkstemp", side_effect=AssertionError("temporary file")), \
                patch.object(cv2, "imread", side_effect=AssertionError("imread")), \
                patch.object(cv2, "imwrite", side_effect=AssertionError("imwrite")):
            self.assertEqual(find_image_in_memory(source_bytes, template_bytes).location["x"], 81)
            with self.assertRaises(ImageNotFoundError):
                find_image_in_memory(template_bytes, source_bytes, scale_min=.1, scale_max=.1)

    def test_scale_grid_is_bounded_inclusive_and_deduplicates_dimensions(self):
        self.assertEqual(len(MatchOptions.parse().scales), 31)
        self.assertEqual(MatchOptions.parse(scale_min=.5, scale_max=.61, scale_step=.1).scales,
                         (.5, .6, .61))
        with self.assertRaises(InvalidArgumentError):
            MatchOptions.parse(scale_step=.001)
        screen, template = fixture()
        element = find_image_in_memory(encoded(screen), encoded(template),
                                       scale_min=1, scale_max=1.001, scale_step=.001)
        self.assertEqual(element.scale, 1)
        self.assertEqual(element.to_dict()["scales"][1]["skipped"], "duplicate_dimensions")

    def test_invalid_inputs_raise_specific_errors(self):
        screen, template = fixture()
        source, target = encoded(screen), encoded(template)
        invalid = [dict(threshold=True), dict(threshold=np.bool_(True)),
                   dict(threshold=float("nan")), dict(threshold=0),
                   dict(scale_min=0), dict(scale_step=-1), dict(scale_max=.1),
                   dict(score_margin=2), dict(roi=[-1, 0, 5, 5]), dict(roi=[0, 0, 2.5, 3]),
                   dict(roi=[0, 0, 400, 300]), dict(debug="sometimes"), dict(debug="always")]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(InvalidArgumentError):
                find_image_in_memory(source, target, **kwargs)
        for bad in (b"invalid", b"", b"\x89PNG\r\n\x1a\n"):
            with self.assertRaises(ImageReadError):
                find_image_in_memory(source, bad)
        with self.assertRaises(InvalidArgumentError):
            find_image_in_memory("screenshot.png", target)
        with self.assertRaises(NoValidScaleError):
            find_image_in_memory(target, source, scale_min=1, scale_max=1)
        with self.assertRaises(DegenerateTemplateError):
            find_image_in_memory(source, encoded(np.full((10, 10), 120, np.uint8)))
        transparent = cv2.cvtColor(template, cv2.COLOR_BGR2BGRA)
        transparent[0, 0, 3] = 0
        with self.assertRaises(UnsupportedTemplateError):
            find_image_in_memory(source, encoded(transparent))

    def test_jpeg_source_and_template(self):
        screen, template = fixture()
        element = find_image_in_memory(encoded(screen, ".jpg"), encoded(template, ".jpg"),
                                       threshold=.85)
        self.assertEqual(element.location, {"x": 81, "y": 63})


class DiagnosticTests(unittest.TestCase):
    def test_exports_exact_bytes_and_distinct_directories(self):
        screen, template = fixture()
        source, target = encoded(screen), encoded(template)
        with workdir() as directory:
            first = find_image_in_memory(source, target, debug="always", debug_dir=directory)
            second = find_image_in_memory(source, target, debug="always", debug_dir=directory)
            self.assertNotEqual(first.debug_paths["source"], second.debug_paths["source"])
            self.assertEqual(Path(first.debug_paths["source"]).read_bytes(), source)
            self.assertEqual(Path(first.debug_paths["template"]).read_bytes(), target)
            metadata = json.loads(Path(first.debug_paths["metadata"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["rect"], first.rect)
            self.assertEqual(metadata["status"], "matched")
            marked = cv2.imdecode(np.frombuffer(Path(first.debug_paths["annotated"]).read_bytes(),
                                                dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(marked.shape, screen.shape)
            self.assertGreater(np.count_nonzero(marked != screen), 0)

    def test_explicit_failure_export_and_no_export_on_success(self):
        screen, template = fixture(duplicate=True)
        with workdir() as directory:
            with self.assertRaises(AmbiguousImageMatchError) as caught:
                find_image_in_memory(encoded(screen), encoded(template),
                                     debug="on_failure", debug_dir=directory)
            self.assertTrue(Path(caught.exception.details["debug_paths"]["annotated"]).is_file())
            screen, template = fixture()
            absent = directory / "must-not-be-created"
            element = find_image_in_memory(encoded(screen), encoded(template),
                                           debug="on_failure", debug_dir=absent)
            self.assertFalse(absent.exists())
            self.assertEqual(element.debug_paths, {})

    def test_export_failure_does_not_replace_match_or_primary_error(self):
        screen, template = fixture()
        with patch.object(Path, "mkdir", side_effect=OSError("read-only output")):
            element = find_image_in_memory(encoded(screen), encoded(template),
                                           debug="always", debug_dir="unused")
            self.assertIn("read-only output", element.diagnostic_error)
            screen, template = fixture(duplicate=True)
            with self.assertRaises(AmbiguousImageMatchError) as caught:
                find_image_in_memory(encoded(screen), encoded(template),
                                     debug="on_failure", debug_dir="unused")
            self.assertIn("read-only output", caught.exception.details["diagnostic_error"])


class FakeSwitch:
    def __init__(self, driver):
        self.driver = driver

    def context(self, context):
        self.driver.transitions.append(context)
        if context == "OCR" and self.driver.fail_restore:
            raise RuntimeError("restore failed")
        self.driver.current_context = context


class FakeDriver:
    def __init__(self, image, context="OCR", width=330, height=230):
        self.png = encoded(image)
        self.current_context = context
        self.window = {"width": width, "height": height}
        self.orientation = "LANDSCAPE"
        self.switch_to = FakeSwitch(self)
        self.transitions = []
        self.capture_count = 0
        self.fail_restore = False
        self.fail_capture = False
        self.change_geometry = False

    def get_window_size(self):
        return dict(self.window)

    def get_screenshot_as_png(self):
        self.capture_count += 1
        if self.fail_capture:
            raise RuntimeError("device disconnected")
        if self.change_geometry:
            self.orientation = "PORTRAIT"
        return self.png


class FakeLibrary:
    def __init__(self, driver):
        self.driver = driver

    def _current_application(self):
        return self.driver


class AppiumTests(unittest.TestCase):
    def scan(self, driver, template, coordinate_mode="screenshot", **kwargs):
        options = MatchOptions.parse(**kwargs)
        return execute_scan(lambda: (encoded(template), None),
                            lambda receive: capture_screen(FakeLibrary(driver), receive),
                            options, coordinate_mode=coordinate_mode)

    def test_one_memory_capture_restores_context_and_returns_element(self):
        screen, template = fixture()
        driver = FakeDriver(screen)
        element = self.scan(driver, template)
        self.assertEqual(driver.capture_count, 1)
        self.assertEqual(driver.current_context, "OCR")
        self.assertEqual(driver.transitions, ["NATIVE_APP", "OCR"])
        self.assertEqual(element.coordinate_mapping, "unverified")
        self.assertIsNone(element.window_rect)
        self.assertEqual(element.window_size, {"width": 330, "height": 230})

    def test_native_context_is_left_in_place(self):
        screen, template = fixture()
        driver = FakeDriver(screen, context="NATIVE_APP")
        self.scan(driver, template)
        self.assertEqual(driver.transitions, [])

    def test_explicit_identity_and_scaled_mapping(self):
        screen, template = fixture()
        element = self.scan(FakeDriver(screen), template, coordinate_mode="full_window")
        self.assertEqual(element.coordinate_mapping, "identity")
        element = self.scan(FakeDriver(screen, width=660, height=460), template,
                            coordinate_mode="full_window")
        self.assertEqual(element.coordinate_mapping, "scaled")
        self.assertEqual(element.window_rect, {"x": 162., "y": 126., "width": 96., "height": 64.})
        self.assertEqual(element.rect["x"], 81)
        with self.assertRaises(CoordinateMappingError):
            self.scan(FakeDriver(screen, width=500, height=230), template,
                      coordinate_mode="full_window")

    def test_capture_failure_and_geometry_change_restore_context(self):
        screen, template = fixture()
        for flag, exception in (("fail_capture", AppiumSessionError),
                                ("change_geometry", ScreenChangedError)):
            with self.subTest(flag=flag):
                driver = FakeDriver(screen)
                setattr(driver, flag, True)
                with self.assertRaises(exception):
                    self.scan(driver, template)
                self.assertEqual(driver.current_context, "OCR")

    def test_frozen_context_is_borrowed_and_released_by_its_owner(self):
        screen, template = fixture()
        driver = FakeDriver(screen)
        library = FakeLibrary(driver)
        with freeze_current_context(library):
            element = self.scan(driver, template)
            self.assertEqual(driver.current_context, "NATIVE_APP")
            self.assertEqual(driver.transitions, ["NATIVE_APP"])
        self.assertEqual(element.location, {"x": 81, "y": 63})
        self.assertEqual(driver.capture_count, 1)
        # The original OCR context is not recoverable; the owner leaves NATIVE_APP.
        self.assertEqual(driver.transitions, ["NATIVE_APP", "NATIVE_APP"])

    def test_restore_error_does_not_hide_primary_error(self):
        screen, template = fixture()
        driver = FakeDriver(screen)
        driver.fail_restore = True
        with self.assertRaises(ContextRestoreError):
            self.scan(driver, template)
        driver = FakeDriver(screen)
        driver.fail_restore = True
        driver.fail_capture = True
        with self.assertRaises(AppiumSessionError) as caught:
            self.scan(driver, template)
        self.assertEqual(caught.exception.details["context_restore_error"]["code"], "CONTEXT_RESTORE_ERROR")

    def test_robot_keyword_handles_alias_and_unicode_template_path(self):
        screen, template = fixture()
        driver = FakeDriver(screen)
        class BuiltinStub:
            def get_library_instance(self, name):
                if name != "Device":
                    raise RuntimeError("bad alias")
                return FakeLibrary(driver)
        with workdir() as directory:
            path = directory / "模板 图片.png"
            path.write_bytes(encoded(template))
            with patch("_opencv_vision.robot_library.BuiltIn", return_value=BuiltinStub()):
                element = OpenCVVision().find_image_element(path, appium_library="Device", threshold="0.8")
                self.assertEqual(element.location, {"x": 81, "y": 63})
                with self.assertRaises(AppiumSessionError):
                    OpenCVVision().find_image_element(path, appium_library="Missing")

    def test_capture_postcheck_error_can_export_original_frame_without_recapture(self):
        screen, template = fixture()
        driver = FakeDriver(screen)
        driver.change_geometry = True
        with workdir() as directory:
            with self.assertRaises(ScreenChangedError) as caught:
                execute_scan(lambda: (encoded(template), None),
                             lambda receive: capture_screen(FakeLibrary(driver), receive),
                             MatchOptions.parse(debug="on_failure"), debug_dir=directory)
            details = caught.exception.details
            self.assertEqual(Path(details["debug_paths"]["source"]).read_bytes(), driver.png)
            self.assertEqual(driver.capture_count, 1)
            self.assertEqual(driver.current_context, "OCR")


class RobotIntegrationTests(unittest.TestCase):
    def test_real_robot_runner_discovers_keyword_and_reads_element_properties(self):
        from robot import run
        from robot.libdocpkg import LibraryDocumentation

        specification = LibraryDocumentation(str(ROOT / "OpenCVVision.py"))
        self.assertEqual([item.name for item in specification.keywords], ["CV Find Image Element"])
        with workdir() as directory:
            console = io.StringIO()
            result = run(str(ROOT / "tests" / "robot_smoke.robot"),
                         outputdir=str(directory), stdout=console, stderr=console)
            self.assertEqual(result, 0, console.getvalue())

    def test_declared_types_stop_robot_from_passing_roi_as_text(self):
        from robot.libdocpkg import LibraryDocumentation
        from robot.running.arguments import ArgumentSpec
        from robot.running.arguments.argumentconverter import ArgumentConverter

        specification = LibraryDocumentation(str(ROOT / "OpenCVVision.py"))
        types = {arg.name: str(arg.type) for arg in specification.keywords[0].args}
        self.assertEqual(types["roi"], "tuple | list | None")
        self.assertEqual(types["threshold"], "float")
        spec = ArgumentSpec("CV Find Image Element",
                            positional_or_named=["template", "threshold", "roi"],
                            defaults={"threshold": 0.9, "roi": None},
                            types={name: types[name] for name in ("threshold", "roi")})
        convert = ArgumentConverter(spec, None)
        _, named = convert.convert(["<template>"], [("roi", ["800", "450", "800", "450"])])
        self.assertEqual(dict(named)["roi"], ["800", "450", "800", "450"])
        _, named = convert.convert(["<template>"], [("roi", "[800, 450, 800, 450]")])
        self.assertEqual(dict(named)["roi"], (800, 450, 800, 450))
        _, named = convert.convert(["<template>"], [("threshold", "0.8")])
        self.assertEqual(dict(named)["threshold"], 0.8)


if __name__ == "__main__":
    unittest.main()
