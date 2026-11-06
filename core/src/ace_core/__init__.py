"""ACE core service.

Voice pipeline, brain, verification council, skills and storage live in this package
(ACE_MASTER_PLAN.md §5 Architecture, §17 Repository layout).
"""

from ace_core.app.version import __version__

__all__ = ["__version__", "main"]


def main() -> int:
    """Console-script entry point (``ace-core``)."""
    from ace_core.app.main import main as run  # imported lazily to keep ``import ace_core`` light

    return run()
