# Magneetar API Reference

## Base URL

- **Production**: `https://api.magneetar.me`
- **Development**: `http://localhost:8000`

## Authentication

Magneetar supports multiple authentication methods:

### 1. API Key (Dashboard)

```bash
curl -H "Authorization: Bearer <api_key>" https://api.magneetar.me/api/dashboard/devices
```

### 2. Device Key

```bash
curl -H "x-device-key: <device_key>" https://api.magneetar.me/api/device/location
```

### 3. JWT Token

```bash
curl -H "Authorization: Bearer <jwt_token>" https://api.magneetar.me/api/device/location
```

## Endpoints

### Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "online",
  "version": "1.4.0",
  "uptime": 12345.67,
  "server_time": "2026-08-09T12:00:00Z",
  "database": true
}
```

### Metrics

```
GET /metrics
```

**Response (Prometheus format):**
```
# HELP magneetar_uptime_seconds Server uptime in seconds
# TYPE magneetar_uptime_seconds gauge
magneetar_uptime_seconds 12345.67
# HELP magneetar_devices_total Total registered devices
# TYPE magneetar_devices_total gauge
magneetar_devices_total 42
```

```
GET /metrics/json
```

**Response (JSON):**
```json
{
  "timestamp": "2026-08-09T12:00:00Z",
  "uptime_seconds": 12345.67,
  "devices": {
    "total": 42,
    "active_1h": 15,
    "owned": 38
  },
  "users": {
    "total": 10,
    "active_24h": 5
  },
  "alerts": {
    "total_24h": 25,
    "delivered_24h": 23,
    "failed_24h": 2
  }
}
```

## Device Endpoints

### Register Device

```
POST /api/device/register
```

**Headers:**
- `Content-Type: application/json`
- `x-device-key: <device_key>` (optional, for device key auth)

**Body:**
```json
{
  "device_id": "device-uuid",
  "model": "Samsung Galaxy S24",
  "android_version": "14",
  "manufacturer": "Samsung"
}
```

**Response:**
```json
{
  "device_id": "device-uuid",
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

### Send Location

```
POST /api/device/location
```

**Headers:**
- `Authorization: Bearer <jwt_token>`
- `Content-Type: application/json`

**Body:**
```json
{
  "lat": 6.5244,
  "lng": 3.3792,
  "accuracy": 10.5,
  "battery": 85,
  "speed": 1.2,
  "heading": 180.0,
  "altitude": 50.0,
  "sim_id": "8901234567890",
  "signal_strength": -75,
  "network_type": "wifi",
  "timestamp": "2026-08-09T12:00:00Z"
}
```

**Response:**
```json
{
  "status": "ok",
  "sentinel_score": 0,
  "commands": []
}
```

### Send Heartbeat

```
POST /api/device/heartbeat
```

**Headers:**
- `Authorization: Bearer <jwt_token>`

**Body:**
```json
{
  "battery": 85,
  "storage_used_gb": 64.5,
  "storage_total_gb": 128.0,
  "ram_used_mb": 3200,
  "ram_total_mb": 8192,
  "uptime_seconds": 86400,
  "device_admin_active": true,
  "is_charging": false
}
```

### Poll Commands

```
POST /api/device/command/poll
```

**Headers:**
- `Authorization: Bearer <jwt_token>`

**Response:**
```json
{
  "commands": [
    {
      "id": "cmd-uuid",
      "type": "lock",
      "status": "pending",
      "created_at": "2026-08-09T12:00:00Z"
    }
  ]
}
```

### Acknowledge Command

```
POST /api/device/command/{command_id}/ack
```

**Headers:**
- `Authorization: Bearer <jwt_token>`

**Body:**
```json
{
  "status": "executed",
  "failure_reason": null
}
```

### Upload Media

```
POST /api/device/media
```

**Headers:**
- `Authorization: Bearer <jwt_token>`
- `Content-Type: multipart/form-data`

**Body:**
- `file`: Photo or audio file
- `media_type`: "photo" | "audio" | "video"
- `device_id`: Device UUID
- `latitude`: Location latitude
- `longitude`: Location longitude
- `timestamp`: Capture timestamp

### Register FCM Token

```
POST /api/device/fcm-token
```

**Headers:**
- `Content-Type: application/json`

**Body:**
```json
{
  "token": "fcm-device-token",
  "device_id": "device-uuid"
}
```

## Dashboard Endpoints

### Login

```
POST /api/auth/login
```

**Body:**
```json
{
  "api_key": "your-api-key"
}
```

**Response:**
```json
{
  "token": "eyJ...",
  "token_type": "bearer"
}
```

### Get Devices

```
GET /api/dashboard/devices
```

**Headers:**
- `Authorization: Bearer <dashboard_token>`

**Response:**
```json
{
  "devices": [
    {
      "id": "device-uuid",
      "model": "Samsung Galaxy S24",
      "last_seen": "2026-08-09T12:00:00Z",
      "owner_id": "user-uuid",
      "sentinel_score": 0,
      "battery": 85,
      "location": {
        "lat": 6.5244,
        "lng": 3.3792
      }
    }
  ]
}
```

### Send Command

```
POST /api/dashboard/command
```

**Headers:**
- `Authorization: Bearer <dashboard_token>`
- `Content-Type: application/json`

**Body:**
```json
{
  "device_id": "device-uuid",
  "command_type": "lock",
  "params": ""
}
```

**Command Types:**
- `lock` - Lock the device
- `wipe` - Factory reset (requires `params: "CONFIRMED_WIPE"` + step-up password). NOTE: executes only when the device has granted Device Admin; otherwise the app clears app-private data, engages Lost Mode, and acks `failed` with the reason — check the command outcome rather than assuming a reset
- `alarm` - Play siren alarm
- `capture_photo` - Take front camera photo
- `capture_audio` - Record 20s audio
- `burst` - 5 rapid location updates

### Get Stats

```
GET /api/dashboard/stats
```

**Response:**
```json
{
  "total_devices": 42,
  "active_devices": 15,
  "total_users": 10,
  "alerts_today": 25,
  "commands_today": 50
}
```

### Get Evidence

```
GET /api/dashboard/evidence/{case_id}
```

**Headers:**
- `Authorization: Bearer <dashboard_token>`

**Response:**
```json
{
  "case_id": "case-uuid",
  "device_id": "device-uuid",
  "photos": [...],
  "audio": [...],
  "chain_of_custody": [...]
}
```

### Generate Evidence PDF

```
GET /api/dashboard/evidence/{case_id}/pdf
```

**Headers:**
- `Authorization: Bearer <dashboard_token>`

**Response:** PDF file download

### Get Error Log

```
GET /api/dashboard/errors
```

**Headers:**
- `Authorization: Bearer <dashboard_token>`

**Query Parameters:**
- `limit`: Number of errors to return (default: 100)
- `level`: Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

## User Endpoints

### Sign Up

```
POST /api/auth/user/signup
```

**Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "display_name": "John Doe"
}
```

### Sign In

```
POST /api/auth/user/signin
```

**Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

### Forgot Password

```
POST /api/auth/forgot-password
```

**Body:**
```json
{
  "email": "user@example.com"
}
```

### Reset Password

```
POST /api/auth/reset-password
```

**Body:**
```json
{
  "email": "user@example.com",
  "token": "reset-token",
  "new_password": "newsecurepassword123"
}
```

### Verify Email

```
POST /api/auth/verify-email
```

**Body:**
```json
{
  "token": "verification-token"
}
```

## Two-Factor Authentication

### Setup 2FA

```
POST /api/auth/2fa/setup
```

**Headers:**
- `Authorization: Bearer <user_token>`

**Response:**
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "otpauth_uri": "otpauth://totp/Magneetar:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Magneetar",
  "qr_svg_data_uri": "data:image/svg+xml;base64,..."
}
```

### Enable 2FA

```
POST /api/auth/2fa/enable
```

**Headers:**
- `Authorization: Bearer <user_token>`

**Body:**
```json
{
  "password": "currentpassword",
  "code": "123456"
}
```

### Disable 2FA

```
POST /api/auth/2fa/disable
```

**Headers:**
- `Authorization: Bearer <user_token>`

**Body:**
```json
{
  "password": "currentpassword"
}
```

## Guardian Network

### Opt-in to Guardian Network

```
POST /api/guardian/opt-in
```

**Headers:**
- `Authorization: Bearer <user_token>`

### Report Sighting

```
POST /api/guardian/sighting
```

**Headers:**
- `Authorization: Bearer <user_token>`

**Body:**
```json
{
  "device_id": "device-uuid",
  "latitude": 6.5244,
  "longitude": 3.3792,
  "notes": "Device found in abandoned building"
}
```

### Launch Recovery Request

```
POST /api/guardian/recovery
```

**Headers:**
- `Authorization: Bearer <user_token>`

**Body:**
```json
{
  "device_id": "device-uuid",
  "latitude": 6.5244,
  "longitude": 3.3792,
  "description": "Phone stolen from office"
}
```

## WebSocket

### Dashboard Connection

```
ws://api.magneetar.me/ws/dashboard?token=<jwt_token>
```

**Events:**
- `device_update` - Device location/status changed
- `alert` - New alert triggered
- `command_ack` - Command acknowledged by device
- `shutdown` - Server shutting down

**Keepalive:**
- Client sends: `{"type": "pong"}`
- Server sends: `{"type": "pong"}`

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 429 | Rate Limit Exceeded |
| 500 | Internal Server Error |
| 504 | Request Timeout |

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/device/register` | 10 | 10 min |
| `/api/device/location` | 20 | 1 min |
| `/api/device/heartbeat` | 10 | 1 min |
| `/api/device/command/poll` | 30 | 1 min |
| `/api/auth/login` | 10 | 15 min |
| `/api/dashboard/command` | 20 | 1 min |

## Changelog

### v1.4.0 (2026-08-06)
- Added device key authentication
- Added metrics endpoint
- Improved alert circuit breaker
- Added evidence chain of custody

### v1.3.0 (2026-08-01)
- Added uninstall protection
- Added background camera/audio capture
- Improved OEM compatibility

### v1.2.0 (2026-07-25)
- Added multi-user support
- Added Guardian Network
- Added per-device alert preferences

---

For interactive API documentation, visit:
- **Swagger UI**: `https://api.magneetar.me/docs` (non-production only)
- **ReDoc**: `https://api.magneetar.me/redoc` (non-production only)
