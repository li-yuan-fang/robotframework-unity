"""Robot-only fixture: simulates screenshot/session APIs without a device."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot.api.deco import keyword
from test_vision import FakeDriver, FakeLibrary, encoded, fixture


class FixtureAppium(FakeLibrary):
    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_AUTO_KEYWORDS = False

    def __init__(self):
        screen, self.template = fixture()
        super().__init__(FakeDriver(screen))

    @keyword
    def get_fixture_template(self):
        return encoded(self.template)

    @keyword
    def get_fixture_capture_count(self):
        return self.driver.capture_count

    @keyword
    def use_duplicate_targets(self):
        screen, _ = fixture(duplicate=True)
        self.driver.png = encoded(screen)
