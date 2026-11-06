"""The package installs, imports and exposes its entry points."""

import ace_core
from ace_core.app import main as app_main


def test_package_exposes_a_version() -> None:
    assert ace_core.__version__


def test_console_entry_points_exist() -> None:
    assert callable(ace_core.main)
    assert callable(app_main.main)
