"""
routers/auth.py
===============
Authentication & User Management REST endpoints.

POST /api/auth/login     Authenticate with username/password -> return JWT access token
GET  /api/auth/me        Return profile and role of authenticated user
GET  /api/auth/roles     List available roles & permission specifications
GET  /api/auth/users     List registered users (Admin only)
POST /api/auth/users     Register a new user (Admin only)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.wheel_lifecycle.auth import (
    AuthRepository,
    LoginResponse,
    ROLE_ADMIN,
    ROLE_HIERARCHY,
    ROLE_MAINTENANCE_SUPERVISOR,
    ROLE_OPERATOR,
    UserLoginRequest,
    UserResponse,
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., description="Unique username")
    password: str = Field(..., min_length=6, description="Password (min 6 characters)")
    full_name: str = Field(..., description="Full name and designation")
    role: str = Field("OPERATOR", description="OPERATOR | MAINTENANCE_SUPERVISOR | ADMIN")


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate and receive JWT Bearer Token",
    description="Pre-seeded accounts: admin/admin123 (ADMIN), supervisor/super123 (MAINTENANCE_SUPERVISOR), operator/oper123 (OPERATOR)",
)
def login(body: UserLoginRequest):
    repo = AuthRepository()
    user = repo.get_user_by_username(body.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(body.password, user["password_hash"], user["salt"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        data={"sub": user["username"], "role": user["role"], "user_id": user["id"]}
    )
    repo.update_last_login(user["id"])

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
        full_name=user["full_name"],
        user_id=user["id"],
        expires_in_minutes=60 * 24 * 7,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        full_name=current_user["full_name"],
        api_key=current_user.get("api_key"),
    )


@router.get(
    "/roles",
    summary="List available roles and access control hierarchy",
)
def list_roles():
    return {
        "roles": [
            {
                "name": ROLE_OPERATOR,
                "level": 1,
                "description": "Wayside Inspection Operator — view fleet assets, schedules, and submit wheel inspections.",
                "permissions": ["view_fleet", "view_trains", "view_schedules", "inspect_wheel", "download_reports"],
            },
            {
                "name": ROLE_MAINTENANCE_SUPERVISOR,
                "level": 2,
                "description": "Depot Maintenance Supervisor — generate recommendations, confirm maintenance slots, update job status.",
                "permissions": ["all_operator_permissions", "recommend_maintenance", "confirm_maintenance_slot", "update_job_status"],
            },
            {
                "name": ROLE_ADMIN,
                "level": 3,
                "description": "Chief Rolling Stock Engineer / Admin — register trains, coaches, wheels, operating schedules, user management.",
                "permissions": ["all_supervisor_permissions", "register_train", "add_coach", "add_wheel", "create_schedules", "manage_users"],
            },
        ],
        "hierarchy": ROLE_HIERARCHY,
    }


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List all system users (Admin only)",
)
def list_users(current_user: Dict[str, Any] = Depends(require_role(ROLE_ADMIN))):
    repo = AuthRepository()
    return [UserResponse(**u) for u in repo.list_users()]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new system user (Admin only)",
)
def create_user(
    body: CreateUserRequest,
    current_user: Dict[str, Any] = Depends(require_role(ROLE_ADMIN)),
):
    role_norm = body.role.upper()
    if role_norm not in ROLE_HIERARCHY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role '{body.role}'. Must be one of: {list(ROLE_HIERARCHY.keys())}",
        )

    repo = AuthRepository()
    if repo.get_user_by_username(body.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' is already registered.",
        )

    import secrets
    from datetime import datetime

    pw_hash, salt = hash_password(body.password)
    api_key = f"key-{secrets.token_hex(8)}"
    now = datetime.now().isoformat(timespec="seconds")

    cursor = repo.db.cursor()
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, salt, role, full_name, api_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (body.username, pw_hash, salt, role_norm, body.full_name, api_key, now),
    )
    repo.db.commit()
    user_id = cursor.lastrowid
    new_user = repo.get_user_by_id(user_id)
    return UserResponse(**new_user)
