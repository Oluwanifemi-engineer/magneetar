import Foundation
import UIKit
import UserNotifications
#if canImport(FirebaseMessaging)
import FirebaseCore
import FirebaseMessaging
#endif

/// Push delivery + command notification handling.
///
/// The server already routes push through FCM v1, which delivers to iOS via
/// APNs when the token's `platform` is "ios" — so enabling push is entirely
/// an app-side concern. Two paths:
///
/// 1. **Full (recommended):** add `GoogleService-Info.plist` (the owner's
///    Firebase project, gitignored) → FirebaseMessaging configures itself,
///    mints an FCM token, and we register it at /api/device/fcm-token.
///    Theft alerts + urgent commands then arrive even when the app is
///    terminated (the SAME delivery the Android app gets).
/// 2. **Fallback (no plist):** the app still works — commands arrive via
///    the 10s poll, and alerts are visible when the app is opened.
///    `configureIfPresent()` makes this graceful: no Firebase, no crash.
final class PushService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = PushService()

    private(set) var isConfigured = false
    private var didRequestPermission = false

    private override init() {
        super.init()
    }

    // MARK: - Setup

    /// Configure Firebase ONLY if the owner's GoogleService-Info.plist is in
    /// the bundle (it's gitignored, so plain builds must not crash).
    func configureIfPresent() {
        guard Bundle.main.url(forResource: "GoogleService-Info", withExtension: "plist") != nil else {
            return
        }
        #if canImport(FirebaseMessaging)
        FirebaseApp.configure()
        Messaging.messaging().delegate = self
        isConfigured = true
        #endif
        requestPermissionAndRegister()
    }

    private func requestPermissionAndRegister() {
        guard !didRequestPermission else { return }
        didRequestPermission = true
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    /// Called from the AppDelegate with the APNs device token.
    func didRegisterForRemoteNotifications(tokenData: Data) {
        let token = tokenData.map { String(format: "%02.2hhx", $0) }.joined()
        #if canImport(FirebaseMessaging)
        if isConfigured {
            Messaging.messaging().apnsToken = tokenData
        }
        #endif
        guard DeviceIdentity.isRegistered else { return }
        Task {
            let request = FCMTokenRequest(
                deviceId: DeviceIdentity.deviceID,
                fcmToken: token,
                platform: "ios"
            )
            try? await APIClient.shared.postVoid("/api/device/fcm-token", body: request)
        }
    }

    // MARK: - UNUserNotificationCenterDelegate

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        // Show alerts even while the app is foregrounded (siren, alerts).
        [.banner, .sound]
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let userInfo = response.notification.request.content.userInfo
        if let command = userInfo["command"] as? String {
            // A push-delivered command: execute it directly (e.g. alarm).
            if command == "alarm" {
                SirenPlayer.shared.play()
            }
        }
    }
}

#if canImport(FirebaseMessaging)
extension PushService: MessagingDelegate {
    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        guard let fcmToken, DeviceIdentity.isRegistered else { return }
        Task {
            let request = FCMTokenRequest(
                deviceId: DeviceIdentity.deviceID,
                fcmToken: fcmToken,
                platform: "ios"
            )
            try? await APIClient.shared.postVoid("/api/device/fcm-token", body: request)
        }
    }
}
#endif
