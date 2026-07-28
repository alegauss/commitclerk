"""`python -m commitclerk`, the in-repo equivalent of the installed `clerk`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
