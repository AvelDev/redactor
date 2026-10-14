"""Report missing, empty or inconsistent translations. Exit code 1 on errors."""

import sys

from redactor.i18n.check import main

if __name__ == "__main__":
    sys.exit(main())
