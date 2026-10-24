# Chakraksh (चक्राक्ष) &mdash; Train-Wise Wheel Health Monitoring & Intelligent Maintenance Scheduling System

> **v2.0** &mdash; End-to-end Fleet Health, Computer Vision Defect Detection, and Intelligent Maintenance Scheduling Platform for railway rolling stock.
>
> 🚀 **Quick Start:** For step-by-step setup and execution instructions, please see the **[Complete How-To-Run Guide (how_to_run.md)](how_to_run.md)**.

---

## Table of Contents

- 📖 **[Quick Start Guide & How to Run (how_to_run.md)](how_to_run.md)**
- 📑 **[4 Additional Enterprise Features Guide (4 additional features.md)](4%20additional%20features.md)**
1. [System Overview & Architecture](#1-system-overview--architecture)
2. [Database Schema & Migrations](#2-database-schema--migrations)
3. [Complete API Endpoints Reference (37 Routes)](#3-complete-api-endpoints-reference)
4. [Live Machine Learning Inspection Pipeline](#4-live-machine-learning-inspection-pipeline)
5. [Intelligent Maintenance Scheduling & Conflict Engine](#5-intelligent-maintenance-scheduling--conflict-engine)
6. [Request & Response Examples](#6-request--response-examples)
7. [Frontend Integration & UI Application](#7-frontend-integration--ui-application)
8. [Testing & Verification Suites (164 Tests)](#8-testing--verification-suites-164-tests)
9. [How to Start & Run Locally](#9-how-to-start--run-locally)
10. [Windows Performance & Network Optimization](#10-windows-performance--network-optimization)

---

## 1. System Overview & Architecture

The system tracks wheelsets within an operational railway fleet hierarchy:

```
Fleet
 └── Train (T001, T002, ...)
      ├── Coaches (C1, C2, ...)
      │    └── Axles & Wheels (WH000001, WH000002, ...)
      ├── Operating Schedules (Passenger / Freight runs)
      ├── Maintenance Windows (Depot service slots)
      └── Maintenance Jobs (Pending, Scheduled, In Progress, Completed)
```

### Directory Structure

```
Railway_wheel_inspection/
├── main.py                          # FastAPI application entry point
├── how_to_run.md                    # Step-by-step installation and running guide
├── 4 additional features.md         # Documentation of 4 enterprise features
├── routers/
│   ├── auth.py                      # JWT authentication & user session endpoints
│   ├── trains.py                    # Train, coach, and wheel management APIs
│   ├── schedules.py                 # Operating schedules & maintenance windows APIs
│   ├── maintenance.py               # Maintenance recommendation & job lifecycle APIs
│   ├── fleet_dashboard.py          # Executive fleet dashboard & drill-down APIs
│   └── admin_backups.py             # Automated SQLite database backups & recovery APIs
├── core/wheel_lifecycle/
│   ├── database.py                  # SQLite schema manager & automatic migrations
│   ├── auth.py                      # Role-Based Access Control (RBAC) & token verification
│   ├── backup.py                    # Zero-downtime online backup manager & safe restore
│   ├── report_generator.py          # Work Order PDF & CSV report export generator
│   ├── fleet_repository.py          # Fleet data access layer (trains, coaches, schedules, jobs)
│   ├── repository.py                # Core Wheel & Inspection repository
│   ├── models.py                    # Domain models (Wheel, Inspection, Defect)
│   ├── id_generator.py              # Unique ID generators (WH000001, INS000001, EVT...)
│   └── history.py                   # Historical record manager
├── maintenance_priority/
│   ├── scheduler.py                 # Intelligent deterministic maintenance scheduler
│   ├── risk_engine.py               # Multi-factor risk calculation engine
│   ├── trend.py                     # Historical defect degradation analysis
│   └── config.py                    # Defect severity weights & safety thresholds
├── detection/                       # YOLOv8 wheel defect detection model & weights
├── severity/                        # Defect severity categorization (Mild, Moderate, Severe)
├── reliability/                     # Test-Time Augmentation (TTA) prediction confidence
├── explainability/                  # Grad-CAM / Layer-CAM heatmap visualization generator
├── outputs/                         # Static outputs (annotated images, heatmaps, uploads)
│   └── evaluation/                  # YOLOv8 benchmark report and confusion matrices
├── database/railway.db              # SQLite persistence layer (auto-initialized)
├── scripts/                         # Standalone CLI utilities (backup_db, evaluate_model)
├── frontend/                        # React + Vite web dashboard
│   ├── src/                         # Dashboard, Trains, Inspect, Planner, Wheels pages
│   ├── package.json                 # React 18, Vite, React Router, Recharts
│   └── .env.example                 # Backend API URL configuration template
└── tests/
    ├── test_fleet_system.py         # 25 pytest integration & unit tests
    ├── test_api_endpoints.py        # 78 live HTTP validation tests (error codes, validation)
    ├── verify_all_endpoints.py      # 46 live end-to-end tests (real YOLO image upload, scheduling)
    ├── test_database_backup.py      # 9 SQLite online backup & restore tests
    └── test_fast_mode.py            # 6 Fast Mode vs Deep Mode benchmark tests
```─ test_api_endpoints.py        # 64 live HTTP validation tests (error codes, validation)
    ├── verify_all_endpoints.py      # 40 live end-to-end tests (real YOLO image upload, scheduling)
    └── test_*.py                    # Unit tests (models, database, ID generator, history)
```

---

## 2. Database Schema & Migrations

The database (`database/railway.db`) supports 7 interrelated tables with foreign key constraints:

```
trains (id PK, train_number UNIQUE, train_name, train_type, operational_status, ...)
  │
  ├── coaches (id PK, coach_number, train_id FK→trains.id, coach_type, ...)
  │     │
  │     └── wheels (asset_id PK, coach_id FK→coaches.id, train_id, axle_number, position, status, ...)
  │           │
  │           ├── inspection_events (event_id PK, asset_id FK→wheels, train_id, coach_id, risk_score, ...)
  │           │     └── inspections (inspection_id PK, asset_id, inspection_event_id FK, defect_type, ...)
  │           │
  │           └── maintenance_jobs (id PK, wheel_asset_id FK, train_id, coach_id, job_status, ...)
  │
  └── operating_schedules (id PK, train_id FK→trains.id, schedule_type, departure_datetime, arrival_datetime, ...)
```

### Automatic Migration
- Built with automatic schema migration in [`core/wheel_lifecycle/database.py`](core/wheel_lifecycle/database.py).
- Tables and new columns (`coach_id`, `train_id`, `inspection_event_id`) are created idempotently (`IF NOT EXISTS`).
- Prior v1.0 data remains untouched and backward-compatible.

---

## 3. Complete API Endpoints Reference

The backend provides **34 active API routes**:

### 3.1 Train & Coach Management (`routers/trains.py`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/trains` | Register a new train (`train_number` must be unique) |
| `GET` | `/api/trains` | List all registered trains |
| `GET` | `/api/trains/{train_id}` | Get train details by ID |
| `PATCH` | `/api/trains/{train_id}` | Update train status (`Active`, `Under Maintenance`, `Decommissioned`) |
| `POST` | `/api/trains/{train_id}/coaches` | Add a coach to a train |
| `GET` | `/api/trains/{train_id}/coaches` | List all coaches for a train |
| `GET` | `/api/trains/{train_id}/coaches/{coach_id}` | Get specific coach details |
| `POST` | `/api/coaches/{coach_id}/wheels` | Register an axle wheel under a coach |
| `GET` | `/api/coaches/{coach_id}/wheels` | List all wheels belonging to a coach |
| `GET` | `/api/trains/{train_id}/health` | Hierarchical health drill-down (**Train → Coaches → Wheels**) |
| `GET` | `/api/trains/{train_id}/inspection-events` | All historical inspection events for a train |

### 3.2 Operating Schedules & Windows (`routers/schedules.py`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/trains/{train_id}/schedules` | Create schedule (`OPERATING`, `MAINTENANCE_WINDOW`, `NON_OPERATING`) |
| `GET` | `/api/trains/{train_id}/schedules` | List train schedules (optional `active_only=true` filter) |
| `GET` | `/api/schedules/{schedule_id}` | Get specific schedule by ID |
| `PATCH` | `/api/schedules/{schedule_id}` | Update schedule timestamps, status (`ACTIVE`, `CANCELLED`), or notes |
| `GET` | `/api/trains/{train_id}/maintenance-windows` | List available upcoming depot maintenance windows |

### 3.3 ML Inspection Pipeline (`main.py`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/inspect` | Upload wheel image for ML inspection. Accepts optional `run_tta: bool = False` for high-throughput screening (~0.22s) vs full 5-pass TTA & Layer-CAM (~3.1s). |
| `GET` | `/api/inspections/{event_id}/work-order-pdf` | Download official Work Order PDF report with defect bounding boxes and heatmap callouts |

### 3.4 Maintenance Scheduling Engine (`routers/maintenance.py`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/maintenance/recommend/{wheel_asset_id}` | Generate intelligent recommendation and detect schedule conflicts |
| `GET` | `/api/maintenance/jobs` | List all maintenance jobs across the fleet |
| `GET` | `/api/maintenance/jobs/pending` | List pending maintenance jobs requiring review |
| `GET` | `/api/maintenance/jobs/urgent` | List critical priority jobs |
| `GET` | `/api/trains/{train_id}/maintenance/jobs` | List maintenance jobs for a specific train |
| `GET` | `/api/maintenance/jobs/{job_id}` | Get specific maintenance job details |
| `POST` | `/api/maintenance/jobs/{job_id}/confirm` | Confirm maintenance slot (`PENDING` → `SCHEDULED`) with overlap validation |
| `PATCH` | `/api/maintenance/jobs/{job_id}/status` | Update lifecycle (`SCHEDULED` → `IN_PROGRESS` → `COMPLETED` / `CANCELLED`) |
| `GET` | `/api/maintenance/history/{wheel_asset_id}` | Complete maintenance service history for a wheel |
| `GET` | `/api/maintenance/jobs/export/csv` | Download full fleet maintenance job log as CSV |

### 3.5 Fleet Dashboard & Core Wheel APIs (`routers/fleet_dashboard.py`, `main.py`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/fleet/dashboard` | Executive fleet overview with 16 aggregation metrics |
| `GET` | `/api/fleet/wheels/{wheel_asset_id}/history` | Deep drill-down of wheel events, defects, and service jobs |
| `GET` | `/api/wheels` | List all wheel records |
| `GET` | `/api/wheels/{wheel_id}` | Get single wheel asset record |
| `GET` | `/api/wheels/{wheel_id}/history` | Historical defect inspection list |
| `GET` | `/api/dashboard` | Legacy overview statistics |
| `GET` | `/api/health` | Service health status and ML model readiness |
| `GET` | `/` | Root service status |

### 3.6 Automated Database Backups & Maintenance (`routers/admin_backups.py`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/admin/backups` | List all SQLite snapshots in the archive with sizes, timestamps, and integrity status |
| `GET` | `/api/admin/backups/status` | Live database health, integrity check, archive storage metrics, and scheduler status |
| `POST` | `/api/admin/backups` | Create an immediate online, lock-free SQLite snapshot (optional `compress=true`) |
| `GET` | `/api/admin/backups/{filename}/download` | Stream and download database snapshot file (`.db` or `.db.gz`) |
| `POST` | `/api/admin/backups/{filename}/restore` | Restore live database from snapshot with automatic pre-restore safety backup |
| `DELETE` | `/api/admin/backups/{filename}` | Delete a snapshot from the backup archive (Admin only) |

### 3.7 Authentication & Role-Based Access Control (`routers/auth.py`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Authenticate user via username & password; returns signed JWT Bearer token |
| `GET` | `/api/auth/me` | Fetch active profile, role permissions, and token validation status |
| `GET` | `/api/auth/users` | List all available system users, roles, and authorization levels |

---

## 4. Live Machine Learning Inspection Pipeline & Toggleable Fast Mode

The `POST /api/inspect` endpoint features a **Toggleable High-Throughput / Deep Diagnostic Engine** configured via `run_tta: bool = False`:

```
                             [Wheel Image Upload]
                                      │
                         [Single-Pass YOLOv8 Detection]
                                      │
                         [Severity Feature Extraction]
                                      │
                                      ▼
                      ┌───────────────────────────────┐
                      │    run_tta == False (Default) │
                      │       Fast Screening Mode     │
                      └───────────────┬───────────────┘
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
                 No Defects Found            Defects Detected
                        │                           │
                 [Healthy Wheel]            [Calibrate Confidence]
                 (Lat: ~0.22s/wheel)        (High >=0.75, Med >=0.45, Low <0.45)
                                                    │
                                            [Multi-Factor Risk]
                                                    │
                                            [One-Click Escalate]
                                                    │
                                                    ▼
                                      ┌───────────────────────────────┐
                                      │    run_tta == True            │
                                      │       Deep Diagnostic Mode    │
                                      └───────────────┬───────────────┘
                                                      │
                                        [5-Pass TTA Forward Passes]
                                        (Rotation, Brightness, Scale)
                                                      │
                                        [Layer-CAM Heatmap Synthesis]
                                        (Pixel Activation Attribution)
                                                      │
                                        [Deep Diagnostic Verification]
                                        (Lat: ~3.1s/wheel)
```

### Modes Comparison

| Feature | Fast Screening Mode (`run_tta=false`) | Deep Diagnostic Mode (`run_tta=true`) |
|---|---|---|
| **Primary Use-Case** | Wayside pass-by screening, line ingestion | Depot verification, flagged wheel audit |
| **Inference Latency** | **~0.22 seconds / wheel** (13.0x speedup) | **~3.10 seconds / wheel** |
| **Defect Detection** | YOLOv8 single-pass bounding boxes | YOLOv8 single-pass bounding boxes |
| **Severity Grading** | Area, perimeter, aspect ratio, entropy | Area, perimeter, aspect ratio, entropy |
| **Confidence Scoring**| Deterministic threshold calibration | 5-Fold TTA Monte-Carlo spread analysis |
| **Explainability** | Skipped for high throughput | Layer-CAM gradient attention heatmaps |
| **Escalation Path** | 1-Click UI button re-runs with TTA + CAM | Immediate depot work-ticket PDF download |

### Multi-Factor Risk Score Formula (0–100)
$$\text{Risk Score} = \min\left(100, (\text{Defect Weight} + \text{Severity Weight} + \text{Trend Weight}) \times \text{Reliability Factor}\right)$$
- **Defect Weights**: `Cracks-Scratches` (40), `Shelling` (35), `Discoloration` (20)
- **Severity Weights**: `Severe` (30), `Moderate` (20), `Mild` (10)
- **Reliability Factors**: `HIGH` (1.0), `MEDIUM` (0.85), `LOW` (0.60)
- **Wheel Action & Status Thresholds**: `Healthy` ($<50$), `Monitor` ($50–79$), `Critical` ($\ge 80$)

---

## 5. Intelligent Maintenance Scheduling & Conflict Engine

The deterministic rule engine (`maintenance_priority/scheduler.py`) maps inspection results directly to operational train schedules:

| Wheel Risk Level | Trigger Condition | Scheduling Strategy | Operational Impact |
|---|---|---|---|
| **CRITICAL** | Risk $\ge 80$ or "Immediate inspection" | Suggests immediate 2-hour mobilization window | **Requires operational clearance**. Flags all overlapping operating train schedules as conflicts. Train cannot depart until cleared. |
| **MODERATE** | Risk $50–79$ or "Schedule maintenance" | Scans train's `MAINTENANCE_WINDOW` schedules for earliest fit | If an operating run conflicts with the window, flags a **Schedule Conflict** and notes conflicting departure/arrival times. |
| **LOW** | Risk $< 50$ or "Monitor only" | Routine monitoring | No operational disruption. Recommends routine maintenance during next depot turnaround. |

### Overlap Collision Prevention
When confirming a maintenance slot via `/api/maintenance/jobs/{id}/confirm`, the engine validates interval overlaps:
$$\text{Existing Start} < \text{Requested End} \quad \text{AND} \quad \text{Existing End} > \text{Requested Start}$$
If an overlapping confirmed job already exists for the wheel, the API rejects the request with HTTP `409 Conflict`.

---

## 6. Request & Response Examples

### 6.1 Register Train, Coach, and Wheels

```bash
# 1. Register Train
POST /api/trains
Content-Type: application/json

{
  "train_number": "TR-2048",
  "train_name": "Vande Bharat Express",
  "train_type": "Superfast Express",
  "operational_status": "Active"
}
# Returns: { "id": 1, "train_number": "TR-2048", ... }

# 2. Add Coach
POST /api/trains/1/coaches
Content-Type: application/json

{
  "coach_number": "C1",
  "coach_type": "Executive Chair Car"
}
# Returns: { "id": 1, "coach_number": "C1", "train_id": 1, ... }

# 3. Register Wheel
POST /api/coaches/1/wheels
Content-Type: application/json

{
  "wheel_identifier": "C1-A1-L",
  "axle_number": 1,
  "position": "Left"
}
# Returns: { "asset_id": "WH000001", "wheel_identifier": "C1-A1-L", "status": "Healthy", ... }
```

### 6.2 Inspect Wheel with Real Image

```bash
POST /api/inspect
Content-Type: multipart/form-data

image: <wheel_sample.jpg>
wheel_id: WH000001
coach_id: 1
```

**Response (200 OK):**
```json
{
  "inspection_id": "INS000001",
  "inspection_event_id": "EVT9F3A10",
  "asset_id": "WH000001",
  "train_id": 1,
  "coach_id": 1,
  "wheel_risk_score": 50.0,
  "wheel_recommended_action": "Schedule maintenance",
  "trend_status": "FIRST_INSPECTION",
  "total_defects_detected": 2,
  "defects": [
    {
      "label": "Shelling",
      "severity": "Mild",
      "confidence": 0.80,
      "risk_score": 50.0,
      "reliability": "HIGH"
    },
    {
      "label": "Cracks-Scratches",
      "severity": "Mild",
      "confidence": 0.78,
      "risk_score": 46.8,
      "reliability": "HIGH"
    }
  ],
  "annotated_image_url": "/outputs/annotated/wheel_sample.jpg",
  "gradcam_image_url": "/outputs/gradcam/wheel_sample.jpg",
  "processing_time_seconds": 4.54
}
```

### 6.3 Maintenance Recommendation & Conflict Detection

```bash
POST /api/maintenance/recommend/WH000001
```

**Response (200 OK):**
```json
{
  "wheel_asset_id": "WH000001",
  "risk_score": 50.0,
  "priority": "MODERATE",
  "recommended_action": "Schedule maintenance",
  "trend_status": "FIRST_INSPECTION",
  "suggested_start": "2026-10-22T18:00:00",
  "suggested_end": "2026-10-22T22:00:00",
  "scheduling_status": "CONFLICT",
  "scheduling_notes": "Moderate-risk defect. A maintenance window was found but conflicts with 1 operating schedule(s). Consider rescheduling the maintenance window or adjusting operations.",
  "conflict_notes": [
    "Conflicts with operating schedule (departure=2026-10-22T16:00:00, arrival=2026-10-22T23:00:00)"
  ],
  "requires_operational_clearance": false,
  "maintenance_job_id": 12,
  "duplicate_job": false
}
```

### 6.4 Executive Fleet Dashboard

```bash
GET /api/fleet/dashboard
```

**Response (200 OK):**
```json
{
  "total_trains": 8,
  "total_coaches": 11,
  "total_wheels": 42,
  "total_inspections": 18,
  "total_inspection_events": 10,
  "inspected_wheels": 7,
  "uninspected_wheels": 35,
  "healthy_wheels": 35,
  "monitor_wheels": 5,
  "critical_wheels": 2,
  "pending_maintenance_jobs": 14,
  "scheduled_maintenance_jobs": 8,
  "train_health_summaries": [...],
  "critical_wheels_by_train": [...],
  "upcoming_maintenance": [...],
  "operating_schedule_conflicts": [...]
}
```

### 6.5 Depot Maintenance Work Orders (PDF) & CSV Exports

Depot engineers can download comprehensive, publication-ready PDF work tickets with railway branding, dual-panel computer vision imagery, defect itemization, scheduling feasibility analysis, and RDSO sign-off checklists:

```bash
# Download Maintenance Work Order PDF for a specific job
GET /api/maintenance/jobs/{job_id}/work-order-pdf

# Download Work Order / Assessment PDF for an inspection event
GET /api/inspections/{event_or_inspection_id}/work-order-pdf

# Download Wheel Assessment PDF
GET /api/fleet/wheels/{wheel_asset_id}/work-order-pdf

# Export all fleet maintenance jobs to CSV spreadsheet
GET /api/maintenance/jobs/export/csv

# Export defect inspection history for a specific wheel as CSV
GET /api/fleet/wheels/{wheel_asset_id}/export/csv
```

**Work Order PDF Contents:**
1. **Header & Metadata**: Official Indian Railways Rolling Stock Department header, work order number, status, and urgency priority banner.
2. **Asset Hierarchy**: Train number/name, coach number/type, wheel asset ID, axle number, wheel position, and depot base.
3. **Health Diagnostics**: Overall risk score, degradation trend status, recommended action, and TTA model reliability score.
4. **Defect Itemization Table**: Defect classes, severity grades, confidence scores, and recommended repair actions.
5. **Computer Vision Visuals**: Dual-panel side-by-side callouts showing **Figure A: YOLOv8 defect bounding boxes** and **Figure B: Layer-CAM deep backbone attention heatmaps**.
6. **Depot Scheduling & Operational Feasibility**: Scheduled window, clearance requirement, and operating schedule conflict notes.
7. **Execution Checklist & Sign-Off**: RDSO-compliant sign-off blocks for inspecting engineer, employee ID, foreman signature, and release date.

### 6.6 Authentication & Role-Based Access Control (RBAC)

The system enforces hierarchical Role-Based Access Control (RBAC) powered by JSON Web Tokens (JWT, HS256) and API Key credentials:

```bash
# Authenticate with credentials and receive JWT Bearer access token
POST /api/auth/login

# Get current user profile and active permissions
GET  /api/auth/me

# List available role specifications & permissions hierarchy
GET  /api/auth/roles

# List registered system users (Admin only)
GET  /api/auth/users

# Create a new user (Admin only)
POST /api/auth/users
```

#### Roles & Permissions Matrix

| Role | Hierarchy Level | Pre-Seeded Account | Description & Allowed Operations |
|---|:---:|---|---|
| **`OPERATOR`** | 1 | `operator` / `oper123`<br>`X-API-Key: opr-key-secret-777` | **Wayside Inspection Operator**: View fleet assets, trains, coaches, wheels, operating schedules; submit wheel inspection images (`POST /api/inspect`); download Work Order PDFs and CSV spreadsheets. |
| **`MAINTENANCE_SUPERVISOR`** | 2 | `supervisor` / `super123`<br>`X-API-Key: sup-key-secret-888` | **Depot Maintenance Supervisor**: All `OPERATOR` permissions + generate intelligent maintenance recommendations (`POST /api/maintenance/recommend/{wheel_id}`), confirm maintenance slots (`POST /api/maintenance/jobs/{id}/confirm`), and update job status (`PATCH /api/maintenance/jobs/{id}/status`). |
| **`ADMIN`** | 3 | `admin` / `admin123`<br>`X-API-Key: adm-key-secret-999` | **Chief Rolling Stock Engineer / Admin**: Full system access: register trains, add coaches, register wheels under coaches, create/update operating schedules, and manage user accounts. |

#### Authentication Methods
1. **JWT Bearer Token**: Pass header `Authorization: Bearer <token>` returned by `/api/auth/login`.
2. **X-API-Key Header**: Pass `X-API-Key: <key>` (ideal for automated wayside imaging scanners and CLI scripts).
3. **Query Parameter**: Pass `?token=<jwt>` or `?api_key=<key>` (built into direct browser links for one-click PDF and CSV downloads).

### 6.7 Automated SQLite Database Backups & Online Snapshots

The system features an automated, lock-free SQLite online backup routine using Python's native `sqlite3.Connection.backup()` API:

```bash
# 1. Trigger an immediate online backup snapshot via REST API (Supervisor / Admin)
POST /api/admin/backups?compress=false

# 2. List all backup snapshots in the archive
GET  /api/admin/backups

# 3. Check storage overview and scheduler status
GET  /api/admin/backups/status

# 4. Download a backup snapshot file (.db or .db.gz)
GET  /api/admin/backups/{filename}/download

# 5. Restore live database from a snapshot (Admin only, pre-restore safety snapshot taken automatically)
POST /api/admin/backups/{filename}/restore

# 6. Delete an old snapshot (Admin only)
DELETE /api/admin/backups/{filename}
```

#### Standalone CLI & Cron Script
Run backups directly from cron, Windows Task Scheduler, or CI/CD pipelines without touching HTTP:

```bash
# Create an online snapshot
python scripts/backup_db.py

# Create a gzip-compressed snapshot (.db.gz)
python scripts/backup_db.py --compress

# Custom retention limit (keeps last 30 snapshots, prunes older)
python scripts/backup_db.py --keep 30

# List all snapshots in the archive
python scripts/backup_db.py --list

# Restore database from snapshot
python scripts/backup_db.py --restore railway_backup_20261024_030003_299707.db
```

#### Background Scheduler Configuration (Environment Variables)
- `BACKUP_INTERVAL_MINUTES`: Frequency in minutes (default: `360` = every 6 hours).
- `BACKUP_MAX_RETAINED`: Maximum snapshots retained before pruning oldest (default: `20`).
- `BACKUP_ON_STARTUP`: Take an automated safety snapshot on server boot (default: `True`).

---

## 7. Frontend Integration & UI Application

The `frontend/` directory contains a single-page React application built with **Vite**, **React 18**, **React Router v6**, and **Recharts**.

### 5 Dedicated Pages & Features
- **Fleet Dashboard (`Dashboard.jsx`)**: Visual gauges, healthy/monitor/critical wheel counts, train condition breakdown, upcoming maintenance timeline, and schedule conflict alerts.
- **Train Registry & Schedules (`Trains.jsx`)**: Hierarchical Train $\rightarrow$ Coach $\rightarrow$ Axle Wheel registration, role-guarded mutation controls (`🔒 Requires Admin`), and interactive 7-day visual operating vs. maintenance window availability lanes.
- **New Inspection (`Inspect.jsx`)**: Drag-and-drop wheel image upload with live inference progression, YOLO bounding box detection plot, and Layer-CAM attention heatmap overlay.
- **Maintenance Planner (`Planner.jsx`)**: Priority maintenance job queue (`CRITICAL`, `MODERATE`, `LOW`), operational clearance hold banners, collision-free slot confirmations (`🔒 Supervisor Role`), and PDF work ticket downloads.
- **Wheel History (`Wheels.jsx`)**: Searchable wheel directory with historical defect timeline, risk score degradation curves, PDF report downloads, and live **Automated Database Backups & Archive Management Panel**.
- **RBAC Role Switcher Widget**: Persistent sidebar switcher allowing live switching between `ADMIN`, `MAINTENANCE_SUPERVISOR`, and `OPERATOR` sessions directly in the browser.

### Running the Frontend
```bash
cd frontend
# 1. Install dependencies
npm install

# 2. Configure environment (copy template)
copy .env.example .env    # On Windows (or cp .env.example .env on Linux/macOS)

# 3. Start local development server
npm run dev
```
Open **http://localhost:5173** in your browser.

> **Frontend Configuration (`frontend/.env`):**
> ```env
> VITE_USE_MOCK=false
> VITE_API_URL=http://127.0.0.1:8000
> ```

---

## 8. Testing & Verification Suites (164 Tests)

The system features automated test suites with a **100% pass rate (164/164)**:

| Test Suite File | Type | Test Count | Scope |
|---|---|:---:|---|
| [`tests/verify_all_endpoints.py`](tests/verify_all_endpoints.py) | **End-to-End Live** | **46** | RBAC login, token verification, role restriction enforcement, multipart image upload, live YOLOv8 + Grad-CAM, priority scheduling, conflict detection, full job lifecycle, and dashboard metrics. |
| [`tests/test_api_endpoints.py`](tests/test_api_endpoints.py) | **Live HTTP** | **78** | JWT authentication, role rejection testing (401/403), database backup API, field-level validation, 404/409/422 status code validation, duplicate rejection, and filtering across all routes. |
| [`tests/test_fleet_system.py`](tests/test_fleet_system.py) | **Pytest Unit / Integration** | **25** | Database foreign keys, hierarchy integrity, trend aggregation, scheduler logic, and job status transitions. |
| [`tests/test_database_backup.py`](tests/test_database_backup.py) | **Backup & Restore** | **9** | SQLite online backup API, PRAGMA integrity verification, gzip compression, retention pruning, RBAC permissions, binary download, and transactional restore with safety snapshots. |
| [`tests/test_fast_mode.py`](tests/test_fast_mode.py) | **Benchmark & Integration** | **6** | Toggleable Fast Mode (`run_tta=false`) vs Deep Diagnostic Mode (`run_tta=true`), single-pass confidence calibration, 13x latency benchmark, and PDF work order generation. |
| **Total Core Suites** | | **164** | **All 164 Passed (100%)** |

### Run the Tests

```bash
# 1. Run live end-to-end ML & scheduling verification (against running server)
python tests/verify_all_endpoints.py

# 2. Run 78 live HTTP validation & RBAC tests
python tests/test_api_endpoints.py

# 3. Run SQLite database backup & restore test suite
python tests/test_database_backup.py

# 4. Run Fast Mode vs Deep Diagnostic Mode benchmark tests
python tests/test_fast_mode.py

# 5. Run pytest unit test suite
python -m pytest tests/test_fleet_system.py -v
```

---

## 9. How to Start & Run Locally

> 💡 **For the full step-by-step setup walkthrough, prerequisites, and troubleshooting, read [HOW TO RUN (how_to_run.md)](how_to_run.md).**

### Quick Launch

Open two terminal windows:

#### Terminal 1: Start the Backend (FastAPI)
```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run backend server on 127.0.0.1:8000
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

#### Terminal 2: Start the Frontend (Vite + React)
```bash
cd frontend

# 1. Install frontend packages
npm install

# 2. Start Vite development server
npm run dev -- --host 127.0.0.1 --port 5173
```

- **Web Dashboard**: `http://127.0.0.1:5173`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc Documentation**: `http://127.0.0.1:8000/redoc`
- **Health Check**: `http://127.0.0.1:8000/api/health`

---

## 10. Windows Performance & Network Optimization

> [!TIP]
> **Use `http://127.0.0.1:8000` instead of `http://localhost:8000` on Windows.**  
> On Windows, requesting `localhost` triggers an IPv6 resolution attempt (`::1`) that times out after ~2,000 ms before falling back to IPv4 (`127.0.0.1`).  
> - Benchmark on this project:
>   - `localhost`: **2,047 ms / request**
>   - `127.0.0.1`: **3.66 ms / request** (560× faster)
> 
> Always point your frontend `.env` and automated API test clients to `http://127.0.0.1:8000`.