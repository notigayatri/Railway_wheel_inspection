import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Trains from "./pages/Trains.jsx";
import Inspect from "./pages/Inspect.jsx";
import Planner from "./pages/Planner.jsx";
import Wheels from "./pages/Wheels.jsx";
import RoleDropdown from "./components/RoleDropdown.jsx";

export default function App() {
  const loc = useLocation();
  const isHomePage = loc.pathname === "/home";

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
    <div className={`shell ${isHomePage ? "shell-home" : ""}`}>
      <header className="global-nav">
        <Link to="/home" className="brand" aria-label="Chakraksh Home" title="Chakraksh Home">
          chakraksh.
        </Link>

        <nav className="nav-links" aria-label="Primary navigation">
          <NavLink
            to="/dashboard"
            className={({ isActive }) => (isActive || loc.pathname === "/" ? "active" : "")}
          >
            DASHBOARD
          </NavLink>
          <NavLink to="/trains">TRAINS</NavLink>
          <NavLink to="/inspect">INSPECTIONS</NavLink>
          <NavLink to="/planner">MAINTENANCE</NavLink>
          <NavLink to="/wheels">WHEELS</NavLink>
        </nav>

        <div className="nav-actions">
          <RoleDropdown />

          <button
            className="nav-btn-outline"
            onClick={handleDownloadChecklist}
            title="Download Depot Safety Checklist"
          >
            Download
          </button>
        </div>
      </header>

      <main key={loc.pathname} className={`page ${isHomePage ? "page-home" : ""}`}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/home" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/trains" element={<Trains />} />
          <Route path="/inspect" element={<Inspect />} />
          <Route path="/planner" element={<Planner />} />
          <Route path="/wheels" element={<Wheels />} />
        </Routes>
      </main>
    </div>
  );
}

