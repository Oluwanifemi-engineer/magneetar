import Foundation

/// Build-time configuration, injected from `Config.xcconfig` via Info.plist
/// (the iOS mirror of the Android app's `BuildConfig.SERVER_URL` /
/// `BuildConfig.DEVICE_KEY`).
enum Config {
    /// Low-privilege shared device key — MUST match the server's MT_DEVICE_KEY
    /// (the DEVICE key, never the master MT_API_KEY). Public by design: it
    /// ships inside every install and only authorises device-scope endpoints.
    /// The per-device secret key (DeviceIdentity.deviceKey) is what actually
    /// protects each device's routes.
    static let deviceKey: String =
        Bundle.main.object(forInfoDictionaryKey: "MagneetarDeviceKey") as? String ?? ""

    /// API origin, e.g. https://api.magneetar.me
    static let serverURL: String =
        Bundle.main.object(forInfoDictionaryKey: "MagneetarServerURL") as? String ?? "https://api.magneetar.me"

    static var apiBase: URL {
        URL(string: serverURL)!
    }

    /// WebSocket origin for live dashboard updates (/ws/dashboard).
    static var wsURL: URL {
        var components = URLComponents(string: serverURL)!
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        return components.url!
    }
}
