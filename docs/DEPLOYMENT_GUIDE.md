# Magneetar Deployment Guide

**Version**: 1.5.0  
**Last Updated**: 2026-09-03

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (Docker)](#quick-start-docker)
3. [Production Deployment](#production-deployment)
4. [Configuration](#configuration)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)
7. [Backup and Recovery](#backup-and-recovery)

---

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 22.04+ recommended) or macOS
- **CPU**: 2+ cores
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 20GB minimum for database and media
- **Docker**: 24.0+
- **Docker Compose**: 2.20+

### Required Accounts

- **Twilio** (optional): For SMS commands and alerts
- **Firebase** (optional): For push notifications
- **Cloudflare** (recommended): For tunnel access and DDoS protection

---

## Quick Start (Docker)

### 1. Clone Repository

```bash
git clone https://github.com/magneetar/magneetar.git
cd magneetar
```

### 2. One-Command Deploy

```bash
bash scripts/deploy-mvp.sh
```

This script will:
- Check Docker installation
- Generate secure secrets
- Build and start all services
- Wait for health checks
- Display access URLs

### 3. Access Services

- **API**: http://localhost:8002
- **Dashboard**: http://localhost:3000
- **Health Check**: http://localhost:8002/health

### 4. Stop Services

```bash
docker compose down
```

---

## Production Deployment

### Step 1: Prepare Environment

Create `server/.env` with production values:

```bash
# Core Secrets (MUST change these!)
MT_API_KEY=$(openssl rand -hex 32)
MT_DEVICE_KEY=$(openssl rand -hex 32)
MT_JWT_SECRET=$(openssl rand -hex 64)
MT_ENCRYPTION_KEY=$(openssl rand -hex 32)

# Environment
MT_ENVIRONMENT=production
MT_DATABASE_URL=postgresql://magneetar:secure_password@postgres:5432/magneetar

# Redis (for multi-worker WebSocket)
MT_REDIS_URL=redis://redis:6379/0

# Storage
MT_DB_PATH=/app/data/magneetar.db
MT_MEDIA_DIR=/app/media
MT_MAX_DEVICES=100

# Retention
MT_RETENTION_DAYS=90
MT_ARCHIVE_AFTER_DAYS=30

# Rate Limits
MT_RATE_LIMIT_ENABLED=true

# Optional: Twilio for SMS
MT_TWILIO_SID=your_twilio_sid
MT_TWILIO_AUTH_TOKEN=your_twilio_token
MT_TWILIO_SMS_FROM=+1234567890

# Optional: Firebase for push
MT_FIREBASE_KEY=./firebase-key.json

# Optional: Alerts
MT_ALERT_PHONE=+2348012345678
MT_ALERT_EMAIL=admin@example.com
```

### Step 2: Configure PostgreSQL

Production uses PostgreSQL by default. Update `docker-compose.yml`:

```yaml
postgres:
  environment:
    POSTGRES_DB: magneetar
    POSTGRES_USER: magneetar
    POSTGRES_PASSWORD: <secure_password>
  volumes:
    - magneetar-pgdata:/var/lib/postgresql/data
```

### Step 3: Configure Cloudflare Tunnel

1. Install cloudflared:
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
```

2. Create tunnel:
```bash
./cloudflared tunnel create magneetar
```

3. Configure routes in `deploy/cloudflared/config.yml`:
```yaml
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: api.magneetar.me
    service: http://server:8000
  - hostname: dashboard.magneetar.me
    service: http://dashboard:80
  - service: http_status:404
```

### Step 4: Deploy

```bash
docker compose -f docker-compose.yml up -d
```

### Step 5: Verify Deployment

```bash
# Check service health
docker compose ps

# Check logs
docker compose logs -f server

# Test API
curl https://api.magneetar.me/health
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MT_API_KEY` | Yes | - | Master API key for admin operations |
| `MT_DEVICE_KEY` | Yes | - | Device registration secret |
| `MT_JWT_SECRET` | Yes | - | JWT signing secret |
| `MT_ENCRYPTION_KEY` | Yes | - | AES-256 encryption key for sensitive data |
| `MT_ENVIRONMENT` | No | `development` | `development` or `production` |
| `MT_DATABASE_URL` | No | SQLite | PostgreSQL connection string |
| `MT_REDIS_URL` | No | - | Redis connection for WebSocket broadcast |
| `MT_DB_PATH` | No | `/app/data/magneetar.db` | SQLite database path |
| `MT_MEDIA_DIR` | No | `/app/media` | Evidence media storage |
| `MT_MAX_DEVICES` | No | `10` | Max devices per user |
| `MT_RETENTION_DAYS` | No | `90` | Data retention period |
| `MT_ARCHIVE_AFTER_DAYS` | No | `30` | Days before device archived |
| `MT_RATE_LIMIT_ENABLED` | No | `true` | Enable rate limiting |

### Feature Flags

Edit `server/feature_flags.json`:

```json
{
  "maintenance_mode": false,
  "beta_p2p_pairing": false,
  "experimental_ai_detection": false
}
```

---

## Monitoring

### Health Endpoints

- **Server Health**: `GET /health`
- **Database Health**: `GET /health/db`
- **Redis Health**: `GET /health/redis`

Response:
```json
{
  "status": "healthy",
  "version": "1.5.0",
  "database": "connected",
  "redis": "connected"
}
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f server

# Last 100 lines
docker compose logs --tail=100 server
```

### Metrics

Access Prometheus metrics at `GET /metrics` (if enabled).

### Sentry Integration

Set `SENTRY_DSN` environment variable for error tracking:

```bash
SENTRY_DSN=https://xxx@sentry.io/xxx
```

---

## Troubleshooting

### Common Issues

#### 1. Server Won't Start

**Symptoms**: Container exits immediately

**Check**:
```bash
docker compose logs server
```

**Common causes**:
- Missing `.env` file
- Invalid `MT_DATABASE_URL`
- Database connection refused

**Solution**:
```bash
# Verify .env exists
ls -la server/.env

# Check database connection
docker compose exec postgres pg_isready
```

#### 2. Database Migration Errors

**Symptoms**: "no such column" errors

**Solution**:
```bash
# Force schema migration
docker compose exec server python -c "from database import init_db; init_db()"
```

#### 3. WebSocket Not Working

**Symptoms**: Dashboard doesn't update in real-time

**Check**:
```bash
# Verify Redis connection
docker compose exec redis redis-cli ping
```

**Solution**:
- Ensure `MT_REDIS_URL` is set
- Check Redis health: `GET /health/redis`

#### 4. Push Notifications Not Working

**Symptoms**: Devices don't receive alerts

**Check**:
- `MT_FIREBASE_KEY` path is correct
- Firebase key file exists and is valid
- Device has FCM token registered

#### 5. SMS Commands Not Working

**Symptoms**: SMS not delivered or processed

**Check**:
- Twilio credentials configured
- `MT_TWILIO_SMS_FROM` is a valid Twilio number
- Webhook endpoint accessible: `POST /api/webhook/sms`

---

## Backup and Recovery

### Database Backup

#### PostgreSQL

```bash
# Backup
docker compose exec postgres pg_dump -U magneetar magneetar > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260903.sql | docker compose exec -T postgres psql -U magneetar magneetar
```

#### SQLite

```bash
# Backup
docker compose exec server sqlite3 /app/data/magneetar.db ".backup /app/data/backup.db"

# Copy to host
docker cp magneetar-server:/app/data/backup.db ./backups/
```

### Media Backup

```bash
# Backup evidence media
docker cp magneetar-server:/app/media ./backups/media_$(date +%Y%m%d)
```

### Automated Backups

Create a cron job:

```bash
# crontab -e
0 2 * * * /path/to/magneetar/scripts/backup.sh
```

`scripts/backup.sh`:
```bash
#!/bin/bash
cd /path/to/magneetar
docker compose exec -T postgres pg_dump -U magneetar magneetar | gzip > backups/db_$(date +%Y%m%d).sql.gz
docker cp magneetar-server:/app/media ./backups/media_$(date +%Y%m%d)
```

---

## Security Checklist

- [ ] Changed all default secrets in `.env`
- [ ] PostgreSQL password is strong and unique
- [ ] `MT_ENCRYPTION_KEY` is set (encrypts sensitive data at rest)
- [ ] Firebase key file has restricted permissions (600)
- [ ] Rate limiting enabled
- [ ] CORS configured for your domain only
- [ ] Cloudflare tunnel configured (not exposing ports directly)
- [ ] Regular backups scheduled
- [ ] Monitoring and alerts configured
- [ ] `.env` file is in `.gitignore`

---

## Scaling Considerations

### Horizontal Scaling

1. **Load Balancer**: Use nginx or Cloudflare Load Balancer
2. **Database**: Use managed PostgreSQL (Neon, AWS RDS, etc.)
3. **Redis**: Use managed Redis or Redis Cluster
4. **Storage**: Move media to S3-compatible storage (Cloudflare R2, AWS S3)

### Vertical Scaling

- Increase `--workers` in server Dockerfile (currently 2)
- Increase container memory/CPU limits
- Use read replicas for database

---

## Support

- **Documentation**: `docs/` directory
- **Issues**: GitHub Issues
- **Email**: support@magneetar.me

---

**Last Updated**: 2026-09-03  
**Maintainer**: Magneetar Engineering Team
