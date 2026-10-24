"""
routers/maintenance.py
======================
Maintenance Job Management — REST endpoints.

POST   /api/maintenance/recommend/{wheel_asset_id}   Generate recommendation
GET    /api/maintenance/jobs                          List all jobs
GET    /api/maintenance/jobs/pending                  Pending jobs
GET    /api/maintenance/jobs/urgent                   CRITICAL priority jobs
GET    /api/maintenance/jobs/{job_id}                 Get a specific job
POST   /api/maintenance/jobs/{job_id}/confirm         Confirm a maintenance slot
PATCH  /api/maintenance/jobs/{job_id}/status          Update job status
GET    /api/maintenance/history/{wheel_asset_id}      Maintenance history for a wheel
GET    /api/trains/{train_id}/maintenance/jobs        Jobs for a specific train
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as FPath, Query, Response
from pydantic import BaseModel, Field

from core.wheel_lifecycle.fleet_repository import FleetRepository
from core.wheel_lifecycle.repository import WheelRepository
from core.wheel_lifecycle.report_generator import ReportGenerator
from core.wheel_lifecycle.auth import require_role, ROLE_MAINTENANCE_SUPERVISOR, ROLE_OPERATOR
from maintenance_priority.scheduler import generate_maintenance_recommendation

router = APIRouter(prefix="/api", tags=["Maintenance Jobs"])

VALID_JOB_STATUSES = {"PENDING", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}


# ── Pydantic models ───────────────────────────────────────────────────────────

class UrgentEscalateRequest(BaseModel):
    wheel_asset_id: Optional[str] = None
    train_id: Optional[int] = None
    notes: Optional[str] = None


class ScheduleSlotRequest(BaseModel):
    wheel_asset_id: Optional[str] = None
    train_id: Optional[int] = None
    start_datetime: str
    end_datetime: str
    notes: Optional[str] = None

class MaintenanceJobResponse(BaseModel):
    id: int
    train_id: Optional[int]
    coach_id: Optional[int]
    wheel_asset_id: str
    inspection_event_id: Optional[str]
    risk_score: Optional[float]
    priority: str
    recommended_action: Optional[str]
    suggested_start: Optional[str]
    suggested_end: Optional[str]
    confirmed_start: Optional[str]
    job_status: str
    completion_notes: Optional[str]
    created_at: str
    last_updated: str
    scheduling_status: Optional[str] = None
    scheduling_notes: Optional[str] = None
    conflict_notes: List[str] = []
    requires_operational_clearance: bool = False


class ConfirmSlotRequest(BaseModel):
    confirmed_start: str = Field(..., description="ISO8601 datetime to confirm e.g. 2026-10-25T08:00:00")


class StatusUpdateRequest(BaseModel):
    job_status: str = Field(..., description="PENDING | SCHEDULED | IN_PROGRESS | COMPLETED | CANCELLED")
    completion_notes: Optional[str] = None


class RecommendationResponse(BaseModel):
    wheel_asset_id: str
    risk_score: float
    priority: str
    recommended_action: str
    trend_status: str
    suggested_start: Optional[str]
    suggested_end: Optional[str]
    scheduling_status: str
    scheduling_notes: str
    conflict_notes: List[str]
    requires_operational_clearance: bool
    maintenance_job_id: Optional[int] = None
    duplicate_job: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_or_404(repo: FleetRepository, job_id: int):
    j = repo.get_maintenance_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail=f"Maintenance job {job_id} not found.")
    return j


def _enrich_job(j: Dict[str, Any]) -> MaintenanceJobResponse:
    d = dict(j)
    sched_status = d.get("scheduling_status")
    if not sched_status:
        if d.get("confirmed_start"):
            sched_status = "CONFIRMED"
        elif d.get("suggested_start"):
            sched_status = "SCHEDULED"
        else:
            sched_status = "ROUTINE"
    d["scheduling_status"] = sched_status
    if "requires_operational_clearance" not in d or d["requires_operational_clearance"] is None:
        d["requires_operational_clearance"] = (d.get("priority") == "CRITICAL")
    if "conflict_notes" not in d or d["conflict_notes"] is None:
        d["conflict_notes"] = []
    if "scheduling_notes" not in d or d["scheduling_notes"] is None:
        d["scheduling_notes"] = d.get("completion_notes") or ""
    return MaintenanceJobResponse(**d)


# ═════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION ENDPOINT
# ═════════════════════════════════════════════════════════════════════════════

@router.post(
    "/maintenance/recommend/{wheel_asset_id}",
    response_model=RecommendationResponse,
    summary="Generate maintenance recommendation for a wheel",
    description=(
        "Uses the existing risk score, defect info, trend status and train schedule "
        "to generate a maintenance recommendation. If no open job exists for the wheel, "
        "a PENDING maintenance job is automatically created. "
        "The job becomes SCHEDULED only after explicit confirmation."
    ),
)
def recommend_maintenance(
    wheel_asset_id: str = FPath(..., description="Wheel asset ID e.g. WH000001"),
    inspection_event_id: Optional[str] = Query(None, description="Link to a specific inspection event"),
    current_user: dict = Depends(require_role(ROLE_MAINTENANCE_SUPERVISOR)),
):
    fleet_repo = FleetRepository()
    wheel_repo = WheelRepository()

    wheel = wheel_repo.get_wheel(wheel_asset_id)
    if not wheel:
        raise HTTPException(status_code=404, detail=f"Wheel '{wheel_asset_id}' not found.")

    # Gather context from most recent inspection event (if any)
    events = fleet_repo.list_inspection_events_for_wheel(wheel_asset_id)
    event: Optional[Dict[str, Any]] = None
    if inspection_event_id:
        event = fleet_repo.get_inspection_event(inspection_event_id)
    elif events:
        event = events[0]

    if not event:
        # No inspection data — cannot make a recommendation
        raise HTTPException(
            status_code=422,
            detail=(
                f"No inspection events found for wheel '{wheel_asset_id}'. "
                "Run an inspection first before requesting a maintenance recommendation."
            ),
        )

    risk_score = event.get("wheel_risk_score", 0.0) or 0.0
    recommended_action = event.get("wheel_recommended_action", "Monitor only") or "Monitor only"
    trend_status = event.get("trend_status", "FIRST_INSPECTION") or "FIRST_INSPECTION"
    train_id_raw = event.get("train_id") or wheel.get("train_id")
    coach_id_raw = event.get("coach_id") or wheel.get("coach_id")

    train_id: Optional[int] = None
    if train_id_raw:
        try:
            train_id = int(train_id_raw)
        except (ValueError, TypeError):
            pass

    coach_id: Optional[int] = None
    if coach_id_raw:
        try:
            coach_id = int(coach_id_raw)
        except (ValueError, TypeError):
            pass

    # Pull inspection defect rows for context
    history = wheel_repo.get_history(wheel_asset_id)
    if event.get("event_id"):
        # Defects from this specific event
        defect_rows = [
            r for r in history
            if r.get("inspection_event_id") == event.get("event_id")
        ]
        if not defect_rows:
            defect_rows = history[:5]
    else:
        defect_rows = history[:5]

    defect_types = [r["defect_type"] for r in defect_rows if r.get("defect_type")]
    severities = [r["severity"] for r in defect_rows if r.get("severity")]
    reliabilities = [r["reliability"] for r in defect_rows if r.get("reliability")]

    # Train operating schedule
    maintenance_windows: List[Dict] = []
    operating_schedules: List[Dict] = []
    if train_id:
        maintenance_windows = fleet_repo.get_maintenance_windows_for_train(train_id)
        operating_schedules = fleet_repo.list_schedules_for_train(train_id, active_only=True)

    recommendation = generate_maintenance_recommendation(
        wheel_asset_id=wheel_asset_id,
        risk_score=risk_score,
        recommended_action=recommended_action,
        trend_status=trend_status,
        defect_types=defect_types,
        severities=severities,
        reliabilities=reliabilities,
        train_id=train_id,
        maintenance_windows=maintenance_windows,
        operating_schedules=operating_schedules,
        inspection_event_id=event.get("event_id"),
    )

    # Check for existing open job (avoid duplicates)
    job_id: Optional[int] = None
    is_duplicate = fleet_repo.has_open_job_for_wheel(wheel_asset_id)
    if not is_duplicate:
        job = fleet_repo.create_maintenance_job(
            wheel_asset_id=wheel_asset_id,
            risk_score=risk_score,
            priority=recommendation["priority"],
            recommended_action=recommended_action,
            train_id=train_id,
            coach_id=coach_id,
            inspection_event_id=event.get("event_id"),
            suggested_start=recommendation.get("suggested_start"),
            suggested_end=recommendation.get("suggested_end"),
        )
        job_id = job["id"]

    return RecommendationResponse(
        **{k: v for k, v in recommendation.items() if k != "inspection_event_id"},
        maintenance_job_id=job_id,
        duplicate_job=is_duplicate,
    )


# ═════════════════════════════════════════════════════════════════════════════
# MAINTENANCE JOB LISTING
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/maintenance/jobs",
    response_model=List[MaintenanceJobResponse],
    summary="List all maintenance jobs",
)
def list_all_jobs(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    train_id: Optional[int] = Query(None),
):
    repo = FleetRepository()
    jobs = repo.list_jobs(train_id=train_id, status=status, priority=priority)
    return [_enrich_job(j) for j in jobs]


@router.get(
    "/maintenance/jobs/pending",
    response_model=List[MaintenanceJobResponse],
    summary="List pending maintenance jobs",
)
def list_pending_jobs():
    repo = FleetRepository()
    return [_enrich_job(j) for j in repo.list_jobs(status="PENDING")]


@router.get(
    "/maintenance/jobs/urgent",
    response_model=List[MaintenanceJobResponse],
    summary="List urgent (CRITICAL priority) maintenance jobs",
)
def list_urgent_jobs():
    repo = FleetRepository()
    return [_enrich_job(j) for j in repo.list_jobs(priority="CRITICAL")]


@router.get(
    "/trains/{train_id}/maintenance/jobs",
    response_model=List[MaintenanceJobResponse],
    summary="List maintenance jobs for a specific train",
)
def list_train_jobs(
    train_id: int = FPath(...),
    status: Optional[str] = Query(None),
):
    repo = FleetRepository()
    if not repo.get_train_by_id(train_id):
        raise HTTPException(status_code=404, detail=f"Train {train_id} not found.")
    jobs = repo.list_jobs(train_id=train_id, status=status)
    return [_enrich_job(j) for j in jobs]


@router.get(
    "/maintenance/history/{wheel_asset_id}",
    response_model=List[MaintenanceJobResponse],
    summary="Maintenance history for a wheel (all jobs including completed)",
)
def maintenance_history_for_wheel(wheel_asset_id: str = FPath(...)):
    repo = FleetRepository()
    jobs = repo.list_jobs(wheel_asset_id=wheel_asset_id)
    return [_enrich_job(j) for j in jobs]


@router.get(
    "/maintenance/jobs/export/csv",
    summary="Export all maintenance jobs as a CSV spreadsheet",
)
def export_jobs_csv():
    generator = ReportGenerator()
    csv_text = generator.generate_jobs_csv()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="maintenance_jobs.csv"'},
    )


@router.get(
    "/maintenance/jobs/{job_id}/work-order-pdf",
    summary="Generate and download a Depot Maintenance Work Order PDF",
)
def download_job_work_order_pdf(job_id: int = FPath(...)):
    repo = FleetRepository()
    _job_or_404(repo, job_id)
    generator = ReportGenerator()
    try:
        pdf_bytes = generator.generate_work_order_pdf(job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate work order PDF: {e}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="work_order_job_{job_id}.pdf"'},
    )


@router.get(
    "/maintenance/jobs/{job_id}",
    response_model=MaintenanceJobResponse,
    summary="Get a specific maintenance job",
)
def get_job(job_id: int = FPath(...)):
    repo = FleetRepository()
    return _enrich_job(_job_or_404(repo, job_id))


# ═════════════════════════════════════════════════════════════════════════════
# JOB ACTIONS
# ═════════════════════════════════════════════════════════════════════════════

@router.post(
    "/maintenance/jobs/{job_id}/confirm",
    response_model=MaintenanceJobResponse,
    summary="Confirm a suggested maintenance slot",
    description=(
        "Moves the job from PENDING → SCHEDULED and records the confirmed start time. "
        "Validates for overlapping confirmed jobs on the same wheel."
    ),
)
def confirm_maintenance_slot(
    body: ConfirmSlotRequest,
    job_id: int = FPath(...),
    current_user: dict = Depends(require_role(ROLE_MAINTENANCE_SUPERVISOR)),
):
    repo = FleetRepository()
    job = _job_or_404(repo, job_id)

    if job["job_status"] not in ("PENDING",):
        raise HTTPException(
            status_code=409,
            detail=f"Job is already in status '{job['job_status']}'. Only PENDING jobs can be confirmed.",
        )

    # Validate no overlapping confirmed jobs for the same wheel
    suggested_end = job.get("suggested_end") or body.confirmed_start
    if repo.has_confirmed_job_overlap(
        wheel_asset_id=job["wheel_asset_id"],
        start_dt=body.confirmed_start,
        end_dt=suggested_end,
        exclude_job_id=job_id,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"A confirmed maintenance job already exists for wheel "
                f"'{job['wheel_asset_id']}' overlapping the requested time slot. "
                "Choose a different time or cancel the existing job first."
            ),
        )

    # Validate against train operating schedule
    train_id_raw = job.get("train_id")
    if train_id_raw:
        conflicts = repo.get_operating_dates_in_range(
            train_id=int(train_id_raw),
            start_dt=body.confirmed_start,
            end_dt=suggested_end,
        )
        if conflicts and job.get("priority") not in ("CRITICAL",):
            # For non-critical, warn but allow with a note
            pass  # could raise 409 if stricter policy desired

    updated = repo.update_maintenance_job(
        job_id=job_id,
        job_status="SCHEDULED",
        confirmed_start=body.confirmed_start,
    )
    return _enrich_job(updated)


@router.patch(
    "/maintenance/jobs/{job_id}/status",
    response_model=MaintenanceJobResponse,
    summary="Update maintenance job status",
)
def update_job_status(
    body: StatusUpdateRequest,
    job_id: int = FPath(...),
    current_user: dict = Depends(require_role(ROLE_MAINTENANCE_SUPERVISOR)),
):
    if body.job_status not in VALID_JOB_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"job_status must be one of {sorted(VALID_JOB_STATUSES)}.",
        )
    repo = FleetRepository()
    wheel_repo = WheelRepository()
    job = _job_or_404(repo, job_id)
    target_status = body.job_status
    wheel_asset_id = job.get("wheel_asset_id")

    train_id = job.get("train_id")
    coach_id = job.get("coach_id")

    # If job has no train_id, ensure a train is associated or created for this wheel/job
    if not train_id and wheel_asset_id:
        train_num = f"TR-{wheel_asset_id}"
        train = repo.get_train_by_number(train_num)
        if not train:
            status_for_new_train = "Under Maintenance" if target_status == "IN_PROGRESS" else "Active"
            train = repo.create_train(
                train_number=train_num,
                train_name=f"Express {wheel_asset_id}",
                train_type="Superfast Express",
                operational_status=status_for_new_train,
            )
            train_id = train["id"]
            coach = repo.add_coach(train_id, f"C1-{wheel_asset_id}", "AC")
            coach_id = coach["id"]
            cursor = repo.db.cursor()
            cursor.execute(
                "UPDATE wheels SET coach_id=?, train_id=? WHERE asset_id=?",
                (str(coach_id), str(train_id), wheel_asset_id),
            )
            now_dt = datetime.now()
            repo.add_schedule(
                train_id=train_id,
                schedule_type="OPERATING",
                departure_datetime=(now_dt + timedelta(days=1, hours=8)).isoformat(timespec="seconds"),
                arrival_datetime=(now_dt + timedelta(days=1, hours=16)).isoformat(timespec="seconds"),
                notes="Daily express run",
                status="ACTIVE",
            )
            repo.add_schedule(
                train_id=train_id,
                schedule_type="MAINTENANCE_WINDOW",
                departure_datetime=(now_dt + timedelta(days=3, hours=2)).isoformat(timespec="seconds"),
                arrival_datetime=(now_dt + timedelta(days=3, hours=8)).isoformat(timespec="seconds"),
                notes="Planned maintenance slot",
                status="ACTIVE",
            )
            repo.db.commit()
        else:
            train_id = train["id"]
            coaches = repo.list_coaches_for_train(train_id)
            if coaches:
                coach_id = coaches[0]["id"]
            status_to_set = "Under Maintenance" if target_status == "IN_PROGRESS" else "Active"
            repo.update_train(train_id, operational_status=status_to_set)

    # When transitioning to IN_PROGRESS (Start job)
    if target_status == "IN_PROGRESS":
        if train_id:
            repo.update_train(train_id, operational_status="Under Maintenance")

    # When transitioning to COMPLETED (Mark as done)
    elif target_status == "COMPLETED":
        if train_id:
            repo.update_train(train_id, operational_status="Active")
        if wheel_asset_id:
            wheel_repo.update_wheel_status(
                asset_id=wheel_asset_id,
                status="Healthy",
                latest_inspection=datetime.now().isoformat(timespec="seconds"),
            )

    updated = repo.update_maintenance_job(
        job_id=job_id,
        job_status=target_status,
        completion_notes=body.completion_notes or ("Maintenance completed successfully. Wheel inspected and cleared for service." if target_status == "COMPLETED" else None),
        train_id=train_id,
        coach_id=coach_id,
    )
    return _enrich_job(updated)


@router.get(
    "/inspections/{event_or_inspection_id}/work-order-pdf",
    summary="Generate Work Order / Inspection Report PDF from inspection event",
)
def download_inspection_work_order_pdf(event_or_inspection_id: str = FPath(...)):
    generator = ReportGenerator()
    try:
        pdf_bytes = generator.generate_inspection_work_order_pdf(event_or_inspection_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="work_order_{event_or_inspection_id}.pdf"'},
    )


@router.get(
    "/fleet/wheels/{wheel_asset_id}/work-order-pdf",
    summary="Generate Work Order / Health Report PDF for a specific wheel asset",
)
def download_wheel_work_order_pdf(wheel_asset_id: str = FPath(...)):
    generator = ReportGenerator()
    try:
        pdf_bytes = generator.generate_wheel_work_order_pdf(wheel_asset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="work_order_wheel_{wheel_asset_id}.pdf"'},
    )


@router.get(
    "/fleet/wheels/{wheel_asset_id}/export/csv",
    summary="Export defect inspection history for a wheel as CSV",
)
def export_wheel_history_csv(wheel_asset_id: str = FPath(...)):
    wheel_repo = WheelRepository()
    if not wheel_repo.get_wheel(wheel_asset_id):
        raise HTTPException(status_code=404, detail=f"Wheel '{wheel_asset_id}' not found.")
    generator = ReportGenerator()
    csv_text = generator.generate_wheel_history_csv(wheel_asset_id)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="wheel_{wheel_asset_id}_history.csv"'},
    )


@router.post(
    "/maintenance/escalate-urgent",
    response_model=MaintenanceJobResponse,
    summary="Escalate train or wheel maintenance to urgent priority",
    description="Marks wheel maintenance as CRITICAL/Urgent priority, placing an operational hold and alerting the maintenance team ASAP.",
)
def escalate_urgent(
    body: UrgentEscalateRequest,
    current_user: dict = Depends(require_role(ROLE_OPERATOR)),
):
    repo = FleetRepository()
    wheel_id = body.wheel_asset_id
    if not wheel_id and body.train_id:
        train_wheels = repo.list_wheels_for_train(body.train_id)
        critical_wheels = [w for w in train_wheels if w.get("status") == "Critical"]
        wheel_id = critical_wheels[0]["asset_id"] if critical_wheels else (train_wheels[0]["asset_id"] if train_wheels else None)
    if not wheel_id:
        raise HTTPException(
            status_code=400,
            detail="A valid wheel_asset_id or train_id with registered wheels is required.",
        )
    job = repo.escalate_job_urgent(wheel_asset_id=wheel_id, train_id=body.train_id, notes=body.notes)
    return _enrich_job(job)


@router.post(
    "/maintenance/schedule-slot",
    response_model=MaintenanceJobResponse,
    summary="Schedule maintenance for a wheel into a specific slot",
    description="Schedules a low/moderate wear wheel into an upcoming turnaround maintenance window.",
)
def schedule_slot(
    body: ScheduleSlotRequest,
    current_user: dict = Depends(require_role(ROLE_OPERATOR)),
):
    repo = FleetRepository()
    wheel_id = body.wheel_asset_id
    if not wheel_id and body.train_id:
        train_wheels = repo.list_wheels_for_train(body.train_id)
        monitor_wheels = [w for w in train_wheels if w.get("status") == "Monitor"]
        wheel_id = monitor_wheels[0]["asset_id"] if monitor_wheels else (train_wheels[0]["asset_id"] if train_wheels else None)
    if not wheel_id:
        raise HTTPException(
            status_code=400,
            detail="A valid wheel_asset_id or train_id with registered wheels is required.",
        )
    job = repo.schedule_maintenance_slot(
        wheel_asset_id=wheel_id,
        train_id=body.train_id,
        start_datetime=body.start_datetime,
        end_datetime=body.end_datetime,
        notes=body.notes,
    )
    return _enrich_job(job)

