"""Enables `python -m scigantic_chembl`, same commands as the `scigantic-chembl` console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
