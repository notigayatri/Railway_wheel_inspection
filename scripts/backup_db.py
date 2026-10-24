"""
scripts/backup_db.py
====================
Standalone CLI / Cron Utility for Railway Database Snapshots & Restoration.

Usage:
    # 1. Create immediate online backup snapshot:
    python scripts/backup_db.py

    # 2. Create gzip-compressed backup snapshot:
    python scripts/backup_db.py --compress

    # 3. Specify custom retention limit:
    python scripts/backup_db.py --keep 30

    # 4. List all existing backups:
    python scripts/backup_db.py --list

    # 5. Restore from a specific backup snapshot:
    python scripts/backup_db.py --restore railway_backup_20261024_025000.db
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.wheel_lifecycle.backup import (
    create_database_backup,
    list_backups,
    restore_database_backup,
    BACKUP_DIR,
    DB_PATH,
)

def main():
    parser = argparse.ArgumentParser(
        description="Railway Database Online Backup & Snapshot Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress the backup into a .db.gz archive",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=20,
        help="Number of snapshots to retain before pruning oldest (default: 20)",
    )
    parser.add_argument(
        "--reason",
        type=str,
        default="cli_manual",
        help="Audit reason tag (default: 'cli_manual')",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all existing snapshots in the archive directory",
    )
    parser.add_argument(
        "--restore",
        type=str,
        default=None,
        metavar="FILENAME",
        help="Restore live database from specified snapshot file",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("  Railway Wheel Health Assessment — Database Backup Utility")
    print("=" * 65)
    print(f"  Source Database : {DB_PATH}")
    print(f"  Backup Archive  : {BACKUP_DIR}")
    print("-" * 65)

    if args.list:
        backups = list_backups()
        if not backups:
            print("  No database snapshots found in archive.")
            return 0
        print(f"  Found {len(backups)} snapshot(s):\n")
        print(f"  {'Filename':<35} {'Size':<10} {'Created':<20} {'Integrity':<8}")
        print("  " + "-" * 75)
        for b in backups:
            print(f"  {b['filename']:<35} {b['human_size']:<10} {b.get('created_at_display', '-'):<20} {b.get('integrity_status', 'ok'):<8}")
        print("=" * 65)
        return 0

    if args.restore:
        print(f"  Restoring database from snapshot: {args.restore}")
        try:
            res = restore_database_backup(args.restore)
            print(f"\n  [SUCCESS] {res['message']}")
            print(f"  Duration: {res['restore_duration_seconds']}s")
            print(f"  Safety Snapshot Created: {res['safety_backup_created']}")
            print(f"  Total Records Restored: {res['total_records']}")
            return 0
        except Exception as exc:
            print(f"\n  [ERROR] Restoration failed: {exc}")
            return 1

    # Default action: Create backup
    print(f"  Creating online backup (compress={args.compress}, keep={args.keep})...")
    try:
        meta = create_database_backup(
            compress=args.compress,
            max_retained=args.keep,
            reason=args.reason,
        )
        print("\n  [SUCCESS] Backup completed successfully!")
        print(f"  Snapshot File : {meta['filename']}")
        print(f"  Archive Path  : {meta['path']}")
        print(f"  File Size     : {meta['human_size']} ({meta['size_bytes']:,} bytes)")
        print(f"  Duration      : {meta['backup_duration_seconds']}s")
        print(f"  SHA-256 Hash  : {meta['sha256']}")
        print(f"  Total Records : {meta['total_records']:,}")
        print(f"  Integrity     : {meta['integrity_status']}")
        if meta.get("pruned_old_backups"):
            print(f"  Pruned Old    : {', '.join(meta['pruned_old_backups'])}")
        print("=" * 65)
        return 0
    except Exception as exc:
        print(f"\n  [ERROR] Backup failed: {exc}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
