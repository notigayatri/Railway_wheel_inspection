import { useState, useRef, useEffect } from "react";
import { useAuth } from "../useAuth.js";

const ROLES = [
  {
    key: "ADMIN",
    label: "Chief Engineer",
    short: "CHIEF ENGINEER",
    tag: "Admin • L3",
    color: "#b45309",
    desc: "Full administrative authority. Register rolling stock, modify operating schedules, restore database.",
    permissions: "All permissions unlocked",
  },
  {
    key: "MAINTENANCE_SUPERVISOR",
    label: "Maintenance Supervisor",
    short: "SUPERVISOR",
    tag: "Supervisor • L2",
    color: "#48807a",
    desc: "Depot maintenance planning. Issue work orders, confirm slots, schedule repairs, take snapshots.",
    permissions: "Locked: Train/Coach/Wheel registration, database restore",
  },
  {
    key: "OPERATOR",
    label: "Wayside Operator",
    short: "OPERATOR",
    tag: "Operator • L1",
    color: "#64748b",
    desc: "Wayside pass-by screening. Defect detection, TTA reliability verification, telemetry view.",
    permissions: "Locked: Work orders, slot confirmations, train registration",
  },
];

export default function RoleDropdown() {
  const { role, roleTitle, changeRole, switching } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  // Close when clicking outside
  useEffect(() => {
    const handleOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const handleEsc = (e) => {
      if (e.key === "Escape") setOpen(false);
    };

    if (open) {
      document.addEventListener("mousedown", handleOutside);
      document.addEventListener("keydown", handleEsc);
    }
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleEsc);
    };
  }, [open]);

  const activeRole = ROLES.find((r) => r.key === role) || ROLES[2];

  const handleSelect = async (roleKey) => {
    if (roleKey === role) {
      setOpen(false);
      return;
    }
    await changeRole(roleKey);
    setOpen(false);
  };

  return (
    <div className="nav-role-dropdown" ref={containerRef}>
      <button
        type="button"
        className={`role-trigger-btn ${open ? "open" : ""} ${switching ? "busy" : ""}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Switch RBAC Active Role & Permission Authority"
      >
        <span className="role-shield-icon" aria-hidden="true">
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M8 1.5l5 2.5v4c0 3.5-2.5 6-5 7-2.5-1-5-3.5-5-7V4l5-2.5z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="role-name">{activeRole.short}</span>
        <span className="role-lvl-pill">{activeRole.tag.split("•")[1]?.trim() || "L1"}</span>
        <span className={`role-chevron ${open ? "rotate" : ""}`} aria-hidden="true">
          <svg viewBox="0 0 10 6" width="9" height="6" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M1 1l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {open && (
        <div className="role-menu-popover" role="listbox" aria-label="Available User Roles">
          <div className="role-menu-header">
            <span className="eyebrow-mini">ACCESS CONTROL HIERARCHY</span>
            <span className="role-status-dot active" title="Active Session" />
          </div>

          <div className="role-menu-list">
            {ROLES.map((r) => {
              const isSelected = r.key === role;
              return (
                <button
                  key={r.key}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={`role-item ${isSelected ? "selected" : ""}`}
                  onClick={() => handleSelect(r.key)}
                  disabled={switching}
                >
                  <div className="role-item-top">
                    <span className="role-item-title">{r.label}</span>
                    <span className={`role-item-badge ${r.key.toLowerCase()}`}>{r.tag}</span>
                  </div>
                  <p className="role-item-desc">{r.desc}</p>
                  <div className="role-item-perms">
                    {isSelected ? (
                      <span className="perm-active-check">
                        <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M2.5 6.5l2.5 2.5 4.5-5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        Active Role
                      </span>
                    ) : (
                      <span className="perm-hint">{r.permissions}</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          <div className="role-menu-footer">
            <span>Role changes instantly update UI permissions across all views.</span>
          </div>
        </div>
      )}
    </div>
  );
}
