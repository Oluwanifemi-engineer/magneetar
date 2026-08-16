import Foundation

enum APIError: LocalizedError {
    case server(String)              // server `detail` message
    case http(Int, String)           // status + body snippet
    case invalidResponse
    case network(String)

    var errorDescription: String? {
        switch self {
        case .server(let detail): return detail
        case .http(let code, let body): return "\(code): \(body)"
        case .invalidResponse: return "Invalid response from server"
        case .network(let message): return message
        }
    }
}

/// Async HTTP client for the Magneetar API.
///
/// Auth headers are attached automatically, mirroring the Android app's
/// `postRaw`: the Bearer user token when a session exists (dashboard + device
/// linking) and the per-device key when this iPhone is a registered device.
/// The registration call passes its own `x-api-key` (the embedded
/// low-privilege device key) explicitly — the only call that needs it.
struct APIClient {
    static let shared = APIClient()

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    // MARK: - Public request helpers

    /// Decodable response.
    func request<T: Decodable>(
        _ method: String,
        _ path: String,
        body: (some Encodable)? = nil,
        extraHeaders: [String: String] = [:]
    ) async throws -> T {
        let (data, response) = try await raw(method, path, body: body, extraHeaders: extraHeaders)
        return try decoder.decode(T.self, from: data)
    }

    /// Raw Data response (binary media files, QR SVG, …).
    func data(
        _ method: String,
        _ path: String,
        body: (some Encodable)? = nil,
        extraHeaders: [String: String] = [:]
    ) async throws -> Data {
        let (data, _) = try await raw(method, path, body: body, extraHeaders: extraHeaders)
        return data
    }

    /// Fire-and-forget POST (acks, heartbeats) — no response decoding.
    func postVoid(_ path: String, body: (some Encodable)? = nil) async throws {
        _ = try await raw("POST", path, body: body)
    }

    /// Form-encoded body helper (not used by v1 endpoints, kept for parity).
    static func form(_ pairs: [String: String]) -> Data {
        pairs.map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? $0.value)" }
            .joined(separator: "&")
            .data(using: .utf8) ?? Data()
    }

    // MARK: - Core

    private func raw(
        _ method: String,
        _ path: String,
        body: (some Encodable)? = nil,
        extraHeaders: [String: String] = [:]
    ) async throws -> (Data, HTTPURLResponse) {
        var url = Config.apiBase.appendingPathComponent(path.hasPrefix("/") ? String(path.dropFirst()) : path)
        // Rebuild with explicit components so query strings survive (e.g. /media/file/{id} has none, but keep it robust).
        if let q = url.query { url = URL(string: url.absoluteString.replacingOccurrences(of: "?", with: "?\(q)&"))! }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Magneetar-iOS/\(appVersion)", forHTTPHeaderField: "User-Agent")

        // Automatic auth headers.
        if let token = Session.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if DeviceIdentity.isRegistered {
            request.setValue(DeviceIdentity.deviceKey, forHTTPHeaderField: "x-device-key")
        }
        for (key, value) in extraHeaders {
            request.setValue(value, forHTTPHeaderField: key)
        }

        if let body, method != "GET" {
            do {
                request.httpBody = try JSONEncoder().encode(body)
            } catch {
                throw APIError.network("Failed to encode request body")
            }
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200..<300).contains(http.statusCode) else {
            throw Self.error(from: data, status: http.statusCode)
        }
        return (data, http)
    }

    /// Server errors carry a FastAPI `{"detail": "..."}` body — surface that
    /// message instead of a bare status code.
    private static func error(from data: Data, status: Int) -> APIError {
        struct Detail: Decodable { let detail: String }
        if let detail = try? JSONDecoder().decode(Detail.self, from: data) {
            return .http(status, detail.detail)
        }
        let snippet = String(data: data, encoding: .utf8)?.prefix(200) ?? ""
        return .http(status, String(snippet))
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    }
}
