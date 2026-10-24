"""
routers/admin_backups.py
========================
REST API Router for Automated Database Backups & Archive Management.

Endpoints:
  GET    /api/admin/backups           List all available backup snapshots & metadata
  GET    /api/admin/backups/status    Overview stats (last backup, archive size, scheduler status)
  POST   /api/admin/backups           Create an immediate online backup snapshot
  GET    /api/admin/backups/{fn}/download  Download a snapshot file (.db or .db.gz)
  POST   /api/admin/backups/{fn}/restore   Restore live database from a snapshot (Admin only)
  DELETE /api/admin/backups/{fn}           Delete a snapshot from archive (Admin only)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.wheel_lifecycle.auth import (
    ROLE_ADMIN,
    ROLE_MAINTENANCE_SUPERVISOR,
    ROLE_OPERATOR,
    require_role,
)
from core.wheel_lifecycle.backup import (
    BACKUP_DIR,
    DB_PATH,
    create_database_backup,
    delete_backup_file,
    human_readable_size,
    list_backups,
    load_manifest,
    restore_database_backup,
    verify_sqlite_integrity,
)

router = APIRouter(prefix="/api/admin/backups", tags=["Database Backups & Maintenance"])


class BackupSnapshotResponse(BaseModel):
    filename: str
    size_bytes: int
    human_size: str
    created_at: str
    created_at_display: Optional[str]
    integrity_status: str
    integrity_ok: bool
    is_compressed: bool
    reason: Optional[str]
    total_records: int
    sha256: Optional[str]


class BackupStatusResponse(BaseModel):
    database_file: str
    database_size_bytes: int
    database_human_size: str
    live_integrity: str
    total_snapshots: int
    total_archive_size_bytes: int
    total_archive_human_size: str
    last_backup_time: Optional[str]
    backup_directory: str
    scheduler_enabled: bool


class CreateBackupRequest(BaseModel):
    compress: bool = Field(False, description="Whether to compress the snapshot with gzip (.db.gz)")
    max_retained: int = Field(20, ge=1, le=100, description="Maximum snapshots to retain")
    reason: str = Field("manual_admin_request", description="Audit reason for backup")


@router.get(
    "",
    response_model=List[BackupSnapshotResponse],
    summary="List all database backup snapshots",
    description="Returns metadata for all available SQLite snapshots in the archive directory, sorted newest-first.",
)
def get_backups(
    current_user: Dict[str, Any] = Depends(require_role(ROLE_OPERATOR)),
):
    items = list_backups()
    return items


@router.get(
    "/status",
    response_model=BackupStatusResponse,
    summary="Get database backup overview & archive storage metrics",
)
def get_backup_status(
    current_user: Dict[str, Any] = Depends(require_role(ROLE_OPERATOR)),
):
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    is_ok, live_msg = verify_sqlite_integrity(DB_PATH) if DB_PATH.exists() else (False, "missing")

    all_backups = list_backups()
    total_archive_bytes = sum(b.get("size_bytes", 0) for b in all_backups)
    manifest = load_manifest()

    return BackupStatusResponse(
        database_file=str(DB_PATH),
        database_size_bytes=db_size,
        database_human_size=human_readable_size(db_size),
        live_integrity=live_msg,
        total_snapshots=len(all_backups),
        total_archive_size_bytes=total_archive_bytes,
        total_archive_human_size=human_readable_size(total_archive_bytes),
        last_backup_time=manifest.get("last_backup"),
        backup_directory=str(BACKUP_DIR),
        scheduler_enabled=True,
    )


@router.post(
    "",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Trigger an immediate online SQLite database backup",
    description="Executes a live, lock-free SQLite online backup snapshot to database/backups/. Requires MAINTENANCE_SUPERVISOR or ADMIN.",
)
def trigger_backup(
    compress: bool = Query(False, description="Compress snapshot to .db.gz"),
    max_retained: int = Query(20, ge=1, le=100, description="Max snapshots to retain"),
    reason: str = Query("manual_api_trigger", description="Audit note"),
    current_user: Dict[str, Any] = Depends(require_role(ROLE_MAINTENANCE_SUPERVISOR)),
):
    try:
        audit_reason = f"{reason} by {current_user.get('username', 'user')}"
        meta = create_database_backup(
            compress=compress,
            max_retained=max_retained,
            reason=audit_reason,
        )
        return {
            "status": "SUCCESS",
            "message": f"Successfully created online database snapshot '{meta['filename']}'.",
            "backup": meta,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup operation failed: {exc}",
        )


@router.get(
    "/{filename}/download",
    summary="Download a database backup snapshot",
    description="Streams the specified .db or .db.gz backup file for download.",
)
def download_backup(
    filename: str,
    current_user: Dict[str, Any] = Depends(require_role(ROLE_MAINTENANCE_SUPERVISOR)),
):
    safe_name = os.path.basename(filename)
    file_path = BACKUP_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup file '{safe_name}' not found.",
        )

    media_type = "application/gzip" if safe_name.endswith(".gz") else "application/x-sqlite3"
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type=media_type,
    )


@router.post(
    "/{filename}/restore",
    summary="Restore live database from a backup snapshot (ADMIN only)",
    description="Restores railway.db from the specified snapshot. Automatically takes a pre-restore safety backup first.",
)
def restore_backup(
    filename: str,
    current_user: Dict[str, Any] = Depends(require_role(ROLE_ADMIN)),
):
    safe_name = os.path.basename(filename)
    try:
        result = restore_database_backup(safe_name)
        return result
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup snapshot '{safe_name}' not found.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database restoration failed: {exc}",
        )


@router.delete(
    "/{filename}",
    summary="Delete a backup snapshot from the archive (ADMIN only)",
)
def delete_backup(
    filename: str,
    current_user: Dict[str, Any] = Depends(require_role(ROLE_ADMIN)),
):
    safe_name = os.path.basename(filename)
    try:
        delete_backup_file(safe_name)
        return {"status": "DELETED", "filename": safe_name, "message": "Backup snapshot deleted."}
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup file '{safe_name}' not found.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete backup snapshot: {exc}",
        )
