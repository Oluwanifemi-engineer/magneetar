"""
Magneetar Pydantic Models
Request/response schemas for all API endpoints.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# ─── Device Models ───────────────────────────────────────────────────────────


class DeviceRegistration(BaseModel):
    device_id: str = Field(..., min_length=3, max_length=64)
    fingerprint: str = Field(..., min_length=8)
    model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    imei_hash: Optional[str] = None
    sim_serial_hash: Optional[str] = None
    device_key: Optional[str] = None

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("device_id must be alphanumeric with hyphens/underscores")
        return v


class DeviceClaimRequest(BaseModel):
    """Link an existing device to the authenticated user's account.

    The device is identified either by the `x-device-key` header (preferred,
    since only the device knows its secret key) or by an explicit `device_id`.
    The user is identified by the JWT in the `Authorization` header.
    """

    device_id: Optional[str] = Field(None, min_length=3, max_length=64)

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v):
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("device_id must be alphanumeric with hyphens/underscores")
        return v


class DeviceResponse(BaseModel):
    id: str
    alias: Optional[str] = None
    model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    last_seen: Optional[str] = None
    registered: Optional[str] = None
    is_stolen: bool = False
    operating_mode: str = "normal"
    sentinel_score: int = 0
    # Latest location summary
    lat: Optional[float] = None
    lng: Optional[float] = None
    battery_percent: Optional[int] = None
    is_online: bool = False


# ─── Telemetry Models ────────────────────────────────────────────────────────


class TelemetryPing(BaseModel):
    # Identity
    device_id: str
    session_id: Optional[str] = None
    ping_sequence: Optional[int] = None

    # Primary location
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    altitude: Optional[float] = None
    accuracy_horizontal: Optional[float] = Field(None, ge=0)
    accuracy_vertical: Optional[float] = Field(None, ge=0)
    confidence_level: str = "UNKNOWN"

    # Movement
    speed: Optional[float] = Field(None, ge=0)
    bearing: Optional[float] = Field(None, ge=0, lt=360)
    activity_type: str = "UNKNOWN"
    step_count: Optional[int] = None

    # Signal sources
    provider: str = "UNKNOWN"
    gps_satellite_count: Optional[int] = None
    wifi_bssids: List[str] = []
    cell_tower_ids: List[str] = []
    ble_devices_nearby: Optional[int] = None

    # Device state
    battery_percent: Optional[int] = Field(None, ge=0, le=100)
    is_charging: Optional[bool] = None
    network_type: Optional[str] = None
    signal_strength_dbm: Optional[int] = None
    is_location_enabled: Optional[bool] = None
    is_airplane_mode: Optional[bool] = None
    sim_serial_hash: Optional[str] = None
    sim_changed: bool = False

    # Threat intelligence
    sentinel_score: int = 0
    threat_level: str = "SAFE"
    anomalies: List[str] = []

    # Timestamps
    device_timestamp: Optional[str] = None
    server_timestamp: Optional[str] = None

    # Queue metadata
    was_queued: bool = False
    queued_at: Optional[str] = None
    queue_position: Optional[int] = None

    @field_validator("confidence_level")
    @classmethod
    def validate_confidence(cls, v):
        valid = {"HIGH", "MEDIUM", "LOW", "OFFLINE", "UNKNOWN"}
        if v not in valid:
            raise ValueError(f"confidence_level must be one of {valid}")
        return v

    @field_validator("threat_level")
    @classmethod
    def validate_threat(cls, v):
        valid = {"SAFE", "ELEVATED", "HIGH", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"threat_level must be one of {valid}")
        return v


class LocationReport(BaseModel):
    """Simplified location report for backward compatibility."""

    device_id: str
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None
    provider: Optional[str] = "gps"
    timestamp: Optional[str] = None


class OfflineQueueUpload(BaseModel):
    """Batch upload of queued pings."""

    pings: List[TelemetryPing]


# ─── Media Models ────────────────────────────────────────────────────────────


class MediaReport(BaseModel):
    device_id: str
    type: str  # photo, audio, video
    data_b64: str
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    timestamp: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        valid = {"photo", "audio", "video"}
        if v not in valid:
            raise ValueError(f"type must be one of {valid}")
        return v


class MediaItem(BaseModel):
    id: int
    device_id: str
    type: str
    timestamp: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


# ─── Command Models ──────────────────────────────────────────────────────────


class CommandRequest(BaseModel):
    device_id: str
    command: str
    params: Optional[str] = ""
    priority: int = Field(5, ge=1, le=10)

    @field_validator("command")
    @classmethod
    def validate_command(cls, v):
        valid = {
            "ping",
            "capture_photo",
            "capture_photo_front",
            "capture_photo_rear",
            "capture_audio",
            "location_burst",
            "location_burst_stop",
            "lock",
            "alarm",
            "phantom_on",
            "phantom_off",
            "fake_shutdown",
            "wipe",
        }
        if v not in valid:
            raise ValueError(f"command must be one of {valid}")
        return v


class CommandAck(BaseModel):
    status: str = "executed"  # executed or failed

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in {"executed", "failed"}:
            raise ValueError('status must be "executed" or "failed"')
        return v


class Command(BaseModel):
    id: int
    device_id: str
    command: str
    params: Optional[str] = ""
    status: str = "pending"
    priority: int = 5
    issued_at: Optional[str] = None
    executed_at: Optional[str] = None


# ─── Heartbeat Models ────────────────────────────────────────────────────────


class HeartbeatPacket(BaseModel):
    device_id: str
    battery_percent: Optional[int] = Field(None, ge=0, le=100)
    is_charging: Optional[bool] = None
    network_type: Optional[str] = None
    device_admin_active: Optional[bool] = None
    sim_hash: Optional[str] = None
    app_version: Optional[str] = None
    pending_evidence_count: int = 0


# ─── Auth Models ─────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class LoginRequest(BaseModel):
    api_key: str
    totp_code: Optional[str] = None


class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return v.lower().strip()


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    tier: str = "free"
    is_active: bool = True
    created_at: Optional[str] = None
    device_count: int = 0
    max_devices: int = 5


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Evidence Models ─────────────────────────────────────────────────────────


class EvidenceCase(BaseModel):
    id: str
    device_id: str
    created_at: Optional[str] = None
    theft_time: Optional[str] = None
    status: str = "active"
    location_count: int = 0
    photo_count: int = 0
    audio_count: int = 0
    sha256_chain: Optional[str] = None


class EvidencePackage(BaseModel):
    case_id: str
    status: str
    item_counts: dict
    sha256_chain: Optional[str] = None


# ─── Geofence Models ─────────────────────────────────────────────────────────


class GeofenceRequest(BaseModel):
    device_id: str
    name: Optional[str] = None
    center_lat: float = Field(..., ge=-90, le=90)
    center_lng: float = Field(..., ge=-180, le=180)
    radius_meters: float = Field(..., gt=0, le=50000)
    is_safe_zone: bool = True


class Geofence(BaseModel):
    id: int
    device_id: str
    name: Optional[str] = None
    center_lat: float
    center_lng: float
    radius_meters: float
    is_safe_zone: bool = True
    active: bool = True


# ─── Guardian Network Models ──────────────────────────────────────────────────


class GuardianOptIn(BaseModel):
    """Opt in (or out) as a community guardian who helps recover stolen devices."""

    opted_in: bool = True
    radius_km: int = Field(20, ge=1, le=1000)
    handle: Optional[str] = Field(None, max_length=40)


class GuardianProfile(BaseModel):
    user_id: str
    opted_in: bool = False
    radius_km: int = 20
    handle: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RecoveryRequestCreate(BaseModel):
    device_id: str
    description: Optional[str] = Field(None, max_length=500)


class RecoverySightingCreate(BaseModel):
    request_id: str
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    note: Optional[str] = Field(None, max_length=300)


# ─── Alert Models ────────────────────────────────────────────────────────────


class Alert(BaseModel):
    id: int
    device_id: str
    alert_type: str
    channel: str
    recipient: Optional[str] = None
    message: Optional[str] = None
    sent_at: Optional[str] = None
    delivered: bool = False


class AlertSettings(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    alert_threshold: int = 50
    quiet_hours_start: Optional[int] = None  # 0-23
    quiet_hours_end: Optional[int] = None
    enabled_types: List[str] = ["theft", "sim_change", "battery_low", "offline"]


# ─── Stats Model ─────────────────────────────────────────────────────────────


class DashboardStats(BaseModel):
    total_devices: int = 0
    active_devices: int = 0
    stolen_devices: int = 0
    recovered_devices: int = 0
    total_locations: int = 0
    total_media: int = 0
    alerts_today: int = 0


# ─── Health Model ────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "online"
    version: str = "1.2.0"
    uptime: float = 0.0
    server_time: str
    database: Optional[bool] = None
    """Database connectivity: True=healthy, False=degraded, None=not checked"""


class ConfigResponse(BaseModel):
    app_version: str = "1.2.0"
    min_android_version: int = 24
    features_enabled: List[str] = [
        "sentinel",
        "phantom_mode",
        "evidence_collection",
        "offline_queue",
        "geofencing",
        "real_time_tracking",
    ]
