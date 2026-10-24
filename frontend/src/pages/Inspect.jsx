import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getCoaches, getTrains, getWheels, imgUrl, inspect, recommend, getInspectionPdfUrl } from "../api.js";
import { Badge, Bar, Gauge, Plan, Trend, WheelChip, fmt, riskTone } from "../ui.jsx";

const FAST_STAGES = ["Running single-pass detector", "Measuring defect severity", "Calibrating confidence", "Calculating risk & schedule"];
const DEEP_STAGES = ["Detecting defects (YOLOv8)", "Measuring severity", "5-Pass TTA reliability check", "Generating Layer-CAM heatmap", "Scoring risk & schedule"];

const TEST_SAMPLES = [
  {
    id: "thermal_cracks",
    title: "Thermal Cracks",
    tag: "Severe",
    tone: "bad",
    description: "Transverse surface cracks & tread scratching",
    filename: "thermal_cracks.jpg",
    url: "/samples/thermal_cracks.jpg",
  },
  {
    id: "moderate_shelling",
    title: "Moderate Shelling",
    tag: "Moderate",
    tone: "warn",
    description: "Multiple tread breakouts & surface spalling",
    filename: "severe_shelling.jpg",
    url: "/samples/severe_shelling.jpg",
  },
  {
    id: "heat_discoloration",
    title: "Heat Discoloration",
    tag: "Severe",
    tone: "bad",
    description: "Thermal discoloration bands from brake friction",
    filename: "heat_discoloration.jpg",
    url: "/samples/heat_discoloration.jpg",
  },
  {
    id: "compound_defect",
    title: "Compound Defects",
    tag: "Moderate",
    tone: "warn",
    description: "Simultaneous cracks & deep metal breakout",
    filename: "compound_defect.jpg",
    url: "/samples/compound_defect.jpg",
  },
  {
    id: "mild_shelling",
    title: "Mild Shelling",
    tag: "Mild",
    tone: "ok",
    description: "Early-stage localized tread flaking",
    filename: "mild_shelling.jpg",
    url: "/samples/mild_shelling.jpg",
  },
  {
    id: "non_wheel_test",
    title: "Non-Wheel (OOD)",
    tag: "Guard Test",
    tone: "neutral",
    description: "Non-railway image to test auto-rejection",
    filename: "non_wheel_test.jpg",
    url: "/samples/non_wheel_test.jpg",
  },
];

function Viewer({ res, preview }) {
  const [tab, setTab] = useState("det");
  // Prefer the real backend-generated image; fall back to local preview only if URL is null
  const backendSrc = imgUrl(tab === "det" ? res.annotated_image_url : res.gradcam_image_url);
  const src = backendSrc || preview;
  const hasGradcam = !!res.gradcam_image_url;
  return (
    <section className="panel">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "det"} onClick={() => setTab("det")}>Detections</button>
        <button role="tab" aria-selected={tab === "cam"} onClick={() => setTab("cam")}>Model attention</button>
      </div>
      <div className="viewer">
        {src ? (
          <a href={src} target="_blank" rel="noreferrer" title="Open full size"><img src={src} alt={tab === "det" ? "Wheel with detected defects" : "Model attention heatmap"} /></a>
        ) : (
          <p className="muted">No {tab === "det" ? "annotated" : "Grad-CAM"} image was generated for this inspection.</p>
        )}
      </div>
      {tab === "cam" && hasGradcam && <p className="muted small">The heatmap shows where the model looked. It does not outline the exact defect boundary.</p>}
      {tab === "cam" && !hasGradcam && (
        <p className="muted small">
          {res.run_tta === false
            ? "Layer-CAM heatmap was skipped in Fast Screening Mode to maximize throughput. Toggle 'Deep Diagnostic Mode' or escalate above to generate attention heatmaps."
            : "Grad-CAM heatmap was not generated. The backend may have encountered an error during generation."}
        </p>
      )}
    </section>
  );
}

export default function Inspect() {
  const [params] = useSearchParams();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [trainId, setTrainId] = useState(params.get("train") || "");
  const [coachId, setCoachId] = useState(params.get("coach") || "");
  const [wheelId, setWheelId] = useState(params.get("wheel") || "");
  const [runTta, setRunTta] = useState(false);
  const [activeSample, setActiveSample] = useState(null);
  const [trains, setTrains] = useState([]);
  const [coaches, setCoaches] = useState([]);
  const [wheels, setWheels] = useState([]);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [plan, setPlan] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [planErr, setPlanErr] = useState("");
  const input = useRef();

  const activeStages = runTta ? DEEP_STAGES : FAST_STAGES;

  useEffect(() => { getTrains().then(setTrains).catch(() => {}); getWheels().then(setWheels).catch(() => {}); }, []);
  useEffect(() => { if (!trainId) { setCoaches([]); return; } getCoaches(trainId).then(setCoaches).catch(() => {}); }, [trainId]);
  useEffect(() => {
    if (!busy) return;
    const intervalMs = runTta ? 1200 : 350;
    const t = setInterval(() => setStage((s) => Math.min(s + 1, activeStages.length - 1)), intervalMs);
    return () => clearInterval(t);
  }, [busy, runTta, activeStages.length]);

  const wheelOpts = wheels.filter((w) => String(w.coach_id) === String(coachId));
  const picked = wheels.find((w) => w.asset_id === wheelId);
  const trainOf = (id) => trains.find((t) => t.id === id);

  const pickTrain = (v) => { setTrainId(v); setCoachId(""); setWheelId(""); };
  const pickCoach = (v) => { setCoachId(v); setWheelId(""); };
  const pick = (f) => { if (!f) return; setFile(f); setPreview(URL.createObjectURL(f)); setRes(null); setPlan(null); setErr(""); };

  const loadSample = async (sample, autoRun = false) => {
    setActiveSample(sample.id);
    try {
      const resp = await fetch(sample.url);
      const blob = await resp.blob();
      const sampleFile = new File([blob], sample.filename, { type: "image/jpeg" });
      pick(sampleFile);
      if (autoRun) {
        setTimeout(() => run(undefined, sampleFile), 60);
      }
    } catch (e) {
      console.error("Failed to load sample", e);
    }
  };
  
  const run = async (overrideTta, overrideFile) => {
    const shouldTta = overrideTta !== undefined ? overrideTta : runTta;
    if (overrideTta !== undefined) setRunTta(overrideTta);
    const targetFile = overrideFile || file;
    if (!targetFile) return;
    setBusy(true);
    setStage(0);
    setErr("");
    setRes(null);
    setPlan(null);
    setPlanErr("");
    try {
      const result = await inspect(targetFile, wheelId, coachId, shouldTta);
      setRes(result);
      getWheels().then(setWheels).catch(() => {});
    } catch (e) {
      setRes(null);
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const makePlan = async () => {
    setPlanBusy(true); setPlanErr("");
    try { setPlan(await recommend(res.asset_id)); } catch (e) { setPlanErr(e.message); }
    setPlanBusy(false);
  };

  const t = res && trainOf(res.train_id);

  return (
    <>
      <header className="page-header">
        <div>
          <span className="eyebrow">AI DIAGNOSTIC STUDIO</span>
          <h1>Wayside Inspection Studio</h1>
          <p>Single-pass YOLOv8 defect detection, 5-pass TTA reliability verification, and Layer-CAM attention heatmaps for wayside pass-by screening.</p>
        </div>
      </header>
      <section className="panel form">
        <div className="drop-column">
          <div className="drop" onClick={() => input.current.click()} onDragOver={(e) => e.preventDefault()}
               onDrop={(e) => { e.preventDefault(); setActiveSample(null); pick(e.dataTransfer.files[0]); }}>
            {preview ? <img src={preview} alt="Selected wheel" /> : <span>Drop a wheel image here, or click to choose (JPEG or PNG)</span>}
            {busy && <div className="scan" />}
            <input ref={input} type="file" accept="image/jpeg,image/png" hidden onChange={(e) => { setActiveSample(null); pick(e.target.files[0]); }} />
          </div>

          {/* Quick Test Samples Gallery */}
          <div className="quick-samples-container">
            <div className="quick-samples-header">
              <div>
                <span className="eyebrow" style={{ fontSize: "0.65rem", margin: 0 }}>QUICK TEST SAMPLES</span>
                <h3 style={{ margin: "0.15rem 0 0", fontSize: "0.95rem", fontWeight: 600 }}>Pre-Loaded Wheel Library</h3>
              </div>
              <span className="muted small">Click to load &bull; Inspect directly</span>
            </div>
            <div className="quick-samples-grid">
              {TEST_SAMPLES.map((s) => (
                <div
                  key={s.id}
                  className={`sample-card ${activeSample === s.id ? "active" : ""}`}
                  onClick={() => loadSample(s, false)}
                  role="button"
                  tabIndex={0}
                >
                  <div className="sample-img-wrap">
                    <img src={s.url} alt={s.title} className="sample-thumb" />
                    <span className={`sample-badge ${s.tone}`}>{s.tag}</span>
                  </div>
                  <div className="sample-content">
                    <strong className="sample-title">{s.title}</strong>
                    <span className="sample-desc">{s.description}</span>
                    <button
                      type="button"
                      className="sample-run-btn"
                      disabled={busy}
                      onClick={(e) => {
                        e.stopPropagation();
                        loadSample(s, true);
                      }}
                      title={`Inspect ${s.title} immediately`}
                    >
                      Inspect
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="fields">
          <label>Train
            <select value={trainId} onChange={(e) => pickTrain(e.target.value)}>
              <option value="">Select a train</option>
              {trains.map((x) => <option key={x.id} value={x.id}>{x.train_number} · {x.train_name}</option>)}
            </select>
          </label>
          <label>Coach
            <select value={coachId} disabled={!trainId} onChange={(e) => pickCoach(e.target.value)}>
              <option value="">{trainId ? "Select a coach" : "Pick a train first"}</option>
              {coaches.map((c) => <option key={c.id} value={c.id}>{c.coach_number}{c.coach_type ? ` · ${c.coach_type}` : ""}</option>)}
            </select>
          </label>
          <label>Wheel
            <select value={wheelId} disabled={!coachId} onChange={(e) => setWheelId(e.target.value)}>
              <option value="">{coachId ? (wheelOpts.length ? "Select a wheel" : "No wheels on this coach") : "Pick a coach first"}</option>
              {wheelOpts.map((w) => <option key={w.asset_id} value={w.asset_id}>{w.wheel_identifier} · {w.asset_id}</option>)}
            </select>
          </label>
          {picked && <div className="chips" style={{ margin: 0 }}><WheelChip w={picked} /><span className="muted small">{picked.inspection_count ?? 0} past inspection(s)</span></div>}
          
          {/* Fast Mode / Deep Diagnostic Mode toggle */}
          <div className="mode-toggle-card">
            <label className="toggle-switch" title="Toggle between Fast Mode and Deep Diagnostic Mode">
              <input
                type="checkbox"
                checked={runTta}
                disabled={busy}
                onChange={(e) => setRunTta(e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
            <div className="toggle-label-group">
              <strong>{runTta ? "Deep Diagnostic Mode (~25s)" : "Fast Screening Mode (~0.4s)"}</strong>
              <p className="muted small" style={{ margin: 0 }}>
                {runTta
                  ? "Full 5-pass TTA stability check + Layer-CAM attention heatmap. Best for depot verification of flagged wheels."
                  : "Rapid wayside pass-by screening (single-pass YOLOv8 + severity grading). TTA & Layer-CAM skipped for maximum throughput."}
              </p>
            </div>
          </div>

          <p className="muted small">Choose the wheel from the registry so this result joins its history, trend and schedule. Leave empty to inspect an image without a registered wheel.</p>
          <button className="primary" disabled={!file || busy} onClick={() => run()}>{busy ? "Inspecting..." : (runTta ? "Run Deep Diagnostic" : "Run Fast Inspection")}</button>
        </div>
      </section>

      {!res && !busy && (
        <section className="panel">
          <h2>Inspection Pipeline {runTta ? "(Deep Diagnostic)" : "(Fast Screening)"}</h2>
          <ol className="pipe">
            {runTta
              ? ["Defect detection", "Severity grading", "5-pass TTA check", "Layer-CAM heatmap", "Risk & schedule", "Health record"].map((s, i) => <li key={s} style={{ "--i": i }}>{s}</li>)
              : ["Defect detection", "Severity grading", "Calibrated confidence", "Risk & schedule", "Health record"].map((s, i) => <li key={s} style={{ "--i": i }}>{s}</li>)
            }
          </ol>
        </section>
      )}
      {busy && (
        <ol className="stages" aria-live="polite">
          {activeStages.map((s, i) => <li key={s} className={i < stage ? "done" : i === stage ? "now" : ""}>{s}</li>)}
        </ol>
      )}
      {err && (
        <section className="validation-alert" role="alert">
          <div className="alert-badge">VALIDATION ERROR</div>
          <div className="alert-body">
            <h3>Image Rejected &bull; Out-of-Distribution</h3>
            <p>{err}</p>
          </div>
        </section>
      )}

      {res && (
        <>
          <section className={`reveal banner ${riskTone(res.wheel_risk_score)}`}>
            <Gauge value={res.wheel_risk_score} />
            <div>
              <div style={{ display: "flex", gap: ".5rem", alignItems: "center", marginBottom: ".4rem" }}>
                <span className={`badge ${res.run_tta ? "warn" : "ok"}`}>
                  {res.run_tta ? "5-Pass TTA & Layer-CAM" : "Fast Screening Mode"}
                </span>
              </div>
              <h2>{res.wheel_recommended_action}</h2>
              <p>Wheel {res.asset_id}{t ? ` · Train ${t.train_number}` : ""} &middot; {res.total_defects_detected} defect(s) found &middot; {res.processing_time_seconds}s</p>
              <Trend value={res.trend_status} />
              <p className="muted small">{fmt(res.inspection_date)}</p>
              
              <div style={{ marginTop: ".8rem", display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center" }}>
                <a
                  href={getInspectionPdfUrl(res.inspection_event_id || res.inspection_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="primary sm"
                  download
                  title="Download Work Order PDF for depot engineers with defect bounding boxes and heatmap callouts"
                >
                  Export Maintenance Work Order (PDF)
                </a>

                {/* If screened in Fast Mode and defect found, allow 1-click escalation */}
                {!res.run_tta && res.total_defects_detected > 0 && (
                  <button
                    className="ghost sm"
                    disabled={busy}
                    onClick={() => run(true)}
                    title="Re-run this wheel with 5-pass TTA reliability and Layer-CAM attention heatmap for depot confirmation"
                  >
                    {busy ? "Escalating..." : "Escalate to Deep Diagnostic (TTA + CAM)"}
                  </button>
                )}
              </div>
            </div>
          </section>
          <Plan rec={plan} busy={planBusy} err={planErr} onGenerate={makePlan} />
          <Viewer res={res} preview={preview} />
          <section className="panel">
            <h2>Defects</h2>
            {res.defects.map((d, i) => (
              <article key={i} style={{ "--i": i + 1 }} className={`reveal defect ${{ Mild: "ok", Moderate: "warn", Severe: "bad" }[d.severity] || ""}`}>
                <header><h3>{d.label}</h3><Badge>{d.severity}</Badge><span className="risk">Risk {d.risk_score}</span></header>
                <div className="meta">
                  <div>Detection confidence <Bar value={d.confidence} /> {(d.confidence * 100).toFixed(0)}%</div>
                  <div>Stability / Reliability <Badge>{d.reliability}</Badge>{d.std_deviation != null && d.std_deviation > 0 ? ` (spread ${d.std_deviation})` : (res.run_tta ? "" : " (calibrated)")}</div>
                </div>
                <p><b>{d.recommended_action}.</b> <span className="muted">{d.trend_note}</span></p>
              </article>
            ))}
          </section>
        </>
      )}
    </>
  );
}

