import sqlite3
from datetime import datetime, timedelta

def seed():
    conn = sqlite3.connect('database/railway.db')
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    now_iso = datetime.now().isoformat(timespec="seconds")

    # Helper for relative iso dates
    def at(days, hours, minutes=0):
        dt = datetime.now() + timedelta(days=days)
        dt = dt.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        return dt.isoformat(timespec="seconds")

    # 1. Trains
    trains_data = [
        (1, "12627", "Karnataka Express", "Superfast Express", "Active", now_iso, now_iso, now_iso),
        (2, "TR-2048", "Vande Bharat Express", "Superfast Express", "Active", now_iso, now_iso, now_iso),
        (3, "TR-3110", "Depot Shuttle", "Passenger", "Under Maintenance", now_iso, now_iso, now_iso),
    ]
    for row in trains_data:
        cur.execute("""
            INSERT OR REPLACE INTO trains (id, train_number, train_name, train_type, operational_status, registration_date, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, row)

    # 2. Coaches
    coaches_data = [
        (1, "B1", "AC 3 Tier", 1, now_iso, now_iso),
        (2, "B2", "AC 3 Tier", 1, now_iso, now_iso),
        (3, "C1", "Executive Chair Car", 2, now_iso, now_iso),
    ]
    for row in coaches_data:
        cur.execute("""
            INSERT OR REPLACE INTO coaches (id, coach_number, coach_type, train_id, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """, row)

    # 3. Wheels
    wheels_data = [
        ("WH000001", "B1-A1-L", "1", "1", 1, "Left", "Healthy", 1, at(-9, 8, 30), now_iso, now_iso),
        ("WH000002", "B1-A1-R", "1", "1", 1, "Right", "Critical", 2, at(-1, 9, 40), now_iso, now_iso),
        ("WH000003", "B1-A2-L", "1", "1", 2, "Left", "Monitor", 2, at(-2, 13, 17), now_iso, now_iso),
        ("WH000004", "B1-A2-R", "1", "1", 2, "Right", "Healthy", 0, None, now_iso, now_iso),
        ("WH000005", "B2-A1-L", "1", "2", 1, "Left", "Healthy", 1, at(-4, 16, 5), now_iso, now_iso),
        ("WH000006", "B2-A1-R", "1", "2", 1, "Right", "Healthy", 0, None, now_iso, now_iso),
        ("WH000007", "C1-A1-L", "2", "3", 1, "Left", "Healthy", 1, at(-3, 11, 45), now_iso, now_iso),
        ("WH000008", "C1-A1-R", "2", "3", 1, "Right", "Monitor", 1, at(-1, 15, 20), now_iso, now_iso),
    ]
    for row in wheels_data:
        cur.execute("""
            INSERT OR REPLACE INTO wheels (asset_id, wheel_identifier, train_id, coach_id, axle_number, position, status, inspection_count, latest_inspection, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row)

    # 4. Schedules
    schedules_data = [
        (1, 1, "OPERATING", at(1, 6), at(1, 22), at(1, 0)[:10], "Bangalore City Depot", "Scheduled passenger run", "ACTIVE", now_iso, now_iso),
        (2, 1, "MAINTENANCE_WINDOW", at(3, 1), at(3, 7), at(3, 0)[:10], "Bangalore City Depot", "Depot slot", "ACTIVE", now_iso, now_iso),
        (3, 2, "OPERATING", at(1, 16), at(1, 23), at(1, 0)[:10], "New Delhi Depot", "Scheduled passenger run", "ACTIVE", now_iso, now_iso),
        (4, 2, "MAINTENANCE_WINDOW", at(1, 18), at(1, 22), at(1, 0)[:10], "New Delhi Depot", "Depot slot", "ACTIVE", now_iso, now_iso),
        (5, 2, "OPERATING", at(4, 6), at(4, 20), at(4, 0)[:10], "New Delhi Depot", "Scheduled passenger run", "ACTIVE", now_iso, now_iso),
    ]
    for row in schedules_data:
        cur.execute("""
            INSERT OR REPLACE INTO operating_schedules (id, train_id, schedule_type, departure_datetime, arrival_datetime, operating_date, depot_location, notes, status, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row)

    # 5. Maintenance Jobs
    jobs_data = [
        (1, 1, 1, "WH000002", None, 84.0, "CRITICAL", "Immediate inspection", at(0, 23), at(1, 1), None, "PENDING", "Critical defect. Urgent inspection is required before the next operation.", now_iso, now_iso),
        (2, 2, 3, "WH000008", None, 58.0, "MODERATE", "Schedule maintenance", at(1, 18), at(1, 22), None, "PENDING", "A maintenance window was found but it overlaps an operating run.", now_iso, now_iso),
        (3, 1, 1, "WH000003", None, 58.0, "MODERATE", "Schedule maintenance", at(3, 1), at(3, 7), None, "SCHEDULED", "Fits the next free maintenance window with no operating conflict.", now_iso, now_iso),
    ]
    for row in jobs_data:
        cur.execute("""
            INSERT OR REPLACE INTO maintenance_jobs (id, train_id, coach_id, wheel_asset_id, inspection_event_id, risk_score, priority, recommended_action, suggested_start, suggested_end, confirmed_start, job_status, completion_notes, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row)

    conn.commit()
    conn.close()
    print("Database seeded successfully with all trains, coaches, wheels, schedules, and jobs!")

if __name__ == "__main__":
    seed()
