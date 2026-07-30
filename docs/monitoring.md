# Magneetar Monitoring Setup

## UptimeRobot (Free Tier)

UptimeRobot is a free uptime monitoring service that checks your API every 5 minutes and sends alerts if it goes down.

### Setup Instructions

1. **Create an account**: Go to [UptimeRobot.com](https://uptimerobot.com) and sign up (free tier: 50 monitors, 5-min intervals)

2. **Add a monitor**:
   - Click "Add New Monitor"
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `Magneetar API`
   - URL: `https://api.magneetar.me/health`
   - Monitoring Interval: **5 minutes**
   - Select alert contacts (email/SMS)

3. **Add another monitor for the dashboard**:
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `Magneetar Dashboard`
   - URL: `https://app.magneetar.me`
   - Monitoring Interval: **5 minutes**

4. **Configure alerts**:
   - Add your email for downtime notifications
   - Optionally add SMS (paid) or Slack/Teams webhooks

### Local Health Monitor

A local cron-based health checker already runs:
```bash
# Check status
bash scripts/health-monitor.sh --status

# Example output:
# === Magneetar Health Monitor ===
# Endpoint: https://api.magneetar.me/health
# Total checks: 42
# ✅ Up: 42 (100%)
# ❌ Down: 0
```

Logs are stored at `/tmp/magneetar-monitor/health.log`

### Alert Configuration

To receive email alerts when the server goes down:
```bash
# Install mail utility (Ubuntu/Debian)
sudo apt-get install -y mailutils

# Run health monitor with email alert
MT_ALERT_EMAIL=your@email.com bash scripts/health-monitor.sh
```
