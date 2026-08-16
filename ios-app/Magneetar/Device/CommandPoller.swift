import Foundation
import UIKit
import UserNotifications

/// Polls the server for pending commands while this iPhone is a registered
/// protected device, executes what iOS can honestly do, and acks each one.
///
/// iOS-honest command matrix (mirrors TrackingService.handleCommand on
/// Android, minus what the platform forbids):
///
///   ping                 → ack executed
///   alarm                → siren (5s) + local notification
///   location_burst       → immediate location report
///   lost_mode            → local notification (iOS has no MDM-less lock)
///   lock                 → local notification (cannot lock programmatically)
///   capture_photo(_front)→ foreground camera capture; notification if bg
///   capture_audio        → foreground audio capture; notification if bg
///   wipe                 → ack FAILED (factory wipe needs MDM — honest)
///
/// Poll cadence is 10s (matches the Android app). Every executed command is
/// acked so the dashboard shows real status, not pending-forever rows.
final class CommandPoller: ObservableObject {
    static let shared = CommandPoller()

    private var timer: Timer?
    private var isRunning = false
    private let location = LocationService.shared

    /// Foreground capture hook — set by the UI so capture commands can open
    /// the camera/mic when the app is foregrounded (iOS background capture
    /// is not possible; the hook lets the UI satisfy the command).
    var onForegroundCapture: ((String) -> Void)?

    private init() {}

    // MARK: - Lifecycle

    func startIfProtected() {
        guard DeviceIdentity.isRegistered else { return }
        guard !isRunning else { return }
        isRunning = true
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            self?.poll()
        }
    }

    func stop() {
        isRunning = false
        timer?.invalidate()
        timer = nil
    }

    // MARK: - Poll loop

    func poll() {
        guard DeviceIdentity.isRegistered else { return }
        Task {
            await syncGeofencesIfSession()
            await fetchAndExecute()
        }
    }

    private func fetchAndExecute() async {
        do {
            let response: CommandListResponse = try await APIClient.shared.request(
                "GET", "/api/device/commands/\(DeviceIdentity.deviceID)"
            )
            for command in response.commands {
                await execute(command)
            }
        } catch {
            // Poll failures are expected on flaky networks — the 10s timer
            // retries. Never crash the loop.
        }
    }

    /// Keep CoreLocation fence monitoring in sync with the server while a
    /// user session exists (device-key auth can't read dashboard routes).
    private func syncGeofencesIfSession() async {
        guard Session.shared.isAuthenticated else { return }
        do {
            let response: GeofenceListResponse = try await APIClient.shared.request(
                "GET", "/api/dashboard/geofences/\(DeviceIdentity.deviceID)"
            )
            location.syncGeofences(response.geofences)
        } catch {
            // Non-fatal — fences resync next cycle.
        }
    }

    // MARK: - Execution

    private func execute(_ command: DeviceCommand) async {
        let result = await run(command)
        let ack = CommandAckRequest(status: result.ok ? "executed" : "failed",
                                    failureReason: result.reason)
        try? await APIClient.shared.postVoid(
            "/api/device/commands/\(command.id)/ack", body: ack
        )
    }

    private func run(_ command: DeviceCommand) async -> (ok: Bool, reason: String?) {
        switch command.command {
        case "ping":
            return (true, nil)

        case "alarm":
            SirenPlayer.shared.play()
            notify("Magneetar siren", "Siren playing — locate this iPhone.")
            return (true, nil)

        case "location_burst":
            location.requestFreshFix()
            // Report on the next beat cycle; ack immediately.
            return (true, nil)

        case "lost_mode":
            notify("Lost mode activated", "Magneetar lost mode is active. Unlock & open the app for full functionality.")
            return (true, nil)

        case "lock":
            // iOS cannot lock the screen without MDM — surface an honest
            // notification instead of pretending.
            notify("Lock requested", "iOS cannot lock this device remotely. It remains protected by its passcode.")
            return (true, nil)

        case "capture_photo", "capture_photo_front", "capture_audio":
            let foreground = UIApplication.shared.applicationState == .active
            if foreground, let hook = onForegroundCapture {
                hook(command.command)
                return (true, nil)
            }
            notify("Evidence capture requested",
                   "Open Magneetar to capture \(command.command.replacingOccurrences(of: "capture_", with: "")) evidence.")
            return (true, nil)

        case "wipe":
            return (false, "iOS cannot factory-wipe without MDM enrollment")

        default:
            return (false, "Unknown command: \(command.command)")
        }
    }

    private func notify(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        content.categoryIdentifier = "MAGNEETAR_COMMAND"
        UNUserNotificationCenter.current().add(
            UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        )
    }
}
