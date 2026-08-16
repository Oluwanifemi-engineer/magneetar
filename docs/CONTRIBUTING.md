# Contributing to Magneetar

Thank you for your interest in contributing to Magneetar! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Architecture Overview](#architecture-overview)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

We are committed to providing a welcoming and inclusive experience for everyone. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose (for production testing)
- Android Studio (for Android development)

### Setting Up Your Environment

1. **Clone the repository**
   ```bash
   git clone git@github.com:Oluwanifemi-engineer/magneetar.git   # private — maintainers only
   cd magneetar
   ```

2. **Generate environment secrets**
   ```bash
   bash scripts/generate-env.sh
   ```

3. **Install dependencies**
   ```bash
   make setup  # Installs server + dashboard dependencies
   ```

4. **Install pre-commit hooks**
   ```bash
   make pre-commit-install
   ```

5. **Start development servers**
   ```bash
   make server      # Backend at http://localhost:8000
   make dashboard   # Frontend at http://localhost:3000
   ```

## Development Environment

### Backend (Python/FastAPI)

```bash
# Start development server with auto-reload
make server

# Run tests
make test-backend

# Run specific tests
cd server && python -m pytest tests/test_api.py -v
```

### Frontend (Next.js/TypeScript)

```bash
# Start development server
make dashboard

# Run tests
make test-dashboard

# Type checking
make typecheck
```

### Android (Kotlin)

```bash
# Build debug APK
cd android-app && ./gradlew assembleDebug

# Run tests
cd android-app && ./gradlew test
```

## Code Style

### Python (Backend)

- **Formatter**: Black (line length 120)
- **Linter**: Flake8
- **Import sorting**: isort (handled by pre-commit)

```bash
# Format code
make server-format

# Lint code
make server-lint
```

### TypeScript/JavaScript (Frontend)

- **Formatter**: ESLint with Next.js config
- **Linter**: ESLint

```bash
# Format and lint
make dashboard-format
make dashboard-lint
```

### Kotlin (Android)

- **Formatter**: Kotlin official style
- **Lint**: Android Lint

## Testing

### Running All Tests

```bash
make test  # Runs backend + dashboard tests
```

### Backend Tests

```bash
cd server && python -m pytest tests/ -v
```

### Dashboard Tests

```bash
cd dashboard && npm run test:ci
```

### Test Coverage

```bash
# Generate coverage report
cd server && python -m pytest tests/ --cov=. --cov-report=term-missing
```

### Writing Tests

- Write tests for all new features
- Maintain or improve test coverage
- Use meaningful test names
- Test both success and failure paths
- Mock external services (SendGrid, Twilio, Firebase)

## Pull Request Process

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Follow code style guidelines
- Write tests for new functionality
- Update documentation if needed

### 3. Run Quality Gates

```bash
make validate  # Runs lint + typecheck + tests
```

### 4. Commit Your Changes

Use conventional commits:
```
feat: add new feature
fix: bug fix
docs: documentation changes
refactor: code refactoring
test: add or update tests
chore: maintenance tasks
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

### 6. PR Requirements

- [ ] Tests pass (`make test`)
- [ ] Lint passes (`make lint`)
- [ ] Type checking passes (`make typecheck`)
- [ ] Documentation updated (if applicable)
- [ ] Changelog updated (for user-facing changes)
- [ ] PR description explains the change

### 7. Code Review

- Address all review comments
- Ensure CI passes
- Get approval from maintainers

## Architecture Overview

### Project Structure

```
magneetar/
├── server/                  # Python FastAPI backend
│   ├── main.py              # App setup and middleware
│   ├── auth.py              # Authentication logic
│   ├── database.py          # SQLite operations
│   ├── alerts.py            # Multi-channel alerts
│   ├── sentinel.py          # Theft detection AI
│   ├── routes/              # API endpoints
│   └── tests/               # Backend tests
├── dashboard/               # Next.js web dashboard
│   ├── src/
│   │   ├── app/             # Pages and layouts
│   │   ├── components/      # React components
│   │   ├── hooks/           # Custom hooks
│   │   └── lib/             # Utilities and API client
│   └── package.json
├── android-app/             # Android Kotlin app
│   └── app/src/main/
│       ├── java/            # Kotlin source files
│       └── res/             # Android resources
├── scripts/                 # Deployment and utilities
└── docs/                    # Documentation
```

### Key Concepts

1. **Device Authentication**: Each device has a unique 256-bit key
2. **Sentinel AI**: Intelligent theft detection with false-positive prevention
3. **Evidence Chain**: SHA-256 hash chain for forensic integrity
4. **Multi-channel Alerts**: Email, SMS, WhatsApp, Push notifications
5. **Real-time Updates**: WebSocket connections for live dashboard

### Security Model

- **Defense in depth**: Multiple security layers
- **Least privilege**: Device keys have minimal permissions
- **Audit logging**: All security events are logged
- **Encryption at rest**: Account secrets (TOTP 2FA) always AES-256-GCM; location telemetry AES-256-GCM with per-device HKDF keys when `MT_ENCRYPTION_KEY` is set (v1.5+); TLS in transit

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

1. **Environment**: OS, Python/Node version, browser
2. **Steps to reproduce**: Clear, numbered steps
3. **Expected behavior**: What should happen
4. **Actual behavior**: What actually happens
5. **Logs**: Relevant error messages

### Feature Requests

When requesting features, please include:

1. **Use case**: Why do you need this feature?
2. **Proposed solution**: How should it work?
3. **Alternatives considered**: Other approaches you've thought about
4. **Additional context**: Mockups, examples, etc.

## Getting Help

- **Documentation**: Check `docs/` directory
- **Issues**: Open a GitHub issue
- **Discussions**: Use GitHub Discussions for questions

## License

By contributing, you agree that your contributions will be licensed under the Business Source License 1.1 (BUSL-1.1).

---

Thank you for contributing to Magneetar! 🛡️
