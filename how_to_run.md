# How to Run Chakraksh (चक्राक्ष)

This step-by-step guide explains how to install, configure, run, and verify **Chakraksh (चक्राक्ष)** &mdash; the Railway Wheel Health Assessment & Intelligent Fleet Maintenance Platform.

---

## ⚡ Quick Start (TL;DR)

If you already have **Python 3.9+** and **Node.js 18+** installed, open two terminal windows:

### Terminal 1 &mdash; Backend (FastAPI)
```bash
# From repository root
python -m venv venv
venv\Scripts\activate       # Windows (or source venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2 &mdash; Frontend (React + Vite)
```bash
# From repository root
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

- Open **http://127.0.0.1:5173** in your web browser.
- Open **http://127.0.0.1:8000/docs** for the interactive Swagger REST API explorer.

---

## 1. Prerequisites & System Requirements

Before starting, ensure your system has the following installed:

| Tool | Recommended Version | Verification Command | Notes |
|---|:---:|---|---|
| **Python** | `3.9` &ndash; `3.12` | `python --version` | Supports both CPU and CUDA-enabled GPU acceleration. |
| **Node.js** | `18.x` or higher | `node --version` | Required for building and running the Vite frontend. |
| **npm** | `9.x` or higher | `npm --version` | Ships automatically with Node.js. |
| **Git** | `2.30+` | `git --version` | For cloning and version control. |

> [!IMPORTANT]
> **Windows Network Tip:** Always use **`127.0.0.1`** instead of `localhost` on Windows.  
> `localhost` triggers a 2-second IPv6 DNS lookup timeout on Windows before falling back to IPv4. Connecting to `127.0.0.1` is **560× faster** (~3 ms vs ~2,000 ms per request).

---

## 2. Step-by-Step Installation

### Step 2.1: Clone the Repository
```bash
git clone https://github.com/notigayatri/Railway_wheel_inspection.git
cd Railway_wheel_inspection
```

---

### Step 2.2: Set Up Python Virtual Environment
Creating an isolated virtual environment prevents library conflicts:

#### On Windows (PowerShell or Command Prompt):
```powershell
python -m venv venv
.\venv\Scripts\activate
```

#### On Linux or macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

*(You will see `(venv)` prepended to your command prompt when the virtual environment is active).*

---

### Step 2.3: Install Python Dependencies
Install all required machine learning, web server, and PDF reporting packages:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> [!NOTE]
> Core dependencies include `fastapi`, `uvicorn`, `ultralytics` (YOLOv8), `torch`, `torchvision`, `opencv-python`, `numpy`, `reportlab` (PDF generation), and `pytest`.

---

### Step 2.4: Install Frontend Dependencies
Open a separate terminal window and install the React frontend packages:

```bash
cd frontend
npm install
```

Configure your local environment file:
```bash
# On Windows:
copy .env.example .env

# On Linux or macOS:
cp .env.example .env
```

Ensure `frontend/.env` contains:
```env
VITE_USE_MOCK=false
VITE_API_URL=http://127.0.0.1:8000
```

---

## 3. Starting the Applications

### 3.1 Start the FastAPI Backend

From the repository root (with `venv` activated):

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

When started successfully, you will see:
```text
INFO:     Started server process
INFO:     Waiting for application startup.
[INIT] Database initialized: database/railway.db
[BACKUP] Initialized auto-backup manager (interval=360m, max_retained=20)
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

#### Backend Access Points:
- **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **API Health Check**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- **Fleet Summary**: [http://127.0.0.1:8000/api/fleet/dashboard](http://127.0.0.1:8000/api/fleet/dashboard)

---

### 3.2 Start the Vite Frontend Server

From the `frontend/` directory:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

When started, open your web browser to:
👉 **[http://127.0.0.1:5173](http://127.0.0.1:5173)**

---

## 4. How to Use the Key Features

Once the application is running in your browser, here is how to explore its features:

### 4.1 Role-Based Access Control (RBAC) Switcher
Chakraksh includes role-based access control. In the top-right header, click the **Role Badge** to test each perspective:

| Role | Default User | Default Password | What You Can Do |
|---|---|---|---|
| **Admin** | `admin` | `admin123` | Full master control: register trains, add coaches, configure operating runs, restore backups. |
| **Supervisor** | `supervisor` | `super123` | Depot foreman: confirm maintenance slots, update job status, generate PDF work tickets. |
| **Operator** | `operator` | `oper123` | Trackside technician: upload wheel photos, run ML defect detection, view fleet health. |

*(API Key authentication is also supported: `adm-key-secret-999`, `sup-key-secret-456`, `opr-key-secret-123`).*

---

### 4.2 Running a Wheel Inspection (`/inspect`)
1. Click **New Inspection** in the top navigation bar.
2. Choose your inspection mode:
   - **⚡ Fast Mode**: Instant single-pass YOLOv8 screening (~3.0 s) &mdash; ideal for high-speed trackside cameras.
   - **🔬 Deep Diagnostic Mode**: 5-pass Test-Time Augmentation (TTA) uncertainty analysis and Layer-CAM attention heatmaps &mdash; ideal for depot engineering audits.
3. Select an existing wheel from the dropdown or click one of the pre-loaded sample cards.
4. Drag and drop a wheel image (or click to upload).
5. View detected bounding boxes, severity classifications (*Mild*, *Moderate*, *Severe*), confidence scores, and risk ratings out of 100.
6. Click **"Download Work Order (PDF)"** to generate a printable PDF ticket with defect images, bounding boxes, and sign-off blocks.

---

### 4.3 Train & Coach Registry (`/trains`)
1. Click **Trains** in the top navigation.
2. Select any train from the left list (e.g., `T001-TEST`).
3. View the coach and wheel hierarchy (`Train → Coach → Axles & Mounted Wheels`).
4. Scroll down to **Schedule and Availability**:
   - Inspect the interactive **7-day visual timeline** displaying operational passenger runs vs. depot maintenance window lanes.
   - If a wheel has moderate wear, click **"Schedule for [Next Day]"** to book turnaround servicing during a clash-free window.
   - If a wheel has critical defect wear, click **"Request Priority Turnaround"** to alert depot operations and place a safety clearance flag.

---

### 4.4 Maintenance Planner (`/planner`)
1. Click **Maintenance** in the navigation bar.
2. Filter jobs by **All Jobs**, **Pending Review**, or **Urgent**.
3. Inspect job details:
   - Notice the **Scheduling** badge displays the exact confirmed date (or `Routine`) with zero placeholder hyphens.
   - Any operational hold is presented with a subtle, non-intimidating engineering review callout.
4. Click **Confirm Slot** to approve a suggested turnaround window.
5. Click **Start Job** and then **Mark as Done** when servicing completes.
6. Click **Export Work Order (PDF)** to print a job ticket, or **Export Jobs (CSV)** to download the fleet schedule spreadsheet.

---

### 4.5 Automated Database Backups (`/wheels`)
1. Click **Wheels** in the navigation bar.
2. Scroll to the bottom to find the **Automated SQLite Database Backups** panel.
3. Features available:
   - **Live Storage Stats**: View active database size, archive disk usage, and snapshot counts.
   - **Create Snapshot**: Take a zero-downtime, lock-free online backup instantly.
   - **Download Snapshot**: Download any `.db` snapshot directly to your machine.
   - **Safe Rollback**: Restore the database to any earlier state (the system automatically takes a safety snapshot before restoring).

---

## 5. Running the Automated Test Suites

The project includes **164 automated tests** covering end-to-end ML inference, HTTP endpoints, RBAC permissions, scheduling logic, and database backups.

Ensure the FastAPI server is running on `http://127.0.0.1:8000`, then run:

```bash
# 1. Live End-to-End ML & Scheduling Verification (46 tests)
python tests/verify_all_endpoints.py

# 2. Live HTTP API Validation & RBAC Security Tests (78 tests)
python tests/test_api_endpoints.py

# 3. Automated SQLite Database Backup & Restore Tests (9 tests)
python tests/test_database_backup.py

# 4. Fast Mode vs Deep Diagnostic Mode Benchmark (6 tests)
python tests/test_fast_mode.py

# 5. Core Fleet Unit & Integration Tests (25 tests)
python -m unittest discover tests/
```

All 164 tests should pass with **100% success rate**.

---

## 6. Standalone CLI Utility Scripts

Useful offline scripts in the `scripts/` folder:

```bash
# 1. Run database backup via CLI (creates a lock-free snapshot)
python scripts/backup_db.py

# 2. List all backup snapshots in the archive
python scripts/backup_db.py --list

# 3. Create a gzip-compressed backup snapshot (.db.gz)
python scripts/backup_db.py --compress

# 4. Evaluate YOLOv8 model performance against held-out test split
python scripts/evaluate_model.py

# 5. Clean up redundant test trains (keeps canonical 5 fleet trains)
python scripts/cleanup_trains.py
```

---

## 7. Troubleshooting & Common Questions

### Q1: The backend says "Address already in use" on port 8000.
**Fix:** Another process is using port 8000. Either terminate the old process or specify a different port:
```bash
# On Windows:
netstat -ano | findstr :8000
taskkill /F /PID <PID_NUMBER>

# Or run uvicorn on another port:
python -m uvicorn main:app --port 8001 --reload
```
*(If you change ports, update `VITE_API_URL` in `frontend/.env`).*

---

### Q2: Why does `localhost` feel slow on Windows?
**Fix:** Windows resolves `localhost` over IPv6 first, causing a 2-second timeout before falling back to IPv4. Always use **`http://127.0.0.1:8000`** in your browser and `.env` file for instant sub-millisecond responses.

---

### Q3: How do I reset the database to a fresh state?
**Fix:** Simply delete `database/railway.db`. On next backend launch, FastAPI will automatically initialize a fresh database with standard fleet tables and default test trains.

---

### Q4: Can I run without a GPU?
**Fix:** Yes! PyTorch and Ultralytics YOLOv8 will automatically run on CPU if no CUDA GPU is detected. Fast Mode single-pass takes ~3.0 seconds on standard CPU hardware.
