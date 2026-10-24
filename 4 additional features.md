# 4 Additional Enterprise Features &bull; Chakraksh (चक्राक्ष)

This document explains the four major enterprise features added to **Chakraksh (चक्राक्ष)** &mdash; the Railway Wheel Health Assessment & Intelligent Fleet Maintenance Platform. Each feature is designed to make the system faster, safer, and easier to use in real-world railway depot and trackside operations.

---

## 1. PDF & CSV Report Export (Work Order Tickets)

### The Problem Before
Inspections and maintenance recommendations could only be viewed inside the web browser. Mechanics and technicians on the depot workshop floor do not always carry laptops and need printable work tickets with clear visual proof.

### What This Feature Does
- **One-Click PDF Work Tickets**: Generates a professional, printable **Maintenance Work Order (PDF)** for any flagged wheel or maintenance job.
- **Visual Defect Callouts**: Includes the original wheel photo, YOLOv8 defect bounding boxes, and Layer-CAM heatmaps showing exactly where cracks or shelling were detected.
- **Depot Clearance Sign-Off**: Includes engineer sign-off blocks (Technician Name, Depot ID, Inspection Date, Completion Status).
- **Spreadsheet Data Exports (CSV)**: Allows fleet managers to download complete CSV tables of all maintenance jobs and wheel inspection histories for reporting and audits.

### Where to Find It
- **Inspect Page**: Click **"Download Work Order (PDF)"** after any wheel inspection.
- **Maintenance Planner**: Click **"PDF Ticket"** next to any job in the queue, or **"Export CSV"** to download the full job list.
- **Wheels Directory**: Click **"Export CSV"** to download a specific wheel's lifetime defect history.

---

## 2. Role-Based Access Control (RBAC) & Security

### The Problem Before
All API endpoints and controls were completely open. Anyone could register new trains, delete schedules, or approve maintenance jobs without verifying who they were.

### What This Feature Does
Secures the application using industry-standard **JSON Web Tokens (JWT)** and organizes users into three clear operational roles:

1. **Operator (Wayside Inspector)**:
   - Can upload wheel photos and run AI inspections.
   - Can view trains, wheels, and dashboards.
   - *Restricted from*: Confirming maintenance jobs, registering trains, or touching backups.
2. **Maintenance Supervisor (Depot Foreman)**:
   - Everything an Operator can do, plus:
   - Confirms and schedules maintenance jobs into open maintenance slots.
   - Updates job progress (`IN_PROGRESS`, `COMPLETED`).
   - Can trigger database snapshots.
3. **Admin (Fleet Operations Director)**:
   - Full master access.
   - Registers trains, adds coaches, and configures operating schedules.
   - Can restore database backups and manage system settings.

### Where to Find It
- **Top Navigation Bar**: A live role badge appears in the top-right header with a quick-switcher to simulate and test different user permissions.
- **API Security**: Any unauthorized action automatically returns `403 Forbidden` with a clear explanation.

---

## 3. Toggleable Fast Mode (High-Throughput Wayside Screening)

### The Problem Before
Every single inspection image was forced to run through **5 heavy Test-Time Augmentations (TTA)** and compute **multi-layer Grad-CAM heatmaps**. While great for deep diagnosis, this took too long when hundreds of wheels pass a trackside camera at high speed.

### What This Feature Does
Introduces a simple toggle switch between two inspection speeds:

- **⚡ Fast Mode (Default for Trackside Waysides)**:
  - Runs a single fast YOLOv8 pass.
  - Skips redundant augmentations and heatmaps.
  - Completes in **~3.0 seconds**, allowing continuous high-speed screening of passing train wheels.
- **🔬 Deep Diagnostic Mode (For Depot Analysis)**:
  - Runs the full 5-pass TTA uncertainty analysis and generates high-resolution Layer-CAM heatmaps.
  - Used when a wheel is flagged as borderline or critical, giving depot engineers full explainability.

### Where to Find It
- **Inspect Page**: Look for the **"⚡ Fast Mode" / "🔬 Deep Mode"** toggle button right above the image upload box.
- **API Query Parameter**: Send `POST /api/inspect?run_tta=false` for fast screening or `?run_tta=true` for deep diagnosis.

---

## 4. Automated Database Backups & Safe Recovery

### The Problem Before
The system stored all train hierarchies, inspection histories, and maintenance schedules in a single local SQLite database file (`railway.db`). If the file became corrupted or accidentally deleted, all historical data would be lost.

### What This Feature Does
- **Zero-Downtime Online Backups**: Uses SQLite's native online backup engine (`sqlite3.backup`) to take a snapshot without locking the database or interrupting running trains or inspections.
- **Automated Background Scheduler**: Runs quietly in the background and automatically takes a backup every 60 minutes (configurable).
- **Integrity Verification**: Automatically runs `PRAGMA integrity_check` on every snapshot to guarantee the backup is not corrupted.
- **Storage Management**: Automatically keeps the latest 20 snapshots and cleans up older ones to prevent filling up hard drive space. Supports optional `.gz` compression.
- **Pre-Restore Safety Net**: Before restoring any previous backup, the system automatically takes an emergency backup of the current database first, so you can never accidentally overwrite live data.

### Where to Find It
- **Wheels Page**: Scroll to the **"Automated SQLite Database Backups"** panel at the bottom to see live storage size, download snapshots, or trigger a manual backup.
- **Command-Line (CLI)**: Run `python scripts/backup_db.py --keep 20` for scheduled OS crontab tasks.
- **Admin REST API**: Endpoints under `/api/admin/backups` (guarded by Supervisor/Admin permissions).

---

## Summary Comparison

| Feature | Primary Beneficiary | Biggest Advantage |
|---|---|---|
| **1. PDF/CSV Exports** | Depot Mechanics & Shop Floor | Physical, printable work tickets with heatmaps & Excel-friendly CSVs |
| **2. Role-Based Access (RBAC)** | Fleet Managers & IT Security | Prevents unauthorized schedule changes and protects safety records |
| **3. Fast Mode / TTA Skip** | Wayside Camera Operators | Rapid ~3.0s throughput for screening hundreds of rolling wheels |
| **4. Automated Backups** | System Administrators | Lock-free snapshots, integrity checks, and zero data loss |
