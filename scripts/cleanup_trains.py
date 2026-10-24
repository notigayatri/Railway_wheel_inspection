import sqlite3
from datetime import datetime, timedelta

def cleanup():
    conn = sqlite3.connect('database/railway.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    now_iso = datetime.now().isoformat(timespec="seconds")
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Identify wheels belonging to trains > 5
    cursor.execute("SELECT asset_id FROM wheels WHERE train_id > 5 OR coach_id IN (SELECT CAST(id AS TEXT) FROM coaches WHERE train_id > 5)")
    to_delete_wheels = [row[0] for row in cursor.fetchall()]

    for wid in to_delete_wheels:
        cursor.execute("DELETE FROM maintenance_jobs WHERE wheel_asset_id=?", (wid,))
        cursor.execute("DELETE FROM inspection_events WHERE asset_id=?", (wid,))
        cursor.execute("DELETE FROM inspections WHERE asset_id=?", (wid,))
        cursor.execute("DELETE FROM wheels WHERE asset_id=?", (wid,))

    # 2. Delete remaining records for trains > 5
    cursor.execute("DELETE FROM maintenance_jobs WHERE train_id > 5")
    cursor.execute("DELETE FROM inspection_events WHERE train_id > 5")
    cursor.execute("DELETE FROM operating_schedules WHERE train_id > 5")
    cursor.execute("DELETE FROM coaches WHERE train_id > 5")
    cursor.execute("DELETE FROM trains WHERE id > 5")

    # 3. Clean up and polish Trains 1 to 5
    # Train 1: T001-TEST (Express Test Train) - keep as is
    cursor.execute("UPDATE trains SET train_type='Superfast Express', operational_status='Active', last_updated=? WHERE id=1", (now_iso,))

    # Train 2: TR-2048 - Vande Bharat Express
    cursor.execute("""
        UPDATE trains
        SET train_number='TR-2048', train_name='Vande Bharat Express', train_type='Superfast Express', operational_status='Active', last_updated=?
        WHERE id=2
    """, (now_iso,))
    cursor.execute("UPDATE coaches SET coach_number='C1', coach_type='Executive Chair Car', last_updated=? WHERE id=3", (now_iso,))
    cursor.execute("UPDATE coaches SET coach_number='C2', coach_type='AC Chair Car', last_updated=? WHERE id=4", (now_iso,))

    # Train 3: 12627 - Karnataka Express
    cursor.execute("""
        UPDATE trains
        SET train_number='12627', train_name='Karnataka Express', train_type='Superfast Express', operational_status='Active', last_updated=?
        WHERE id=3
    """, (now_iso,))
    # Add coaches to Train 3 if none exist
    cursor.execute("SELECT COUNT(*) FROM coaches WHERE train_id=3")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO coaches (coach_number, coach_type, train_id, created_at, last_updated) VALUES (?, ?, ?, ?, ?)",
                       ('B1', 'AC 3 Tier', 3, now_iso, now_iso))
        c_b1 = cursor.lastrowid
        cursor.execute("INSERT INTO coaches (coach_number, coach_type, train_id, created_at, last_updated) VALUES (?, ?, ?, ?, ?)",
                       ('B2', 'AC 3 Tier', 3, now_iso, now_iso))
        c_b2 = cursor.lastrowid

        # Register wheels for B1 and B2
        for i, pos, axle in [(1, 'Left', 1), (2, 'Right', 1), (3, 'Left', 2), (4, 'Right', 2)]:
            wid = f"WH0003{i:02d}"
            ident = f"B1-A{axle}-{'L' if pos == 'Left' else 'R'}"
            cursor.execute("""
                INSERT OR IGNORE INTO wheels (asset_id, wheel_identifier, train_id, coach_id, axle_number, position, status, inspection_count, created_at, last_updated)
                VALUES (?, ?, '3', ?, ?, ?, 'Healthy', 0, ?, ?)
            """, (wid, ident, str(c_b1), axle, pos, now_iso, now_iso))

        for i, pos, axle in [(5, 'Left', 1), (6, 'Right', 1), (7, 'Left', 2), (8, 'Right', 2)]:
            wid = f"WH0003{i:02d}"
            ident = f"B2-A{axle}-{'L' if pos == 'Left' else 'R'}"
            cursor.execute("""
                INSERT OR IGNORE INTO wheels (asset_id, wheel_identifier, train_id, coach_id, axle_number, position, status, inspection_count, created_at, last_updated)
                VALUES (?, ?, '3', ?, ?, ?, 'Healthy', 0, ?, ?)
            """, (wid, ident, str(c_b2), axle, pos, now_iso, now_iso))

    # Train 4: 12951 - Mumbai Rajdhani Express
    cursor.execute("""
        UPDATE trains
        SET train_number='12951', train_name='Mumbai Rajdhani Express', train_type='Rajdhani Express', operational_status='Active', last_updated=?
        WHERE id=4
    """, (now_iso,))
    cursor.execute("UPDATE coaches SET coach_number='H1', coach_type='AC First Class', last_updated=? WHERE id=5", (now_iso,))

    # Train 5: 12002 - Bhopal Shatabdi Express
    cursor.execute("""
        UPDATE trains
        SET train_number='12002', train_name='Bhopal Shatabdi Express', train_type='Shatabdi Express', operational_status='Under Maintenance', last_updated=?
        WHERE id=5
    """, (now_iso,))
    cursor.execute("UPDATE coaches SET coach_number='E1', coach_type='Executive Chair Car', last_updated=? WHERE id=6", (now_iso,))

    # Add realistic upcoming schedules for Trains 2, 3, 4, 5 if needed
    for tid in (2, 3, 4, 5):
        cursor.execute("SELECT COUNT(*) FROM operating_schedules WHERE train_id=?", (tid,))
        if cursor.fetchone()[0] < 2:
            t0 = datetime.now().replace(minute=0, second=0, microsecond=0)
            dep1 = (t0 + timedelta(days=1, hours=6)).isoformat()
            arr1 = (t0 + timedelta(days=1, hours=14)).isoformat()
            dep2 = (t0 + timedelta(days=2, hours=22)).isoformat()
            arr2 = (t0 + timedelta(days=3, hours=4)).isoformat()
            cursor.execute("""
                INSERT INTO operating_schedules (train_id, schedule_type, departure_datetime, arrival_datetime, operating_date, depot_location, notes, status, created_at, last_updated)
                VALUES (?, 'OPERATING', ?, ?, ?, 'Platform 1', 'Scheduled revenue run', 'ACTIVE', ?, ?)
            """, (tid, dep1, arr1, dep1[:10], now_iso, now_iso))
            cursor.execute("""
                INSERT INTO operating_schedules (train_id, schedule_type, departure_datetime, arrival_datetime, operating_date, depot_location, notes, status, created_at, last_updated)
                VALUES (?, 'MAINTENANCE_WINDOW', ?, ?, ?, 'Depot Line 3', 'Turnaround servicing', 'ACTIVE', ?, ?)
            """, (tid, dep2, arr2, dep2[:10], now_iso, now_iso))

    conn.commit()

    # Verify final count
    train_count = cursor.execute("SELECT COUNT(*) FROM trains").fetchone()[0]
    trains = cursor.execute("SELECT id, train_number, train_name, operational_status FROM trains ORDER BY id").fetchall()
    conn.close()

    print(f"Cleanup complete. Total trains remaining: {train_count}")
    for t in trains:
        print(f"  Train {t[0]}: {t[1]} - {t[2]} [{t[3]}]")

if __name__ == "__main__":
    cleanup()
