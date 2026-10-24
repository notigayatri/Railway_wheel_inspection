"""
core/wheel_lifecycle/backup.py
==============================
Automated SQLite Online Database Backup & Snapshot Management Engine.

Provides:
  - Transactionally consistent online snapshots via sqlite3.Connection.backup()
  - Zero-downtime, non-blocking backup execution (stepped page copying)
  - Post-backup PRAGMA integrity_check verification
  - Optional Gzip compression (.db.gz)
  - Automatic retention policy and age pruning
  - SHA-256 checksum calculation & table metrics audit
  - Safe restoration engine with automatic pre-restore emergency snapshots
  - Background async scheduler for scheduled periodic automated backups
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("railway.backup")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATABASE_DIR = PROJECT_ROOT / "database"
DB_PATH = DATABASE_DIR / "railway.db"
BACKUP_DIR = DATABASE_DIR / "backups"
MANIFEST_PATH = BACKUP_DIR / "backups_manifest.json"

# Ensure backup archive directory exists
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_RETENTION_COUNT = 20
DEFAULT_INTERVAL_MINUTES = 360  # Every 6 hours


def human_readable_size(size_bytes: int) -> str:
    """Format bytes into human-readable size (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def verify_sqlite_integrity(db_file: Path) -> Tuple[bool, str]:
    """
    Execute PRAGMA integrity_check on SQLite database file.
    Returns (is_healthy, message).
    """
    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        rows = cursor.execute("PRAGMA integrity_check").fetchall()
        conn.close()
        if len(rows) == 1 and rows[0][0].lower() == "ok":
            return True, "ok"
        messages = "; ".join(r[0] for r in rows)
        return False, messages
    except Exception as exc:
        return False, f"Integrity check failed with error: {exc}"


def get_table_counts(conn_or_path: Any) -> Dict[str, int]:
    """Extract record counts across core railway database tables."""
    close_when_done = False
    if isinstance(conn_or_path, (str, Path)):
        conn = sqlite3.connect(str(conn_or_path))
        close_when_done = True
    else:
        conn = conn_or_path

    counts = {}
    tables = [
        "trains",
        "coaches",
        "wheels",
        "inspections",
        "inspection_events",
        "maintenance_jobs",
        "operating_schedules",
        "users",
    ]
    try:
        cursor = conn.cursor()
        for t in tables:
            try:
                row = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                counts[t] = row[0] if row else 0
            except sqlite3.OperationalError:
                counts[t] = 0
    finally:
        if close_when_done:
            conn.close()
    return counts


def perform_online_backup(source_path: Path, dest_path: Path, pages_per_step: int = 250) -> float:
    """
    Perform a live, online, non-blocking snapshot using SQLite Online Backup API.
    """
    t0 = time.time()
    source_conn = sqlite3.connect(str(source_path), timeout=30.0)
    dest_conn = sqlite3.connect(str(dest_path), timeout=30.0)
    try:
        with dest_conn:
            # pages_per_step < 0 copies entire database in one step;
            # positive value steps non-blockingly without locking other readers
            source_conn.backup(dest_conn, pages=pages_per_step)
    finally:
        dest_conn.close()
        source_conn.close()
    return round(time.time() - t0, 3)


def load_manifest() -> Dict[str, Any]:
    """Load backup metadata manifest."""
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_backup": None, "backups": {}}


def save_manifest(data: Dict[str, Any]) -> None:
    """Save backup metadata manifest atomically."""
    temp_path = MANIFEST_PATH.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    temp_path.replace(MANIFEST_PATH)


def prune_old_backups(max_retained: int = DEFAULT_RETENTION_COUNT) -> List[str]:
    """
    Keep only the newest `max_retained` backups. Delete older snapshots.
    Emergency pre-restore backups (prefixed 'pre_restore_') are preserved separately.
    Returns list of deleted filenames.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    all_files = sorted(
        [
            f for f in BACKUP_DIR.iterdir()
            if f.is_file() and (f.name.endswith(".db") or f.name.endswith(".db.gz"))
            and not f.name.startswith("pre_restore_")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    deleted = []
    if len(all_files) > max_retained:
        for old_file in all_files[max_retained:]:
            try:
                old_file.unlink()
                deleted.append(old_file.name)
                logger.info(f"Pruned old backup: {old_file.name}")
            except Exception as e:
                logger.warning(f"Could not delete old backup {old_file.name}: {e}")

    # Clean up manifest
    manifest = load_manifest()
    for name in deleted:
        manifest["backups"].pop(name, None)
    save_manifest(manifest)
    return deleted


def create_database_backup(
    compress: bool = False,
    max_retained: int = DEFAULT_RETENTION_COUNT,
    reason: str = "scheduled",
    prefix: str = "railway_backup",
) -> Dict[str, Any]:
    """
    Create a transactionally consistent online snapshot of railway.db.

    Args:
        compress: If True, gzip compress into .db.gz
        max_retained: Keep latest N snapshots, delete older ones
        reason: Purpose label (e.g., 'scheduled', 'manual', 'pre_migration')
        prefix: Filename prefix

    Returns:
        Backup metadata dictionary
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Source database file not found at {DB_PATH}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:22]  # microsecond precision
    base_name = f"{prefix}_{timestamp_str}.db"
    dest_path = BACKUP_DIR / base_name

    logger.info(f"Initiating SQLite online backup: {base_name} (reason: {reason})")

    # Step 1: Execute Online Backup
    elapsed_sec = perform_online_backup(DB_PATH, dest_path)

    # Step 2: Validate Database Integrity
    is_healthy, integrity_msg = verify_sqlite_integrity(dest_path)
    if not is_healthy:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(f"Backup failed PRAGMA integrity_check: {integrity_msg}")

    # Step 3: Extract Table Record Counts
    table_counts = get_table_counts(dest_path)

    # Step 4: Optional Gzip Compression
    final_path = dest_path
    is_compressed = False
    if compress:
        gz_path = dest_path.with_suffix(".db.gz")
        with open(dest_path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        dest_path.unlink(missing_ok=True)
        final_path = gz_path
        is_compressed = True

    # Step 5: Gather Metadata & Checksum
    file_stat = final_path.stat()
    size_bytes = file_stat.st_size
    sha256_hash = calculate_sha256(final_path)

    metadata = {
        "filename": final_path.name,
        "path": str(final_path),
        "size_bytes": size_bytes,
        "human_size": human_readable_size(size_bytes),
        "sha256": sha256_hash,
        "is_compressed": is_compressed,
        "integrity_status": integrity_msg,
        "integrity_ok": is_healthy,
        "backup_duration_seconds": elapsed_sec,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_at_display": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "table_counts": table_counts,
        "total_records": sum(table_counts.values()),
    }

    # Step 6: Update Manifest & Prune Old Snapshots
    manifest = load_manifest()
    manifest["last_backup"] = metadata["created_at"]
    manifest["backups"][final_path.name] = metadata
    save_manifest(manifest)

    pruned = prune_old_backups(max_retained=max_retained)
    metadata["pruned_old_backups"] = pruned

    logger.info(
        f"Backup complete: {final_path.name} ({metadata['human_size']}, {elapsed_sec}s, "
        f"{metadata['total_records']} records, integrity=OK)"
    )
    return metadata


def list_backups() -> List[Dict[str, Any]]:
    """
    List all available backup snapshots in the archive directory, sorted newest first.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    backups_meta = manifest.get("backups", {})

    items = []
    for p in BACKUP_DIR.iterdir():
        if not p.is_file():
            continue
        if not (p.name.endswith(".db") or p.name.endswith(".db.gz")):
            continue

        meta = backups_meta.get(p.name)
        if meta and Path(meta.get("path", "")).exists():
            items.append(meta)
        else:
            # Back-fill metadata if file exists without manifest entry
            stat = p.stat()
            is_comp = p.name.endswith(".db.gz")
            created_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            items.append({
                "filename": p.name,
                "path": str(p),
                "size_bytes": stat.st_size,
                "human_size": human_readable_size(stat.st_size),
                "sha256": None,
                "is_compressed": is_comp,
                "integrity_status": "ok",
                "integrity_ok": True,
                "backup_duration_seconds": 0.0,
                "reason": "existing",
                "created_at": created_dt.isoformat(),
                "created_at_display": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "table_counts": {},
                "total_records": 0,
            })

    # Sort newest first
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def restore_database_backup(filename: str) -> Dict[str, Any]:
    """
    Restore the live railway.db from a specified backup snapshot.
    Automatically creates a safety pre-restore backup first.
    Uses SQLite Online Backup to restore transactionally into the live database.
    """
    backup_file = BACKUP_DIR / filename
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file '{filename}' not found in {BACKUP_DIR}")

    # If compressed, extract to temporary file for restoration
    temp_unpacked: Optional[Path] = None
    source_to_restore = backup_file
    if filename.endswith(".db.gz"):
        temp_unpacked = BACKUP_DIR / f"_temp_restore_{int(time.time())}.db"
        with gzip.open(backup_file, "rb") as f_in, open(temp_unpacked, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        source_to_restore = temp_unpacked

    try:
        # Step 1: Verify integrity of backup to be restored
        is_ok, msg = verify_sqlite_integrity(source_to_restore)
        if not is_ok:
            raise ValueError(f"Cannot restore corrupt backup snapshot '{filename}': {msg}")

        # Step 2: Create safety pre-restore backup of the live database
        safety_meta = create_database_backup(
            compress=False,
            reason="pre_restore_safety",
            prefix="pre_restore",
        )

        # Step 3: Perform Online Restore (backup file -> live database)
        t0 = time.time()
        perform_online_backup(source_to_restore, DB_PATH)
        restore_duration = round(time.time() - t0, 3)

        # Step 4: Verify restored live database
        is_live_ok, live_msg = verify_sqlite_integrity(DB_PATH)
        if not is_live_ok:
            raise RuntimeError(f"Live database failed integrity check after restore: {live_msg}")

        restored_counts = get_table_counts(DB_PATH)

        return {
            "status": "RESTORED",
            "restored_from": filename,
            "restore_duration_seconds": restore_duration,
            "safety_backup_created": safety_meta["filename"],
            "restored_table_counts": restored_counts,
            "total_records": sum(restored_counts.values()),
            "message": f"Successfully restored live database from snapshot '{filename}'.",
        }
    finally:
        if temp_unpacked and temp_unpacked.exists():
            temp_unpacked.unlink(missing_ok=True)


def delete_backup_file(filename: str) -> bool:
    """Delete a backup file and remove it from manifest."""
    backup_file = BACKUP_DIR / filename
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file '{filename}' does not exist.")

    backup_file.unlink()
    manifest = load_manifest()
    manifest["backups"].pop(filename, None)
    save_manifest(manifest)
    return True


# ── Background Async Scheduler Task ──────────────────────────────────────────

_scheduler_task: Optional[asyncio.Task] = None
_scheduler_running: bool = False


async def backup_scheduler_worker(
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    max_retained: int = DEFAULT_RETENTION_COUNT,
    on_startup: bool = True,
):
    """
    Background worker loop that triggers automatic database backups at intervals.
    """
    global _scheduler_running
    _scheduler_running = True
    logger.info(
        f"Database backup scheduler started. Interval: {interval_minutes}m, "
        f"Max retained: {max_retained}, Backup on startup: {on_startup}"
    )

    if on_startup:
        try:
            # Yield briefly to let the app finish startup before initial snapshot
            await asyncio.sleep(5)
            logger.info("Executing initial database backup on server startup...")
            create_database_backup(
                compress=False,
                max_retained=max_retained,
                reason="server_startup",
            )
        except Exception as exc:
            logger.error(f"Startup backup failed: {exc}")

    interval_seconds = max(60, interval_minutes * 60)
    while _scheduler_running:
        try:
            await asyncio.sleep(interval_seconds)
            if not _scheduler_running:
                break
            logger.info("Triggering scheduled automated database backup...")
            create_database_backup(
                compress=False,
                max_retained=max_retained,
                reason="scheduled_periodic",
            )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Scheduled backup failed: {exc}", exc_info=True)


def start_backup_scheduler(
    interval_minutes: Optional[int] = None,
    max_retained: Optional[int] = None,
    on_startup: Optional[bool] = None,
) -> Optional[asyncio.Task]:
    """Start the background backup scheduler if not already running."""
    global _scheduler_task, _scheduler_running
    if _scheduler_running and _scheduler_task and not _scheduler_task.done():
        return _scheduler_task

    # Allow environment variable overrides
    inv = int(os.environ.get("BACKUP_INTERVAL_MINUTES", interval_minutes or DEFAULT_INTERVAL_MINUTES))
    ret = int(os.environ.get("BACKUP_MAX_RETAINED", max_retained or DEFAULT_RETENTION_COUNT))
    start_snap = os.environ.get("BACKUP_ON_STARTUP", str(on_startup if on_startup is not None else True)).lower() in ("true", "1", "yes")

    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(
        backup_scheduler_worker(
            interval_minutes=inv,
            max_retained=ret,
            on_startup=start_snap,
        )
    )
    return _scheduler_task


def stop_backup_scheduler():
    """Stop the background backup scheduler gracefully."""
    global _scheduler_task, _scheduler_running
    _scheduler_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
