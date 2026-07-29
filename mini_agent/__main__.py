"""Module entry point for ``python -m mini_agent``."""

from __future__ import annotations

import argparse
import json

from .bootstrap import initialize_foundation
from .config import Config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m mini_agent")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate AGENT_* configuration and initialize the database",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.check:
        raise SystemExit("The interactive CLI is not available yet. Run with --check.")

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

