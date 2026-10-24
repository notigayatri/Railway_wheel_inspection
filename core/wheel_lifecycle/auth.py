"""
core/wheel_lifecycle/auth.py
============================
Authentication & Role-Based Access Control (RBAC) Module for Railway Wheel Health.

Roles:
  - OPERATOR: View fleet, trains, wheels, schedules, download reports, and submit inspections.
  - MAINTENANCE_SUPERVISOR: All OPERATOR privileges + generate recommendations, confirm slots, and update job status.
  - ADMIN: All SUPERVISOR privileges + register trains, coaches, wheels, create schedules, and manage users.

Supports:
  - JWT Bearer tokens (HS256)
  - API Keys via X-API-Key header or ?api_key= query parameter (for direct browser PDF downloads)
  - PBKDF2-HMAC password hashing
  - Built-in seeded accounts:
      * admin      / admin123  (ADMIN)
      * supervisor / super123  (MAINTENANCE_SUPERVISOR)
      * operator   / oper123   (OPERATOR)
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import jwt
from fastapi import Depends, Header, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core.wheel_lifecycle.database import DatabaseManager

# ── Cryptographic Constants ──────────────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "railway-wheel-health-rbac-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ── Roles & Hierarchy ────────────────────────────────────────────────────────
ROLE_OPERATOR = "OPERATOR"
ROLE_MAINTENANCE_SUPERVISOR = "MAINTENANCE_SUPERVISOR"
ROLE_ADMIN = "ADMIN"

ROLE_HIERARCHY: Dict[str, int] = {
    ROLE_OPERATOR: 1,
    ROLE_MAINTENANCE_SUPERVISOR: 2,
    ROLE_ADMIN: 3,
}

# Pre-seeded API keys for automated wayside scanners & integration scripts
DEFAULT_API_KEYS = {
    "adm-key-secret-999": ("admin", ROLE_ADMIN),
    "sup-key-secret-888": ("supervisor", ROLE_MAINTENANCE_SUPERVISOR),
    "opr-key-secret-777": ("operator", ROLE_OPERATOR),
}

security_bearer = HTTPBearer(auto_error=False)


# ── Password Hashing Helpers ──────────────────────────────────────────────────
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash password with PBKDF2-HMAC-SHA256 and return (hex_hash, salt)."""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    ).hex()
    return pw_hash, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify plain password against stored PBKDF2 hash and salt."""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)


# ── JWT Token Helpers ─────────────────────────────────────────────────────────
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Auth Models ───────────────────────────────────────────────────────────────
class UserLoginRequest(BaseModel):
    username: str = Field(..., description="Username e.g. admin, supervisor, operator")
    password: str = Field(..., description="Password e.g. admin123, super123, oper123")


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    full_name: str
    api_key: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: str
    user_id: int
    expires_in_minutes: int


# ── Auth Repository & Database ────────────────────────────────────────────────
class AuthRepository:
    """Handles user persistence, password validation, and DB migrations."""

    def __init__(self):
        self.db = DatabaseManager().get_connection()
        self._ensure_table()
        self.seed_default_users()

    def _ensure_table(self):
        cursor = self.db.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'OPERATOR',
            full_name TEXT NOT NULL,
            api_key TEXT UNIQUE,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
        """)
        self.db.commit()

    def seed_default_users(self):
        """Seed default Admin, Supervisor, and Operator if not present."""
        defaults = [
            ("admin", "admin123", ROLE_ADMIN, "Chief Rolling Stock Engineer (Admin)", "adm-key-secret-999"),
            ("supervisor", "super123", ROLE_MAINTENANCE_SUPERVISOR, "Depot Maintenance Supervisor", "sup-key-secret-888"),
            ("operator", "oper123", ROLE_OPERATOR, "Wayside Inspection Operator", "opr-key-secret-777"),
        ]
        cursor = self.db.cursor()
        now = datetime.now().isoformat(timespec="seconds")

        for u_name, u_pass, u_role, u_fullname, u_key in defaults:
            cursor.execute("SELECT id FROM users WHERE username=?", (u_name,))
            if not cursor.fetchone():
                pw_hash, salt = hash_password(u_pass)
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, salt, role, full_name, api_key, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (u_name, pw_hash, salt, u_role, u_fullname, u_key, now),
                )
        self.db.commit()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM users WHERE api_key=?", (api_key,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_users(self) -> List[Dict[str, Any]]:
        cursor = self.db.cursor()
        cursor.execute("SELECT id, username, role, full_name, api_key, created_at, last_login FROM users ORDER BY id")
        return [dict(r) for r in cursor.fetchall()]

    def update_last_login(self, user_id: int):
        cursor = self.db.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cursor.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
        self.db.commit()


# ── Dependency Injection for FastAPI ──────────────────────────────────────────
def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    query_api_key: Optional[str] = Query(None, alias="api_key"),
    query_token: Optional[str] = Query(None, alias="token"),
) -> Dict[str, Any]:
    """
    Authenticate request via JWT Bearer token, X-API-Key header, or query param.
    If no credentials are provided, defaults to ADMIN in dev/test mode so automated
    background tests and local scripts continue working with zero friction.
    """
    repo = AuthRepository()

    # 1. Check API Key (Header or Query Param)
    api_key = x_api_key or query_api_key
    if api_key:
        user = repo.get_user_by_api_key(api_key)
        if user:
            return user
        # Check hardcoded default api keys
        if api_key in DEFAULT_API_KEYS:
            u_name, u_role = DEFAULT_API_KEYS[api_key]
            user = repo.get_user_by_username(u_name)
            if user:
                return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 2. Check JWT Bearer Token (Authorization Header or Query Param)
    token = None
    if auth_header and auth_header.credentials:
        token = auth_header.credentials
    elif query_token:
        token = query_token

    if token:
        payload = decode_access_token(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = repo.get_user_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    # 3. Handling unauthenticated requests:
    require_auth_env = os.environ.get("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")
    if require_auth_env:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token or API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # In local development mode without explicit auth credentials,
    # default to OPERATOR role (can view & submit inspections, but cannot confirm jobs or register trains).
    anonymous_role = os.environ.get("DEV_ANONYMOUS_ROLE", ROLE_OPERATOR)
    default_user = repo.get_user_by_username(
        "operator" if anonymous_role == ROLE_OPERATOR else "admin"
    )
    if default_user:
        return default_user

    return {
        "id": 3,
        "username": "operator",
        "role": anonymous_role,
        "full_name": "Wayside Inspection Operator (Guest)",
    }


def require_role(min_role: str):
    """
    FastAPI dependency that enforces a minimum RBAC role hierarchy:
      ADMIN (3) > MAINTENANCE_SUPERVISOR (2) > OPERATOR (1)
    """
    def _role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = user.get("role", ROLE_OPERATOR).upper()
        user_level = ROLE_HIERARCHY.get(user_role, 0)
        required_level = ROLE_HIERARCHY.get(min_role.upper(), 999)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access Denied: Requires '{min_role}' role or higher. "
                    f"Current user '{user.get('username')}' has role '{user_role}'."
                ),
            )
        return user

    return _role_checker
