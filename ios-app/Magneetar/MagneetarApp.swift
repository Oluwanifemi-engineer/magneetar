import SwiftUI
import UserNotifications

@main
struct MagneetarApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    // Singletons: @ObservedObject (not @StateObject) — these are shared
    // services owned elsewhere; StateObject would imply per-view ownership.
    @ObservedObject private var session = Session.shared
    @ObservedObject private var beacon = BeaconService.shared

    init() {
        // APNs/FCM delivery delegate (command push → execute, token → register).
        UNUserNotificationCenter.current().delegate = PushService.shared
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(beacon)
                .task {
                    await session.restore()
                    PushService.shared.configureIfPresent()
                }
        }
    }
}

/// Bridges APNs token delivery (FirebaseMessaging consumes it to mint the
/// FCM token the server delivers through). Standard SwiftUI app-delegate
/// adaptor — no logic beyond forwarding the token.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        PushService.shared.didRegisterForRemoteNotifications(tokenData: deviceToken)
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        // Non-fatal: push is a convenience layer over the 10s command poll.
    }
}

/// Chooses the auth flow vs. the dashboard, and boots the tracked-device
/// services when this iPhone is registered as a protected device.
struct RootView: View {
    @EnvironmentObject var session: Session
    @EnvironmentObject var beacon: BeaconService

    var body: some View {
        Group {
            if session.isAuthenticated {
                DashboardView()
            } else {
                AuthView()
            }
        }
        .onChange(of: session.isAuthenticated) { signedIn in
            if signedIn {
                beacon.startIfProtected()
                CommandPoller.shared.startIfProtected()
                DashboardSocket.shared.connectIfAuthenticated()
            } else {
                beacon.stop()
                CommandPoller.shared.stop()
                DashboardSocket.shared.disconnect()
            }
        }
    }
}
