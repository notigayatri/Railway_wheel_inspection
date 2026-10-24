import { useState, useEffect, useCallback } from "react";
import { getCurrentUser, switchPresetRole, PRESET_USERS } from "./api.js";

/**
 * Reactive Authentication & RBAC Hook.
 * Automatically synchronizes whenever switchPresetRole or auth-changed is fired.
 */
export function useAuth() {
  const [user, setUser] = useState(getCurrentUser());
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    const handleAuth = (e) => {
      setUser(e?.detail?.user || getCurrentUser());
    };
    window.addEventListener("auth-changed", handleAuth);
    return () => window.removeEventListener("auth-changed", handleAuth);
  }, []);

  const changeRole = useCallback(async (roleKey) => {
    setSwitching(true);
    try {
      const u = await switchPresetRole(roleKey);
      if (u) setUser(u);
    } finally {
      setSwitching(false);
    }
  }, []);

  const role = (user?.role || "OPERATOR").toUpperCase();
  const isAdmin = role === "ADMIN";
  const isSupervisor = isAdmin || role === "MAINTENANCE_SUPERVISOR";
  const isOperator = true; // All roles inherit operator baseline

  const level = isAdmin ? 3 : isSupervisor ? 2 : 1;

  const roleTitle = isAdmin
    ? "Chief Engineer"
    : role === "MAINTENANCE_SUPERVISOR"
    ? "Supervisor"
    : "Operator";

  return {
    user,
    role,
    roleTitle,
    level,
    isAdmin,
    isSupervisor,
    isOperator,
    switching,
    changeRole,
    presets: PRESET_USERS,
  };
}
