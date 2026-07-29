"""Entry point for the frozen executable.

PyInstaller analyses its entry script as a top-level module, so the relative
imports inside `timelapser/__main__.py` cannot be resolved from there. Importing
the package absolutely gives the dependency graph a real package to follow.
"""

import sys

from timelapser.__main__ import main
from timelapser.fonts import load_bundled_fonts

if __name__ == "__main__":
    load_bundled_fonts()
    sys.exit(main())
