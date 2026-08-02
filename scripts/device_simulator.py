#!/usr/bin/env python3
"""
Magneetar Device Simulator
Simulates an Android device for end-to-end testing of the tracking pipeline.

Usage:
    # Normal device walking around
    python3 scripts/device_simulator.py --mode normal

    # Simulate theft (SIM change + airplane mode + high speed)
    python3 scripts/device_simulator.py --mode theft

    # Driving scenario
    python3 scripts/device_simulator.py --mode driving

    # Custom with all options
    python3 scripts/device_simulator.py \\
        --server http://localhost:8000 \\
        --api-key <your-api-key> \\
        --device-id my-test-phone \\
        --mode theft \\
        --pings 5
"""

import argparse
import os
import sys
import time
import random
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ Missing dependency: 'requests'")
    print("   Install with: pip install requests")
    sys.exit(1)


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_SERVER = "http://localhost:8000"
# Read API key from environment variable (never hardcode in source!)
DEFAULT_API_KEY = None  # Must be provided via --api-key or MT_API_KEY env var
DEFAULT_DEVICE_ID = f"sim-device-{int(time.time()) % 100000}"

# Base coordinates (Abuja, Nigeria)
BASE_LAT = 9.0820
BASE_LNG = 8.6753


# ─── Device Simulator ─────────────────────────────────────────────────────────

class DeviceSimulator:
    def __init__(self, server_url: str, api_key: str, device_id: str, user_token: Optional[str] = None, device_key: str = ""):
        self.server = server_url.rstrip("/")
        self.api_key = api_key
        self.device_id = device_id
        self.user_token = user_token  # Bearer token linking the device to an account
        self.device_key = device_key
        self.access_token: Optional[str] = None
        self.session = requests.Session()
        self.ping_count = 0
        self.current_lat = BASE_LAT
        self.current_lng = BASE_LNG

    # ── Registration ──────────────────────────────────────────────────────

    def register(self) -> bool:
        """Register this device with the server."""
        print(f"\n{'='*60}")
        print(f"📱 Registering device: {self.device_id}")
        print(f"{'='*60}")

        payload = {
            "device_id": self.device_id,
            "fingerprint": f"sim-{self.device_id}-fingerprint",
            "model": "Simulated Phone v1.0",
            "os_version": "Android 14",
            "app_version": "1.0.0",
        }
        if self.device_key:
            payload["device_key"] = self.device_key

        headers = {"x-api-key": self.api_key}
        if self.user_token:
            # Mirror the Android TrackingService multi-user flow: send the
            # signed-in user's bearer token so the server links this device
            # to the account (owner_id) — it then appears in that user's
            # dashboard and is scoped to them.
            headers["Authorization"] = f"Bearer {self.user_token}"

        resp = self.session.post(
            f"{self.server}/api/device/register",
            json=payload,
            headers=headers,
        )

        if resp.status_code == 200:
            data = resp.json()
            self.access_token = data["token"]
            linked = "yes" if (self.user_token and data.get("owner_id")) else "no"
            print(f"✅ Registered successfully")
            print(f"   Tokens: access={data['token'][:20]}... refresh={data['refresh_token'][:20]}...")
            if self.user_token:
                print(f"   Account-linked: {linked} (owner_id={data.get('owner_id')})")
            return True
        else:
            print(f"❌ Registration failed: {resp.status_code} {resp.text}")
            return False

    # ── Location Ping ─────────────────────────────────────────────────────

    def send_ping(
        self,
        lat: float,
        lng: float,
        speed: float = 0.0,
        battery: int = 85,
        is_charging: bool = False,
        sim_changed: bool = False,
        airplane_mode: bool = False,
        location_enabled: bool = True,
        accuracy: float = 10.0,
        provider: str = "gps",
        confidence: str = "HIGH",
    ) -> Optional[dict]:
        """Send a telemetry ping to the server."""
        self.ping_count += 1
        ts = datetime.now(timezone.utc).isoformat()

        payload = {
            "device_id": self.device_id,
            "ping_sequence": self.ping_count,
            "lat": lat,
            "lng": lng,
            "accuracy_horizontal": accuracy,
            "speed": speed,
            "provider": provider,
            "confidence_level": confidence,
            "battery_percent": battery,
            "is_charging": is_charging,
            "sim_changed": sim_changed,
            "is_airplane_mode": airplane_mode,
            "is_location_enabled": location_enabled,
            "device_timestamp": ts,
            "network_type": "airplane" if airplane_mode else ("LTE" if not sim_changed else "NO_SERVICE"),
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}
        resp = self.session.post(
            f"{self.server}/api/device/location",
            json=payload,
            headers=headers,
        )

        if resp.status_code == 200:
            data = resp.json()
            commands = data.get("commands_pending", 0)
            return {
                "status": "ok",
                "commands": commands,
                "server_time": data.get("server_time"),
            }
        else:
            print(f"   ⚠️ Ping #{self.ping_count} failed: {resp.status_code} {resp.text[:100]}")
            return None

    # ── Ping Display ──────────────────────────────────────────────────────

    def print_ping(self, result: Optional[dict], scenario: str, lat: float, lng: float):
        """Pretty-print a ping result."""
        if result:
            cmd_str = f" | 📨 {result['commands']} cmd" if result["commands"] else ""
            print(
                f"   #{self.ping_count:3d} | {scenario:15s} | "
                f"📍 {lat:.4f},{lng:.4f} | ✅ OK{cmd_str}"
            )
        else:
            print(f"   #{self.ping_count:3d} | {scenario:15s} | ❌ FAILED")

    # ── Scenarios ─────────────────────────────────────────────────────────

    def scenario_normal(self, pings: int = 10):
        """
        Normal device behavior.
        Walking around a neighborhood with occasional pauses.
        """
        print(f"\n{'='*60}")
        print(f"🚶 Normal Walking Scenario — {pings} pings")
        print(f"{'='*60}")

        self.current_lat = BASE_LAT
        self.current_lng = BASE_LNG

        for i in range(pings):
            # Walk slowly around the base location
            self.current_lat += random.uniform(-0.0005, 0.0005)
            self.current_lng += random.uniform(-0.0005, 0.0005)
            speed = random.uniform(0.5, 3.0)  # walking speed (m/s)
            battery = max(10, 85 - i * 2)  # slowly drain

            result = self.send_ping(
                lat=self.current_lat,
                lng=self.current_lng,
                speed=speed,
                battery=battery,
                location_enabled=True,
                accuracy=random.uniform(3, 12),
            )

            self.print_ping(result, "walking", self.current_lat, self.current_lng)
            time.sleep(0.5)

    def scenario_driving(self, pings: int = 10):
        """
        Driving scenario.
        Moving at highway speeds in a straight-ish line.
        """
        print(f"\n{'='*60}")
        print(f"🚗 Driving Scenario — {pings} pings")
        print(f"{'='*60}")

        self.current_lat = BASE_LAT
        self.current_lng = BASE_LNG

        for i in range(pings):
            # Move at highway speed in a consistent direction
            self.current_lat += random.uniform(0.001, 0.003)
            self.current_lng += random.uniform(0.001, 0.003)
            speed = random.uniform(60, 100)  # highway speed (km/h in m/s)
            battery = max(10, 90 - i * 3)

            result = self.send_ping(
                lat=self.current_lat,
                lng=self.current_lng,
                speed=speed,
                battery=battery,
                location_enabled=True,
                accuracy=random.uniform(5, 15),
                provider="gps",
            )

            self.print_ping(result, "driving", self.current_lat, self.current_lng)
            time.sleep(0.5)

    def scenario_theft(self, pings: int = 10):
        """
        Theft scenario.
        Starts normal → SIM removed → airplane mode → fast movement.
        """
        print(f"\n{'='*60}")
        print(f"🚨 Theft Scenario — {pings} pings")
        print(f"{'='*60}")
        print(f"   Phase 1: Normal operation")
        print(f"   Phase 2: ⚠️ SIM card removed!")
        print(f"   Phase 3: ⚠️ Airplane mode enabled + theft detected!")
        print(f"{'='*60}\n")

        self.current_lat = BASE_LAT
        self.current_lng = BASE_LNG

        for i in range(pings):
            phase = "normal"
            sim_changed = False
            airplane = False
            loc_enabled = True
            speed = random.uniform(0.5, 2.0)
            battery = max(10, 85 - i * 5)
            accuracy = random.uniform(3, 8)
            confidence = "HIGH"

            if i >= 3 and i < 6:
                # Phase 2: SIM removed (still tracking)
                phase = "sim_removed"
                sim_changed = True
                speed = random.uniform(1, 5)
                battery = max(10, battery - 5)
                print(f"   ⚠️ Ping #{i+1}: SIM card REMOVED, location still tracking")
            elif i >= 6:
                # Phase 3: Full theft (airplane mode + disabled location)
                phase = "theft"
                sim_changed = True
                airplane = True
                loc_enabled = False
                speed = random.uniform(40, 80)  # vehicle speed
                accuracy = 50.0  # degraded accuracy
                confidence = "LOW"
                battery = max(10, battery - 3)
                print(f"   🚨 Ping #{i+1}: AIRPLANE MODE + LOCATION OFF + HIGH SPEED!")

            # Move more aggressively in theft phase
            self.current_lat += random.uniform(-0.0005, 0.003)
            self.current_lng += random.uniform(-0.0005, 0.003)

            result = self.send_ping(
                lat=self.current_lat,
                lng=self.current_lng,
                speed=speed,
                battery=battery,
                sim_changed=sim_changed,
                airplane_mode=airplane,
                location_enabled=loc_enabled,
                accuracy=accuracy,
                confidence=confidence,
            )

            self.print_ping(result, phase, self.current_lat, self.current_lng)
            time.sleep(0.5)

    def scenario_battery_death(self, pings: int = 10):
        """
        Battery drain scenario.
        Device battery slowly drains until it dies.
        """
        print(f"\n{'='*60}")
        print(f"🔋 Battery Drain Scenario — {pings} pings")
        print(f"{'='*60}")

        self.current_lat = BASE_LAT
        self.current_lng = BASE_LNG

        for i in range(pings):
            self.current_lat += random.uniform(-0.0003, 0.0003)
            self.current_lng += random.uniform(-0.0003, 0.0003)
            battery = max(0, 100 - i * 12)
            speed = random.uniform(0.5, 2.0)

            is_charging = battery > 70  # was charging earlier
            if battery < 20:
                is_charging = False

            result = self.send_ping(
                lat=self.current_lat,
                lng=self.current_lng,
                speed=speed,
                battery=battery,
                is_charging=is_charging,
                location_enabled=True,
                accuracy=10,
            )

            status = f"🔋 {battery}%"
            if battery <= 0:
                status = "💀 DEAD"
            elif battery < 15:
                status = "⚠️ CRITICAL"
            elif battery < 30:
                status = "⚠️ LOW"

            self.print_ping(result, status, self.current_lat, self.current_lng)
            time.sleep(0.5)

    # ── Dashboard check ───────────────────────────────────────────────────

    def check_dashboard(self):
        """Fetch device status from dashboard API."""
        print(f"\n{'='*60}")
        print(f"📊 Dashboard Status")
        print(f"{'='*60}")

        # When a user token was used, check the dashboard as THAT user so we
        # verify ownership scoping (the device should appear). Otherwise fall
        # back to the shared API key (admin view).
        if self.user_token:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            scope = "user (ownership-scoped)"
        else:
            headers = {"x-api-key": self.api_key}
            scope = "api key (admin)"
        print(f"   Viewing as: {scope}")
        resp = self.session.get(
            f"{self.server}/api/dashboard/devices",
            headers=headers,
        )

        if resp.status_code == 200:
            devices = resp.json().get("devices", [])
            our_device = next((d for d in devices if d["id"] == self.device_id), None)

            if our_device:
                print(f"✅ Device found on dashboard:")
                print(f"   ID:       {our_device['id']}")
                print(f"   Online:   {'✅ Yes' if our_device['is_online'] else '❌ No'}")
                print(f"   Stolen:   {'🚨 YES' if our_device['is_stolen'] else '✅ No'}")
                print(f"   Score:    {our_device['sentinel_score']}/100")
                print(f"   Mode:     {our_device.get('operating_mode', 'normal')}")
                print(f"   Battery:  {our_device.get('battery_percent', '?')}%")
                print(f"   Location: {our_device.get('lat', '?')}, {our_device.get('lng', '?')}")
            else:
                print(f"⚠️ Device '{self.device_id}' not found in dashboard")
                print(f"   Total devices: {len(devices)}")
                for d in devices[:5]:
                    print(f"   - {d['id']} (online: {d['is_online']})")
        else:
            print(f"❌ Dashboard check failed: {resp.status_code}")

    # ── Health check ──────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check if the server is alive."""
        try:
            resp = self.session.get(f"{self.server}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Server online — v{data['version']}")
                return True
            else:
                print(f"❌ Server returned {resp.status_code}")
                return False
        except requests.ConnectionError:
            print(f"❌ Cannot connect to {self.server}")
            print(f"   Make sure the server is running and accessible.")
            return False


# ─── Interactive Mode ─────────────────────────────────────────────────────────

def interactive_mode(sim: DeviceSimulator):
    """Interactive menu-driven mode."""
    if not sim.health_check():
        return

    if not sim.register():
        print("Failed to register device. Check your API key.")
        return

    while True:
        print(f"\n{'='*60}")
        print(f"📱 Device: {sim.device_id}")
        print(f"📍 Position: {sim.current_lat:.4f}, {sim.current_lng:.4f}")
        print(f"{'='*60}")
        print("1. 🚶 Normal walking (10 pings)")
        print("2. 🚗 Driving (10 pings)")
        print("3. 🚨 Simulate theft (10 pings)")
        print("4. 🔋 Battery drain test (10 pings)")
        print("5. 📊 Check dashboard status")
        print("6. 🔄 Register again")
        print("0. Exit")
        print()

        try:
            choice = input("Choose a scenario [0-6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "1":
            sim.scenario_normal()
        elif choice == "2":
            sim.scenario_driving()
        elif choice == "3":
            sim.scenario_theft()
        elif choice == "4":
            sim.scenario_battery_death()
        elif choice == "5":
            sim.check_dashboard()
        elif choice == "6":
            sim.register()
        elif choice == "0":
            print("Goodbye!")
            break


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Magneetar Device Simulator — Test the tracking pipeline without a phone",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Normal device walking around
  python3 scripts/device_simulator.py --mode normal

  # Simulate theft (SIM change + airplane mode + high speed)
  python3 scripts/device_simulator.py --mode theft --pings 5

  # Interactive mode
  python3 scripts/device_simulator.py --interactive
        """,
    )

    parser.add_argument("--server", default=DEFAULT_SERVER, help="Server URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for registration")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="Device identifier")
    parser.add_argument("--user-token", default=None,
                        help="User JWT (Bearer) — links the device to that account (multi-user flow)")
    parser.add_argument("--device-key", default="",
                        help="Per-device secret key to send at registration (defaults to none; server generates one)")
    parser.add_argument("--mode", choices=["normal", "driving", "theft", "battery"],
                        help="Scenario mode")
    parser.add_argument("--pings", type=int, default=10, help="Number of pings to send")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive menu mode")

    args = parser.parse_args()

    # Read API key from environment if not provided via CLI
    if not args.api_key:
        args.api_key = os.environ.get("MT_API_KEY", "")
        if not args.api_key:
            print("❌ No API key provided. Use --api-key or set MT_API_KEY environment variable.")
            sys.exit(1)

    sim = DeviceSimulator(args.server, args.api_key, args.device_id,
                          user_token=args.user_token, device_key=args.device_key)

    if not sim.health_check():
        return

    if args.interactive:
        interactive_mode(sim)
        return

    if args.mode:
        if not sim.register():
            print("❌ Failed to register. Check your server URL and API key.")
            return

        if args.mode == "normal":
            sim.scenario_normal(args.pings)
        elif args.mode == "driving":
            sim.scenario_driving(args.pings)
        elif args.mode == "theft":
            sim.scenario_theft(args.pings)
        elif args.mode == "battery":
            sim.scenario_battery_death(args.pings)

        # Show dashboard status after scenario
        sim.check_dashboard()
    else:
        interactive_mode(sim)


if __name__ == "__main__":
    main()
