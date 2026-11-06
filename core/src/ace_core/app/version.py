"""Installed package version. Single source of truth: ``core/pyproject.toml``."""

from importlib.metadata import version

__version__ = version("ace-core")
