import Foundation

// Codable mirrors of the Magneetar server API. Field names use
// convertFromSnakeCase on decode (device_id → deviceId), so every property
// here is camelCase Swift against the snake_case JSON contract. Timestamps
// are kept as strings — the server emits several ISO-8601 variants and the
// UI formats them with `displayDate` helpers instead of risking decode
// failures on exotic formats.

// MARK: - Auth

struct TokenResponse: Codable, Equatable {
    let token: String
    let refreshToken: String
    let tokenType: String?
    let expiresIn: Int?
}

/// Dynamic login response: either real tokens, or a 2FA challenge
/// ({requires_2fa, two_factor_token}) when the account has TOTP enabled.
struct LoginChallenge: Codable, Equatable {
    let requires2fa: Bool?
    let twoFactorToken: String?
}

struct UserResponse: Codable, Equatable {
    let id: String
    let email: String
    let displayName: String?
    let tier: String?
    let isActive: Bool?
    let createdAt: String?
    let deviceCount: Int?
    let maxDevices: Int?
    let totpEnabled: Bool?
    let emailVerified: Bool?
}

struct TwoFactorSetupResponse: Codable, Equatable {
    let secret: String
    let otpauthUri: String
    let qrSvgDataUri: String?
}

// MARK: - Device (tracked-device side)

struct DeviceRegistrationRequest: Encodable {
    let deviceId: String
    let fingerprint: String
    let model: String
    let osVersion: String
    let appVersion: String
    let imeiHash: String
    let simSerialHash: String
    let deviceKey: String
    let simPhone: String
}

struct DeviceRegistrationResponse: Decodable {
    let token: String
    let refreshToken: String
    let deviceId: String
    let hasDeviceKey: Bool
    let ownerId: String?
}

struct HeartbeatPacket: Encodable {
    let deviceId: String
    let batteryPercent: Int?
    let isCharging: Bool?
    let networkType: String?
    let appVersion: String?
}

struct LocationReport: Encodable {
    let deviceId: String
    let lat: Double
    let lng: Double
    let accuracy: Double?
    let provider: String?
    let timestamp: String?
}

struct FCMTokenRequest: Encodable {
    let deviceId: String
    let fcmToken: String
    let platform: String
}

struct DeviceCommand: Decodable, Identifiable {
    let id: Int
    let command: String
    let params: String?
    let priority: Int?
}

struct CommandAckRequest: Encodable {
    let status: String          // "executed" | "failed"
    let failureReason: String?
}

// MARK: - Dashboard (owner side)

struct Device: Decodable, Identifiable, Equatable {
    let id: String
    let alias: String?
    let model: String?
    let osVersion: String?
    let appVersion: String?
    let lastSeen: String?
    let registered: String?
    let isStolen: Bool?
    let operatingMode: String?
    let sentinelScore: Int?
    let lat: Double?
    let lng: Double?
    // Optional: the server emits null when the device has no location row
    // yet (the join to locations yields no battery either).
    let batteryPercent: Int?
    let locationEncrypted: Bool?
    let isOnline: Bool?
    let accessRole: String?
    let isOwner: Bool?
    let captureArmed: Bool?
    let archivedAt: String?
    let alertPhone: String?
    let alertEmail: String?
    let smsPhone: String?
    let smsCommandsEnabled: Bool?
    /// Human-friendly name for lists/maps.
    var displayName: String {
        alias ?? model ?? id
    }
}

struct CommandRequest: Encodable {
    let deviceId: String
    let command: String
    let params: String?
    let password: String?
}

struct GeofenceRequest: Encodable {
    let deviceId: String
    let name: String?
    let centerLat: Double
    let centerLng: Double
    let radiusMeters: Double
    let isSafeZone: Bool
    let autoAction: String?
}

struct Geofence: Codable, Identifiable, Equatable {
    let id: Int
    let deviceId: String
    let name: String?
    let centerLat: Double
    let centerLng: Double
    let radiusMeters: Double
    let isSafeZone: Bool?
    let active: Bool?
}

struct AlertItem: Decodable, Identifiable, Equatable {
    let id: Int
    let deviceId: String
    let alertType: String?
    let message: String?
    let severity: String?
    let sentAt: String?
    let channel: String?
}

struct MediaItem: Decodable, Identifiable, Equatable {
    let id: Int
    let deviceId: String
    let type: String
    let timestamp: String?
    let lat: Double?
    let lng: Double?
}

// MARK: - Response envelopes

struct DeviceListResponse: Decodable {
    let devices: [Device]
}

struct CommandListResponse: Decodable {
    let commands: [DeviceCommand]
}

struct GeofenceListResponse: Decodable {
    let geofences: [Geofence]
}

struct AlertListResponse: Decodable {
    let alerts: [AlertItem]
}

struct MediaListResponse: Decodable {
    let media: [MediaItem]
}

// MARK: - Display helpers

extension String {
    /// Best-effort ISO-8601 → short display string ("15 Aug, 14:32").
    var displayDateTime: String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let isoNoFraction = ISO8601DateFormatter()
        isoNoFraction.formatOptions = [.withInternetDateTime]
        guard let date = iso.date(from: self) ?? isoNoFraction.date(from: self) else { return self }
        let formatter = DateFormatter()
        formatter.dateFormat = "d MMM, HH:mm"
        return formatter.string(from: date)
    }

    var displayRelative: String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let isoNoFraction = ISO8601DateFormatter()
        isoNoFraction.formatOptions = [.withInternetDateTime]
        guard let date = iso.date(from: self) ?? isoNoFraction.date(from: self) else { return self }
        let seconds = max(0, Date().timeIntervalSince(date))
        switch seconds {
        case ..<60: return "just now"
        case ..<3600: return "\(Int(seconds / 60))m ago"
        case ..<86400: return "\(Int(seconds / 3600))h ago"
        default: return "\(Int(seconds / 86400))d ago"
        }
    }
}
