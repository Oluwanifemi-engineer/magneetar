"""
Magneetar Pydantic Models
Request/response schemas for all API endpoints.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Best-effort SIM phone number (E.164-ish, often empty on Android 10+ due
    # to getLine1Number gating). Used to prefill the Offline Command Relay's
    # sms_phone — the OWNER confirms/overrides it on the dashboard before any
    # SMS is sent.
    sim_phone: Optional[str] = None

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


class DeviceClaimByPairingRequest(BaseModel):
    """Link an ownerless device to the authenticated user's account using the
    pairing code shown in the Magneetar app on the phone.

    The pairing code is the first 8 hex chars of SHA-256(device_key): the app
    displays it (it holds the raw key) and the server stores only the hash, so
    both sides derive it without ever sharing the key. 8 hex chars = 32 bits of
    guessing entropy — safe because the endpoint is rate-limited per user and
    the code is only shown on the physical phone.
    """

    device_id: str = Field(..., min_length=3, max_length=64)
    pairing_code: str = Field(..., min_length=8, max_length=8)

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("device_id must be alphanumeric with hyphens/underscores")
        return v

    @field_validator("pairing_code")
    @classmethod
    def validate_pairing_code(cls, v):
        if not re.match(r"^[a-f0-9]{8}$", v):
            raise ValueError("pairing_code must be 8 lowercase hex characters")
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
    # Failed unlock attempts since the last successful unlock (the "theftie"
    # signal, COMPETITOR_AUDIT P1 #4). Reported by the app's keyguard/DPC
    # monitor on every ping and heartbeat; Sentinel scores it (+20) and the
    # telemetry path queues an evidence capture when it crosses the
    # configured threshold. None = not reported (older app builds).
    failed_unlock_count: Optional[int] = Field(None, ge=0)
    # Armed Watch state — True while the device's camera|mic foreground
    # service is armed (remote capture possible). Reported by the app on
    # every location ping and heartbeat so the dashboard can show the
    # honest capture availability instead of a phantom 'executed'.
    capture_armed: Optional[bool] = None

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
    # Step-up password — REQUIRED for destructive commands (wipe). A stolen
    # dashboard session alone must not be able to factory-reset a device; the
    # caller re-authenticates with the account password (users) or master API
    # key (admin), exactly like device/media deletion. Optional for all other
    # commands so the plain issue flow is unchanged.
    password: Optional[str] = Field(None, max_length=200)

    @field_validator("command")
    @classmethod
    def validate_command(cls, v):
        # Every command here must be IMPLEMENTED end-to-end: the Android app's
        # TrackingService.handleCommand() has a branch for each one. Commands
        # the app cannot execute were removed (phantom_on/off, fake_shutdown,
        # location_burst_stop, capture_photo_rear) — the old set accepted them
        # but the device always acked 'failed', so the dashboard could queue
        # commands that could NEVER work. Keep this list in sync with
        # android-app .../TrackingService.kt and dashboard CommandPanel.tsx.
        valid = {
            "ping",
            "capture_photo",
            "capture_photo_front",
            "capture_audio",
            "location_burst",
            "lock",
            "alarm",
            "wipe",
            "lost_mode",
        }
        if v not in valid:
            raise ValueError(f"command must be one of {valid}")
        return v


class CommandAck(BaseModel):
    status: str = "executed"  # executed or failed
    # Human-readable reason for a FAILED ack (e.g. "Microphone muted — set
    # Microphone to Allow all the time"). The Android app sends it so the
    # dashboard shows WHY a capture failed instead of a bare red FAILED.
    failure_reason: Optional[str] = Field(None, max_length=300)

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
    # Armed Watch state (see TelemetryPing.capture_armed) — sent on the
    # 60s heartbeat so an idle device still reports its capture posture.
    capture_armed: Optional[bool] = None
    # SIM-change signal (see TelemetryPing.sim_changed): the device flags a
    # permission-free operator-fingerprint change exactly once; the server
    # fires the always-deliver sim_changed alert and lets Sentinel score it.
    sim_changed: Optional[bool] = None
    # Failed unlock attempts since the last successful unlock (see
    # TelemetryPing.failed_unlock_count) — carried on the heartbeat so a
    # locked screen is still reported when the location stream is quiet.
    failed_unlock_count: Optional[int] = Field(None, ge=0)
    # Location-services + airplane state (G1-10): a device with location OFF
    # pings 0,0 and the location path rejects the coordinates BEFORE Sentinel
    # scoring — so location_disabled (+20) and airplane_mode (+15) were dead
    # signals. The heartbeat is the designed belt-and-braces path for a quiet
    # location stream (same as admin_disabled), so the state is carried here.
    is_location_enabled: Optional[bool] = None
    is_airplane_mode: Optional[bool] = None


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
    # Account security (v1.4): 2FA state + email verification status, surfaced
    # so the dashboard can show the right settings UI.
    totp_enabled: bool = False
    email_verified: bool = False


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    email: str
    token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return v.lower().strip()

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        # Mirror UserRegisterRequest's strength rules (a reset must not be
        # able to set a weaker password than registration allows).
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)


class TwoFactorVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    password: Optional[str] = Field(None, max_length=200)


class TwoFactorDisableRequest(BaseModel):
    password: str = Field(..., max_length=200)


class LoginTwoFactorRequest(BaseModel):
    two_factor_token: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Developer API Keys (docs/developer-api.md) ──────────────────────────────


class ApiKeyCreateRequest(BaseModel):
    """Create a scoped developer API key (step-up gated).

    scopes defaults to read-only devices:read; a key is ALWAYS intersected
    with the owning account's own rights (a viewer-shared device stays
    read-only through the key too). expires_at (ISO-8601, optional) makes the
    key self-destruct — NULL = never.
    """

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["devices:read"])
    # 'live' (default) or 'readonly'. Readonly keys get the mtk_read_ prefix
    # and can NEVER carry devices:write — enforced at validation AND again at
    # auth time (get_api_key_actor), so a leaked readonly key is structurally
    # incapable of issuing wipe/lock commands even if the row were tampered.
    key_type: str = Field(default="live", max_length=16)
    expires_at: Optional[str] = Field(None, max_length=40)
    # Step-up: the account password is re-verified (rate-limited) so a stolen
    # dashboard session alone cannot mint long-lived credentials.
    password: str = Field(..., max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v):
        from auth import VALID_API_KEY_SCOPES

        if not v:
            raise ValueError("At least one scope is required")
        if not all(isinstance(s, str) for s in v):
            raise ValueError("scopes must be strings")
        unknown = set(v) - VALID_API_KEY_SCOPES
        if unknown:
            raise ValueError(f"Unknown scopes: {sorted(unknown)}")
        # Dedupe, preserving order.
        return list(dict.fromkeys(v))

    @field_validator("key_type")
    @classmethod
    def validate_key_type(cls, v):
        if v not in ("live", "readonly"):
            raise ValueError("key_type must be 'live' or 'readonly'")
        return v

    @model_validator(mode="after")
    def readonly_cannot_write(self):
        # Structural guarantee (belt + braces with auth-time filtering): a
        # readonly key is created without write scopes, and get_api_key_actor
        # re-filters at every request — a leaked readonly key can never wipe
        # or lock a device.
        if self.key_type == "readonly" and "devices:write" in self.scopes:
            raise ValueError("readonly keys cannot carry the devices:write scope")
        return self

    @field_validator("expires_at")
    @classmethod
    def validate_expires(cls, v):
        from datetime import datetime, timezone

        if v is None:
            return v
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("expires_at must be an ISO-8601 timestamp (e.g. 2027-01-01T00:00:00Z)")
        if parsed < datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return v


class ApiKeyActionRequest(BaseModel):
    """Revoke/rotate a key — step-up password re-authenticates the caller."""

    password: str = Field(..., max_length=200)


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    # The FULL key — returned exactly once at creation, never stored.
    key: str
    key_prefix: str
    scopes: list[str]
    key_type: str = "live"
    created_at: str
    expires_at: Optional[str] = None


class ApiKeyListItem(BaseModel):
    """Listed keys expose prefix + metadata only — never the hash or the key.
    key_type tells the owner live vs readonly at a glance; request_count is
    the usage meter (incremented per key-authenticated request)."""

    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    key_type: str = "live"
    request_count: int = 0
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None


class PlanUpdateRequest(BaseModel):
    """Admin-only: set a user's plan tier (manual upgrade path until
    self-serve payments land)."""

    email: str
    tier: str = "free"

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v):
        valid = {"free", "personal", "guardian", "enterprise"}
        if v not in valid:
            raise ValueError(f"tier must be one of {sorted(valid)}")
        return v


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
    # Per-zone automated reaction fired on an EXIT transition (exactly once,
    # at the entry→exit boundary): 'capture' queues a front-camera photo +
    # audio capture, 'siren' queues the max-volume alarm, 'alert' (or None)
    # fires the geofence_exit alert only. The alert always fires for safe-zone
    # exits regardless; auto_action ADDS the on-device reaction
    # (COMPETITOR_AUDIT P0 gap-closer #1).
    auto_action: Optional[str] = None

    @field_validator("auto_action")
    @classmethod
    def validate_auto_action(cls, v):
        if v is None:
            return v
        if v not in {"capture", "siren", "alert"}:
            raise ValueError("auto_action must be one of: capture, siren, alert")
        return v


class Geofence(BaseModel):
    id: int
    device_id: str
    name: Optional[str] = None
    center_lat: float
    center_lng: float
    radius_meters: float
    is_safe_zone: bool = True
    active: bool = True


# ─── Device Sharing Models (Milestone 2 P1) ─────────────────────────────────


class ShareRequest(BaseModel):
    """Grant another account access to a device (roadmap Milestone 2 P1).

    Roles, least → most privileged:
      device_only — status glance only (online, battery, last seen). No
                    location, evidence, or command access (privacy tier).
      viewer      — full read access (locations, media, evidence, history).
      admin       — viewer + full control (commands, geofences, settings).
    Only the device OWNER can grant, change, or revoke shares.
    """

    email: str = Field(..., min_length=5, max_length=255)
    role: str = "viewer"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in {"admin", "viewer", "device_only"}:
            raise ValueError("role must be one of: admin, viewer, device_only")
        return v


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
    # Exactly one of request_id / beacon_token is required: the dashboard
    # flow reports by request_id, while Find Network guardians report the
    # opaque beacon_token they picked up over BLE (the request id never goes
    # on the air). The endpoint resolves either to the active request.
    request_id: Optional[str] = None
    beacon_token: Optional[str] = None
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
    # NOTE: uptime is deliberately NOT exposed publicly (F-08) — it reveals
    # deploy timing. It stays available to operators via the admin-gated
    # /api/metrics endpoint (magneetar_uptime_seconds).
    status: str = "online"
    version: str = "1.2.0"
    server_time: str
    database: Optional[bool] = None
    """Database connectivity: True=healthy, False=degraded, None=not checked"""


class ConfigResponse(BaseModel):
    # Must be passed explicitly by the /api/config handler (main.py passes
    # APP_VERSION from the VERSION file) — a hardcoded default here went stale
    # (1.2.0 vs the live 1.3.0) and silently broke the Android app's
    # "update available" nudge for 1.2.0 users (latestVersion == their version
    # meant no nudge, even though 1.3.0 was out).
    app_version: str
    min_android_version: int = 24
    features_enabled: List[str] = [
        "sentinel",
        "phantom_mode",
        "evidence_collection",
        "offline_queue",
        "geofencing",
        "real_time_tracking",
    ]
    # Offline Command Relay (SMS): the number command SMS are sent FROM. The
    # Android app allowlists this as the ONLY sender that may issue commands
    # (alongside the pairing code) — a leaked/intercepted SMS alone can't be
    # replayed from a different number. Empty when the server has no SMS
    # sender configured; the app then falls back to code-only verification.
    sms_relay_number: str = ""
