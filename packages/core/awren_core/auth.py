"""Authentication and authorization for Awren Core API.

Provides JWT-based auth, password hashing, API key support,
and RBAC with role-based access control.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from awren_core.database import create_session
from awren_core.orm_models import UserModel, RoleModel, PermissionModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SECRET_KEY: str = ""
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_SCHEME = HTTPBearer(auto_error=False)


def _get_secret() -> str:
    global SECRET_KEY
    if not SECRET_KEY:
        from awren_core.settings import get_settings
        env = get_settings()
        SECRET_KEY = env.jwt_secret or secrets.token_hex(32)
    return SECRET_KEY


# ---------------------------------------------------------------------------
# Password hashing (SHA-256 HMAC — no external deps)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split("$", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": time.time()})
    return jwt.encode(to_encode, _get_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# API Key validation
# ---------------------------------------------------------------------------


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def validate_api_key(key: str, db: Session) -> Optional[UserModel]:
    key_hash = _hash_api_key(key)
    user = db.query(UserModel).filter(
        UserModel.api_key_hash == key_hash,
        UserModel.is_active == True,
    ).first()
    if user and user.api_key_expires_at and user.api_key_expires_at < datetime.now(timezone.utc):
        return None
    return user


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------


def _get_db_for_auth() -> Session:
    db = create_session()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(BEARER_SCHEME),
    api_key: Optional[str] = Security(API_KEY_HEADER),
    db: Session = Depends(_get_db_for_auth),
) -> UserModel:
    """Dependency that returns the authenticated user from JWT or API key."""
    if credentials:
        payload = decode_access_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user = db.query(UserModel).filter(
            UserModel.id == UUID(user_id),
            UserModel.is_active == True,
        ).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    if api_key:
        user = validate_api_key(api_key, db)
        if user:
            return user
        raise HTTPException(status_code=401, detail="Invalid API key")

    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(BEARER_SCHEME),
    api_key: Optional[str] = Security(API_KEY_HEADER),
    db: Session = Depends(_get_db_for_auth),
) -> Optional[UserModel]:
    """Dependency that returns the authenticated user or None."""
    if credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            user_id = payload.get("sub")
            if user_id:
                return db.query(UserModel).filter(
                    UserModel.id == UUID(user_id),
                    UserModel.is_active == True,
                ).first()
        except Exception:
            pass
    if api_key:
        return validate_api_key(api_key, db)
    return None


def require_role(role: str):
    """Dependency factory: requires a specific role to access the endpoint."""
    async def _check_role(current_user: UserModel = Depends(get_current_user)) -> UserModel:
        if current_user.role != role and current_user.role != "admin":
            raise HTTPException(status_code=403, detail=f"Requires role: {role}")
        return current_user
    return _check_role


def require_permission(resource: str, action: str):
    """Dependency factory: requires a specific permission."""
    async def _check_permission(
        current_user: UserModel = Depends(get_current_user),
        db: Session = Depends(_get_db_for_auth),
    ) -> UserModel:
        if current_user.role == "admin":
            return current_user
        perm = db.query(PermissionModel).filter(
            PermissionModel.role == current_user.role,
            PermissionModel.resource == resource,
            PermissionModel.action == action,
        ).first()
        if not perm:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {action} on {resource}",
            )
        return current_user
    return _check_permission


# ---------------------------------------------------------------------------
# Seed default roles and permissions
# ---------------------------------------------------------------------------


DEFAULT_ROLES = {
    "admin": "Full system access",
    "operator": "Can manage entities, ingest data, use chat",
    "viewer": "Read-only access to entities and relationships",
    "ingest": "Can upload and process files only",
}

DEFAULT_PERMISSIONS: list[dict[str, str]] = [
    # Admin gets everything via role check

    # Operator permissions
    {"role": "operator", "resource": "entities", "action": "create"},
    {"role": "operator", "resource": "entities", "action": "read"},
    {"role": "operator", "resource": "entities", "action": "update"},
    {"role": "operator", "resource": "entities", "action": "delete"},
    {"role": "operator", "resource": "relationships", "action": "create"},
    {"role": "operator", "resource": "relationships", "action": "read"},
    {"role": "operator", "resource": "relationships", "action": "delete"},
    {"role": "operator", "resource": "ingestion", "action": "upload"},
    {"role": "operator", "resource": "ingestion", "action": "process"},
    {"role": "operator", "resource": "chat", "action": "send"},
    {"role": "operator", "resource": "settings", "action": "read"},
    {"role": "operator", "resource": "settings", "action": "update"},

    # Viewer permissions
    {"role": "viewer", "resource": "entities", "action": "read"},
    {"role": "viewer", "resource": "relationships", "action": "read"},
    {"role": "viewer", "resource": "events", "action": "read"},
    {"role": "viewer", "resource": "chat", "action": "send"},

    # Ingest permissions
    {"role": "ingest", "resource": "ingestion", "action": "upload"},
    {"role": "ingest", "resource": "ingestion", "action": "process"},
    {"role": "ingest", "resource": "entities", "action": "read"},
]


def seed_roles_and_permissions(db: Session) -> None:
    """Seed default roles and permissions if they don't exist."""
    for role_name, desc in DEFAULT_ROLES.items():
        existing = db.query(RoleModel).filter(RoleModel.name == role_name).first()
        if not existing:
            db.add(RoleModel(id=uuid4(), name=role_name, description=desc))

    for perm in DEFAULT_PERMISSIONS:
        existing = db.query(PermissionModel).filter(
            PermissionModel.role == perm["role"],
            PermissionModel.resource == perm["resource"],
            PermissionModel.action == perm["action"],
        ).first()
        if not existing:
            db.add(PermissionModel(id=uuid4(), **perm))

    # Create default admin user if none exists
    admin = db.query(UserModel).filter(UserModel.role == "admin").first()
    if not admin:
        db.add(UserModel(
            id=uuid4(),
            username="admin",
            email="admin@awren.local",
            hashed_password=hash_password("admin"),
            role="admin",
            is_active=True,
        ))

    db.commit()
