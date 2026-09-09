# Magneetar Developer Setup Guide

**Version**: 1.4.4  
**Last Updated**: 2026-09-03

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Project Structure](#project-structure)
5. [Development Workflow](#development-workflow)
6. [Testing](#testing)
7. [Code Style](#code-style)
8. [Debugging](#debugging)

---

## Overview

Magneetar is an anti-theft tracking platform for Android devices. This guide will help you set up your development environment and start contributing.

### Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Cache/Pub-Sub | Redis |
| Dashboard | Next.js 14, TypeScript, Tailwind CSS |
| Android | Kotlin, Jetpack, Material Design 3 |
| CI/CD | GitHub Actions |
| Monitoring | Sentry, Prometheus |

---

## Prerequisites

### Required

- **Python 3.12+**
- **Node.js 20+**
- **Android Studio** (for Android development)
- **Git**
- **Docker** (optional, for full stack)

### Recommended

- **VS Code** with extensions:
  - Python
  - Pylance
  - ESLint
  - TypeScript
  - Kotlin
- **PostgreSQL 16** (for production parity)
- **Redis** (for WebSocket testing)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/magneetar/magneetar.git
cd magneetar
```

### 2. Backend Setup

```bash
cd server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up environment
cp .env.example .env
# Edit .env with your values

# Initialize database
python -c "from database import init_db; init_db()"

# Run server
uvicorn main:app --reload --port 8002
```

### 3. Dashboard Setup

```bash
cd dashboard

# Install dependencies
npm install

# Set up environment
cp .env.example .env.local
# Edit .env.local with your values

# Run development server
npm run dev
```

### 4. Android Setup

1. Open Android Studio
2. Open project: `android-app/`
3. Sync Gradle files
4. Run on emulator or device

---

## Project Structure

```
magneetar/
├── server/                    # FastAPI backend
│   ├── main.py               # Entry point
│   ├── routes/               # API modules
│   │   ├── devices.py        # Device endpoints
│   │   ├── dashboard.py      # Dashboard endpoints
│   │   ├── auth.py           # Authentication
│   │   └── ...
│   ├── models.py             # Pydantic schemas
│   ├── database.py           # SQLite/PostgreSQL
│   ├── config.py             # Environment config
│   └── tests/                # Pytest tests
│
├── dashboard/                 # Next.js web app
│   ├── src/
│   │   ├── app/              # Pages (Next.js 14 app router)
│   │   ├── components/       # React components
│   │   ├── hooks/            # Custom hooks
│   │   └── lib/              # Utilities
│   ├── public/               # Static assets
│   └── tests/                # Jest tests
│
├── android-app/               # Android app
│   └── app/src/main/java/com/magneetar/app/
│       ├── MainActivity.kt
│       ├── TrackingService.kt
│       ├── DashboardActivity.kt
│       └── ...
│
├── docs/                      # Documentation
├── scripts/                   # Deployment scripts
├── deploy/                    # Deployment configs
└── tests/                     # Integration tests
```

---

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Integration branch
- `feature/*` - New features
- `fix/*` - Bug fixes

### Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add biometric authentication
fix: resolve WebSocket reconnection issue
docs: update API documentation
test: add evidence integration tests
refactor: extract telemetry domain
chore: update dependencies
```

### Pull Request Process

1. Create feature branch from `develop`
2. Make changes and write tests
3. Run linting and tests locally
4. Create PR with description
5. Wait for CI checks
6. Address review feedback
7. Squash and merge

---

## Testing

### Backend Tests

```bash
cd server

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_evidence_integration.py -v

# Run specific test
pytest tests/test_evidence_integration.py::TestMediaUpload::test_upload_photo_creates_media_record -v
```

### Dashboard Tests

```bash
cd dashboard

# Run unit tests
npm test

# Run E2E tests
npm run test:e2e

# Run with coverage
npm test -- --coverage
```

### Android Tests

```bash
cd android-app

# Run unit tests
./gradlew test

# Run instrumentation tests
./gradlew connectedAndroidTest
```

---

## Code Style

### Python

We use:
- **Black** for formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

```bash
# Format code
black server/
isort server/

# Check linting
flake8 server/

# Type check
mypy server/
```

### TypeScript/React

We use:
- **ESLint** for linting
- **Prettier** for formatting

```bash
cd dashboard

# Lint
npm run lint

# Fix linting issues
npm run lint -- --fix
```

### Kotlin

We use **ktlint** with default rules.

---

## Debugging

### Backend Debugging

1. **VS Code**: Add to `.vscode/launch.json`:

```json
{
  "name": "Debug Server",
  "type": "python",
  "request": "launch",
  "module": "uvicorn",
  "args": ["main:app", "--reload", "--port", "8002"],
  "jinja": true,
  "justMyCode": false
}
```

2. **Logging**:

```python
import logging
logger = logging.getLogger(__name__)
logger.debug("Debug message")
```

3. **Database queries**:

```bash
# SQLite
sqlite3 /app/data/magneetar.db
> SELECT * FROM devices;

# PostgreSQL
docker compose exec postgres psql -U magneetar magneetar
```

### Dashboard Debugging

1. **React DevTools**: Install browser extension
2. **Next.js Debug Mode**:

```bash
NODE_OPTIONS='--inspect' npm run dev
```

3. **Network Tab**: Check API requests in browser DevTools

### Android Debugging

1. **Logcat**: View logs in Android Studio
2. **Breakpoints**: Set breakpoints in Kotlin code
3. **Layout Inspector**: Inspect UI hierarchy

---

## Environment Variables

### Backend (.env)

```bash
# Required
MT_API_KEY=dev-key-change-in-production
MT_DEVICE_KEY=dev-device-key
MT_JWT_SECRET=dev-jwt-secret
MT_ENCRYPTION_KEY=dev-encryption-key

# Optional
MT_ENVIRONMENT=development
MT_DB_PATH=data/magneetar.db
MT_REDIS_URL=redis://localhost:6379/0
MT_DATABASE_URL=postgresql://user:pass@localhost/magneetar

# Services
MT_TWILIO_SID=
MT_TWILIO_AUTH_TOKEN=
MT_FIREBASE_KEY=
```

### Dashboard (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8002
NEXT_PUBLIC_APP_VERSION=1.4.4-dev
```

---

## Common Tasks

### Add New API Endpoint

1. Create route in `server/routes/`
2. Add schema to `server/models.py`
3. Write tests in `server/tests/`
4. Update API documentation

### Add New Dashboard Page

1. Create page in `dashboard/src/app/`
2. Create components in `dashboard/src/components/`
3. Add tests in `dashboard/src/__tests__/`
4. Update navigation

### Add New Android Feature

1. Create fragment/activity
2. Update navigation graph
3. Add to `TrackingService` if needed
4. Write unit tests
5. Test on multiple devices

---

## Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Next.js Docs**: https://nextjs.org/docs
- **Android Docs**: https://developer.android.com/docs
- **Material Design**: https://m3.material.io/
- **Project Wiki**: `docs/` directory

---

## Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: General questions
- **Code Review**: Tag maintainers in PRs

---

**Last Updated**: 2026-09-03  
**Maintainer**: Magneetar Engineering Team
