# Magneetar Deployment Guide

## Production deployment with Docker and Cloudflare Tunnel

---

## Overview

Magneetar can be deployed:
- **Development**: SQLite + local server (quick start)
- **Production**: Docker + Cloudflare Tunnel (recommended)

The app's live data plane is **SQLite** at `/app/data/magneetar.db` on the
persisted `magneetar-data` volume (see `MT_DB_PATH`). PostgreSQL is optional
and holds no app data in the current deployment — `backup-db.sh` snapshots the
SQLite database.

---

## 1. Quick Start (Development)

```bash
# 1. Clone and generate secrets
cd magneetar
./scripts/generate-env.sh
source server/venv/bin/activate
pip install -r server/requirements.txt

# 2. Start the server
cd server
python main.py

# 3. In another terminal, start the dashboard
cd dashboard
npm install
npm run dev
```

---

## 2. Production with Docker

### Prerequisites

- Docker & Docker Compose v2+
- A domain name pointed to your server (or use Cloudflare Tunnel)
- Ports 80/443 open (or Cloudflare Tunnel)

### Step 1: Generate production secrets

```bash
./scripts/generate-env.sh --docker
```

This creates:
- `server/.env` — API keys, JWT secret, encryption key
- `server/.db_password` — PostgreSQL password (mounted as Docker secret)

### Step 2: Build and start

```bash
docker compose build
docker compose up -d
```

Services:
| Service    | Port   | URL                       |
|------------|--------|---------------------------|
| API Server | 8000   | http://localhost:8000      |
| Dashboard  | 3000   | http://localhost:3000      |
| PostgreSQL (optional, not the live data plane) | 5432 | internal (db:5432) |

### Step 3: Verify

```bash
curl http://localhost:8000/health
# → {"status":"online","version":"1.0.0",...}
```

### Step 4: Choose the database engine

The server auto-detects `MT_DATABASE_URL`. The current production deployment
uses **SQLite on a persisted volume** (the default when `MT_DATABASE_URL` is
blank), because the route layer reads/writes SQLite via `database.py`:

```env
# Production (default — SQLite on persisted volume)
MT_DB_PATH=/app/data/magneetar.db

# Optional (PostgreSQL — secondary/experimental, not the live data plane)
# MT_DATABASE_URL=postgresql://magneetar:your-password@db:5432/magneetar
```

---

## 3. Cloudflare Tunnel (Recommended)

Cloudflare Tunnel provides secure public access without opening firewall ports.

### Setup

```bash
# 1. Install cloudflared
sudo apt install cloudflared  # Linux
# OR download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

# 2. Authenticate
cloudflared tunnel login

# 3. Create a tunnel
cloudflared tunnel create magneetar

# 4. Create config file (~/.cloudflared/config.yml)
```

`~/.cloudflared/config.yml`:
```yaml
tunnel: <your-tunnel-uuid>
credentials-file: /home/user/.cloudflared/<your-tunnel-uuid>.json

ingress:
  - hostname: api.magneetar.me
    service: http://localhost:8000
  - hostname: app.magneetar.me
    service: http://localhost:3000
  - service: http_status:404
```

### DNS Configuration

```bash
# Point your domains to the tunnel
cloudflared tunnel route dns magneetar api.magneetar.me
cloudflared tunnel route dns magneetar app.magneetar.me
```

### Run as Service

```bash
# Install as systemd service
sudo cloudflared service install

# Or run directly
cloudflared tunnel run magneetar
```

### Docker Compose with Cloudflare (alternative)

Add to your `docker-compose.yml`:

```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  restart: unless-stopped
  command: tunnel --no-autoupdate run
  environment:
    - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
```

---

## 4. Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MT_API_KEY` | ✅ Yes | — | Min 32 chars, used by dashboard to login |
| `MT_JWT_SECRET` | ✅ Yes | — | Min 64 chars, JWT signing key |
| `MT_ENCRYPTION_KEY` | ✅ Yes | — | 32 bytes hex, encryption key |
| `MT_DATABASE_URL` | No | — | Optional PostgreSQL URL (not the live data plane) |
| `MT_DB_PATH` | No | `magneetar.db` | SQLite database path — set to `/app/data/magneetar.db` (persisted volume) in production |
| `MT_ENVIRONMENT` | No | `development` | `development` or `production` |
| `MT_HOST` | No | `0.0.0.0` | Server bind address |
| `MT_PORT` | No | `8000` | Server port |
| `MT_SENDGRID_KEY` | No | — | SendGrid API key for email alerts |
| `MT_TERMII_KEY` | No | — | Termii API key for SMS alerts |
| `MT_TWILIO_SID` | No | — | Twilio SID for WhatsApp alerts |
| `MT_TWILIO_AUTH_TOKEN` | No | — | Twilio auth token |
| `MT_MAX_DEVICES` | No | `5` | Max devices per user |
| `MT_RETENTION_DAYS` | No | `90` | Data retention in days |

---

## 5. Production Checklist

### Security

- [ ] `MT_API_KEY` is at least 32 random characters
- [ ] `MT_JWT_SECRET` is at least 64 random characters
- [ ] `MT_ENCRYPTION_KEY` is exactly 32 bytes (64 hex chars)
- [x] SQLite database lives on the persisted Docker volume (`MT_DB_PATH=/app/data/magneetar.db`)
- [x] Daily backups run via `bash scripts/backup-db.sh` (snapshots the live SQLite DB)
- [ ] CORS is configured with specific origins in production
- [ ] HTTPS is enforced (via Cloudflare or reverse proxy)
- [ ] Rate limiting is active (default: 5 login attempts/10 min)
- [ ] Docker secrets are used for database password
- [ ] All sensitive data is encrypted at rest

### Monitoring

- [ ] Health check endpoint is monitored (`/health`)
- [ ] Server logs are collected (structured JSON output)
- [ ] Audit log table tracks all admin actions
- [ ] Sentry DSN configured for error tracking (optional)

### Backup

- [x] Live SQLite database is backed up daily (`bash scripts/backup-db.sh`)
- [ ] Set up automatic daily backups via cron:
  ```bash
  # crontab -e
  0 3 * * * cd /path/to/magneetar && bash scripts/backup-db.sh >> /var/log/magneetar-backup.log 2>&1
  ```
- [x] Test restore procedure documented (`bash scripts/backup-db.sh --restore <file>`)
- [ ] Evidence files and media are backed up separately

> **Note:** The app's live data plane is SQLite at `/app/data/magneetar.db` (the
> persisted `magneetar-data` volume) inside the `magneetar-server` container.
> `backup-db.sh` snapshots that database via the SQLite online backup API.
> PostgreSQL (`magneetar-db`) is optional and holds no app data — do not back
> it up in place of the SQLite database.

### Alerts (Configure at least one)

- [ ] SendGrid API key set for email alerts
- [ ] Termii API key set for SMS alerts (Nigerian users)
- [ ] Twilio configured for WhatsApp alerts (optional)
- [ ] Alert phone number and email configured

### Android App

- [ ] `SERVER_URL` set in `android-app/app/build.gradle.kts`
- [ ] `API_KEY` set in `android-app/app/build.gradle.kts`
- [ ] APK built with release signing
- [ ] Device Admin permission requested on first launch
- [ ] Battery optimization is disabled for the app

---

## 6. Scaling Considerations

### Small deployment (1-10 devices)
- Single server, SQLite or PostgreSQL
- Cloudflare Tunnel for public access
- ~$5-10/month VPS

### Medium deployment (10-100 devices)
- Single server, PostgreSQL
- Cloudflare Tunnel with caching
- ~$10-20/month VPS

### Large deployment (100+ devices)
- Separate database server
- Load-balanced API servers
- Redis for rate limiting (future)
- Object storage for evidence media (future)

---

## 7. Troubleshooting

### Server won't start

```bash
# Check environment
docker compose exec server env | grep MT_

# Check database connection
docker compose exec server python -c "
from config import settings
print(f'DB: {settings.DB_PATH}')
print(f'PG: {settings.DATABASE_URL}')
"

# Check logs
docker compose logs server
```

### PostgreSQL connection refused

```bash
# Wait for DB to be ready
docker compose logs db

# Verify credentials
docker compose exec db psql -U magneetar -d magneetar -c "SELECT 1"
```

### Dashboard can't reach API

```bash
# Check DNS resolution (with Cloudflare Tunnel)
curl -H "Host: api.magneetar.me" http://localhost:8000/health

# Verify dashboard env
docker compose exec dashboard env | grep NEXT_PUBLIC
```

---

## 8. Updating (safe, no-breaking-changes policy)

Magneetar is designed so that consumers' devices and dashboards keep working
across updates — no forced-breakage, no data loss. The three layers of the
policy:

### 8.1 Schema migrations are additive & idempotent

- `server/database.py` → `init_db()` runs `CREATE TABLE IF NOT EXISTS ...` and
  additive `ALTER TABLE ... ADD COLUMN` guarded by a column-existence check.
  It is called on every server start, so **new columns appear automatically**;
  old columns are **never dropped** and existing rows are **never rewritten**.
- When adding a column, follow the existing pattern in `init_db()`:
  ```python
  # ALTER TABLE devices ADD COLUMN device_key_hash TEXT  (guarded by PRAGMA check)
  ```
- **Never** rename/remove a column or table that production data depends on.
  If a column must change meaning, add a NEW column and keep the old one.
- No separate migration tool is required; a server restart applies migrations.

### 8.2 API compatibility is additive-only

- New endpoints and new **optional** fields are always safe.
- Existing endpoints never change field types, remove fields, or tighten
  validators in a way that rejects old clients.
- The public `GET /api/config` endpoint tells old clients what the server
  expects:
  ```json
  {"app_version": "1.2.0", "min_android_version": 24, "features_enabled": [...]}
  ```
- The Android app reads `/api/config` after registration and, if the device
  OS is older than `min_android_version` or a newer app exists, shows a
  **non-blocking** notification. Tracking never stops because of a version
  mismatch — old clients degrade gracefully.

### 8.3 Deploy & rollback

Use the hardened deploy script — it backs up the DB first, tags the current
images for rollback, rebuilds only `server` + `dashboard` (never touching
`db`/`cloudflared`), and blocks on a real health gate:

```bash
bash scripts/deploy.sh
```

If a deploy is bad:

```bash
bash scripts/rollback.sh          # restores :predeploy images + recreates containers
# or manually:
#   docker tag magneetar-server:predeploy magneetar-server:latest
#   docker tag magneetar-dashboard:predeploy magneetar-dashboard:latest
#   docker compose up -d --no-deps server dashboard

# If the DB state itself is suspect:
bash scripts/backup-db.sh --list
bash scripts/backup-db.sh --restore <file>
```

Legacy quick update (not recommended for production):

```bash
git pull
docker compose build
docker compose up -d
```

---

## 9. Security Hardening

### Additional Recommended Measures

1. **Fail2Ban** — Block IPs after repeated failed login attempts:
   ```ini
   [magneetar-login]
   enabled = true
   filter = magneetar-login
   logpath = /var/log/docker/containers/*/*.log
   maxretry = 10
   bantime = 3600
   ```

2. **Cloudflare WAF** — Enable Bot Fight Mode and rate limiting rules in Cloudflare dashboard.

3. **Docker network** — Restrict inter-container communication:
   ```yaml
   networks:
     magneetar:
       internal: true  # No external access
   ```

4. **Regular security updates**:
   ```bash
   docker compose pull  # Update all images
   docker compose up -d  # Recreate containers
   ```

---

> **Need help?** Open an issue at github.com/Oluwanifemi-engineer/magneetar
