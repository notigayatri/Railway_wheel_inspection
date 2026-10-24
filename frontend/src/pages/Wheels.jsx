import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getHistory,
  getServiceHistory,
  getTrains,
  getWheels,
  getWheelPdfUrl,
  getWheelCsvUrl,
  getBackupStatus,
  getBackups,
  triggerBackup,
  getBackupDownloadUrl,
  restoreBackup,
} from "../api.js";
import { Badge, JobStatus, Priority, Trend, fmt, fmtWindow, neverInspected, useLoad } from "../ui.jsx";
import { useAuth } from "../useAuth.js";

function LockIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor" aria-hidden="true" style={{ verticalAlign: "-1px" }}>
      <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H3.75A1.75 1.75 0 0 0 2 7.75v5.5C2 14.216 2.784 15 3.75 15h8.5A1.75 1.75 0 0 0 14 13.25v-5.5A1.75 1.75 0 0 0 12.25 6h-.75V4.5A3.5 3.5 0 0 0 8 1zm2 5H6V4.5a2 2 0 1 1 4 0V6z" />
    </svg>
  );
}

function DatabaseBackupsPanel() {
  const [backups, setBackups] = useState([]);
  const [status, setStatus] = useState(null);
  const [compress, setCompress] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const { isAdmin, isSupervisor } = useAuth();

  const refresh = () => {
    getBackupStatus().then(setStatus).catch(() => {});
    getBackups().then(setBackups).catch(() => {});
  };

  useEffect(() => { refresh(); }, []);

  const handleCreate = async () => {
    setBusy(true); setMsg(""); setErr("");
    try {
      const res = await triggerBackup(compress);
      setMsg(res.message || "Backup created successfully!");
      refresh();
    } catch (e) {
      setErr(e.message || "Failed to create backup");
    }
    setBusy(false);
  };

  const handleRestore = async (fn) => {
    if (!window.confirm(`Are you sure you want to restore the live database from '${fn}'? A pre-restore safety snapshot will be created automatically.`)) return;
    setBusy(true); setMsg(""); setErr("");
    try {
      const res = await restoreBackup(fn);
      setMsg(res.message || "Database restored successfully!");
      refresh();
    } catch (e) {
      setErr(e.message || "Failed to restore database");
    }
    setBusy(false);
  };

  return (
    <section className="panel backup-card">
      <div className="backup-toolbar">
        <div>
          <h2>Automated SQLite Database Backups</h2>
          <p className="muted small">Lock-free online snapshots of railway.db. Automated background backups scheduled every 6 hours.</p>
        </div>
        <div className="backup-actions-row">
          {!isSupervisor && (
            <span className="rbac-lock-pill supervisor" title="Maintenance Supervisor or Admin role required">
              <LockIcon /> Supervisor Only
            </span>
          )}
          <label style={{ display: "inline-flex", alignItems: "center", gap: ".4rem", fontSize: ".85rem", cursor: isSupervisor ? "pointer" : "not-allowed", opacity: isSupervisor ? 1 : 0.6 }}>
            <input type="checkbox" disabled={!isSupervisor} checked={compress} onChange={(e) => setCompress(e.target.checked)} />
            Compress (.db.gz)
          </label>
          <button
            className={`primary sm ${!isSupervisor ? "rbac-locked-btn" : ""}`}
            disabled={!isSupervisor || busy}
            onClick={handleCreate}
            title={!isSupervisor ? "Supervisor clearance required to snapshot database" : "Snapshot Database Now"}
          >
            {busy ? "Backing up..." : !isSupervisor ? "Locked · Supervisor Required" : "Snapshot Database Now"}
          </button>
        </div>
      </div>

      {status && (
        <div className="backup-stat-group" style={{ marginBottom: "1.2rem", padding: ".75rem 1rem", background: "rgba(0,0,0,.02)", borderRadius: "10px" }}>
          <div className="backup-stat-item"><label>Live Database</label><span>{status.database_human_size}</span></div>
          <div className="backup-stat-item"><label>Integrity Check</label><span style={{ color: "var(--teal)" }}>{status.live_integrity}</span></div>
          <div className="backup-stat-item"><label>Total Snapshots</label><span>{status.total_snapshots}</span></div>
          <div className="backup-stat-item"><label>Archive Size</label><span>{status.total_archive_human_size}</span></div>
          <div className="backup-stat-item"><label>Background Scheduler</label><span style={{ color: "var(--teal)" }}>Active (Every 6h)</span></div>
        </div>
      )}

      {msg && <p className="alert ok" style={{ marginBottom: ".9rem" }}>{msg}</p>}
      {err && <p className="alert warn" style={{ marginBottom: ".9rem" }}>{err}</p>}

      {backups.length ? (
        <table>
          <thead>
            <tr>
              <th>Snapshot Filename</th>
              <th>Size</th>
              <th>Created Date</th>
              <th>Records</th>
              <th>Integrity</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.filename}>
                <td>
                  <strong>{b.filename}</strong>
                  {b.reason && <div className="muted small">{b.reason}</div>}
                </td>
                <td>{b.human_size}</td>
                <td>{b.created_at_display || b.created_at}</td>
                <td>{b.total_records || "-"}</td>
                <td><Badge tone={b.integrity_ok !== false ? "ok" : "bad"}>{b.integrity_status || "ok"}</Badge></td>
                <td>
                  <div style={{ display: "flex", gap: ".4rem", alignItems: "center" }}>
                    <a
                      href={isSupervisor ? getBackupDownloadUrl(b.filename) : "#"}
                      className={`primary sm ${!isSupervisor ? "rbac-locked-btn" : ""}`}
                      download={isSupervisor ? b.filename : undefined}
                      onClick={(e) => { if (!isSupervisor) { e.preventDefault(); } }}
                      title={!isSupervisor ? "Supervisor clearance required to download database snapshots" : "Download SQLite database snapshot"}
                    >
                      {!isSupervisor ? "Locked" : "Download"}
                    </a>
                    <button
                      className={`ghost sm ${!isAdmin ? "rbac-locked-btn" : ""}`}
                      disabled={!isAdmin || busy}
                      onClick={() => handleRestore(b.filename)}
                      title={!isAdmin ? "Chief Engineer (Level 3) clearance required to restore database" : "Restore live database to this snapshot"}
                    >
                      {!isAdmin ? "Locked" : "Restore"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No snapshots created yet. Click "Snapshot Database Now" to take your first backup.</p>
      )}
    </section>
  );
}

export default function Wheels() {
  const [data, loadErr] = useLoad(() => Promise.all([getWheels(), getTrains().catch(() => [])]));
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(null);
  const [hist, setHist] = useState([]);
  const [service, setService] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!sel) return;
    setHist([]); setService([]);
    getHistory(sel).then(setHist).catch((e) => setErr(e.message));
    getServiceHistory(sel).then(setService).catch(() => {});
  }, [sel]);

  if (err || loadErr) return <p className="error">{err || loadErr}</p>;
  if (!data) return <p className="muted">Loading wheels...</p>;
  const [list, trains] = data;
  const trainNo = (id) => trains.find((t) => t.id === id)?.train_number ?? "-";
  const term = q.toLowerCase();
  const rows = list.filter((w) => `${w.asset_id} ${w.wheel_identifier ?? ""} ${trainNo(w.train_id)}`.toLowerCase().includes(term));
  const series = [...hist].reverse().map((h) => ({ date: new Date(h.inspection_date).toLocaleDateString("en-IN"), risk: h.risk_score }));
  const wheel = list.find((w) => w.asset_id === sel);

  return (
    <>
      <header className="page-header">
        <div>
          <span className="eyebrow">ASSET TELEMETRY & SNAPSHOTS</span>
          <h1>Wheelset History & Backups</h1>
          <p>Longitudinal wear degradation, defect severity trends, automated diagnostic reports, and point-in-time database snapshots.</p>
        </div>
      </header>
      <div className="grid2 wide start">
        <section className="panel">
          <input className="search" placeholder="Search by wheel ID, identifier or train" value={q} onChange={(e) => setQ(e.target.value)} />
          {rows.length ? (
            <table>
              <thead><tr><th>Wheel</th><th>Train</th><th>Status</th><th>Inspections</th><th>Last inspected</th></tr></thead>
              <tbody>
                {rows.map((w) => (
                  <tr key={w.asset_id} className={`click ${sel === w.asset_id ? "sel" : ""}`} onClick={() => setSel(w.asset_id)}>
                    <td>{w.asset_id}{w.wheel_identifier && <div className="muted small">{w.wheel_identifier}</div>}</td>
                    <td>{trainNo(w.train_id)}</td>
                    <td>{neverInspected(w) ? <span className="badge">Not inspected</span> : <Badge>{w.status}</Badge>}</td>
                    <td>{w.inspection_count ?? "-"}</td><td>{fmt(w.latest_inspection)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="muted">No wheels match that search.</p>}
        </section>
        <section className="panel">
          {!sel ? <p className="muted">Select a wheel to see how its risk has changed.</p> : (
            <>
              <h2>{sel} history{wheel?.wheel_identifier ? ` · ${wheel.wheel_identifier}` : ""}</h2>
              <div className="export-actions" style={{ marginBottom: ".9rem" }}>
                <a
                  href={getWheelPdfUrl(sel)}
                  target="_blank"
                  rel="noreferrer"
                  className="primary sm"
                  download
                  title="Download Maintenance Work Order PDF for this wheel"
                >
                  Export Work Order (PDF)
                </a>
                <a
                  href={getWheelCsvUrl(sel)}
                  download
                  className="ghost sm"
                  title="Export inspection history as CSV"
                >
                  Export History (CSV)
                </a>
              </div>
              {hist.length > 0 ? (
                <ResponsiveContainer width="100%" height={170}>
                  <LineChart data={series} margin={{ left: -20 }}>
                    <CartesianGrid vertical={false} stroke="#DDE6E4" />
                    <XAxis dataKey="date" tickLine={false} /><YAxis domain={[0, 100]} tickLine={false} axisLine={false} /><Tooltip />
                    <Line dataKey="risk" stroke="#48807a" strokeWidth={2} dot />
                  </LineChart>
                </ResponsiveContainer>
              ) : <p className="muted">No inspections recorded for this wheel yet.</p>}
              <ul className="timeline">
                {hist.map((h, i) => (
                  <li key={i}><b>{h.label ?? h.defect_type ?? "Inspection"}</b> <Badge>{h.severity}</Badge> <Trend value={h.trend_status} />
                    <div className="muted small">{fmt(h.inspection_date)} &middot; risk {h.risk_score} &middot; {h.recommended_action}</div></li>
                ))}
              </ul>
              {service.length > 0 && (
                <>
                  <h2 style={{ marginTop: "1.4rem" }}>Maintenance history</h2>
                  <ul className="timeline">
                    {service.map((j, i) => (
                      <li key={j.id ?? i}><Priority value={j.priority} /> <JobStatus value={j.job_status} />
                        <div className="muted small">{j.suggested_start ? fmtWindow(j.suggested_start, j.suggested_end) : "Routine"}{j.recommended_action ? ` · ${j.recommended_action}` : ""}</div></li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </section>
      </div>

      {/* Database Backups & Archive Management Panel */}
      <DatabaseBackupsPanel />
    </>
  );
}

