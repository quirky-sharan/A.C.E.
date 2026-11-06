"""S00 placeholder tests: the package installs, imports and exposes its entry point."""

import pytest

import ace_core


def test_package_exposes_a_version() -> None:
    assert ace_core.__version__


def test_entry_point_is_a_placeholder_until_s01() -> None:
    with pytest.raises(SystemExit):
        ace_core.main()
