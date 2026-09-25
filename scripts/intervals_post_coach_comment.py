#!/usr/bin/env python3
"""Post a coach comment on an Intervals.icu activity (signed — Ole by default)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import COACH_ACTIVITY_SIGNOFF, format_coach_activity_message, post_activity_message  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Post coach comment on Intervals activity")
    parser.add_argument(
        "--activity",
        required=True,
        help="Activity id from Intervals (e.g. i190349972)",
    )
    parser.add_argument("-m", "--message", help="Comment text (markdown ok)")
    parser.add_argument(
        "--file",
        type=Path,
        help="Read comment body from file (UTF-8)",
    )
    parser.add_argument(
        "--no-sign",
        action="store_true",
        help=f"Do not append — {COACH_ACTIVITY_SIGNOFF}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print final message only",
    )
    args = parser.parse_args()

    if args.file and args.message:
        print("Use either --message or --file, not both.", file=sys.stderr)
        return 1
    if args.file:
        body = args.file.read_text(encoding="utf-8")
    elif args.message:
        body = args.message
    else:
        print("Provide --message or --file.", file=sys.stderr)
        return 1

    final = (
        format_coach_activity_message(body)
        if not args.no_sign
        else body.strip()
    )
    if args.dry_run:
        print(final)
        return 0

    result = post_activity_message(args.activity, body, sign=not args.no_sign)
    print(f"Posted to {args.activity} (signed: {not args.no_sign})")
    if isinstance(result, dict) and result.get("id"):
        print(f"message id: {result['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
