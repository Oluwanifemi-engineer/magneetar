package com.magneetar.app

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Accessibility Service that detects when the user navigates to:
 * - Settings > Apps > Magneetar
 * - Settings > Security > Device Admin
 * - Any attempt to force stop or uninstall the app
 *
 * When detected, the service:
 * 1. Immediately sends the user back to the home screen
 * 2. Triggers a security alert notification
 * 3. Logs the attempt for the owner to see on the dashboard
 *
 * This is the LAYER 2 protection (Device Admin is LAYER 1).
 * Even if a thief deactivates Device Admin, this service intercepts
 * the uninstall attempt before it can complete.
 */
class UninstallGuardService : AccessibilityService() {

    companion object {
        private const val TAG = "UninstallGuard"

        // Package names that indicate uninstall/settings navigation
        private val SETTINGS_PACKAGES = setOf(
            "com.android.settings",
            "com.android.packageinstaller",
            "com.google.android.packageinstaller",
            "com.samsung.android.packageinstaller",
            "com.huawei.android.packageinstaller",
            "com.miui.packageinstaller",
            "com.coloros.packageinstaller",
            "com.heytap.soc",
            "com.oppo.packageinstaller"
        )

        // Keywords that indicate app management screens
        private val APP_INFO_KEYWORDS = setOf(
            "Magneetar",
            "com.magneetar.app",
            "Force stop",
            "Uninstall",
            "Disable",
            "Device admin",
            "Device administrator"
        )

        // Current state
        @Volatile
        var isRunning = false
            private set

        @Volatile
        var lastBlockedAttempt: Long = 0
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        isRunning = true

        val info = serviceInfo.apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                    AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS or
                    AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                    AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            notificationTimeout = 100
        }
        serviceInfo = info

        Log.i(TAG, "UninstallGuard service connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return

        val packageName = event.packageName?.toString() ?: return
        val className = event.className?.toString() ?: return

        // Check if user is navigating to Settings or Package Installer
        if (packageName in SETTINGS_PACKAGES) {
            handleSettingsNavigation(event, packageName, className)
        }
    }

    private fun handleSettingsNavigation(
        event: AccessibilityEvent,
        packageName: String,
        className: String
    ) {
        try {
            // Check if our app's info is being viewed
            val rootNode = rootInActiveWindow ?: return
            val textToCheck = buildString {
                append(event.text?.toString() ?: "")
                append(" ")
                append(className)
            }

            // Scan the UI for Magneetar-related text
            if (containsAppInfo(rootNode)) {
                Log.w(TAG, "Uninstall attempt detected! Package: $packageName, Class: $className")
                blockUninstallAttempt()
                return
            }

            // Also check event text for keywords
            if (APP_INFO_KEYWORDS.any { keyword ->
                    textToCheck.contains(keyword, ignoreCase = true)
                }) {
                Log.w(TAG, "Settings navigation blocked: $textToCheck")
                blockUninstallAttempt()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error checking accessibility event: ${e.message}")
        }
    }

    /**
     * Recursively scan the UI tree for Magneetar-related content.
     */
    private fun containsAppInfo(node: AccessibilityNodeInfo, depth: Int = 0): Boolean {
        if (depth > 15) return false // Prevent infinite recursion

        // Check node text and content description
        val nodeText = node.text?.toString() ?: ""
        val contentDesc = node.contentDescription?.toString() ?: ""

        if (APP_INFO_KEYWORDS.any { keyword ->
                nodeText.contains(keyword, ignoreCase = true) ||
                        contentDesc.contains(keyword, ignoreCase = true)
            }) {
            return true
        }

        // Recurse into children
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            if (containsAppInfo(child, depth + 1)) {
                return true
            }
        }

        return false
    }

    /**
     * Block the uninstall attempt by:
     * 1. Sending user back to home screen
     * 2. Triggering a security alert
     * 3. Recording the attempt
     */
    private fun blockUninstallAttempt() {
        lastBlockedAttempt = System.currentTimeMillis()

        // Method 1: Perform HOME action (most reliable)
        performGlobalAction(GLOBAL_ACTION_HOME)

        // Method 2: Launch our activity as a security measure
        try {
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP or
                        Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("security_alert", "uninstall_attempt")
            }
            startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch security activity: ${e.message}")
        }

        // Method 3: Send broadcast for other components to handle
        try {
            val intent = Intent("com.magneetar.UNINSTALL_BLOCKED").apply {
                putExtra("timestamp", System.currentTimeMillis())
                setPackage(packageName)
            }
            sendBroadcast(intent)
        } catch (e: Exception) {
            // Best effort
        }

        // Record the attempt in SharedPreferences
        try {
            val prefs = getSharedPreferences("mt", MODE_PRIVATE)
            val attempts = prefs.getInt("uninstall_attempts", 0) + 1
            prefs.edit()
                .putInt("uninstall_attempts", attempts)
                .putLong("last_uninstall_attempt", System.currentTimeMillis())
                .apply()
        } catch (e: Exception) {
            // Non-fatal
        }
    }

    override fun onInterrupt() {
        Log.d(TAG, "UninstallGuard service interrupted")
        isRunning = false
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        Log.d(TAG, "UninstallGuard service destroyed")
    }
}
