"""
tests/test_database_backup.py
=============================
Test suite for SQLite Online Database Backup, Scheduled Archiving, and Restoration.
"""

import io
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

def get_auth_token(username: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return r.json()["access_token"]


def test_backup_system():
    print("\n" + "=" * 65)
    print("  TESTING AUTOMATED DATABASE BACKUP SYSTEM")
    print("=" * 65)

    # 1. Acquire tokens for roles
    admin_token = get_auth_token("admin", "admin123")
    super_token = get_auth_token("supervisor", "super123")
    oper_token = get_auth_token("operator", "oper123")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    super_headers = {"Authorization": f"Bearer {super_token}"}
    oper_headers = {"Authorization": f"Bearer {oper_token}"}

    # 2. Check Backup Status
    print("\n1. Testing GET /api/admin/backups/status...")
    r_status = requests.get(f"{BASE_URL}/api/admin/backups/status", headers=oper_headers)
    assert r_status.status_code == 200, f"Status check failed: {r_status.text}"
    st = r_status.json()
    print(f"   [PASS] DB Size: {st['database_human_size']} | Snapshots in archive: {st['total_snapshots']} | Integrity: {st['live_integrity']}")
    assert st["live_integrity"] == "ok"
    assert st["scheduler_enabled"] is True

    # 3. List Existing Backups
    print("\n2. Testing GET /api/admin/backups...")
    r_list = requests.get(f"{BASE_URL}/api/admin/backups", headers=oper_headers)
    assert r_list.status_code == 200, f"List backups failed: {r_list.text}"
    backups = r_list.json()
    print(f"   [PASS] Retrieved {len(backups)} snapshot(s).")
    assert isinstance(backups, list)

    # 4. Trigger Uncompressed Backup (Supervisor role)
    print("\n3. Testing POST /api/admin/backups (Supervisor role)...")
    t0 = time.time()
    r_snap = requests.post(f"{BASE_URL}/api/admin/backups?compress=false&reason=test_uncompressed", headers=super_headers)
    dur = time.time() - t0
    assert r_snap.status_code == 201, f"Backup creation failed: {r_snap.text}"
    snap_data = r_snap.json()
    b1 = snap_data["backup"]
    print(f"   [PASS] Created snapshot: {b1['filename']} ({b1['human_size']}, {b1['backup_duration_seconds']}s, {dur:.3f}s total)")
    assert b1["integrity_ok"] is True
    assert b1["is_compressed"] is False
    assert b1["filename"].endswith(".db")

    # 5. Trigger Compressed Backup (Admin role)
    print("\n4. Testing POST /api/admin/backups?compress=true (Admin role)...")
    r_gz = requests.post(f"{BASE_URL}/api/admin/backups?compress=true&reason=test_compressed", headers=admin_headers)
    assert r_gz.status_code == 201, f"Compressed backup creation failed: {r_gz.text}"
    gz_data = r_gz.json()["backup"]
    print(f"   [PASS] Created compressed snapshot: {gz_data['filename']} ({gz_data['human_size']})")
    assert gz_data["is_compressed"] is True
    assert gz_data["filename"].endswith(".db.gz")

    # 6. Verify RBAC Protection: Operator cannot trigger backup
    print("\n5. Testing RBAC: Operator forbidden from creating backup...")
    r_oper_block = requests.post(f"{BASE_URL}/api/admin/backups", headers=oper_headers)
    assert r_oper_block.status_code == 403, f"Expected 403 Forbidden, got {r_oper_block.status_code}"
    print("   [PASS] Operator correctly received 403 Forbidden.")

    # 7. Test Backup Download Endpoint
    print("\n6. Testing GET /api/admin/backups/{filename}/download...")
    r_down = requests.get(f"{BASE_URL}/api/admin/backups/{b1['filename']}/download", headers=super_headers)
    assert r_down.status_code == 200, f"Download failed: {r_down.status_code}"
    assert len(r_down.content) == b1["size_bytes"]
    print(f"   [PASS] Downloaded {len(r_down.content)} bytes of SQLite binary successfully.")

    # 8. Test Online Database Restoration
    print("\n7. Testing POST /api/admin/backups/{filename}/restore (Admin role)...")
    # Operator blocked from restore
    r_block_rest = requests.post(f"{BASE_URL}/api/admin/backups/{b1['filename']}/restore", headers=oper_headers)
    assert r_block_rest.status_code == 403
    print("   [PASS] Operator correctly forbidden from restoring database.")

    # Admin performs restore
    r_rest = requests.post(f"{BASE_URL}/api/admin/backups/{b1['filename']}/restore", headers=admin_headers)
    assert r_rest.status_code == 200, f"Restore failed: {r_rest.text}"
    rest_data = r_rest.json()
    print(f"   [PASS] Live DB Restored: {rest_data['message']}")
    print(f"          Safety snapshot: {rest_data['safety_backup_created']}")
    print(f"          Records verified: {rest_data['total_records']}")
    assert rest_data["status"] == "RESTORED"

    # 9. Test Backup Deletion
    print("\n8. Testing DELETE /api/admin/backups/{filename}...")
    # Operator blocked
    r_del_block = requests.delete(f"{BASE_URL}/api/admin/backups/{gz_data['filename']}", headers=oper_headers)
    assert r_del_block.status_code == 403
    # Admin deletes
    r_del = requests.delete(f"{BASE_URL}/api/admin/backups/{gz_data['filename']}", headers=admin_headers)
    assert r_del.status_code == 200, f"Delete failed: {r_del.text}"
    print(f"   [PASS] Deleted snapshot: {gz_data['filename']}")

    print("\n" + "=" * 65)
    print("  ALL DATABASE BACKUP TESTS PASSED SUCCESSFULLY!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    test_backup_system()
