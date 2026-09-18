"""
Shared test isolation (conftest.py)

Strips REAL external-service credentials from the environment BEFORE any test
module imports config. config.py does `load_dotenv(server/.env)` with
override=False, so a variable that is already present (even as an empty
string) wins over the .env file — which is exactly what we exploit here.

Why this matters: without it, alert-path tests inherited the developer's live
Twilio / SendGrid / Resend / Firebase credentials from server/.env and made
REAL network calls to those APIs during the run. The occasional slow or
unreachable provider blew past the 30s request-timeout middleware (HTTP 504),
which aborted the request before the alert row was written — producing
order- and timing-dependent flakes (e.g. test_sim_change.py's
count_alerts()/sentinel-score assertions) that could not be reproduced in
isolation.

With the credentials stripped, alert_engine.send_all() takes the "channel not
configured" path: it still logs the alert row (delivered=0) so incident dedup
and the alert-history assertions keep working, but it never touches the
network. Tests that explicitly want a fake provider set their own values via
monkeypatch / direct config.settings mutation (see test_reliability.py) and
are unaffected.
"""

import atexit
import os
import shutil
import tempfile

for _var in (
    "MT_TWILIO_SID",
    "MT_TWILIO_AUTH_TOKEN",
    "MT_TWILIO_SMS_FROM",
    "MT_TWILIO_WHATSAPP_FROM",
    "MT_ALERT_PHONE",
    "MT_ALERT_EMAIL",
    "MT_SENDGRID_KEY",
    "MT_SENDGRID_API_KEY",
    # Resend transactional email — added to the strip list with the provider
    # round (2026-08-14): without it, tests took the REAL Resend delivery path
    # whenever the host .env carries MT_RESEND_KEY, making live resend.com
    # calls on every register/forgot-password and breaking
    # test_reset_token_never_logged_without_email_provider (the no-provider
    # WARNING it pins never fired).
    "MT_RESEND_KEY",
    "MT_RESEND_API_KEY",
    "MT_TERMII_KEY",
    "MT_FIREBASE_KEY",
):
    # Set to empty (NOT popped): an absent var would be re-loaded from
    # server/.env by load_dotenv; an empty one is "already set" and skipped.
    os.environ[_var] = ""

# ─────────────────────────────────────────────────────────────────────────────
# Canonical test auth material (2026-09-09)
#
# config.py binds settings.API_KEY / JWT_SECRET / ENCRYPTION_KEY from the
# environment ONCE per module generation. Test files that evict and re-import
# config (test_e2e & friends) create additional generations mid-suite, and
# each generation previously carried ITS OWN file's key/secret. A request
# authenticated against generation A's settings while the app resolved
# generation B's produced the order-dependent 401 / "Invalid token" /
# split-brain cascades whose failure set changed with import order (85- and
# 103-failure full-suite runs that no two runs reproduced identically).
#
# Fix: ONE canonical key/secret set, established here before any test module
# import and re-asserted (as a no-op) by each file's own env preamble. Every
# generation now binds identical auth material, so a stale module binding and
# the live resolution agree on auth regardless of import order. The values
# mirror the historical shared suite key/secret on purpose: tokens and keys
# hardcoded in existing tests keep working unchanged.
#
# MT_ENCRYPTION_KEY is pinned to a FIXED value (was secrets.token_hex(32) per
# file): two generations with different encryption keys could not decrypt each
# other's stored location ciphertext, which is the mechanism behind the
# order-dependent test_encryption_at_rest failures.
# ─────────────────────────────────────────────────────────────────────────────
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_DEVICE_KEY"] = "test-device-key-" + "c" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = "e" * 64

# ─────────────────────────────────────────────────────────────────────────────
# Filesystem isolation for evidence media (2026-09-17)
#
# media_store.get_media_dir() resolves MT_MEDIA_DIR live from the environment
# and falls back to `media/` relative to the server CWD. Test modules that
# forgot to override it therefore wrote REAL evidence files into the repo's
# server/media/ directory — which is how eight runtime artifacts (ev-case-*,
# ev-photo-*, ev-pdf-*, ev-counts-*.png) ended up committed to git despite
# .gitignore's explicit "server/media/ MUST NOT enter git" rule.
#
# A session temp dir is set here, BEFORE any test module import, so a missing
# per-test override can never touch the working tree again. Tests that want
# their own directory still override via monkeypatch/os.environ
# (see test_api.py, test_media_store.py) and are unaffected.
# ─────────────────────────────────────────────────────────────────────────────
_TMP_ROOT = tempfile.mkdtemp(prefix="magneetar-test-")
atexit.register(shutil.rmtree, _TMP_ROOT, True)
os.environ["MT_MEDIA_DIR"] = os.path.join(_TMP_ROOT, "media")
