"""ACE core service.

Voice pipeline, brain, verification council, skills and storage live in this package
(ACE_MASTER_PLAN.md §5 Architecture, §17 Repository layout). The real service arrives in S01.
"""

from importlib.metadata import version

__all__ = ["__version__", "main"]

__version__ = version("ace-core")


def main() -> None:
    """Console-script entry point. Placeholder until stage S01 builds the service."""
    raise SystemExit("ace-core is not implemented yet (see stage S01 in ACE_MASTER_PLAN.md).")
