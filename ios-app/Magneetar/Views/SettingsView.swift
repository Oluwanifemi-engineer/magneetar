import SwiftUI
import CryptoKit

/// Settings: account profile, "Protect this iPhone" (register + link this
/// device so it reports to the account), pairing code, and sign-out.
struct SettingsView: View {
    @EnvironmentObject var session: Session
    @State private var protecting = false
    @State private var busy = false
    @State private var errorMessage: String?

    var body: some View {
        Form {
            if let user = session.user {
                Section("Account") {
                    LabeledContent("Name", value: user.displayName ?? "—")
                    LabeledContent("Email", value: user.email)
                    LabeledContent("Plan", value: user.tier ?? "—")
                    LabeledContent("Devices", value: "\(user.deviceCount ?? 0) / \(user.maxDevices ?? 1)")
                }
            }

            Section("This iPhone") {
                if DeviceIdentity.isRegistered {
                    LabeledContent("Status", value: "Protected")
                    LabeledContent("Device ID", value: DeviceIdentity.deviceID)
                    LabeledContent("Pairing code", value: Self.pairingCode)
                    Text("On another phone, open Magneetar → Settings → Protect this iPhone and enter this code to link it as a protected device.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Register this iPhone as a protected device. It will report its location and geofence exits so it can be recovered if lost or stolen.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button {
                        Task { await protect() }
                    } label: {
                        Group {
                            if busy { ProgressView() } else { Text("Protect this iPhone") }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(busy)
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }

            Section {
                Button("Sign out", role: .destructive) {
                    session.logout()
                }
            }
        }
        .navigationTitle("Settings")
    }

    /// First 8 hex chars of SHA-256(deviceKey) — the server's pairing code
    /// (it stores only the hash, so both sides derive the code without ever
    /// sharing the key).
    static var pairingCode: String {
        let digest = SHA256.hash(data: Data(DeviceIdentity.deviceKey.utf8))
        return digest.map { String(format: "%02x", $0) }.joined().prefix(8).description
    }

    @MainActor
    private func protect() async {
        busy = true
        errorMessage = nil
        defer { busy = false }

        // Permissions first: background location is the core capability.
        LocationService.shared.requestAlwaysAuthorization()
        let center = UNUserNotificationCenter.current()
        _ = try? await center.requestAuthorization(options: [.alert, .sound])

        do {
            let body = DeviceRegistrationRequest(
                deviceId: DeviceIdentity.deviceID,
                fingerprint: DeviceIdentity.fingerprint,
                model: UIDevice.current.modelName,
                osVersion: UIDevice.current.systemVersion,
                appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0",
                imeiHash: DeviceIdentity.fingerprint,
                simSerialHash: DeviceIdentity.fingerprint,
                deviceKey: DeviceIdentity.deviceKey,
                simPhone: ""
            )
            let response: DeviceRegistrationResponse = try await APIClient.shared.request(
                "POST", "/api/device/register",
                body: body,
                extraHeaders: ["x-api-key": Config.deviceKey]
            )

            // Linking: if the register call didn't already attach this
            // account (no bearer sent with it), claim via pairing code.
            if response.ownerId == nil && Session.shared.isAuthenticated {
                let claimBody = ["device_id": response.deviceId, "pairing_code": Self.pairingCode]
                struct ClaimAck: Decodable { let status: String? }
                let _: ClaimAck = try await APIClient.shared.request(
                    "POST", "/api/dashboard/devices/claim-by-pairing",
                    body: claimBody
                )
            }

            DeviceIdentity.isRegistered = true
            BeaconService.shared.startIfProtected()
            CommandPoller.shared.startIfProtected()
            protecting = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private extension UIDevice {
    var modelName: String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let mirror = Mirror(reflecting: systemInfo.machine)
        let identifier = mirror.children.reduce("") { partial, element in
            guard let value = element.value as? Int8, value != 0 else { return partial }
            return partial + String(UnicodeScalar(UInt8(value)))
        }
        return identifier.isEmpty ? "iPhone" : identifier
    }
}
