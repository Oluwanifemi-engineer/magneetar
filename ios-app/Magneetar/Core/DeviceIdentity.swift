import Foundation
import UIKit

/// Per-install identity for the tracked-device side.
///
/// - `deviceID`   — stable UUID identifying this iPhone to the server
///                  (Android mirror: the generated device_id).
/// - `deviceKey`  — per-device SECRET key, stored in the Keychain, sent as
///                  the `x-device-key` header on every device route. The
///                  server stores only SHA-256(deviceKey), so even a DB
///                  breach never exposes it.
/// - `fingerprint`— stable per-install fingerprint for reinstall adoption
///                  (Android mirror: ANDROID_ID). identifierForVendor is
///                  stable while the app stays installed from the same
///                  vendor, which is exactly the adoption scenario.
enum DeviceIdentity {
    private static let deviceIDDefaultsKey = "magneetar.device_id"
    private static let deviceKeyKeychainKey = "magneetar.device_key"

    static var deviceID: String {
        if let existing = UserDefaults.standard.string(forKey: deviceIDDefaultsKey) {
            return existing
        }
        let fresh = UUID().uuidString
        UserDefaults.standard.set(fresh, forKey: deviceIDDefaultsKey)
        return fresh
    }

    static var deviceKey: String {
        if let existing = KeychainStore.read(deviceKeyKeychainKey) {
            return existing
        }
        let fresh = UUID().uuidString
        KeychainStore.save(fresh, key: deviceKeyKeychainKey)
        return fresh
    }

    static var fingerprint: String {
        UIDevice.current.identifierForVendor?.uuidString ?? deviceID
    }

    /// True once this iPhone has been registered as a protected device
    /// (Settings → Protect this iPhone). The local flag mirrors the Android
    /// app's SharedPreferences "registered" marker.
    static var isRegistered: Bool {
        get { UserDefaults.standard.bool(forKey: "magneetar.device_registered") }
        set { UserDefaults.standard.set(newValue, forKey: "magneetar.device_registered") }
    }
}
