import SwiftUI

/// Login / register / 2FA completion. The 2FA step appears only when the
/// password step returns a challenge (the server never issues real tokens
/// to a 2FA-enabled account from the password step alone).
struct AuthView: View {
    @EnvironmentObject var session: Session
    @State private var isRegister = false
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var twoFactorToken: String?
    @State private var twoFactorCode = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    Image(systemName: "shield.lefthalf.filled")
                        .font(.system(size: 56))
                        .foregroundStyle(.tint)
                    Text("Magneetar")
                        .font(.largeTitle.bold())
                    Text("Anti-theft protection & recovery")
                        .foregroundStyle(.secondary)

                    if let twoFactorToken {
                        twoFactorField
                    } else {
                        authFields
                    }

                    if let error = session.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                    }
                }
                .padding()
            }
        }
    }

    private var authFields: some View {
        VStack(spacing: 12) {
            TextField("Email", text: $email)
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)

            if isRegister {
                TextField("Display name (optional)", text: $displayName)
                    .textFieldStyle(.roundedBorder)
            }

            SecureField("Password", text: $password)
                .textContentType(isRegister ? .newPassword : .password)
                .textFieldStyle(.roundedBorder)

            Button {
                Task { await submit() }
            } label: {
                Group {
                    if busy { ProgressView() } else { Text(isRegister ? "Create account" : "Sign in") }
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(email.isEmpty || password.isEmpty || busy)

            Button(isRegister ? "Already have an account? Sign in" : "New to Magneetar? Register") {
                withAnimation { isRegister.toggle() }
            }
            .font(.footnote)
        }
    }

    private var twoFactorField: some View {
        VStack(spacing: 12) {
            Text("Two-factor authentication")
                .font(.headline)
            Text("Enter the 6-digit code from your authenticator app.")
                .font(.footnote)
                .foregroundStyle(.secondary)

            TextField("000000", text: $twoFactorCode)
                .keyboardType(.numberPad)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.center)

            Button {
                Task { await submit2FA() }
            } label: {
                Group {
                    if busy { ProgressView() } else { Text("Verify code") }
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(twoFactorCode.count < 6 || busy)

            Button("Use a different account") {
                withAnimation { twoFactorToken = nil }
            }
            .font(.footnote)
        }
    }

    private func submit() async {
        busy = true
        defer { busy = false }
        let result: (ok: Bool, twoFactorToken: String?)
        if isRegister {
            let ok = await session.register(email: email, password: password, displayName: displayName.isEmpty ? nil : displayName)
            result = (ok, nil)
        } else {
            result = await session.login(email: email, password: password)
        }
        if !result.ok, let token = result.twoFactorToken {
            withAnimation { twoFactorToken = token }
        }
    }

    private func submit2FA() async {
        guard let token = twoFactorToken else { return }
        busy = true
        defer { busy = false }
        if await session.completeTwoFactor(twoFactorToken: token, code: twoFactorCode) {
            twoFactorToken = nil
        }
    }
}
