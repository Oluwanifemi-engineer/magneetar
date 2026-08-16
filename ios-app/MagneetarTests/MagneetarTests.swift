import XCTest
import CryptoKit
@testable import Magneetar

/// Core-logic tests that run without a device or network: API contract
/// decoding, the pairing-code derivation (must match the server's
/// sha256(device_key)[:8]), and display formatting.
final class MagneetarTests: XCTestCase {

    // MARK: - Auth contract

    func testLoginResultDecodesTokens() throws {
        let json = #"{"token":"abc.def","refresh_token":"refresh-1","token_type":"bearer","expires_in":3600}"#
        let result = try LoginResult.decode(Data(json.utf8))
        guard case .tokens(let tokens) = result else {
            return XCTFail("expected .tokens")
        }
        XCTAssertEqual(tokens.token, "abc.def")
        XCTAssertEqual(tokens.refreshToken, "refresh-1")
    }

    func testLoginResultDecodesTwoFactorChallenge() throws {
        let json = #"{"requires_2fa":true,"two_factor_token":"challenge-token"}"#
        let result = try LoginResult.decode(Data(json.utf8))
        guard case .requires2fa(let token) = result else {
            return XCTFail("expected .requires2fa")
        }
        XCTAssertEqual(token, "challenge-token")
    }

    func testLoginResultRejectsGarbage() {
        XCTAssertThrowsError(try LoginResult.decode(Data("{}".utf8)))
    }

    // MARK: - Pairing code (server parity)

    func testPairingCodeMatchesServerDerivation() {
        // Server: sha256(key).hexdigest()[:8]. CryptoKit hex is lowercase,
        // same as Python's hexdigest.
        let key = "test-device-key-\(UUID().uuidString)"
        let expected = Self.sha256Hex(key).prefix(8)
        XCTAssertEqual(String(SettingsView.pairingCode), String(expected))
    }

    // MARK: - Model decoding (snake_case → camelCase)

    func testDeviceDecodesFromSnakeCase() throws {
        let json = """
        {"id":"dev-1","alias":"My phone","model":"iPhone 15","os_version":"17.5",
         "last_seen":"2026-08-16T10:00:00Z","is_stolen":false,
         "sentinel_score":0,"lat":7.5181,"lng":4.5284,"battery_percent":82,
         "is_online":true,"access_role":"owner","is_owner":true}
        """
        let device = try JSONDecoder().decode(Device.self, from: Data(json.utf8))
        XCTAssertEqual(device.id, "dev-1")
        XCTAssertEqual(device.accessRole, "owner")
        XCTAssertEqual(device.displayName, "My phone")
        XCTAssertEqual(device.lat, 7.5181)
    }

    func testGeofenceRequestEncodesSnakeCase() throws {
        let req = GeofenceRequest(
            deviceId: "dev-1", name: "Home", centerLat: 7.5, centerLng: 4.5,
            radiusMeters: 500, isSafeZone: true, autoAction: "alert"
        )
        let data = try JSONEncoder().encode(req)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["device_id"] as? String, "dev-1")
        XCTAssertEqual(json["radius_meters"] as? Double, 500)
        XCTAssertEqual(json["is_safe_zone"] as? Bool, true)
        XCTAssertEqual(json["center_lat"] as? Double, 7.5)
    }

    // MARK: - Display helpers

    func testDisplayRelative() {
        let future = ISO8601DateFormatter().string(from: Date())
        XCTAssertEqual(future.displayRelative, "just now")
    }

    func testDisplayDateTimeParsesFractionalISO() {
        let iso = "2026-08-16T10:00:00.123456+00:00"
        XCTAssertFalse(iso.displayDateTime.isEmpty)
        XCTAssertNotEqual(iso.displayDateTime, iso) // must actually format
    }

    // MARK: - Helpers

    private static func sha256Hex(_ string: String) -> String {
        let digest = SHA256.hash(data: Data(string.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}
