"""
core/wheel_lifecycle/report_generator.py
=========================================
Generates depot-grade Maintenance Work Orders (PDF) and operational data exports (CSV)
for railway wheel health inspections, defect diagnostics, and scheduling jobs.

Features:
  - Generates comprehensive PDF Work Tickets with railway branding.
  - Embeds dual-panel diagnostic imagery: YOLOv8 defect bounding boxes and Layer-CAM attention heatmaps.
  - Includes defect itemization, risk diagnostics, scheduling conflict analysis, and RDSO sign-off checklist.
  - Exports maintenance jobs and wheel histories to standard CSV spreadsheets.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from core.wheel_lifecycle.database import DatabaseManager
from core.wheel_lifecycle.fleet_repository import FleetRepository
from core.wheel_lifecycle.repository import WheelRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_image_path(path_str: Optional[str]) -> Optional[Path]:
    """Resolve an image path stored in the DB to an existing local file."""
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_file():
        return p
    # Relative to project root
    p2 = PROJECT_ROOT / path_str.lstrip("/\\")
    if p2.is_file():
        return p2
    # In outputs directory
    p3 = PROJECT_ROOT / "outputs" / p.name
    if p3.is_file():
        return p3
    p4 = PROJECT_ROOT / "outputs" / "annotated" / p.name
    if p4.is_file():
        return p4
    p5 = PROJECT_ROOT / "outputs" / "gradcam" / p.name
    if p5.is_file():
        return p5
    p6 = PROJECT_ROOT / "outputs" / "uploads" / p.name
    if p6.is_file():
        return p6
    return None


class ReportGenerator:
    """Generates PDF Work Orders and CSV exports for the Railway Wheel Health system."""

    def __init__(self):
        self.db = DatabaseManager().connection
        self.fleet_repo = FleetRepository()
        self.wheel_repo = WheelRepository()

    # ═════════════════════════════════════════════════════════════════════════
    # PDF WORK ORDER GENERATION
    # ═════════════════════════════════════════════════════════════════════════

    def generate_work_order_pdf(self, job_id: int) -> bytes:
        """Generate a complete Maintenance Work Order PDF for a specific maintenance job."""
        job = self.fleet_repo.get_maintenance_job(job_id)
        if not job:
            raise ValueError(f"Maintenance Job #{job_id} not found.")

        # Train & Coach
        train = self.fleet_repo.get_train_by_id(job["train_id"]) if job.get("train_id") else None
        coach = self.fleet_repo.get_coach_by_id(job["coach_id"]) if job.get("coach_id") else None
        wheel = self.wheel_repo.get_wheel(job["wheel_asset_id"])

        # Inspection Event & Defect Records
        event = None
        if job.get("inspection_event_id"):
            event = self.fleet_repo.get_inspection_event(job["inspection_event_id"])
        
        # If no direct event found, get latest inspection event for this wheel
        if not event:
            events = self.fleet_repo.list_inspection_events_for_wheel(job["wheel_asset_id"])
            if events:
                event = events[0]

        # Fetch defect records
        defects = []
        if event and event.get("event_id"):
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT * FROM inspections WHERE inspection_event_id=? ORDER BY risk_score DESC",
                (event["event_id"],),
            )
            defects = [dict(r) for r in cursor.fetchall()]

        if not defects:
            # Fallback to wheel inspection history
            defects = self.wheel_repo.get_history(job["wheel_asset_id"])

        return self._build_pdf(
            doc_title=f"WORK ORDER #WO-JOB-{job_id:04d}",
            ref_number=f"WO-JOB-{job_id:04d}",
            job=job,
            event=event,
            train=train,
            coach=coach,
            wheel=wheel,
            defects=defects,
        )

    def generate_inspection_work_order_pdf(self, event_or_inspection_id: str) -> bytes:
        """Generate a Work Order / Inspection Report PDF from an inspection event ID."""
        event = self.fleet_repo.get_inspection_event(event_or_inspection_id)
        single_inspection = None
        if not event:
            # Maybe it's a legacy inspection_id
            single_inspection = self.wheel_repo.get_inspection(event_or_inspection_id)
            if not single_inspection:
                raise ValueError(f"Inspection ID or Event '{event_or_inspection_id}' not found.")

        asset_id = event["asset_id"] if event else single_inspection["asset_id"]
        wheel = self.wheel_repo.get_wheel(asset_id)
        train_id = event.get("train_id") if event else (wheel.get("train_id") if wheel else None)
        coach_id = event.get("coach_id") if event else (wheel.get("coach_id") if wheel else None)

        train = self.fleet_repo.get_train_by_id(train_id) if train_id else None
        coach = self.fleet_repo.get_coach_by_id(coach_id) if coach_id else None

        # Defect records
        if event:
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT * FROM inspections WHERE inspection_event_id=? ORDER BY risk_score DESC",
                (event["event_id"],),
            )
            defects = [dict(r) for r in cursor.fetchall()]
            if not defects:
                defects = self.wheel_repo.get_history(asset_id)
        else:
            defects = [single_inspection]

        # Any open job for this wheel?
        jobs = self.fleet_repo.list_jobs(wheel_asset_id=asset_id)
        job = jobs[0] if jobs else None

        ref_no = f"INSP-{event_or_inspection_id[:12]}"
        return self._build_pdf(
            doc_title=f"INSPECTION WORK TICKET #{ref_no}",
            ref_number=ref_no,
            job=job,
            event=event,
            train=train,
            coach=coach,
            wheel=wheel,
            defects=defects,
        )

    def generate_wheel_work_order_pdf(self, wheel_asset_id: str) -> bytes:
        """Generate a Work Order / Health Report PDF for a specific wheel asset."""
        wheel = self.wheel_repo.get_wheel(wheel_asset_id)
        if not wheel:
            raise ValueError(f"Wheel asset '{wheel_asset_id}' not found.")

        train = self.fleet_repo.get_train_by_id(wheel.get("train_id")) if wheel and wheel.get("train_id") else None
        coach = self.fleet_repo.get_coach_by_id(wheel.get("coach_id")) if wheel and wheel.get("coach_id") else None

        events = self.fleet_repo.list_inspection_events_for_wheel(wheel_asset_id)
        event = events[0] if events else None

        defects = self.wheel_repo.get_history(wheel_asset_id)
        jobs = self.fleet_repo.list_jobs(wheel_asset_id=wheel_asset_id)
        job = jobs[0] if jobs else None

        ref_no = f"WHEEL-{wheel_asset_id}"
        return self._build_pdf(
            doc_title=f"WHEEL ASSESSMENT #{ref_no}",
            ref_number=ref_no,
            job=job,
            event=event,
            train=train,
            coach=coach,
            wheel=wheel,
            defects=defects,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # CORE PDF BUILDER
    # ═════════════════════════════════════════════════════════════════════════

    def _build_pdf(
        self,
        doc_title: str,
        ref_number: str,
        job: Optional[Dict[str, Any]],
        event: Optional[Dict[str, Any]],
        train: Optional[Dict[str, Any]],
        coach: Optional[Dict[str, Any]],
        wheel: Optional[Dict[str, Any]],
        defects: List[Dict[str, Any]],
    ) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=32,
            bottomMargin=32,
        )

        styles = getSampleStyleSheet()

        # Custom typography styles
        brand_title = ParagraphStyle(
            "BrandTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#0F172A"),
        )
        doc_header = ParagraphStyle(
            "DocHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#1E3A8A"),
        )
        sub_text = ParagraphStyle(
            "SubText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475569"),
        )
        sec_heading = ParagraphStyle(
            "SecHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=8,
            spaceAfter=4,
        )
        cell_bold = ParagraphStyle(
            "CellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
        )
        header_cell_bold = ParagraphStyle(
            "HeaderCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
        )
        cell_normal = ParagraphStyle(
            "CellNormal",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#334155"),
        )
        caption_style = ParagraphStyle(
            "Caption",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475569"),
        )

        story = []

        # ── 1. Header Banner & Branding ──────────────────────────────────────
        priority = (job.get("priority") if job else None) or "NORMAL"
        priority_color = {
            "CRITICAL": colors.HexColor("#DC2626"),
            "HIGH": colors.HexColor("#EA580C"),
            "MODERATE": colors.HexColor("#D97706"),
            "LOW": colors.HexColor("#16A34A"),
        }.get(priority.upper(), colors.HexColor("#2563EB"))

        job_status = (job.get("job_status") if job else "INSPECTED")

        header_data = [
            [
                Paragraph("<b>INDIAN RAILWAYS &bull; CHAKRAKSH (चक्राक्ष) FLEET INTELLIGENCE</b><br/><font color='#1E3A8A'><b>DEPOT MAINTENANCE WORK ORDER & WHEEL HEALTH TICKET</b></font>", brand_title),
                Paragraph(
                    f"<b>REF: {ref_number}</b><br/>"
                    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>"
                    f"Status: <b>{job_status}</b> &bull; Priority: <b>{priority}</b>",
                    sub_text,
                ),
            ]
        ]
        t_header = Table(header_data, colWidths=[350, 190])
        t_header.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(t_header)
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceBefore=2, spaceAfter=8))

        # ── 2. Asset Identification & Hierarchy ──────────────────────────────
        train_str = f"{train['train_number']} &bull; {train['train_name']}" if train else "N/A"
        coach_str = f"{coach['coach_number']} ({coach.get('coach_type', 'Standard')})" if coach else "N/A"
        wheel_id = wheel.get("wheel_identifier") or (wheel.get("asset_id") if wheel else "N/A")
        asset_id = wheel.get("asset_id") if wheel else (job.get("wheel_asset_id") if job else "N/A")
        axle_pos = f"Axle {wheel.get('axle_number', '-')} ({wheel.get('position', '-')})" if wheel else "N/A"

        asset_table_data = [
            [
                Paragraph("<b>Train / Rake:</b>", cell_bold),
                Paragraph(train_str, cell_normal),
                Paragraph("<b>Coach Identifier:</b>", cell_bold),
                Paragraph(coach_str, cell_normal),
            ],
            [
                Paragraph("<b>Wheel Asset ID:</b>", cell_bold),
                Paragraph(f"<b>{asset_id}</b> ({wheel_id})", cell_normal),
                Paragraph("<b>Axle / Position:</b>", cell_bold),
                Paragraph(axle_pos, cell_normal),
            ],
            [
                Paragraph("<b>Depot / Base:</b>", cell_bold),
                Paragraph("Northern Railway Rolling Stock Depot", cell_normal),
                Paragraph("<b>Wheel Status:</b>", cell_bold),
                Paragraph(f"<b>{wheel.get('status', 'Monitor') if wheel else 'Monitor'}</b>", cell_normal),
            ],
        ]
        t_asset = Table(asset_table_data, colWidths=[105, 165, 105, 165])
        t_asset.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(Paragraph("1. Rolling Stock Asset Identification", sec_heading))
        story.append(t_asset)
        story.append(Spacer(1, 6))

        # ── 3. Health & Risk Diagnostics ─────────────────────────────────────
        risk_score = (
            (job.get("risk_score") if job else None)
            or (event.get("wheel_risk_score") if event else None)
            or (defects[0].get("risk_score") if defects else 0.0)
            or 0.0
        )
        recommended_action = (
            (job.get("recommended_action") if job else None)
            or (event.get("wheel_recommended_action") if event else None)
            or (defects[0].get("recommended_action") if defects else "Routine wayside monitoring")
            or "Routine wayside monitoring"
        )
        trend = (event.get("trend_status") if event else None) or (defects[0].get("trend_status") if defects else "STABLE")
        reliability = defects[0].get("reliability", "High") if defects else "High"
        std_dev = defects[0].get("std_deviation", 0.02) if defects else 0.02

        diag_data = [
            [
                Paragraph("<b>Aggregate Risk Score:</b>", cell_bold),
                Paragraph(f"<font color='{priority_color.hexval()}'><b>{risk_score:.1f} / 100</b></font>", cell_normal),
                Paragraph("<b>Recommended Action:</b>", cell_bold),
                Paragraph(f"<b>{recommended_action}</b>", cell_normal),
            ],
            [
                Paragraph("<b>Degradation Trend:</b>", cell_bold),
                Paragraph(f"<b>{trend}</b>", cell_normal),
                Paragraph("<b>TTA Model Reliability:</b>", cell_bold),
                Paragraph(f"{reliability} (spread: {std_dev})", cell_normal),
            ],
        ]
        t_diag = Table(diag_data, colWidths=[115, 155, 115, 155])
        t_diag.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(Paragraph("2. Health Diagnostics & Risk Assessment", sec_heading))
        story.append(t_diag)
        story.append(Spacer(1, 6))

        # ── 4. Itemized Defect Records Table ─────────────────────────────────
        story.append(Paragraph("3. Detected Defect Specifications", sec_heading))
        defect_rows = [
            [
                Paragraph("<b>Defect Class</b>", header_cell_bold),
                Paragraph("<b>Severity</b>", header_cell_bold),
                Paragraph("<b>Confidence</b>", header_cell_bold),
                Paragraph("<b>Risk Score</b>", header_cell_bold),
                Paragraph("<b>Recommended Maintenance</b>", header_cell_bold),
            ]
        ]

        if defects and any(d.get("defect_type") for d in defects):
            for d in defects:
                if not d.get("defect_type"):
                    continue
                d_type = d.get("defect_type") or "Anomaly"
                d_sev = d.get("severity") or "Mild"
                d_conf = f"{float(d.get('confidence', 0)):.1%}" if d.get("confidence") is not None else "-"
                d_risk = f"{float(d.get('risk_score', 0)):.1f}" if d.get("risk_score") is not None else "-"
                d_act = d.get("recommended_action") or "Monitor"
                defect_rows.append([
                    Paragraph(f"<b>{d_type}</b>", cell_normal),
                    Paragraph(d_sev, cell_normal),
                    Paragraph(d_conf, cell_normal),
                    Paragraph(d_risk, cell_normal),
                    Paragraph(d_act, cell_normal),
                ])
        else:
            defect_rows.append([
                Paragraph("No active surface defects detected.", cell_normal),
                Paragraph("Healthy", cell_normal),
                Paragraph("-", cell_normal),
                Paragraph("0.0", cell_normal),
                Paragraph("Routine wayside monitoring", cell_normal),
            ])

        t_defects = Table(defect_rows, colWidths=[110, 80, 75, 75, 200])
        t_defects.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(t_defects)
        story.append(Spacer(1, 8))

        # ── 5. Visual Inspection Imagery (Side-by-side callouts) ───────────────
        annotated_path = (
            (event.get("annotated_image_path") if event else None)
            or (defects[0].get("annotated_image_path") if defects else None)
        )
        gradcam_path = (
            (event.get("gradcam_image_path") if event else None)
            or (defects[0].get("gradcam_image_path") if defects else None)
        )

        img_ann_file = _resolve_image_path(annotated_path)
        img_cam_file = _resolve_image_path(gradcam_path)

        story.append(Paragraph("4. Computer Vision Diagnostic Visuals", sec_heading))

        img_col_w = 260
        img_h = 140

        left_cell = []
        if img_ann_file and img_ann_file.is_file():
            try:
                left_cell.append(RLImage(str(img_ann_file), width=img_col_w - 10, height=img_h))
            except Exception:
                left_cell.append(Paragraph("<i>[Annotated Defect Image File Unavailable]</i>", caption_style))
        else:
            left_cell.append(Paragraph("<i>[Annotated Detection Image Unavailable]</i>", caption_style))
        left_cell.append(Paragraph("<b>Figure A: YOLOv8 Surface Defect Bounding Boxes</b>", caption_style))

        right_cell = []
        if img_cam_file and img_cam_file.is_file():
            try:
                right_cell.append(RLImage(str(img_cam_file), width=img_col_w - 10, height=img_h))
            except Exception:
                right_cell.append(Paragraph("<i>[Layer-CAM Heatmap File Unavailable]</i>", caption_style))
        else:
            right_cell.append(Paragraph("<i>[Layer-CAM Heatmap Unavailable]</i>", caption_style))
        right_cell.append(Paragraph("<b>Figure B: Layer-CAM Deep Attention Heatmap</b>", caption_style))

        t_images = Table([[left_cell, right_cell]], colWidths=[img_col_w, img_col_w])
        t_images.setStyle(
            TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(t_images)
        story.append(Spacer(1, 8))

        # ── 6. Intelligent Scheduling & Maintenance Execution ────────────────
        s_start = job.get("confirmed_start") or job.get("suggested_start") if job else None
        s_end = job.get("suggested_end") if job else None
        window_str = f"{s_start} &rarr; {s_end}" if (s_start and s_end) else (s_start or "Next Scheduled Depot Overhaul")

        conflict_notes = []
        if job and job.get("conflict_notes"):
            notes_raw = job["conflict_notes"]
            if isinstance(notes_raw, list):
                conflict_notes = notes_raw
            elif isinstance(notes_raw, str):
                try:
                    conflict_notes = json.loads(notes_raw)
                except Exception:
                    conflict_notes = [notes_raw]

        hold_req = "YES &mdash; MANDATORY OPERATIONAL HOLD (DO NOT RELEASE TRAIN)" if priority == "CRITICAL" else "NO &mdash; Clear to operate until depot arrival"
        sched_data = [
            [
                Paragraph("<b>Suggested Depot Window:</b>", cell_bold),
                Paragraph(window_str, cell_normal),
                Paragraph("<b>Operational Clearance Required:</b>", cell_bold),
                Paragraph(f"<b>{hold_req}</b>", cell_normal),
            ],
            [
                Paragraph("<b>Operating Conflict Status:</b>", cell_bold),
                Paragraph(
                    "<font color='#DC2626'><b>CONFLICT DETECTED</b></font>" if conflict_notes else "<font color='#16A34A'><b>CLEARED (No Overlap)</b></font>",
                    cell_normal,
                ),
                Paragraph("<b>Conflict Notes:</b>", cell_bold),
                Paragraph("; ".join(conflict_notes) if conflict_notes else "None. Depot slot aligned with maintenance availability.", cell_normal),
            ],
        ]
        t_sched = Table(sched_data, colWidths=[120, 150, 120, 150])
        t_sched.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(Paragraph("5. Depot Scheduling & Operational Feasibility", sec_heading))
        story.append(t_sched)
        story.append(Spacer(1, 8))

        # ── 7. Maintenance Execution Checklist & Depot Sign-Off ───────────────
        checklist_data = [
            [
                Paragraph("<b>Depot Work Order Verification Checklist:</b>", cell_bold),
                Paragraph("<b>Inspection & Authorisation Sign-Off:</b>", cell_bold),
            ],
            [
                Paragraph(
                    "[ &nbsp; ] Wheel Lathe Reprofiling & Truing completed<br/>"
                    "[ &nbsp; ] Ultrasonic Flaw Detection (USFD) crack depth check<br/>"
                    "[ &nbsp; ] Axle Bearing & Journal inspection completed<br/>"
                    "[ &nbsp; ] Flange & Tread dimensions within RDSO clearance",
                    cell_normal,
                ),
                Paragraph(
                    "Inspecting Engineer: _________________________<br/>"
                    "Emp ID / Designation: _______________________<br/>"
                    "Depot Foreman Sign: ________________________<br/>"
                    "Release Date / Time: ________________________",
                    cell_normal,
                ),
            ],
        ]
        t_sign = Table(checklist_data, colWidths=[270, 270])
        t_sign.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(Paragraph("6. Work Execution Checklist & Depot Sign-Off", sec_heading))
        story.append(t_sign)

        # Build document
        doc.build(story)
        buf.seek(0)
        return buf.getvalue()

    # ═════════════════════════════════════════════════════════════════════════
    # CSV EXPORTS
    # ═════════════════════════════════════════════════════════════════════════

    def generate_jobs_csv(self) -> str:
        """Export all maintenance jobs with train/coach details as a CSV string."""
        jobs = self.fleet_repo.list_jobs()
        trains_map = {t["id"]: t for t in self.fleet_repo.list_trains()}
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM coaches")
        coaches_map = {c["id"]: dict(c) for c in cursor.fetchall()}

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([
            "Job ID",
            "Train Number",
            "Train Name",
            "Coach Number",
            "Coach Type",
            "Wheel Asset ID",
            "Priority",
            "Risk Score",
            "Job Status",
            "Recommended Action",
            "Suggested Start",
            "Suggested End",
            "Confirmed Start",
            "Conflict Notes",
            "Created At",
            "Last Updated",
        ])

        for j in jobs:
            t = trains_map.get(j.get("train_id"), {})
            c = coaches_map.get(j.get("coach_id"), {})
            conflict = j.get("conflict_notes") or ""
            if isinstance(conflict, list):
                conflict = "; ".join(conflict)

            writer.writerow([
                j.get("id"),
                t.get("train_number", ""),
                t.get("train_name", ""),
                c.get("coach_number", ""),
                c.get("coach_type", ""),
                j.get("wheel_asset_id", ""),
                j.get("priority", ""),
                f"{float(j.get('risk_score', 0)):.1f}" if j.get("risk_score") is not None else "",
                j.get("job_status", ""),
                j.get("recommended_action", ""),
                j.get("suggested_start", ""),
                j.get("suggested_end", ""),
                j.get("confirmed_start", ""),
                conflict,
                j.get("created_at", ""),
                j.get("last_updated", ""),
            ])

        return out.getvalue()

    def generate_wheel_history_csv(self, wheel_asset_id: str) -> str:
        """Export full defect inspection history for a specific wheel as CSV."""
        history = self.wheel_repo.get_history(wheel_asset_id)
        wheel = self.wheel_repo.get_wheel(wheel_asset_id)
        train = self.fleet_repo.get_train_by_id(wheel.get("train_id")) if wheel and wheel.get("train_id") else None

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([
            "Wheel Asset ID",
            "Wheel Identifier",
            "Train Number",
            "Axle Number",
            "Position",
            "Inspection Date",
            "Defect Type",
            "Severity",
            "Confidence",
            "Risk Score",
            "Recommended Action",
            "Reliability",
            "Std Deviation",
            "Processing Time (s)",
            "Notes",
        ])

        for h in history:
            writer.writerow([
                wheel_asset_id,
                wheel.get("wheel_identifier", "") if wheel else "",
                train.get("train_number", "") if train else "",
                wheel.get("axle_number", "") if wheel else "",
                wheel.get("position", "") if wheel else "",
                h.get("inspection_date", ""),
                h.get("defect_type", "None"),
                h.get("severity", "Healthy"),
                f"{float(h.get('confidence', 0)):.2f}" if h.get("confidence") is not None else "",
                f"{float(h.get('risk_score', 0)):.1f}" if h.get("risk_score") is not None else "",
                h.get("recommended_action", ""),
                h.get("reliability", ""),
                h.get("std_deviation", ""),
                h.get("processing_time", ""),
                h.get("notes", ""),
            ])

        return out.getvalue()
