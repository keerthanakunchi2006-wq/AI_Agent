"""CLI: generate dataset CSVs and seed the database.

Usage:
    python -m scripts.seed_db            # generate + seed (idempotent)
    python -m scripts.seed_db --force     # wipe + reseed
    python -m scripts.seed_db --gen-only  # only write CSVs
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# allow running as `python -m scripts.seed_db` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed supply-chain database")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--force", action="store_true", help="wipe and reseed")
    parser.add_argument("--gen-only", action="store_true", help="only generate CSVs")
    args = parser.parse_args()

    from app.core.logging import configure_logging
    configure_logging()

    if args.gen_only:
        from scripts.generate_dataset import generate, write_csvs, validate_tables, total_records
        tables = generate()
        issues = validate_tables(tables)
        write_csvs(tables, args.data_dir)
        print(f"Generated {total_records(tables)} records into {args.data_dir}")
        for i in issues:
            print("  note:", i)
        return

    from app.seed import seed_database
    counts = seed_database(data_dir=args.data_dir, force=args.force)
    print("Seeded database:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print("Demo users: admin/admin123, approver/approver123, analyst/analyst123")


if __name__ == "__main__":
    main()
