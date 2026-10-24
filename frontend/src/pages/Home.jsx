import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import ParticleSimulation from "../components/ParticleSimulation.jsx";
import { getCurrentUser } from "../api.js";

export default function Home() {
  const [showHow, setShowHow] = useState(false);
  const navigate = useNavigate();
  const user = getCurrentUser();

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") setShowHow(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const handleDownloadChecklist = () => {
    const text = `CHAKRAKSH • RAILWAY WHEEL HEALTH & SAFETY CHECKLIST
1. Wayside Screening: Verify pass-by camera alignment and acoustic wheel-impact threshold.
2. Defect Screening: Run rapid single-pass detection on all incoming train coaches.
3. Diagnostic Escalation: On any Moderate or Severe defect, trigger 5-pass TTA & Layer-CAM.
4. Schedule Deconfliction: Check maintenance turnaround window against operating runs.
5. Work Order Release: Issue stamped depot maintenance PDF before releasing train to service.
`;
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "chakraksh-depot-checklist.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="hero-38">
      <div className="hero-38-container" id="top">
        {/* Ambient Display Watermark Word */}
        <div className="ghost-word" aria-hidden="true">
          chakraksh
        </div>

        {/* Central Particle Simulation */}
        <section className="visual" role="img" aria-label="Interactive particle simulation of wheel aperture tree branch">
          <div className="visual__sim" id="visual-sim">
            <ParticleSimulation
              portraitImage="/tree.png"
              background="transparent"
              density={50}
              dotSize={30}
              hover={{ reach: 32, lift: 51, damping: 58 }}
              style={{ width: "100%", height: "100%", minWidth: 0, minHeight: 0 }}
            />
          </div>
        </section>

        {/* Bottom Hero Layout */}
        <section className="bottom-layout">
          <div className="headline-block">
            <button className="dark-cta" id="howBtn" onClick={() => setShowHow(true)}>
              <span>See how it works</span>
              <span className="arrow">↗</span>
            </button>
            <h1>
              Predictive wheel health<br />
              that survives scrutiny.
            </h1>
          </div>

          <p className="intro">
            Chakraksh analyzes wayside acoustic and visual telemetry the moment a train passes — detecting surface spalling, calibrating risk, and orchestrating maintenance before defects cause operational holds.
          </p>

          <div className="stat-grid" id="benchmarks">
            <article className="stat-card" onClick={() => navigate("/inspect")} style={{ cursor: "pointer" }}>
              <strong>99.4%</strong>
              <div className="stat-bottom">
                <p>Defect detection precision across Vande Bharat and freight bogies.</p>
                <button aria-label="Open inspection studio" className="round-link">
                  ↗
                </button>
              </div>
            </article>

            <article className="stat-card" onClick={() => navigate("/dashboard")} style={{ cursor: "pointer" }}>
              <strong>120+</strong>
              <div className="stat-bottom">
                <p>Active wheelsets and coaches tracked in real-time across railway depots.</p>
                <button aria-label="Open fleet dashboard" className="round-link">
                  ↗
                </button>
              </div>
            </article>
          </div>
        </section>

        {/* Interactive "How it Works" Panel */}
        {showHow && (
          <div className="demo-panel" id="how" role="dialog" aria-modal="true" aria-labelledby="how-title">
            <button className="panel-close" id="closePanel" aria-label="Close" onClick={() => setShowHow(false)}>
              ×
            </button>
            <span className="eyebrow">HOW IT WORKS</span>
            <h2 id="how-title">Wayside Sensing → AI Grading → Work Order</h2>
            <p>
              Chakraksh continuously monitors the wheelsets of operating railway stock. When high-speed wayside cameras capture a wheel, our calibrated YOLOv8 pipeline detects surface flaws in ~0.4s.
            </p>
            <p style={{ marginTop: "0.6rem" }}>
              Depot supervisors escalate flagged wheels for 5-pass Test-Time Augmentation (TTA) and Layer-CAM attention heatmaps, and our conflict-free scheduler locks in depot repair windows before the train departs.
            </p>
            <div style={{ marginTop: "1.2rem", display: "flex", gap: "0.6rem" }}>
              <button className="primary sm" onClick={() => navigate("/inspect")}>
                Try Live Inspection
              </button>
              <button className="ghost sm" onClick={() => navigate("/dashboard")}>
                Explore Fleet
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
