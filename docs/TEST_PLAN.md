# Magneetar — On-Device Test Plan

**Version:** 1.0  
**Prepared:** 2026-07-29  
**Scope:** Android app — full onboarding, sign-in, permissions, background persistence  

---

## Test Environment Requirements

| Requirement | Value |
|-------------|-------|
| Android Device | Physical phone (Samsung, Xiaomi, Huawei, Pixel, etc.) |
| Android Version | 8.0 (API 26) or higher |
| ADB | Installed on dev machine (`platform-tools`) |
| Server | Running at `http://<your-ip>:8000` or `https://api.magneetar.me` |
| APK | `android-app/app/build/outputs/apk/release/app-release.apk` |

---

## Prerequisites Setup

```bash
# 1. Ensure server is running
cd server && source venv/bin/activate && python3 main.py

# 2. Build the release APK
cd android-app && ./gradlew assembleRelease

# 3. Connect device via USB (enable Developer Options + USB Debugging)
adb devices   # Should show your device

# 4. Install the APK
bash scripts/install-apk.sh -y
```

---

## Test Case 1: Fresh Install — First Launch

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1.1 | Tap **Magneetar** app icon | App opens to **Welcome/Onboarding screen** | ☐ |
| 1.2 | Verify UI elements | Shield icon, app name "Magneetar", 4 feature bullets, "GET STARTED" + "SIGN IN" buttons | ☐ |
| 1.3 | Tap **GET STARTED** | Navigates to **Create Account** screen | ☐ |
| 1.4 | Tap back arrow | Returns to onboarding | ☐ |
| 1.5 | Tap **SIGN IN** | Navigates to **Sign In** screen | ☐ |
| 1.6 | Tap back arrow | Returns to onboarding | ☐ |

---

## Test Case 2: Account Creation

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 2.1 | Tap **GET STARTED** | Create Account screen shows | ☐ |
| 2.2 | Leave all fields empty, tap **CREATE ACCOUNT** | Error: "Please enter your server URL" | ☐ |
| 2.3 | Enter invalid email `notanemail`, valid password `TestPass123` | Error: "Invalid email" (server-side validation) | ☐ |
| 2.4 | Enter valid data: | | ☐ |
| | Server: `https://api.magneetar.me` | | |
| | Name: `Test User` | | |
| | Email: `test@example.com` | | |
| | Password: `Weak1` (too short) | Error: "Password must be at least 8 characters" | ☐ |
| 2.5 | Enter matching passwords `TestPass123` + `TestPass456` | Error: "Passwords do not match" | ☐ |
| 2.6 | Enter valid full data: | | |
| | Server: `https://api.magneetar.me` | | |
| | Email: `your-email@example.com` | | |
| | Password: `YourPass123` | | |
| | Tap **CREATE ACCOUNT** | Loading spinner → navigates to **Permissions** screen | ☐ |

---

## Test Case 3: Permission Grants

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 3.1 | Verify permission list | Shows 6 permission rows: Location, Camera, Microphone, Storage, Device Admin, Battery | ☐ |
| 3.2 | All show "Required" (yellow) | All rows show "Required" in amber | ☐ |
| 3.3 | Tap **GRANT ALL PERMISSIONS** | System permission dialogs appear one by one | ☐ |
| 3.4 | **Location** dialog | Tap "Allow all the time" + "Use precise location" | ☐ |
| 3.5 | **Camera** dialog | Tap "Allow" | ☐ |
| 3.6 | **Microphone** dialog | Tap "Allow" | ☐ |
| 3.7 | **Storage** dialog | Tap "Allow" (may not appear on Android 13+) | ☐ |
| 3.8 | **Device Admin** screen | Tap "Activate" | ☐ |
| 3.9 | **Battery Optimization** dialog | Tap "Allow" / "Don't optimize" | ☐ |
| 3.10 | After all granted, verify | All rows show "Granted" (green), "GRANT ALL" replaced by "CONTINUE" button | ☐ |
| 3.11 | Tap **CONTINUE** | Navigates to Home screen (or splash briefly then Home) | ☐ |

---

## Test Case 4: Home Screen — Protection Status

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 4.1 | Verify protection card | Shows green checkmark + "Device Protected" text | ☐ |
| 4.2 | Verify connection status | Shows "Connected — your@email.com" | ☐ |
| 4.3 | Verify battery opt status | Shows "Battery optimization disabled ✓" | ☐ |
| 4.4 | If using Chinese OEM phone | Shows OEM-specific warning + "Enable Auto-Start" button | ☐ |
| 4.5 | Tap **Open Dashboard** | Opens browser to the dashboard login page — derived from the API server URL (`https://api.<host>` → `https://app.<host>/login`); self-hosted non-`api.*` servers fall back to the server URL | ☐ |
| 4.6 | Verify dashboard shows | Device appears in the dashboard device list | ☐ |

---

## Test Case 5: Background Persistence

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 5.1 | Close app (swipe from recents) | App should restart within 5 minutes (AlarmManager 5-min watchdog interval) | ☐ |
| 5.2 | Check notifications | Two notifications visible: "Magneetar Security" + "Magneetar Protection" | ☐ |
| 5.3 | Reboot device | After reboot, app auto-starts within 2 minutes (10s delay on Chinese OEMs) | ☐ |
| 5.4 | Check dashboard after reboot | Device shows "online" within 1-2 minutes | ☐ |
| 5.5 | Put phone in Doze/idle for 30 min | Dashboard still shows device as online | ☐ |

---

## Test Case 6: Sign In (Existing User)

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 6.1 | Uninstall app, reinstall via ADB | Fresh install, shows onboarding | ☐ |
| 6.2 | Tap **SIGN IN** | Sign In screen appears | ☐ |
| 6.3 | Enter server URL + wrong credentials | Error: "Invalid email or password" | ☐ |
| 6.4 | Enter correct credentials from Test 2 | Navigates to Permissions screen | ☐ |
| 6.5 | All permissions already granted? | Should show all "Granted" and CONTINUE button | ☐ |
| 6.6 | Tap **CONTINUE** | Navigates to Home screen | ☐ |

---

## Test Case 7: Remote Commands

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 7.1 | From dashboard, issue **PING** command | Phone notification: "Ping received" | ☐ |
| 7.2 | Issue **CAPTURE PHOTO** (rear) | Photo appears in dashboard media gallery | ☐ |
| 7.3 | Issue **CAPTURE PHOTO FRONT** | Front camera photo in gallery | ☐ |
| 7.4 | Issue **CAPTURE AUDIO** | 20-second audio clip in gallery | ☐ |
| 7.5 | Issue **SIREN** | Phone plays max-volume alarm for 5 seconds | ☐ |
| 7.6 | Issue **LOCK** | Phone locks immediately | ☐ |

---

## Test Case 8: Edge Cases

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 8.1 | Turn off network, move phone | Locations fail silently (offline queue not yet implemented) | ☐ |
| 8.2 | Remove SIM card while device is on | Dashboard shows SIM change alert | ☐ |
| 8.3 | Kill app via Settings → Force Stop | App restarts via AlarmManager watchdog within 5 minutes | ☐ |
| 8.4 | Clear app data | Next launch shows onboarding (fresh start) | ☐ |
| 8.5 | Rapidly grant/deny permissions | App handles gracefully without crash | ☐ |

---

## Test Results Summary

| Test Case | Description | Status | Notes |
|-----------|-------------|--------|-------|
| TC-1 | First Launch / Onboarding | ☐ | |
| TC-2 | Account Creation | ☐ | |
| TC-3 | Permission Grants | ☐ | |
| TC-4 | Home Screen | ☐ | |
| TC-5 | Background Persistence | ☐ | |
| TC-6 | Sign In (Existing User) | ☐ | |
| TC-7 | Remote Commands | ☐ | |
| TC-8 | Edge Cases | ☐ | |

**Overall Verdict:** ☐ PASS / ☐ FAIL with notes

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tester | | | |
| Engineer | | | |
| Product | | | |

---

## Appendices

### A. Installing ADB
```bash
# macOS
brew install android-platform-tools

# Ubuntu/Debian
sudo apt install adb

# Windows
# Download from: https://developer.android.com/studio/releases/platform-tools
```

### B. Useful ADB Commands for Testing
```bash
# Force-kill the app (simulate OEM killing)
adb shell am force-stop com.magneetar.app

# Grant permissions silently
adb shell pm grant com.magneetar.app android.permission.ACCESS_FINE_LOCATION
adb shell pm grant com.magneetar.app android.permission.CAMERA

# Revoke permissions
adb shell pm revoke com.magneetar.app android.permission.CAMERA

# Check if service is running
adb shell dumpsys activity services | grep TrackingService

# Pull logs
adb logcat -s Magneetar MagneetarWatchdog MagneetarFCM MagneetarPersistence MagneetarTracking
```

### C. Test on Chinese OEM Phones
| OEM | Special Attention |
|-----|-------------------|
| Xiaomi (MIUI) | Auto-start must be manually enabled in Settings → Apps → Magneetar |
| Huawei (EMUI) | Lock app in recent apps tray, enable auto-launch in Phone Manager |
| Oppo (ColorOS) | Disable "Sleep standby optimization" for Magneetar |
| Vivo (Funtouch OS) | Enable "Background power consumption" → Allow |
| Realme (RealmeUI) | Same as Oppo — disable freeze in app management |
