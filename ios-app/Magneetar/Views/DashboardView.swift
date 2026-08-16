import SwiftUI

/// Owner dashboard: live device list with online state, battery, last seen
/// and role tag. Pull-to-refresh + live WS updates; each row opens the
/// device detail (map, commands, geofences, alerts, evidence).
struct DashboardView: View {
    @EnvironmentObject var session: Session
    @State private var devices: [Device] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            List {
                if let errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
                if devices.isEmpty && !isLoading {
                    emptyState
                }
                ForEach(devices) { device in
                    NavigationLink(value: device) {
                        DeviceRow(device: device)
                    }
                }
            }
            .navigationTitle("My devices")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink {
                        SettingsView()
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        Task { await load() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(isLoading)
                }
            }
            .navigationDestination(for: Device.self) { device in
                DeviceDetailView(device: device)
            }
            .task {
                await load()
                DashboardSocket.shared.connectIfAuthenticated()
            }
            .refreshable { await load() }
            .onChange(of: DashboardSocket.shared.lastEvent?.type) { type in
                // Live refresh on any relevant broadcast (device_update,
                // command_ack, alert) — cheap, keeps the list honest.
                guard type == "device_update" || type == "command_ack" || type == "alert" else { return }
                Task { await load(quiet: true) }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "iphone.radiowaves.left.and.right")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            Text("No devices yet")
                .font(.headline)
            Text("Protect this iPhone from Settings, or install Magneetar on an Android phone and link it here.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    @MainActor
    private func load(quiet: Bool = false) async {
        if !quiet { isLoading = true }
        defer { if !quiet { isLoading = false } }
        do {
            let response: DeviceListResponse = try await APIClient.shared.request("GET", "/api/dashboard/devices")
            devices = response.devices
            errorMessage = nil
        } catch {
            if !quiet { errorMessage = error.localizedDescription }
        }
    }
}

/// One device row: name, online dot, battery, last seen, role.
struct DeviceRow: View {
    let device: Device

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(device.isOnline == true ? Color.green : Color.gray)
                .frame(width: 10, height: 10)

            VStack(alignment: .leading, spacing: 2) {
                Text(device.displayName)
                    .font(.headline)
                if let model = device.model, !model.isEmpty {
                    Text(model)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                if let battery = device.batteryPercent {
                    HStack(spacing: 2) {
                        Image(systemName: "battery.\(batteryIcon(battery))")
                        Text("\(battery)%")
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
                Text(device.lastSeen?.displayRelative ?? "—")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let role = device.accessRole, role != "owner" {
                    Text(role)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(Capsule().fill(Color.orange.opacity(0.2)))
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func batteryIcon(_ level: Int) -> String {
        switch level {
        case ..<20: return "25"
        case ..<45: return "50"
        case ..<75: return "75"
        default: return "100"
        }
    }
}
