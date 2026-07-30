# Magneetar Installation Guide

## Installing the APK on Your Android Device

### Prerequisites
- Android 8.0+ (API 24)
- Location permissions enabled
- Internet connection

### Download the APK

**Option 1: Download from the dashboard**
1. Open `https://app.magneetar.me/apk/magneetar-release.apk` on your phone
2. The APK will download automatically (3.8 MB)

**Option 2: Sideload via ADB**
```bash
adb install /home/oluwanifemi/Projects/magneetar/dashboard/public/apk/magneetar-release.apk
```

### Install on Your Phone
1. Open the downloaded APK file
2. If prompted, enable "Install from unknown sources" in Settings → Security
3. Tap "Install"
4. Open the Magneetar app

### First Launch — Device Registration

When you first open the app:

1. **Auto-generated device key** — The app generates a unique 256-bit key on first launch. This key is stored securely in the app's private storage (never in the APK).

2. **Get your device ID** — The app will show a device ID like `mag-a1b2c3d4`

3. **Register from the dashboard**:
   - Open `https://app.magneetar.me` in your browser
   - Click "API Key" mode
   - Enter: `https://api.magneetar.me` as Server URL
   - Enter your API key (from server/.env `MT_API_KEY`)
   - Click "Connect"
   - The dashboard will show all registered devices

### Device Key Authentication

Once registered, your device authenticates using its unique `x-device-key` header:
```
POST /api/device/location
x-device-key: <your-device-key>
{
  "lat": 9.082,
  "lng": 8.675,
  "provider": "gps"
}
```

### Sending Test Locations

You can test the device from your computer:

```bash
# Register a test device
curl -X POST https://api.magneetar.me/api/device/register \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"my-phone","fingerprint":"android-fingerprint-here","device_key":"my-secret-key-32-bytes-hex"}'

# Send a location
curl -X POST https://api.magneetar.me/api/device/location \
  -H 'x-device-key: my-secret-key-32-bytes-hex' \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"my-phone","lat":9.082,"lng":8.675,"provider":"gps"}'
```

### Troubleshooting

**APK won't install**
- Ensure "Install from unknown apps" is enabled for your browser/file manager
- Check that you have enough storage space
- Try redownloading the APK

**Device not showing on dashboard**
- Verify the device is connected to the internet
- Check the server URL is correct: `https://api.magneetar.me`
- Ensure the API key matches the server's `MT_API_KEY`

**Push notifications not working**
- The FCM token is registered automatically when you open the app
- Check the dashboard error log for FCM-related errors
- Ensure Google Play Services is installed on your device
