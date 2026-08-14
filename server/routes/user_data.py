"""
Magneetar User Data API
Endpoints for data export, deletion, and retention controls.
"""

import logging
from typing import Optional

from auth import get_current_user
from data_export import data_export_service
from database import get_db_context, log_audit
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from user_security import _require_user_actor

logger = logging.getLogger(__name__)

# NOTE: data_export / get_db_context / log_audit are imported at MODULE level
# (not inside the handlers) on purpose. data_export does `from database import
# get_db_context` at its own module level, so a lazy `from data_export import
# data_export_service` inside a handler would resolve whichever database
# module is current at request time — under full-suite test collection
# (test_e2e / test_sim_change evict modules from sys.modules) that is a
# DIFFERENT module instance than the one main/app bound at import, so
# deletion/export would run against the wrong DB (same bug class as the
# evidence PDF / step-up password evictions documented in routes/dashboard.py
# and the user_auth bindings). Module-level import binds it alongside main;
# both eviction lists must include data_export so it re-imports fresh with
# main in every era.

router = APIRouter()


class DataExportRequest(BaseModel):
    format: str = "json"  # json or zip


class DataRetentionUpdateRequest(BaseModel):
    locations_days: Optional[int] = None
    commands_days: Optional[int] = None
    alerts_days: Optional[int] = None
    heartbeats_days: Optional[int] = None
    media_days: Optional[int] = None
    evidence_days: Optional[int] = None
    auto_cleanup_enabled: Optional[bool] = None


class AccountDeletionRequest(BaseModel):
    confirm: bool = False
    password: Optional[str] = None


@router.get("/api/user/data/export")
async def export_user_data(
    format: str = "json",
    user_id: str = Depends(get_current_user),
):
    """Export all user data (GDPR data portability)."""
    _require_user_actor(user_id)

    if format == "zip":
        zip_path = data_export_service.create_zip_export(user_id)
        if zip_path:
            from fastapi.responses import FileResponse

            return FileResponse(
                zip_path,
                media_type="application/zip",
                filename=f"magneetar_export_{user_id}.zip",
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to create export")
    else:
        export_data = data_export_service.export_user_data(user_id)
        if "error" in export_data:
            raise HTTPException(status_code=404, detail=export_data["error"])
        return export_data


@router.get("/api/user/data/device/{device_id}")
async def export_device_data(
    device_id: str,
    user_id: str = Depends(get_current_user),
):
    """Export data for a specific device."""
    _require_user_actor(user_id)

    export_data = data_export_service.export_device_data(device_id, user_id)
    if "error" in export_data:
        raise HTTPException(status_code=404, detail=export_data["error"])
    return export_data


@router.delete("/api/user/account")
async def delete_user_account(
    req: AccountDeletionRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """Delete user account and all data (right to erasure)."""
    _require_user_actor(user_id)

    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm deletion with confirm=true",
        )

    # Verify password if provided
    if req.password:
        from auth import check_password_verify_rate_limit, verify_password

        if not check_password_verify_rate_limit(user_id):
            raise HTTPException(status_code=429, detail="Too many verification attempts")

        with get_db_context() as conn:
            user = conn.execute(
                "SELECT password_hash FROM users WHERE id=?",
                (user_id,),
            ).fetchone()

        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")

    # Get client IP for audit
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    )

    result = data_export_service.delete_user_data(user_id, confirm=True)

    log_audit(
        "account_deleted",
        actor=user_id,
        ip_address=client_ip,
        details=str(result.get("deleted", {})),
    )

    return result


@router.get("/api/user/retention")
async def get_retention_settings(
    user_id: str = Depends(get_current_user),
):
    """Get data retention settings."""
    _require_user_actor(user_id)

    from data_retention import data_retention_service

    return data_retention_service.get_user_retention(user_id)


@router.patch("/api/user/retention")
async def update_retention_settings(
    req: DataRetentionUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """Update data retention settings."""
    _require_user_actor(user_id)

    from data_retention import data_retention_service

    return data_retention_service.update_user_retention(
        user_id,
        locations_days=req.locations_days,
        commands_days=req.commands_days,
        alerts_days=req.alerts_days,
        heartbeats_days=req.heartbeats_days,
        media_days=req.media_days,
        evidence_days=req.evidence_days,
        auto_cleanup_enabled=req.auto_cleanup_enabled,
    )


@router.post("/api/user/retention/cleanup")
async def trigger_cleanup(
    dry_run: bool = False,
    user_id: str = Depends(get_current_user),
):
    """Trigger data cleanup based on retention settings."""
    _require_user_actor(user_id)

    from data_retention import data_retention_service

    return data_retention_service.cleanup_user_data(user_id, dry_run=dry_run)


@router.get("/api/user/retention/schedule")
async def get_cleanup_schedule(
    user_id: str = Depends(get_current_user),
):
    """Get cleanup schedule information."""
    _require_user_actor(user_id)

    from data_retention import data_retention_service

    return data_retention_service.get_cleanup_schedule()


@router.get("/api/user/data/status")
async def get_export_status(
    user_id: str = Depends(get_current_user),
):
    """Get export status for user."""
    _require_user_actor(user_id)

    from data_export import data_export_service

    return data_export_service.get_export_status(user_id)
