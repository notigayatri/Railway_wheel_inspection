import { useState } from "react";
import { confirmJob, escalateUrgent, getJobs, getTrains, getWheels, recommend, setJobStatus, getWorkOrderPdfUrl, getJobsCsvUrl } from "../api.js";
import { Count, Hold, JobStatus, Priority, Sched, SimNote, fmt, fmtWindow, neverInspected, useLoad } from "../ui.jsx";
import { useAuth } from "../useAuth.js";

function LockIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor" aria-hidden="true" style={{ verticalAlign: "-1px" }}>
      <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H3.75A1.75 1.75 0 0 0 2 7.75v5.5C2 14.216 2.784 15 3.75 15h8.5A1.75 1.75 0 0 0 14 13.25v-5.5A1.75 1.75 0 0 0 12.25 6h-.75V4.5A3.5 3.5 0 0 0 8 1zm2 5H6V4.5a2 2 0 1 1 4 0V6z" />
    </svg>
  );
}

const OPEN = ["PENDING", "SCHEDULED", "IN_PROGRESS"];
const RANK = { CRITICAL: 0, MODERATE: 1, LOW: 2 };
const TONE = { CRITICAL: "bad", MODERATE: "warn", LOW: "ok" };
const TABS = [["all", "All jobs"], ["pending", "Pending review"], ["urgent", "Urgent"]];
const NEXT = { PENDING: [["Confirm slot", "confirm"]], SCHEDULED: [["Start job", "IN_PROGRESS"]], IN_PROGRESS: [["Mark as done", "COMPLETED"]] };

export default function Planner() {
  const [data, err, reload] = useLoad(() => Promise.all([getJobs(), getTrains(), getWheels()]));
  const [tab, setTab] = useState("all");
  const [busy, setBusy] = useState(null);
  const [msgs, setMsgs] = useState({});
  const [pick, setPick] = useState("");
  const [genBusy, setGenBusy] = useState(false);
  const [genMsg, setGenMsg] = useState("");
  const { isSupervisor } = useAuth();

  if (err) return <p className="error">{err}</p>;
  if (!data) return <p className="muted">Loading maintenance jobs...</p>;
  const [jobs, trains, wheels] = data;
  const train = (id) => trains.find((t) => t.id === id);
  const isOpen = (j) => OPEN.includes(j.job_status);
  const urgent = jobs.filter((j) => j.priority === "CRITICAL" && isOpen(j));

  const shown = jobs
    .filter((j) => (tab === "pending" ? j.job_status === "PENDING" : tab === "urgent" ? urgent.includes(j) : true))
    .sort((a, b) => Number(!isOpen(a)) - Number(!isOpen(b)) || (RANK[a.priority] ?? 3) - (RANK[b.priority] ?? 3) || String(a.suggested_start).localeCompare(String(b.suggested_start)));

  const stats = [
    ["Urgent", urgent.length, "bad"],
    ["Pending review", jobs.filter((j) => j.job_status === "PENDING").length, "warn"],
    ["Scheduled", jobs.filter((j) => j.job_status === "SCHEDULED").length, "ok"],
    ["With schedule conflicts", jobs.filter((j) => isOpen(j) && j.conflict_notes.length).length, "bad"],
  ];

  const act = async (j, kind) => {
    setBusy(j.id); setMsgs((m) => ({ ...m, [j.id]: "" }));
    try { await (kind === "confirm" ? confirmJob(j.id) : setJobStatus(j.id, kind)); reload(); }
    catch (e) { setMsgs((m) => ({ ...m, [j.id]: e.status === 409 ? "That slot overlaps another confirmed job for this wheel (409 conflict). Pick a different window." : e.message })); }
    setBusy(null);
  };
  const generate = async () => {
    setGenBusy(true); setGenMsg("");
    try { const r = await recommend(pick); setGenMsg(r.duplicate_job ? `${pick} already has an open job (#${r.maintenance_job_id}).` : `Created job #${r.maintenance_job_id} for ${pick}.`); setPick(""); reload(); }
    catch (e) { setGenMsg(e.message); }
    setGenBusy(false);
  };

  const handleUrgentPick = async () => {
    setGenBusy(true); setGenMsg("");
    try {
      const res = await escalateUrgent({
        wheel_asset_id: pick,
        notes: `Urgent priority escalation triggered from Maintenance Planner for wheel ${pick}.`,
      });
      setGenMsg(`Priority service requested for Job #${res.id}. Depot engineering team notified.`);
      setPick("");
      reload();
    } catch (e) {
      setGenMsg(e.message);
    }
    setGenBusy(false);
  };

  const inspected = wheels.filter((w) => !neverInspected(w));
  const selectedWheel = inspected.find((w) => w.asset_id === pick);
  const isSeverePick = selectedWheel?.status === "Critical";

  return (
    <>
      <header className="page-header">
        <div>
          <span className="eyebrow">DEPOT WORK ORDERS & DISPATCH</span>
          <h1>Maintenance Planner</h1>
          <p>Prioritized wheel service work orders deconflicted against operating runs and track availability windows.</p>
        </div>
        <div className="export-actions">
          <a href={getJobsCsvUrl()} download className="ghost" title="Export all jobs to CSV spreadsheet">
            Export Jobs (CSV)
          </a>
        </div>
      </header>
      {urgent.length > 0 && (
        <div className="alert reveal" role="alert">
          <div><b>{urgent.length} priority maintenance item{urgent.length === 1 ? "" : "s"}.</b> Inspection advised prior to departure; operational hold flagged for engineering clearance.</div>
        </div>
      )}
      <div className="stats four">
        {stats.map(([l, v, t], i) => <div key={l} style={{ "--i": i }} className={`stat sm ${t}`}><b><Count to={v} /></b><span>{l}</span></div>)}
      </div>

      <section className="panel">
        <div className="split">
          <div className="tabs" role="tablist">
            {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
          </div>
          <div className="genrow">
            {!isSupervisor && <span className="rbac-lock-pill supervisor" title="Maintenance Supervisor or Admin role required"><LockIcon /> Supervisor Only</span>}
            <select disabled={!isSupervisor} value={pick} onChange={(e) => { setPick(e.target.value); setGenMsg(""); }} aria-label="Wheel to plan" className={!isSupervisor ? "rbac-locked-box" : ""}>
              <option value="">{isSupervisor ? "Plan maintenance for a wheel..." : "Locked · Supervisor required to plan"}</option>
              {inspected.map((w) => <option key={w.asset_id} value={w.asset_id}>{w.wheel_identifier ?? w.asset_id} · {w.status}</option>)}
            </select>
            {isSeverePick ? (
              <button
                className={`urgent-btn ${!isSupervisor ? "rbac-locked-btn" : ""}`}
                disabled={!isSupervisor || !pick || genBusy}
                onClick={handleUrgentPick}
                title={!isSupervisor ? "Requires Supervisor role" : "Request priority maintenance turnaround"}
              >
                {genBusy ? "Requesting..." : !isSupervisor ? "Locked" : "Request Priority Turnaround"}
              </button>
            ) : (
              <button
                className={`primary sm ${!isSupervisor ? "rbac-locked-btn" : ""}`}
                disabled={!isSupervisor || !pick || genBusy}
                onClick={generate}
                title={!isSupervisor ? "Requires Supervisor role" : ""}
              >
                {genBusy ? "Planning..." : !isSupervisor ? "Locked" : "Schedule Next Available Window"}
              </button>
            )}
          </div>
        </div>
        {selectedWheel && isSeverePick && (
          <div className="intel-feedback urgent" style={{ margin: ".5rem 0 .7rem" }}>
            Elevated wear recorded on <b>{selectedWheel.wheel_identifier ?? selectedWheel.asset_id}</b>. Standard turnaround window held for priority depot review.
          </div>
        )}
        {selectedWheel && !isSeverePick && (
          <div className="intel-feedback ok" style={{ margin: ".5rem 0 .7rem" }}>
            Moderate wear on <b>{selectedWheel.wheel_identifier ?? selectedWheel.asset_id}</b> ({selectedWheel.status}). Turnaround slot can be assigned to the next available window.
          </div>
        )}
        {genMsg && <p className="muted small" style={{ margin: ".2rem 0 .8rem" }}>{genMsg}</p>}

        {shown.length ? shown.map((j) => {
          const t = train(j.train_id);
          const open = isOpen(j);
          const hold = open && (j.requires_operational_clearance || j.priority === "CRITICAL");
          return (
            <article key={j.id} className={`job ${open ? TONE[j.priority] || "" : "done"}`}>
              <header>
                <h3>{j.wheel_asset_id}</h3><Priority value={j.priority} /><JobStatus value={j.job_status} />
                {j.risk_score != null && <span className="risk">Risk {Math.round(j.risk_score)}</span>}
              </header>
              <div className="meta">
                <div>Train <b>{t ? `${t.train_number} · ${t.train_name}` : j.train_id ?? "-"}</b></div>
                <div>Scheduling <Sched value={j.confirmed_start ? fmt(j.confirmed_start) : j.suggested_start ? fmt(j.suggested_start) : j.scheduling_status || "Routine turnaround"} /></div>
                <div>Suggested window <b>{j.suggested_start ? fmtWindow(j.suggested_start, j.suggested_end) : "Routine, at next depot turnaround"}</b></div>
                <div>Recommended action <b>{j.recommended_action ?? "-"}</b></div>
              </div>
              {hold && <Hold />}
              {j.conflict_notes.length > 0 && open && <ul className="conf">{j.conflict_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
              {j.scheduling_notes && open && <p className="muted small" style={{ margin: ".4rem 0 0" }}>{j.scheduling_notes}</p>}
              {msgs[j.id] && <p className="error" style={{ marginTop: ".7rem" }}>{msgs[j.id]}</p>}
              <div className="acts">
                {open && (NEXT[j.job_status] || []).map(([label, kind]) => (
                  <button
                    key={kind}
                    className={`primary sm ${!isSupervisor ? "rbac-locked-btn" : ""}`}
                    disabled={!isSupervisor || busy === j.id}
                    onClick={() => act(j, kind)}
                    title={!isSupervisor ? "Supervisor clearance required to execute work orders" : ""}
                  >
                    {busy === j.id ? "Working..." : !isSupervisor ? `Locked · ${label}` : label}
                  </button>
                ))}
                <a href={getWorkOrderPdfUrl(j.id)} target="_blank" rel="noreferrer" className="ghost sm" download title="Download Depot Maintenance Work Order PDF">Export Work Order (PDF)</a>
                {open && (
                  <button
                    className={`ghost danger ${!isSupervisor ? "rbac-locked-btn" : ""}`}
                    disabled={!isSupervisor || busy === j.id}
                    onClick={() => act(j, "CANCELLED")}
                    title={!isSupervisor ? "Supervisor clearance required to cancel jobs" : ""}
                  >
                    {!isSupervisor ? "Locked" : "Cancel job"}
                  </button>
                )}
                {!isSupervisor && open && <span className="rbac-lock-pill supervisor" style={{ alignSelf: "center" }}><LockIcon /> Supervisor Required</span>}
              </div>
            </article>
          );
        }) : <p className="muted">{tab === "all" ? "No maintenance jobs yet. Inspect a wheel, then generate a plan." : "Nothing in this view."}</p>}
      </section>
      <SimNote />
    </>
  );
}
