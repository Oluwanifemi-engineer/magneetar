import SwiftUI
import MapKit

/// Per-device control center: live map, command buttons, geofences, alert
/// history and evidence media. Role-gated: viewer/device_only shares can
/// look but not control (mirrors the server's _assert_device_access).
struct DeviceDetailView: View {
    let device: Device
    @State private var region = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 0, longitude: 0),
        span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
    )
    @State private var devices: [Device] = []
    @State private var geofences: [Geofence] = []
    @State private var alerts: [AlertItem] = []
    @State private var media: [MediaItem] = []
    @State private var errorMessage: String?
    @State private var busyCommand: String?
    @State private var showAddGeofence = false

    private var canControl: Bool {
        device.accessRole != "viewer" && device.accessRole != "device_only"
    }

    var body: some View {
        List {
            mapSection
            if canControl { commandsSection }
            geofencesSection
            alertsSection
            evidenceSection
        }
        .navigationTitle(device.displayName)
        .task {
            await loadAll()
        }
        .refreshable { await loadAll() }
        .sheet(isPresented: $showAddGeofence) {
            AddGeofenceView(deviceId: device.id, center: region.center) {
                Task { await loadGeofences() }
            }
        }
    }

    // MARK: - Map

    private var mapSection: some View {
        Section("Live location") {
            Map(coordinateRegion: $region, annotationItems: mapAnnotations) { item in
                MapAnnotation(coordinate: item.coordinate) {
                    VStack(spacing: 2) {
                        Image(systemName: item.icon)
                            .font(.system(size: item.isDevice ? 22 : 16))
                            .foregroundStyle(item.isDevice ? .red : .blue)
                        if item.isDevice {
                            Text(device.displayName)
                                .font(.caption2)
                                .padding(4)
                                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
                        }
                    }
                }
            }
            .frame(height: 260)
        }
    }

    private struct MapItem: Identifiable {
        let id: String
        let coordinate: CLLocationCoordinate2D
        let icon: String
        let isDevice: Bool
    }

    private var mapAnnotations: [MapItem] {
        var items: [MapItem] = []
        if let lat = device.lat, let lng = device.lng {
            items.append(MapItem(id: "device", coordinate: .init(latitude: lat, longitude: lng),
                                 icon: "iphone", isDevice: true))
            region.center = .init(latitude: lat, longitude: lng)
        }
        for fence in geofences {
            items.append(MapItem(id: "fence-\(fence.id)",
                                 coordinate: .init(latitude: fence.centerLat, longitude: fence.centerLng),
                                 icon: fence.isSafeZone == true ? "checkmark.shield" : "exclamationmark.shield",
                                 isDevice: false))
        }
        return items
    }

    // MARK: - Commands

    private var commandsSection: some View {
        Section("Commands") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                commandButton("Ping", icon: "waveform.path.ecg", command: "ping")
                commandButton("Locate", icon: "location", command: "location_burst")
                commandButton("Siren", icon: "speaker.wave.2", command: "alarm", tint: .orange)
                commandButton("Photo", icon: "camera", command: "capture_photo_front")
                commandButton("Audio", icon: "mic", command: "capture_audio")
                commandButton("Lost mode", icon: "person.fill.questionmark", command: "lost_mode", tint: .purple)
            }
            .padding(.vertical, 4)

            if let errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        }
    }

    private func commandButton(_ label: String, icon: String, command: String, tint: Color = .accentColor) -> some View {
        Button {
            Task { await send(command) }
        } label: {
            VStack(spacing: 6) {
                if busyCommand == command {
                    ProgressView()
                } else {
                    Image(systemName: icon)
                }
                Text(label)
                    .font(.caption)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 10).fill(tint.opacity(0.12)))
        }
        .buttonStyle(.plain)
        .disabled(busyCommand != nil)
    }

    private func send(_ command: String) async {
        busyCommand = command
        errorMessage = nil
        defer { busyCommand = nil }
        do {
            let body = CommandRequest(deviceId: device.id, command: command, params: nil, password: nil)
            struct Ack: Decodable { let status: String? }
            let _: Ack = try await APIClient.shared.request("POST", "/api/dashboard/command", body: body)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Geofences

    private var geofencesSection: some View {
        Section {
            ForEach(geofences) { fence in
                HStack {
                    Image(systemName: fence.isSafeZone == true ? "checkmark.shield" : "exclamationmark.shield")
                        .foregroundStyle(fence.isSafeZone == true ? .green : .red)
                    VStack(alignment: .leading) {
                        Text(fence.name ?? "Geofence #\(fence.id)")
                        Text("\(Int(fence.radiusMeters))m · \(String(format: "%.4f, %.4f", fence.centerLat, fence.centerLng))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if canControl {
                        Button(role: .destructive) {
                            Task { await deleteFence(fence) }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                    }
                }
            }
        } header: {
            HStack {
                Text("Geofences")
                Spacer()
                if canControl {
                    Button("Add") { showAddGeofence = true }
                        .font(.caption)
                }
            }
        }
    }

    private func deleteFence(_ fence: Geofence) async {
        do {
            struct Ack: Decodable { let status: String? }
            let _: Ack = try await APIClient.shared.request("DELETE", "/api/dashboard/geofence/\(fence.id)")
            await loadGeofences()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Alerts

    private var alertsSection: some View {
        Section("Alerts") {
            if alerts.isEmpty {
                Text("No alerts")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            ForEach(alerts.prefix(10)) { alert in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: severityIcon(alert.severity))
                        .foregroundStyle(severityColor(alert.severity))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(alert.message ?? alert.alertType ?? "Alert")
                            .font(.footnote)
                        Text("\(alert.sentAt?.displayDateTime ?? "—") · \(alert.channel ?? "")")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func severityIcon(_ severity: String?) -> String {
        switch severity?.lowercased() {
        case "critical": return "exclamationmark.octagon.fill"
        case "high": return "exclamationmark.triangle.fill"
        default: return "info.circle"
        }
    }

    private func severityColor(_ severity: String?) -> Color {
        switch severity?.lowercased() {
        case "critical": return .red
        case "high": return .orange
        default: return .blue
        }
    }

    // MARK: - Evidence

    private var evidenceSection: some View {
        Section("Evidence") {
            if media.isEmpty {
                Text("No media yet")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(media.prefix(21)) { item in
                    MediaThumbnail(item: item)
                }
            }
            .padding(.vertical, 4)
        }
    }

    // MARK: - Loading

    @MainActor
    private func loadAll() async {
        async let d: () = loadDevices()
        async let g: () = loadGeofences()
        async let a: () = loadAlerts()
        async let m: () = loadMedia()
        _ = await (d, g, a, m)
    }

    @MainActor
    private func loadDevices() async {
        do {
            let response: DeviceListResponse = try await APIClient.shared.request("GET", "/api/dashboard/devices")
            devices = response.devices
        } catch { errorMessage = error.localizedDescription }
    }

    @MainActor
    private func loadGeofences() async {
        do {
            let response: GeofenceListResponse = try await APIClient.shared.request(
                "GET", "/api/dashboard/geofences/\(device.id)")
            geofences = response.geofences
        } catch { errorMessage = error.localizedDescription }
    }

    @MainActor
    private func loadAlerts() async {
        do {
            let response: AlertListResponse = try await APIClient.shared.request(
                "GET", "/api/dashboard/alerts/\(device.id)")
            alerts = response.alerts
        } catch { errorMessage = error.localizedDescription }
    }

    @MainActor
    private func loadMedia() async {
        do {
            let response: MediaListResponse = try await APIClient.shared.request(
                "GET", "/api/dashboard/media/\(device.id)")
            media = response.media
        } catch { errorMessage = error.localizedDescription }
    }
}

/// Remote thumbnail (photo/audio) loaded from the authenticated media
/// endpoint. Audio items get a mic badge instead of a photo.
struct MediaThumbnail: View {
    let item: MediaItem
    @State private var image: UIImage?

    var body: some View {
        Group {
            if item.type == "audio" {
                VStack {
                    Image(systemName: "mic.fill")
                    Text(item.timestamp?.displayDateTime ?? "")
                        .font(.caption2)
                }
                .frame(height: 80)
                .frame(maxWidth: .infinity)
                .background(RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.15)))
            } else if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(height: 80)
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            } else {
                Rectangle()
                    .fill(Color.gray.opacity(0.15))
                    .frame(height: 80)
                    .overlay(ProgressView())
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .task {
            guard item.type != "audio" else { return }
            do {
                let data = try await APIClient.shared.data("GET", "/api/dashboard/media/file/\(item.id)")
                image = UIImage(data: data)
            } catch {
                // Thumbnail failures are non-fatal.
            }
        }
    }
}

/// Create a geofence around the device's current map position.
struct AddGeofenceView: View {
    let deviceId: String
    let center: CLLocationCoordinate2D
    var onAdded: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var radius = 500.0
    @State private var isSafeZone = false
    @State private var autoAction = "alert"
    @State private var busy = false
    @State private var errorMessage: String?

    private let autoActions = ["alert", "capture", "siren"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Fence") {
                    TextField("Name (optional)", text: $name)
                    HStack {
                        Text("Radius")
                        Slider(value: $radius, in: 100...5000, step: 100)
                        Text("\(Int(radius))m")
                            .monospacedDigit()
                    }
                    Toggle("Safe zone", isOn: $isSafeZone)
                    Picker("On exit", selection: $autoAction) {
                        Text("Alert only").tag("alert")
                        Text("Capture evidence").tag("capture")
                        Text("Siren").tag("siren")
                    }
                }
                Section {
                    Text("Center: \(String(format: "%.5f, %.5f", center.latitude, center.longitude))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let errorMessage {
                    Section {
                        Text(errorMessage).font(.footnote).foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Add geofence")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .disabled(busy)
                }
            }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let body = GeofenceRequest(
                deviceId: deviceId,
                name: name.isEmpty ? nil : name,
                centerLat: center.latitude,
                centerLng: center.longitude,
                radiusMeters: radius,
                isSafeZone: isSafeZone,
                autoAction: autoAction
            )
            struct Ack: Decodable { let status: String? }
            let _: Ack = try await APIClient.shared.request("POST", "/api/dashboard/geofence", body: body)
            onAdded()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
