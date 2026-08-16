import Foundation
import Combine

/// Live dashboard feed over the authenticated WebSocket.
///
/// Connects to `wss://…/ws/dashboard?token=<jwt>` (token in the query
/// string, exactly like the web dashboard — the server rejects anonymous
/// connections with close code 4408, F-01). Reconnects with backoff on
/// drops. Message types observed in production: `ping`, `device_update`,
/// `alert`, `command_ack` — unknown types are ignored so the client stays
/// forward-compatible with new broadcast kinds.
final class DashboardSocket: NSObject, ObservableObject, URLSessionWebSocketDelegate {
    static let shared = DashboardSocket()

    @Published private(set) var isConnected = false
    @Published private(set) var lastEvent: (type: String, payload: [String: Any])?

    private var task: URLSessionWebSocketTask?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 8

    private let session: URLSession

    private override init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = true
        session = URLSession(configuration: config)
        super.init()
    }

    /// (Re)connect using the current session token. Call on login and on
    /// token refresh.
    func connectIfAuthenticated() {
        guard Session.shared.isAuthenticated, let token = Session.shared.accessToken else {
            disconnect()
            return
        }
        disconnect()

        var components = URLComponents(url: Config.wsURL, resolvingAgainstBaseURL: false)!
        components.path = "/ws/dashboard"
        components.queryItems = [URLQueryItem(name: "token", value: token)]
        guard let url = components.url else { return }

        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        let task = session.webSocketTask(with: request, delegate: self)
        self.task = task
        task.resume()
        receiveLoop()
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        reconnectAttempts = 0
        isConnected = false
    }

    // MARK: - Receive loop

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                self.handle(message)
                self.receiveLoop()
            case .failure:
                self.scheduleReconnect()
            }
        }
    }

    private func handle(_ message: URLSessionWebSocketTask.Message) {
        switch message {
        case .data(let data):
            parse(data)
        case .string(let string):
            parse(Data(string.utf8))
        @unknown default:
            break
        }
    }

    private func parse(_ data: Data) {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        if let type = json["type"] as? String {
            let payload = json["data"] as? [String: Any] ?? json
            lastEvent = (type, payload)
        }
    }

    // MARK: - Reconnect

    private func scheduleReconnect() {
        isConnected = false
        guard reconnectAttempts < maxReconnectAttempts else { return }
        reconnectAttempts += 1
        let delay = min(pow(2.0, Double(reconnectAttempts)), 30)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard Session.shared.isAuthenticated else { return }
            self?.connectIfAuthenticated()
        }
    }

    // MARK: - URLSessionWebSocketDelegate

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        reconnectAttempts = 0
        isConnected = true
    }

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        isConnected = false
        // 4408 = auth required (session gone); don't hammer the server.
        if closeCode.rawValue == 4408 { reconnectAttempts = maxReconnectAttempts }
    }
}
