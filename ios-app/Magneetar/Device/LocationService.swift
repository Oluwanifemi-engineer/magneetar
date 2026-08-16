import Foundation
import CoreLocation

/// Location + geofence monitoring for the protected-iPhone side.
///
/// iOS honest scope: background location via `significant-change` +
/// `visit` monitoring (both keep running after the app is terminated),
/// and CLRegion geofences pushed from the server. The tracked iPhone can
/// report its position and trigger fence exits without any foreground
/// requirement — the same guarantees Android gives, minus the continuous
/// GPS stream (that's a battery trade iOS makes for us).
final class LocationService: NSObject, ObservableObject, CLLocationManagerDelegate {
    static let shared = LocationService()

    @Published private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published private(set) var lastLocation: CLLocation?
    /// Server geofences mirrored into CLRegion monitoring.
    @Published private(set) var monitoredGeofences: [Geofence] = []

    /// Called on every fence exit (used by BeaconService to report the exit
    /// to the server's alert engine).
    var onGeofenceExit: ((Geofence) -> Void)?

    let manager = CLLocationManager()
    private let defaultsKey = "magneetar.active_geofences"

    private override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.distanceFilter = 250
        manager.pausesLocationUpdatesAutomatically = true
        manager.activityType = .otherNavigation
    }

    // MARK: - Authorization

    var isAuthorized: Bool {
        authorizationStatus == .authorizedAlways || authorizationStatus == .authorizedWhenInUse
    }

    func requestAlwaysAuthorization() {
        manager.requestAlwaysAuthorization()
    }

    // MARK: - Start / stop

    /// Begin background-aware tracking. Significant-change + visit
    /// monitoring are the iOS-native way to keep the phone locatable with
    /// near-zero battery and no persistent green indicator.
    func start() {
        guard isAuthorized else { return }
        if CLLocationManager.significantLocationChangeMonitoringAvailable() {
            manager.startMonitoringSignificantLocationChanges()
        }
        if CLLocationManager.isMonitoringAvailable(for: CLCircularRegion.self) {
            manager.startUpdatingLocation() // seeds an immediate fix, then pauses
        }
        manager.startMonitoringVisits()
    }

    func stop() {
        manager.stopMonitoringSignificantLocationChanges()
        manager.stopUpdatingLocation()
        manager.stopMonitoringVisits()
        for region in manager.monitoredRegions {
            manager.stopMonitoring(for: region)
        }
    }

    /// Request a fresh fix immediately (used by location_burst / locate).
    func requestFreshFix() {
        guard isAuthorized else { return }
        manager.requestLocation()
    }

    // MARK: - Geofences (server mirror)

    /// Sync the server's active geofences into CoreLocation region
    /// monitoring. Safe to call on every poll — CoreLocation handles
    /// duplicate regions gracefully (same identifier = same region).
    func syncGeofences(_ fences: [Geofence]) {
        monitoredGeofences = fences
        // Persist so a cold start after termination can re-register them.
        if let data = try? JSONEncoder().encode(fences) {
            UserDefaults.standard.set(data, forKey: defaultsKey)
        }
        let active = fences.filter { $0.active != false }
        var identifiers = Set(active.map { String($0.id) })
        for region in manager.monitoredRegions {
            guard let circular = region as? CLCircularRegion else { continue }
            if identifiers.contains(circular.identifier) {
                identifiers.remove(circular.identifier)
            } else {
                manager.stopMonitoring(for: circular)
            }
        }
        for fence in active {
            let region = CLCircularRegion(
                center: CLLocationCoordinate2D(latitude: fence.centerLat, longitude: fence.centerLng),
                radius: max(fence.radiusMeters, 100),
                identifier: String(fence.id)
            )
            region.notifyOnEntry = true
            region.notifyOnExit = true
            manager.startMonitoring(for: region)
        }
    }

    /// Restore persisted geofences after a terminated-app relaunch.
    func restoreGeofencesIfNeeded() {
        guard manager.monitoredRegions.isEmpty,
              let data = UserDefaults.standard.data(forKey: defaultsKey),
              let fences = try? JSONDecoder().decode([Geofence].self, from: data) else { return }
        syncGeofences(fences)
    }

    // MARK: - CLLocationManagerDelegate

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        lastLocation = locations.last
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Non-fatal: location simply unavailable right now (airplane mode,
        // denied mid-run). Keep the beacon running — it retries next cycle.
    }

    func locationManager(_ manager: CLLocationManager, didExitRegion region: CLRegion) {
        guard let fence = monitoredGeofences.first(where: { String($0.id) == region.identifier }) else { return }
        onGeofenceExit?(fence)
    }
}
