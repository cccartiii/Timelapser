"""Top-level launcher for the frozen .exe and for `python run_app.py`.

PyInstaller runs the entry script as a bare module (no package parent), so
relative imports inside `timelapser/__main__.py` blow up. Launching through this
file keeps every import absolute and package-scoped.
"""

from __future__ import annotations

import sys

from timelapser.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
