# Magneetar API Documentation

**Base URL**: `https://api.magneetar.me`  
**Version**: 1.4.4  
**Last Updated**: 2026-09-03

---

## Overview

Magneetar provides a RESTful API for anti-theft tracking, device management, and real-time location monitoring. The API supports two primary authentication methods:

1. **Device Authentication**: JWT tokens for Android app devices
2. **Dashboard Authentication**: JWT tokens for web dashboard users

---

## Authentication

### Device Authentication

Devices authenticate using a device key generated during registration. The server issues a JWT token valid for 30 days.

```http
POST /api/device/register
Content-Type: application/json

{
  "device_id": "unique-device-identifier",
  "model": "Samsung Galaxy S24",
  "os_version": "14",
  "app_version": "1.4.4"
}
```

**Response**:
```json
{
  "device_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "device_key": "a1b2c3d4e5f6...",
  "expires_at": "2026-10-03T00:00:00Z"
}
```

### Dashboard Authentication

Users authenticate with email/password. The server issues access and refresh tokens.

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure-password"
}
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600
}
```

---

## Device Endpoints

### Register Device

```http
POST /api/device/register
```

Registers a new device and returns authentication credentials.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | string | Yes | Unique device identifier |
| model | string | No | Device model (e.g., "Samsung Galaxy S24") |
| os_version | string | No | Android OS version |
| app_version | string | No | Magneetar app version |

**Response**: `200 OK` or `409 Conflict` (device already registered)

---

### Report Location

```http
POST /api/device/location
Authorization: Bearer {device_token}
```

Reports GPS coordinates and device telemetry.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | string | Yes | Device identifier |
| lat | number | Yes | Latitude (-90 to 90) |
| lng | number | Yes | Longitude (-180 to 180) |
| accuracy | number | No | GPS accuracy in meters |
| speed | number | No | Speed in m/s |
| bearing | number | No | Bearing in degrees |
| battery_percent | number | No | Battery level (0-100) |
| is_charging | boolean | No | Charging status |
| network_type | string | No | "wifi", "4g", "3g", etc. |

**Response**: `200 OK`

**Rate Limit**: 1 request per 3 seconds (enforced client-side)

---

### Send Heartbeat

```http
POST /api/device/heartbeat
Authorization: Bearer {device_token}
```

Sends periodic device health status.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | string | Yes | Device identifier |
| battery_percent | number | No | Battery level (0-100) |
| is_charging | boolean | No | Charging status |
| device_admin_active | boolean | No | Device admin status |
| sim_hash | string | No | SIM serial hash (for change detection) |
| app_version | string | No | Current app version |

**Response**: `200 OK` with pending commands (if any)

**Rate Limit**: 1 request per 60 seconds

---

### Upload Evidence Media

```http
POST /api/device/media
Authorization: Bearer {device_token}
Content-Type: application/json
```

Uploads photos or audio recordings as evidence.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | string | Yes | Device identifier |
| type | string | Yes | "photo" or "audio" |
| data_b64 | string | Yes | Base64-encoded media data |
| lat | number | No | Capture location latitude |
| lng | number | No | Capture location longitude |

**Response**: `200 OK` with `media_id`

**Size Limit**: 10MB per upload

---

### Poll Commands

```http
GET /api/device/commands/{device_id}
Authorization: Bearer {device_token}
```

Retrieves pending commands for the device.

**Response**:
```json
{
  "commands": [
    {
      "id": 123,
      "command": "lock",
      "params": {},
      "issued_at": "2026-09-03T08:00:00Z"
    }
  ]
}
```

---

### Acknowledge Command

```http
POST /api/device/commands/{command_id}/ack
Authorization: Bearer {device_token}
```

Marks a command as executed or failed.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | string | Yes | "executed" or "failed" |
| failure_reason | string | No | Reason if status is "failed" |

---

## Dashboard Endpoints

### User Registration

```http
POST /api/auth/register
Content-Type: application/json
```

Creates a new user account.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email | string | Yes | User email address |
| password | string | Yes | Password (min 8 characters) |
| display_name | string | No | Display name |

**Response**: `201 Created` with verification email sent

---

### List Devices

```http
GET /api/dashboard/devices
Authorization: Bearer {access_token}
```

Returns all devices owned by the authenticated user.

**Response**:
```json
{
  "devices": [
    {
      "id": "device-123",
      "alias": "My Phone",
      "model": "Samsung Galaxy S24",
      "last_seen": "2026-09-03T08:00:00Z",
      "battery_percent": 87,
      "is_charging": true,
      "online": true,
      "last_location": {
        "lat": 6.5244,
        "lng": 3.3792,
        "accuracy": 10,
        "timestamp": "2026-09-03T08:00:00Z"
      },
      "sentinel_score": 12,
      "threat_level": "safe"
    }
  ]
}
```

---

### Issue Remote Command

```http
POST /api/dashboard/command
Authorization: Bearer {access_token}
```

Sends a command to a device.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | string | Yes | Target device |
| command | string | Yes | Command type (see below) |
| params | object | No | Command parameters |

**Command Types**:
- `lock` - Lock the device with a PIN
- `alarm` - Trigger a loud siren
- `capture_photo` - Take a front-camera photo
- `capture_audio` - Record 10 seconds of audio
- `wipe` - Factory reset the device (requires step-up auth). Only executes when the device has granted Device Admin; otherwise app data is cleared, Lost Mode engages, and the command acks `failed` with the reason
- `locate` - Request immediate GPS update

**Response**: `200 OK` with `command_id`

---

### Get Device Location History

```http
GET /api/dashboard/devices/{device_id}/locations?start={iso8601}&end={iso8601}
Authorization: Bearer {access_token}
```

Returns location history for a time range.

**Query Parameters**:
- `start`: ISO 8601 timestamp (default: 24 hours ago)
- `end`: ISO 8601 timestamp (default: now)

**Response**: Array of location objects

---

### Create Geofence

```http
POST /api/dashboard/geofence
Authorization: Bearer {access_token}
```

Creates a geofence (safe zone or danger zone).

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | string | Yes | Device to track |
| name | string | No | Geofence name |
| center_lat | number | Yes | Center latitude |
| center_lng | number | Yes | Center longitude |
| radius_meters | number | Yes | Radius in meters (10-10000) |
| is_safe_zone | boolean | No | Default true |
| auto_action | string | No | "capture", "alarm", or null |

---

### Get Evidence Cases

```http
GET /api/dashboard/evidence/{device_id}
Authorization: Bearer {access_token}
```

Returns evidence cases for a device.

**Response**:
```json
{
  "cases": [
    {
      "id": "case-123",
      "device_id": "device-456",
      "created_at": "2026-09-01T10:00:00Z",
      "status": "active",
      "photo_count": 5,
      "audio_count": 2
    }
  ]
}
```

---

### Generate Police Report PDF

```http
POST /api/dashboard/evidence/{device_id}/generate-pdf
Authorization: Bearer {access_token}
```

Generates a PDF police report from evidence.

**Response**: PDF file download

---

## WebSocket Real-Time Updates

### Connect

```javascript
const ws = new WebSocket('wss://api.magneetar.me/ws?token={access_token}');
```

### Message Types

**Server → Client**:
```json
{
  "type": "device_location",
  "device_id": "device-123",
  "lat": 6.5244,
  "lng": 3.3792,
  "timestamp": "2026-09-03T08:00:00Z"
}
```

```json
{
  "type": "alert",
  "device_id": "device-123",
  "alert_type": "theft_detected",
  "message": "Suspicious activity detected"
}
```

```json
{
  "type": "device_offline",
  "device_id": "device-123"
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {}
}
```

**Common Error Codes**:
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (invalid/expired token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (resource already exists)
- `429` - Rate Limited
- `500` - Internal Server Error

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/device/register` | 5 requests | 1 hour |
| `/api/device/location` | 1 request | 3 seconds |
| `/api/device/heartbeat` | 1 request | 60 seconds |
| `/api/auth/login` | 10 requests | 1 minute |
| All others | 100 requests | 1 minute |

---

## SDKs and Client Libraries

### JavaScript/TypeScript

```bash
npm install @magneetar/sdk
```

```typescript
import { MagneetarClient } from '@magneetar/sdk';

const client = new MagneetarClient({
  apiUrl: 'https://api.magneetar.me',
  accessToken: 'your-token'
});

const devices = await client.devices.list();
```

### Android (Kotlin)

```kotlin
val api = MagneetarApi(context)
api.reportLocation(lat, lng, accuracy)
```

---

## Support

- **Documentation**: https://docs.magneetar.me
- **API Status**: https://status.magneetar.me
- **Support**: support@magneetar.me
- **GitHub Issues**: https://github.com/magneetar/magneetar/issues
