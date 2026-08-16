import Foundation
import Combine

/// Result of the password-only login step: either real tokens, or a 2FA
/// challenge that must be completed with a TOTP code at
/// /api/auth/user/login/2fa (the server never hands a 2FA account real
/// tokens from the password step alone).
enum LoginResult: Equatable {
    case tokens(TokenResponse)
    case requires2fa(twoFactorToken: String)

    static func decode(_ data: Data) throws -> LoginResult {
        struct Challenge: Decodable {
            let requires2fa: Bool?
            let twoFactorToken: String?
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        if let tokens = try? decoder.decode(TokenResponse.self, from: data) {
            return .tokens(tokens)
        }
        let challenge = try decoder.decode(Challenge.self, from: data)
        if challenge.requires2fa == true, let token = challenge.twoFactorToken {
            return .requires2fa(twoFactorToken: token)
        }
        throw APIError.invalidResponse
    }
}

/// Owns the user session: tokens (Keychain, never UserDefaults), the current
/// profile, and the auth flow (register / login / 2FA / refresh / logout).
/// Mirrors the Android app's session handling — same endpoints, same
/// refresh-on-401 behaviour.
///
/// Not actor-isolated on purpose: it is a cross-cutting singleton read from
/// the dashboard socket and the device poller as well as the views. All its
/// mutations happen inside its own async methods, which the UI awaits on the
/// main thread.
final class Session: ObservableObject {
    static let shared = Session()

    // MARK: - Published state

    @Published private(set) var isAuthenticated = false
    @Published private(set) var user: UserResponse?
    @Published var isLoading = false
    @Published var errorMessage: String?

    // MARK: - Token storage (Keychain)

    private let accessKey = "magneetar.access_token"
    private let refreshKey = "magneetar.refresh_token"

    var accessToken: String? { KeychainStore.read(accessKey) }
    var refreshToken: String? { KeychainStore.read(refreshKey) }

    private init() {}

    // MARK: - Lifecycle

    /// Restore a persisted session on launch (token present → fetch /me).
    func restore() async {
        guard let token = accessToken else { return }
        do {
            let me: UserResponse = try await APIClient.shared.request("GET", "/api/auth/me")
            self.user = me
            self.isAuthenticated = true
        } catch {
            // Token expired/invalid — try one refresh before giving up.
            await refresh()
            if isAuthenticated {
                self.user = try? await APIClient.shared.request("GET", "/api/auth/me")
            }
        }
    }

    func register(email: String, password: String, displayName: String?) async -> Bool {
        isLoading = true
        defer { isLoading = false }
        do {
            struct RegisterBody: Encodable {
                let email: String
                let password: String
                let displayName: String?
            }
            let tokens: TokenResponse = try await APIClient.shared.request(
                "POST", "/api/auth/register",
                body: RegisterBody(email: email, password: password, displayName: displayName)
            )
            apply(tokens)
            user = try? await APIClient.shared.request("GET", "/api/auth/me")
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    /// Password step. Returns true when fully signed in; false + a
    /// `twoFactorToken` when the account requires a TOTP code (call
    /// `completeTwoFactor` next).
    @discardableResult
    func login(email: String, password: String) async -> (ok: Bool, twoFactorToken: String?) {
        isLoading = true
        defer { isLoading = false }
        do {
            struct LoginBody: Encodable { let email: String; let password: String }
            let data = try await APIClient.shared.data(
                "POST", "/api/auth/user/login",
                body: LoginBody(email: email, password: password)
            )
            switch try LoginResult.decode(data) {
            case .tokens(let tokens):
                apply(tokens)
                user = try? await APIClient.shared.request("GET", "/api/auth/me")
                return (true, nil)
            case .requires2fa(let token):
                return (false, token)
            }
        } catch {
            errorMessage = error.localizedDescription
            return (false, nil)
        }
    }

    /// Second half of a 2FA login: challenge token + TOTP code → real tokens.
    func completeTwoFactor(twoFactorToken: String, code: String) async -> Bool {
        isLoading = true
        defer { isLoading = false }
        do {
            struct TwoFactorBody: Encodable {
                let twoFactorToken: String
                let code: String
            }
            let tokens: TokenResponse = try await APIClient.shared.request(
                "POST", "/api/auth/user/login/2fa",
                body: TwoFactorBody(twoFactorToken: twoFactorToken, code: code)
            )
            apply(tokens)
            user = try? await APIClient.shared.request("GET", "/api/auth/me")
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    /// Exchange the refresh token for a fresh pair. Returns true on success.
    @discardableResult
    func refresh() async -> Bool {
        guard let refresh = refreshToken else { return false }
        do {
            struct RefreshBody: Encodable { let refreshToken: String }
            let tokens: TokenResponse = try await APIClient.shared.request(
                "POST", "/api/auth/user/refresh",
                body: RefreshBody(refreshToken: refresh)
            )
            apply(tokens)
            return true
        } catch {
            logout()
            return false
        }
    }

    func logout() {
        KeychainStore.delete(accessKey)
        KeychainStore.delete(refreshKey)
        user = nil
        isAuthenticated = false
    }

    // MARK: - Private

    private func apply(_ tokens: TokenResponse) {
        KeychainStore.save(tokens.token, key: accessKey)
        KeychainStore.save(tokens.refreshToken, key: refreshKey)
        isAuthenticated = true
        errorMessage = nil
    }
}
