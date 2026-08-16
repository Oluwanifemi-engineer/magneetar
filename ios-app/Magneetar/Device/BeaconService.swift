import Foundation
import Combine
import SystemConfiguration
import UIKit

/// Background heartbeat + location reporter for a protected iPhone.
///
/// While `DeviceIdentity.isRegistered`, posts a heartbeat every 60s (with
/// battery/network state) and a location report whenever a fix is available
/// (or on geofence exit). Runs from the app's lifecycle — on iOS a
/// terminated app cannot self-awaken on a timer, so the authoritative
/// always-on beat comes from the server's archive monitor + push-triggered
/// launch; this service keeps the beat alive while the app is running or
/// has a background task grant.
final class BeaconService: ObservableObject {
    static let shared = BeaconService()

    private let location = LocationService.shared
    private var timer: Timer?
    private var isRunning = false

    private init() {
        // Report fence exits to the server so the alert engine can fire
        // geofence_exit alerts exactly like the Android app does.
        location.onGeofenceExit = { [weak self] fence in
            Task { await self?.reportGeofenceExit(fence) }
        }
    }

    // MARK: - Lifecycle

    /// Start when this iPhone is a registered protected device.
    func startIfProtected() {
        guard DeviceIdentity.isRegistered else { return }
        guard !isRunning else { return }
        isRunning = true

        location.requestAlwaysAuthorization()
        location.start()
        location.restoreGeofencesIfNeeded()

        // Immediate first beat, then every 60s.
        Task { await beat() }
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { await self?.beat() }
        }
    }

    func stop() {
        isRunning = false
        timer?.invalidate()
        timer = nil
        location.stop()
    }

    // MARK: - Beats

    private func beat() async {
        guard DeviceIdentity.isRegistered else { return }
        await sendHeartbeat()
        if let fix = location.lastLocation {
            await sendLocation(lat: fix.coordinate.latitude, lng: fix.coordinate.longitude,
                               accuracy: fix.horizontalAccuracy)
        } else {
            // No fix yet — ask for one; CoreLocation will callback via
            // didUpdateLocations and the next beat reports it.
            location.requestFreshFix()
        }
    }

    func sendHeartbeat() async {
        // Enable battery monitoring FIRST, then read (the level is -1 until
        // monitoring is on for a beat or two).
        UIDevice.current.isBatteryMonitoringEnabled = true
        let battery = UIDevice.current.batteryLevel
        let packet = HeartbeatPacket(
            deviceId: DeviceIdentity.deviceID,
            batteryPercent: battery >= 0 ? Int(battery * 100) : nil,
            isCharging: UIDevice.current.batteryState == .charging || UIDevice.current.batteryState == .full,
            networkType: Self.networkType,
            appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        )
        try? await APIClient.shared.postVoid("/api/device/heartbeat", body: packet)
    }

    func sendLocation(lat: Double, lng: Double, accuracy: Double?) async {
        let report = LocationReport(
            deviceId: DeviceIdentity.deviceID,
            lat: lat,
            lng: lng,
            accuracy: accuracy,
            provider: "ios",
            timestamp: ISO8601DateFormatter().string(from: Date())
        )
        try? await APIClient.shared.postVoid("/api/device/location", body: report)
    }

    /// Fire an immediate location report (command: location_burst / locate).
    func reportNow() async {
        if let fix = location.lastLocation {
            await sendLocation(lat: fix.coordinate.latitude, lng: fix.coordinate.longitude,
                               accuracy: fix.horizontalAccuracy)
        } else {
            location.requestFreshFix()
        }
    }

    private func reportGeofenceExit(_ fence: Geofence) async {
        // The server's geofence engine keys on device pings; a dedicated
        // exit report keeps the alert immediate rather than waiting for the
        // next heartbeat cadence. The endpoint is the same location POST
        // (the server derives enter/exit from it).
        if let fix = location.lastLocation {
            await sendLocation(lat: fix.coordinate.latitude, lng: fix.coordinate.longitude,
                               accuracy: fix.horizontalAccuracy)
        }
    }

    // MARK: - Helpers

    private static var networkType: String {
        // Honest minimal mapping: wifi vs cellular (no entitlement needed).
        // "cellular" covers 2G/3G/4G/5G — the server only needs the class.
        let status = Reachability.current
        return status
    }
}

/// Tiny reachability helper (no third-party dep, matches the server's
/// network_type values: "wifi" / "cellular").
enum Reachability {
    static var current: String {
        var zero = sockaddr_storage()
        zero.ss_len = UInt8(MemoryLayout<sockaddr_storage>.size)
        zero.ss_family = sa_family_t(AF_INET)
        var flags = SCNetworkReachabilityFlags()
        guard let ref = withUnsafePointer(to: &zero, {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                SCNetworkReachabilityCreateWithAddress(nil, $0)
            }
        }) else { return "unknown" }
        SCNetworkReachabilityGetFlags(ref, &flags)
        return flags.contains(.isWWAN) ? "cellular" : "wifi"
    }
}
