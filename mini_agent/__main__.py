"""Module entry point for ``python -m mini_agent``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .bootstrap import initialize_foundation
from .cli import main as cli_main
from .config import Config


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mini-agent")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate AGENT_* configuration and initialize the database",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--check" not in arguments:
        return cli_main(arguments)
    _parse_args(arguments)

    try:
        config = Config.from_env()
        database = initialize_foundation(config)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Configuration check failed: {exc}") from None

    summary = config.safe_summary()
    summary["database_initialized"] = database.is_initialized()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
