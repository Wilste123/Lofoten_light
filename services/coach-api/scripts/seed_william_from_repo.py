#!/usr/bin/env python3
"""CLI: seed William from repo athlete docs into coach-web.

Usage (from repo root or coach-api):

  python3 services/coach-api/scripts/seed_william_from_repo.py
  python3 services/coach-api/scripts/seed_william_from_repo.py --dry-run
  python3 services/coach-api/seed_from_repo.py --help

See docs/product/import-from-repo.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1]
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from seed_from_repo import main

if __name__ == "__main__":
    raise SystemExit(main())
