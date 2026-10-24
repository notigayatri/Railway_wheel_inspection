import { useEffect, useMemo, useRef, useState } from "react";
import { createCoach, createSchedule, createTrain, createWheel, deleteCoach, escalateUrgent, getSchedules, getTrainTree, getTrains, scheduleMaintenanceSlot, updateSchedule, updateTrain } from "../api.js";
import { Badge, WheelChip, fmt, human, useLoad } from "../ui.jsx";
import { useAuth } from "../useAuth.js";

function LockIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor" aria-hidden="true" style={{ verticalAlign: "-1px" }}>
      <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H3.75A1.75 1.75 0 0 0 2 7.75v5.5C2 14.216 2.784 15 3.75 15h8.5A1.75 1.75 0 0 0 14 13.25v-5.5A1.75 1.75 0 0 0 12.25 6h-.75V4.5A3.5 3.5 0 0 0 8 1zm2 5H6V4.5a2 2 0 1 1 4 0V6z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" width="11" height="11" fill="currentColor" aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: "4px" }}>
      <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
      <path fillRule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
    </svg>
  );
}

const STATUSES = ["Active", "Under Maintenance", "Decommissioned"];
const TYPES = { OPERATING: ["Operating run", "warn"], MAINTENANCE_WINDOW: ["Maintenance window", "ok"], NON_OPERATING: ["Non-operating", ""] };
const DAY = 864e5;

function useForm(init) {
  const [f, setF] = useState(init);
  const on = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  return [f, on, () => setF(init), setF];
}

/* 7-day lane view: when the train runs, when it is free for maintenance */
function Availability({ items }) {
  const t0 = new Date(); t0.setHours(0, 0, 0, 0);
  const start = t0.getTime(), span = 7 * DAY;
  const pct = (t) => Math.max(0, Math.min(100, ((t - start) / span) * 100));
  const days = Array.from({ length: 7 }, (_, i) => new Date(start + i * DAY));
  return (
    <div className="lanes" role="img" aria-label="Next seven days of operating runs and maintenance windows">
      <div className="lane"><span /><div className="dayrow">{days.map((d) => <span key={+d}>{d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric" })}</span>)}</div></div>
      {Object.entries(TYPES).map(([k, [label]]) => (
        <div className="lane" key={k}>
          <span className="lane-l">{label}</span>
          <div className="track">
            {items.filter((s) => s.schedule_type === k).map((s) => {
              const a = pct(+new Date(s.departure_datetime)), b = pct(+new Date(s.arrival_datetime));
              if (!(b > a)) return null;
              return <i key={s.id} className={`seg ${k} ${s.status === "CANCELLED" ? "off" : ""}`} style={{ left: `${a}%`, width: `${b - a}%` }} title={`${label}: ${fmt(s.departure_datetime)} to ${fmt(s.arrival_datetime)}`} />;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function RegisterTrain({ onDone }) {
  const [f, on, reset] = useForm({ train_number: "", train_name: "", train_type: "Superfast Express", operational_status: "Active" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const detailsRef = useRef(null);
  const { isAdmin } = useAuth();
  const submit = async (e) => {
    e.preventDefault();
    if (!isAdmin) return;
    setBusy(true); setMsg("");
    try {
      const t = await createTrain({ ...f, train_number: f.train_number.trim(), train_name: f.train_name.trim() });
      reset();
      if (detailsRef.current) detailsRef.current.open = false;
      onDone(t);
    } catch (x) {
      setMsg(x.message);
    }
    setBusy(false);
  };
  return (
    <details ref={detailsRef} className="addbox">
      <summary>
        <span className={!isAdmin ? "rbac-scratched" : ""}>Register a train</span>
        {!isAdmin && <span className="rbac-lock-pill admin" style={{ marginLeft: ".6rem" }}><LockIcon /> Chief Engineer Only</span>}
      </summary>
      <form onSubmit={submit}>
        {!isAdmin && (
          <div className="rbac-lock-banner">
            <LockIcon />
            <span>Authority Insufficient: Chief Engineer (Level 3) clearance required to register rolling stock.</span>
          </div>
        )}
        <div className={`inline ${!isAdmin ? "rbac-locked-box" : ""}`}>
          <label>Train number<input required disabled={!isAdmin} value={f.train_number} onChange={on("train_number")} placeholder="e.g. 12627" /></label>
          <label>Train name<input required disabled={!isAdmin} value={f.train_name} onChange={on("train_name")} placeholder="e.g. Karnataka Express" /></label>
          <label>Type<input disabled={!isAdmin} value={f.train_type} onChange={on("train_type")} /></label>
          <label>Status<select disabled={!isAdmin} value={f.operational_status} onChange={on("operational_status")}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
        {msg && <p className="error" style={{ marginTop: ".7rem" }}>{msg}</p>}
        <button className={`primary sm ${!isAdmin ? "rbac-locked-btn" : ""}`} style={{ marginTop: ".8rem" }} disabled={!isAdmin || busy}>
          {busy ? "Saving..." : !isAdmin ? "Locked · Chief Engineer Only" : "Register train"}
        </button>
      </form>
    </details>
  );
}

function AddCoach({ trainId, onDone }) {
  const [f, on, reset] = useForm({ coach_number: "", coach_type: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const detailsRef = useRef(null);
  const { isAdmin } = useAuth();
  const submit = async (e) => {
    e.preventDefault();
    if (!isAdmin) return;
    setBusy(true); setMsg("");
    try {
      await createCoach(trainId, { coach_number: f.coach_number.trim(), coach_type: f.coach_type.trim() || undefined });
      reset();
      if (detailsRef.current) detailsRef.current.open = false;
      onDone();
    } catch (x) {
      setMsg(x.message);
    }
    setBusy(false);
  };
  return (
    <details ref={detailsRef} className="addbox">
      <summary>
        <span className={!isAdmin ? "rbac-scratched" : ""}>Add a coach</span>
        {!isAdmin && <span className="rbac-lock-pill admin" style={{ marginLeft: ".6rem" }}><LockIcon /> Chief Engineer Only</span>}
      </summary>
      <form onSubmit={submit}>
        {!isAdmin && (
          <div className="rbac-lock-banner">
            <LockIcon />
            <span>Authority Insufficient: Chief Engineer (Level 3) clearance required to attach coaches.</span>
          </div>
        )}
        <div className={`inline ${!isAdmin ? "rbac-locked-box" : ""}`}>
          <label>Coach number<input required disabled={!isAdmin} value={f.coach_number} onChange={on("coach_number")} placeholder="e.g. B3" /></label>
          <label>Coach type<input disabled={!isAdmin} value={f.coach_type} onChange={on("coach_type")} placeholder="e.g. AC 3 Tier" /></label>
        </div>
        {msg && <p className="error" style={{ marginTop: ".7rem" }}>{msg}</p>}
        <button className={`primary sm ${!isAdmin ? "rbac-locked-btn" : ""}`} style={{ marginTop: ".8rem" }} disabled={!isAdmin || busy}>
          {busy ? "Saving..." : !isAdmin ? "Locked · Chief Engineer Only" : "Add coach"}
        </button>
      </form>
    </details>
  );
}

function AddWheel({ coach, onDone }) {
  const [f, on, reset] = useForm({ wheel_identifier: "", axle_number: "1", position: "Left" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const detailsRef = useRef(null);
  const { isAdmin } = useAuth();
  const suggest = `${coach.coach_number}-A${f.axle_number || 1}-${f.position === "Right" ? "R" : "L"}`;
  const submit = async (e) => {
    e.preventDefault();
    if (!isAdmin) return;
    setBusy(true); setMsg("");
    try {
      await createWheel(coach.id, { wheel_identifier: f.wheel_identifier.trim() || suggest, axle_number: Number(f.axle_number), position: f.position });
      reset();
      if (detailsRef.current) detailsRef.current.open = false;
      onDone();
    } catch (x) {
      setMsg(x.message);
    }
    setBusy(false);
  };
  return (
    <details ref={detailsRef} className="addbox">
      <summary>
        <span className={!isAdmin ? "rbac-scratched" : ""}>Add a wheel</span>
        {!isAdmin && <span className="rbac-lock-pill admin" style={{ marginLeft: ".6rem" }}><LockIcon /> Chief Engineer Only</span>}
      </summary>
      <form onSubmit={submit}>
        {!isAdmin && (
          <div className="rbac-lock-banner">
            <LockIcon />
            <span>Authority Insufficient: Chief Engineer (Level 3) clearance required to mount wheelsets.</span>
          </div>
        )}
        <div className={`inline ${!isAdmin ? "rbac-locked-box" : ""}`}>
          <label>Axle<input type="number" min="1" required disabled={!isAdmin} value={f.axle_number} onChange={on("axle_number")} /></label>
          <label>Position<select disabled={!isAdmin} value={f.position} onChange={on("position")}><option>Left</option><option>Right</option></select></label>
          <label>Identifier<input disabled={!isAdmin} value={f.wheel_identifier} onChange={on("wheel_identifier")} placeholder={suggest} /></label>
        </div>
        {msg && <p className="error" style={{ marginTop: ".7rem" }}>{msg}</p>}
        <button className={`primary sm ${!isAdmin ? "rbac-locked-btn" : ""}`} style={{ marginTop: ".8rem" }} disabled={!isAdmin || busy}>
          {busy ? "Saving..." : !isAdmin ? "Locked · Chief Engineer Only" : "Add wheel"}
        </button>
      </form>
    </details>
  );
}

function Schedules({ train, tree, onTreeChanged }) {
  const [list, err, reload] = useLoad(() => getSchedules(train.id), [train.id]);
  const [f, on, reset, setF] = useForm({ schedule_type: "OPERATING", departure_datetime: "", arrival_datetime: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [schedTarget, setSchedTarget] = useState("TRAIN");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [actionTone, setActionTone] = useState("ok");
  const detailsRef = useRef(null);
  const { isAdmin } = useAuth();

  const allWheels = useMemo(() => {
    if (!tree) return [];
    return tree.flatMap((c) => (c.wheels || []).map((w) => ({ ...w, coach_number: c.coach_number, coach_id: c.id })));
  }, [tree]);

  const targetWheel = schedTarget === "TRAIN" ? null : allWheels.find((w) => w.asset_id === schedTarget);
  const criticalWheels = allWheels.filter((w) => w.status === "Critical");
  const monitorWheels = allWheels.filter((w) => w.status === "Monitor");

  const isSevere = schedTarget === "TRAIN" ? criticalWheels.length > 0 : targetWheel?.status === "Critical";
  const affectedWheelId = schedTarget === "TRAIN" ? (criticalWheels[0]?.asset_id || monitorWheels[0]?.asset_id || allWheels[0]?.asset_id) : schedTarget;

  const rows = [...(list || [])].sort((a, b) => String(a.departure_datetime).localeCompare(String(b.departure_datetime)));

  // Calculate upcoming maintenance window
  const now = new Date();
  const upcomingWindows = rows.filter(
    (s) => s.schedule_type === "MAINTENANCE_WINDOW" && s.status === "ACTIVE" && new Date(s.arrival_datetime || s.departure_datetime) > now
  );
  const nextWin = upcomingWindows[0];

  let nextDayName = "Next Available Day";
  let nextDateStr = "Upcoming depot turnaround";
  let nextTimeStr = "06:00 to 12:00";
  let nextDepotStr = "Depot turnaround slot";

  if (nextWin && nextWin.departure_datetime) {
    const d = new Date(nextWin.departure_datetime);
    nextDayName = d.toLocaleDateString(undefined, { weekday: "long" });
    nextDateStr = d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    nextTimeStr = `${fmt(nextWin.departure_datetime)} to ${fmt(nextWin.arrival_datetime)}`;
    nextDepotStr = nextWin.depot_location || nextWin.notes || "Turnaround servicing slot";
  } else {
    const tomorrow = new Date(now.getTime() + 864e5);
    nextDayName = tomorrow.toLocaleDateString(undefined, { weekday: "long" });
    nextDateStr = tomorrow.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    nextTimeStr = "06:00 to 12:00 (Depot Gap)";
    nextDepotStr = "Operational turnaround window";
  }

  const handleEscalateUrgent = async () => {
    setActionBusy(true); setActionMsg("");
    try {
      if (!affectedWheelId) throw new Error("No wheel found to escalate.");
      await escalateUrgent({
        wheel_asset_id: affectedWheelId,
        train_id: train.id,
        notes: `Immediate priority escalation triggered from Schedule & Availability for ${train.train_number}.`,
      });
      setActionTone("urgent");
      setActionMsg(`Priority service requested for ${targetWheel ? (targetWheel.wheel_identifier || targetWheel.asset_id) : train.train_number}. Depot engineering team notified.`);
      if (onTreeChanged) onTreeChanged();
      reload();
    } catch (x) {
      setActionTone("urgent");
      setActionMsg(x.message || "Failed to escalate to maintenance team.");
    }
    setActionBusy(false);
  };

  const handleScheduleSlot = async () => {
    setActionBusy(true); setActionMsg("");
    try {
      const targetId = affectedWheelId || allWheels[0]?.asset_id;
      if (!targetId) throw new Error("No wheel registered on this train.");
      const startDt = nextWin ? nextWin.departure_datetime : new Date(now.getTime() + 864e5).toISOString();
      const endDt = nextWin ? nextWin.arrival_datetime : new Date(now.getTime() + 864e5 + 6 * 36e5).toISOString();
      await scheduleMaintenanceSlot({
        wheel_asset_id: targetId,
        train_id: train.id,
        start_datetime: startDt,
        end_datetime: endDt,
        notes: `Servicing booked for ${nextDayName} turnaround slot.`,
      });
      setActionTone("ok");
      setActionMsg(`Maintenance successfully scheduled for ${nextDayName}, ${nextDateStr} (${nextTimeStr}).`);
      if (onTreeChanged) onTreeChanged();
      reload();
    } catch (x) {
      setActionTone("urgent");
      setActionMsg(x.message || "Failed to schedule maintenance slot.");
    }
    setActionBusy(false);
  };

  const autoFillNextDay = () => {
    const d1 = nextWin?.departure_datetime ? new Date(nextWin.departure_datetime) : new Date(now.getTime() + 864e5);
    if (!nextWin?.departure_datetime) d1.setHours(6, 0, 0, 0);
    const d2 = nextWin?.arrival_datetime ? new Date(nextWin.arrival_datetime) : new Date(d1.getTime() + 6 * 36e5);
    const toLocalISO = (dt) => {
      const pad = (n) => String(n).padStart(2, "0");
      return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    };
    setF((prev) => ({
      ...prev,
      schedule_type: "MAINTENANCE_WINDOW",
      departure_datetime: toLocalISO(d1),
      arrival_datetime: toLocalISO(d2),
      notes: nextWin?.notes || "Turnaround servicing slot",
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!isAdmin) return;
    setMsg("");
    if (f.arrival_datetime <= f.departure_datetime) { setMsg("Arrival must be after departure."); return; }
    setBusy(true);
    try {
      await createSchedule(train.id, { ...f, notes: f.notes.trim() || undefined });
      reset();
      if (detailsRef.current) detailsRef.current.open = false;
      reload();
    } catch (x) {
      setMsg(x.message);
    }
    setBusy(false);
  };
  const cancel = async (s) => {
    if (!isAdmin) return;
    try { await updateSchedule(s.id, { status: "CANCELLED" }); reload(); } catch (x) { setMsg(x.message); }
  };

  return (
    <section className="panel">
      <h2>Schedule and availability</h2>
      {err && <p className="error">{err}</p>}

      {/* Target Selector */}
      <div className="sched-target-picker">
        <label>
          <b>Asset for Scheduling:</b>
          <select value={schedTarget} onChange={(e) => { setSchedTarget(e.target.value); setActionMsg(""); }}>
            <option value="TRAIN">Entire Train · {train.train_number} ({train.train_name})</option>
            {allWheels.length > 0 && (
              <optgroup label="Mounted Wheels">
                {allWheels.map((w) => (
                  <option key={w.asset_id} value={w.asset_id}>
                    {w.wheel_identifier || w.asset_id} · Coach {w.coach_number} ({w.status})
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
      </div>

      {/* Conditional Next Day Maintenance vs Urgent Escalation */}
      {isSevere ? (
        <div className="sched-intel-card severe">
          <div className="intel-header">
            <span className="intel-pill severe">Priority inspection</span>
            <span className="intel-target-tag">Engineering review recommended</span>
          </div>
          <div className="intel-content">
            <div className="intel-text">
              <h4>Priority Turnaround Recommended</h4>
              <p>
                {schedTarget === "TRAIN"
                  ? `Elevated defect detected on wheelset (${criticalWheels.map((w) => `${w.wheel_identifier || w.asset_id} [Coach ${w.coach_number}]`).join(", ")}). Standard turnaround window deferred pending engineering assessment.`
                  : `Elevated defect detected on wheel ${targetWheel?.wheel_identifier || targetWheel?.asset_id} (Coach ${targetWheel?.coach_number}). Recommended for prompt depot turnaround.`}
              </p>
            </div>
            <div className="intel-action-row">
              <button
                type="button"
                className="urgent-btn"
                disabled={actionBusy}
                onClick={handleEscalateUrgent}
              >
                {actionBusy ? "Requesting..." : "Request Priority Turnaround"}
              </button>
            </div>
            {actionMsg && <div className={`intel-feedback ${actionTone}`}>{actionMsg}</div>}
          </div>
        </div>
      ) : (
        <div className="sched-intel-card moderate">
          <div className="intel-header">
            <span className="intel-pill ok">Next available window</span>
            <span className="intel-target-tag">
              {targetWheel
                ? (targetWheel.status === "Monitor" ? "Moderate Wear" : "Routine Inspection")
                : (monitorWheels.length ? `${monitorWheels.length} Wheels with Moderate Wear` : "Routine Servicing")}
            </span>
          </div>
          <div className="intel-content">
            <div className="intel-slot-box">
              <div className="intel-day-callout">
                <span className="intel-day-name">{nextDayName}</span>
                <span className="intel-date-str">{nextDateStr}</span>
              </div>
              <div className="intel-slot-details">
                <div className="intel-time"><b>Window:</b> {nextTimeStr}</div>
                <div className="intel-depot"><b>Depot Slot:</b> {nextDepotStr}</div>
                <div className="muted small">
                  Routine turnaround servicing accommodated in this upcoming maintenance window with zero conflict to active revenue operations.
                </div>
              </div>
            </div>
            <div className="intel-action-row">
              <button
                type="button"
                className="primary sm"
                disabled={actionBusy}
                onClick={handleScheduleSlot}
              >
                {actionBusy ? "Booking..." : `Schedule for ${nextDayName} (${nextDateStr})`}
              </button>
            </div>
            {actionMsg && <div className={`intel-feedback ${actionTone}`}>{actionMsg}</div>}
          </div>
        </div>
      )}

      {list && <Availability items={rows} />}
      <ul className="sched">
        {rows.map((s) => {
          const [label, tone] = TYPES[s.schedule_type] || [human(s.schedule_type), ""];
          return (
            <li key={s.id} className={s.status === "CANCELLED" ? "off" : ""}>
              <span><span className={`badge ${tone}`}>{label}</span></span>
              <span>
                {s.departure_datetime && s.arrival_datetime
                  ? `${fmt(s.departure_datetime)} to ${fmt(s.arrival_datetime)}`
                  : s.departure_datetime
                  ? fmt(s.departure_datetime)
                  : "Standing non-revenue schedule"}
                {s.notes && <div className="muted small">{s.notes}</div>}
              </span>
              {s.status === "CANCELLED" ? <span className="badge">Cancelled</span>
                : <button className={`ghost danger ${!isAdmin ? "rbac-locked-btn" : ""}`} disabled={!isAdmin} onClick={() => cancel(s)} title={!isAdmin ? "Chief Engineer authorization required to cancel operating schedules" : "Cancel schedule"}>{!isAdmin ? "Locked" : "Cancel"}</button>}
            </li>
          );
        })}
        {list && !rows.length && <li className="muted">No schedule entries yet.</li>}
      </ul>
      <details ref={detailsRef} className="addbox">
        <summary>
          <span className={!isAdmin ? "rbac-scratched" : ""}>Add a schedule entry</span>
          {!isAdmin && <span className="rbac-lock-pill admin" style={{ marginLeft: ".6rem" }}><LockIcon /> Chief Engineer Only</span>}
        </summary>
        <form onSubmit={submit}>
          {!isAdmin && (
            <div className="rbac-lock-banner">
              <LockIcon />
              <span>Authority Insufficient: Chief Engineer (Level 3) clearance required to schedule operating runs.</span>
            </div>
          )}
          <div style={{ marginBottom: ".6rem" }}>
            <button
              type="button"
              className="ghost sm"
              style={{ fontSize: ".82rem" }}
              disabled={!isAdmin}
              onClick={autoFillNextDay}
            >
              Auto-fill Next Available Maintenance Day ({nextDayName})
            </button>
          </div>
          <div className={`inline ${!isAdmin ? "rbac-locked-box" : ""}`}>
            <label>Type<select disabled={!isAdmin} value={f.schedule_type} onChange={on("schedule_type")}>{Object.entries(TYPES).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label>Departure<input type="datetime-local" required disabled={!isAdmin} value={f.departure_datetime} onChange={on("departure_datetime")} /></label>
            <label>Arrival<input type="datetime-local" required disabled={!isAdmin} value={f.arrival_datetime} onChange={on("arrival_datetime")} /></label>
            <label>Notes<input disabled={!isAdmin} value={f.notes} onChange={on("notes")} placeholder="optional" /></label>
          </div>
          {msg && <p className="error" style={{ marginTop: ".7rem" }}>{msg}</p>}
          <button className={`primary sm ${!isAdmin ? "rbac-locked-btn" : ""}`} style={{ marginTop: ".8rem" }} disabled={!isAdmin || busy}>
            {busy ? "Saving..." : !isAdmin ? "Locked · Chief Engineer Only" : "Add entry"}
          </button>
        </form>
      </details>
    </section>
  );
}

function TrainDetail({ train, onChanged }) {
  const [tree, err, reload] = useLoad(() => getTrainTree(train.id), [train.id]);
  const [msg, setMsg] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const { isAdmin } = useAuth();

  const setStatus = async (e) => { setMsg(""); try { await updateTrain(train.id, { operational_status: e.target.value }); onChanged(); } catch (x) { setMsg(x.message); } };
  const wheelCount = tree?.reduce((n, c) => n + c.wheels.length, 0) ?? 0;

  const removeCoach = async (coach) => {
    if (!isAdmin) return;
    const count = coach.wheels?.length || 0;
    const warn = count > 0
      ? `Coach ${coach.coach_number} has ${count} registered wheel${count > 1 ? "s" : ""}. Deleting this coach will also unregister these wheels. Proceed?`
      : `Are you sure you want to delete Coach ${coach.coach_number}?`;
    if (!window.confirm(warn)) return;
    setDeletingId(coach.id);
    setMsg("");
    try {
      await deleteCoach(train.id, coach.id);
      await reload();
      onChanged();
    } catch (x) {
      setMsg(x.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      <section className="panel">
        <header className="split">
          <div><h2 style={{ marginBottom: ".2rem" }}>{train.train_number} &middot; {train.train_name}</h2><span className="muted small">{train.train_type || "Train"}{tree ? ` · ${tree.length} coach${tree.length === 1 ? "" : "es"} · ${wheelCount} wheel${wheelCount === 1 ? "" : "s"}` : ""}</span></div>
          <label className="statussel">Status<select value={train.operational_status} onChange={setStatus}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select></label>
        </header>
        {msg && <p className="error">{msg}</p>}
        {err && <p className="error">{err}</p>}
        {!tree && !err && <p className="muted">Loading coaches...</p>}
        {tree?.map((c) => (
          <div className="coach" key={c.id}>
            <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: ".6rem" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: ".6rem" }}>
                <h3 style={{ margin: 0 }}>Coach {c.coach_number}</h3>
                {c.coach_type && <span className="muted small">{c.coach_type}</span>}
              </div>
              <button
                type="button"
                className={`ghost danger sm ${!isAdmin ? "rbac-locked-btn" : ""}`}
                disabled={!isAdmin || deletingId === c.id}
                onClick={() => removeCoach(c)}
                title={!isAdmin ? "Chief Engineer authorization required to delete coaches" : `Delete coach ${c.coach_number}`}
              >
                {!isAdmin ? (
                  <><LockIcon /> <span style={{ marginLeft: "4px" }}>Locked</span></>
                ) : deletingId === c.id ? (
                  "Deleting..."
                ) : (
                  <><TrashIcon /> Delete coach</>
                )}
              </button>
            </header>
            {c.wheels.length ? (
              <div className="chips">{c.wheels.map((w) => <WheelChip key={w.asset_id} w={w} to={`/inspect?train=${train.id}&coach=${c.id}&wheel=${w.asset_id}`} />)}</div>
            ) : <p className="muted small" style={{ margin: ".5rem 0 0" }}>No wheels registered on this coach yet.</p>}
            <AddWheel coach={c} onDone={reload} />
          </div>
        ))}
        {tree && !tree.length && <p className="muted">No coaches yet. Add the first one below.</p>}
        <AddCoach trainId={train.id} onDone={reload} />
        {tree?.some((c) => c.wheels.length) && <p className="muted small" style={{ marginTop: ".8rem" }}>Click a wheel to inspect it.</p>}
      </section>
      <Schedules train={train} tree={tree} onTreeChanged={reload} />
    </>
  );
}

export default function Trains() {
  const [trains, err, reload] = useLoad(getTrains);
  const [sel, setSel] = useState(null);
  useEffect(() => { if (trains?.length && (sel == null || !trains.some((t) => t.id === sel))) setSel(trains[0].id); }, [trains]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <p className="error">{err}</p>;
  if (!trains) return <p className="muted">Loading trains...</p>;
  const train = trains.find((t) => t.id === sel);

  return (
    <>
      <header className="page-header">
        <div>
          <span className="eyebrow">FLEET INVENTORY & ROLLING STOCK</span>
          <h1>Train & Coach Registry</h1>
          <p>Browse trains, inspect coach wheelsets, verify operational statuses, and configure 7-day maintenance availability lanes.</p>
        </div>
      </header>
      <div className="grid2 wide start">
        <section className="panel">
          <h2>Trains</h2>
          {trains.length ? (
            <table>
              <thead><tr><th>Number</th><th>Name</th><th>Status</th></tr></thead>
              <tbody>
                {trains.map((t) => (
                  <tr key={t.id} className={`click ${sel === t.id ? "sel" : ""}`} onClick={() => setSel(t.id)}>
                    <td><b>{t.train_number}</b></td><td>{t.train_name}</td><td><Badge>{t.operational_status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="muted">No trains yet. Register the first one below.</p>}
          <RegisterTrain onDone={(t) => { reload(); if (t?.id != null) setSel(t.id); }} />
        </section>
        <div>
          {train ? <TrainDetail key={train.id} train={train} onChanged={reload} /> : <section className="panel"><p className="muted">Select a train to see its coaches, wheels and schedule.</p></section>}
        </div>
      </div>
    </>
  );
}
