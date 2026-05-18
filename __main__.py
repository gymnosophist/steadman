"""
__main__.py — Entry point for `python -m steadman`.

This module is executed when the user runs:
    python -m steadman [options]

or (after installation via pip install):
    steadman [options]

Keeping this file minimal — just logging setup and CLI dispatch —
means it's easy to test cli.py independently by calling run() directly.
"""

import logging
import sys

from steadman.cli import build_parser, run


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging based on verbosity flag.
    # In normal use, we want clean output — only warnings and errors.
    # With --verbose, show debug messages from all our modules.
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )

    run(args)


if __name__ == "__main__":
    main()
