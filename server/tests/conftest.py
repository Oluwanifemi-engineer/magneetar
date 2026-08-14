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

import os

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
