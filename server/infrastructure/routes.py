"""
Magneetar APK & Static Asset Routes (extracted from main.py — Phase 0).

Short-lived signed APK downloads, checksum verification, source tarball
distribution, and version check endpoint. These routes are app-level
(they depend on APP_VERSION and the JWT secret) but don't belong in the
domain layer — they serve the Android app's self-update mechanism.

Separated from main.py to:
- Reduce main.py from 1400+ lines to < 300
- Group related APK logic in one file
- Make the HMAC ticket signing testable in isolation
"""

import asyncio
import hashlib
import hmac
import os
import time

from config import settings
from database import check_rate_limit
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from logging_config import get_logger

logger = get_logger("magneetar")

router = APIRouter(tags=["APK Distribution"])

# ─── APK Download Gating (short-lived signed tickets) ───────────────────────
# /apk/download used to be anonymous: anyone could hotlink the binary and
# scrape the whole APK/CDN bandwidth. Downloads now require a short-lived
# HMAC-signed ticket minted by /apk/ticket (rate-limited per IP). The signing
# key is DERIVED FROM THE JWT SECRET, never MT_API_KEY — that key ships inside
# every APK, so using it would let anyone mint their own tickets.

APK_TICKET_TTL_SECONDS = 600  # 10 minutes — short enough that a leaked URL dies fast


def get_app_version() -> str:
    """Read project version from VERSION file (cached at import time)."""
    version_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")
    try:
        with open(version_path) as f:
            return f.read().strip()
    except Exception:
        return "1.0.0"


APP_VERSION = get_app_version()


# ─── APK Helper Functions ────────────────────────────────────────────────────


def _apk_download_page() -> str:
    """Where a browser lands when it follows a stale/expired download link.

    The download page re-mints a fresh ticket on load, so a dead link self-heals
    instead of dead-ending on a raw 403 JSON body. Configurable for self-hosters
    whose dashboard lives elsewhere; the trailing '/download' is the page that
    mints tickets (see dashboard/src/app/download/page.tsx).
    """
    base = settings.DASHBOARD_URL.strip().rstrip("/")
    # Defensive: an empty base degrades to a same-host relative redirect (a
    # 404 on the API host) rather than a malformed URL — never a crash.
    return base + "/download" if base else "/download"


def _apk_ticket_key() -> bytes:
    """HMAC key for APK download tickets (server-only JWT secret, domain-separated)."""
    return hmac.new(settings.JWT_SECRET.encode(), b"magneetar:apk-ticket:v1", hashlib.sha256).digest()


def _sign_apk_ticket(expires_epoch: int) -> str:
    """HMAC-SHA256 signature over 'download|<expires>'."""
    msg = f"download|{expires_epoch}".encode()
    return hmac.new(_apk_ticket_key(), msg, hashlib.sha256).hexdigest()


def _verify_apk_ticket(expires_epoch: int, sig: str) -> bool:
    """True when the signature matches AND the URL is still inside its TTL.

    The far-future check (expires - now <= TTL) makes a signed URL that was
    leaked from logs useless once its window closes — a stolen URL cannot be
    replayed for weeks by bumping nothing.
    """
    if not sig:
        return False
    now = int(time.time())
    expected = _sign_apk_ticket(expires_epoch)
    return hmac.compare_digest(expected, sig) and now <= expires_epoch and expires_epoch - now <= APK_TICKET_TTL_SECONDS


def _apk_ticket_sig_valid(expires_epoch: int, sig: str) -> bool:
    """True when the signature is GENUINE (constant-time compare), regardless
    of whether the window has lapsed. Used to tell a tampered/forged ticket
    (bad signature → 403) apart from a genuine-but-stale one (valid signature,
    expired window → 302 self-heal)."""
    if not sig:
        return False
    expected = _sign_apk_ticket(expires_epoch)
    return hmac.compare_digest(expected, sig)


# ─── APK Resolution (shared by /apk/download + /apk/checksum) ───────────────


def _apk_candidates():
    """APK paths in order of preference — a version bump never breaks a link."""
    apk_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "apk")
    yield os.path.join(apk_dir, f"magneetar-v{APP_VERSION}-release.apk")
    yield os.path.join(apk_dir, "magneetar-latest.apk")
    try:
        apks = sorted(
            (f for f in os.listdir(apk_dir) if f.endswith(".apk") and f.startswith("magneetar-")),
            key=lambda f: os.path.getmtime(os.path.join(apk_dir, f)),
            reverse=True,
        )
    except OSError:
        apks = []
    for name in apks:
        yield os.path.join(apk_dir, name)


def _resolve_apk():
    """Return the path of the APK that /apk/download would serve, or None."""
    for path in _apk_candidates():
        if os.path.exists(path):
            return path
    return None


def _sha256_file(path: str) -> str:
    """Streaming SHA-256 of a file without loading it into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# path -> (mtime, size, sha256) — invalidated when the file changes
_apk_checksum_cache: dict[str, tuple[int, int, str]] = {}


def _get_apk_checksum(path: str) -> tuple[str, int]:
    """(sha256, size_bytes) of an APK file, cached per (mtime, size) so
    repeated requests don't re-hash multi-MB files. Replaced files yield fresh
    digests. One stat feeds both the cache key and the reported size, so a
    checksum response can never pair a size from one version of a file with a
    hash from another."""
    stat = os.stat(path)
    cached = _apk_checksum_cache.get(path)
    if cached is not None and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2], stat.st_size
    digest = _sha256_file(path)
    _apk_checksum_cache[path] = (stat.st_mtime, stat.st_size, digest)
    return digest, stat.st_size


def _source_tarball_path():
    """Path of the source tarball for this release, or None."""
    apk_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "apk")
    # Version-pinned first (a release ships exactly one), then the pointer.
    for name in (f"magneetar-v{APP_VERSION}-source.tar.gz", "magneetar-source.tar.gz"):
        path = os.path.join(apk_dir, name)
        if os.path.exists(path):
            return path
    return None


# ─── APK Routes ──────────────────────────────────────────────────────────────


@router.get("/apk/ticket")
async def apk_ticket(request: Request):
    """Mint a short-lived signed download URL for the current release APK.

    Rate-limited per IP (20 tickets / 10 min) so the binary can't be scraped
    in bulk, while the landing page's download button just works for humans.
    """
    from infrastructure.middleware import extract_client_ip

    if _resolve_apk() is None:
        raise HTTPException(status_code=404, detail="APK not found on server")

    client_ip = extract_client_ip(request)

    if not check_rate_limit(f"apk_ticket:{client_ip}", "apk_ticket", 20, 10):
        raise HTTPException(status_code=429, detail="Too many download requests — try again shortly")

    from datetime import datetime, timezone

    expires = int(time.time()) + APK_TICKET_TTL_SECONDS
    sig = _sign_apk_ticket(expires)
    return {
        "url": f"/apk/download?expires={expires}&sig={sig}",
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
    }


@router.get("/apk/download")
async def download_apk(expires: int = 0, sig: str = ""):
    """Download the latest Magneetar release APK.

    Requires a short-lived signed ticket (?expires=<epoch>&sig=<hmac>) minted
    by /apk/ticket. A missing/expired ticket is redirected to the download
    page (302), which mints a fresh one — anonymous/hotlinked downloads never
    receive bytes.

    Resolves in order of preference so a version bump never breaks the link:
    1. magneetar-v{APP_VERSION}-release.apk  (the release built for this version)
    2. magneetar-latest.apk                  (the always-current pointer)
    3. the newest magneetar-*.apk on disk     (last resort)
    """
    if not sig:
        # A bare link (no ticket at all) is almost certainly a human clicking
        # the URL or a scraper probing — self-heal to the download page, which
        # mints a fresh ticket on load.
        return RedirectResponse(
            _apk_download_page(),
            status_code=302,
        )
    if not _apk_ticket_sig_valid(expires, sig):
        # A PRESENT but forged/tampered signature gets a clean 403 — this is
        # an attack probe or a corrupted link, and self-healing would just
        # mask it. Only genuine signatures may ever receive the self-heal
        # redirect or the bytes.
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired download link — mint a fresh one from the download page",
        )
    if not _verify_apk_ticket(expires, sig):
        # Genuine signature whose window lapsed (stale/expired link) — don't
        # dead-end on raw JSON: the download page mints a fresh ticket on
        # load, so bounce the browser there.
        return RedirectResponse(
            _apk_download_page(),
            status_code=302,
        )
    path = _resolve_apk()
    if path is None:
        raise HTTPException(status_code=404, detail="APK not found on server")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=f"Magneetar-v{APP_VERSION}-release.apk",
    )


@router.get("/apk/checksum")
async def apk_checksum():
    """SHA-256 checksum + size for the exact bytes /apk/download serves.

    Lets sideloaders verify a downloaded file byte-for-byte against the
    official build before installing. The hash is computed once per file
    change (cache keyed on mtime + size) so repeated hits stay cheap.
    """
    path = _resolve_apk()
    if path is None:
        raise HTTPException(status_code=404, detail="APK not found on server")

    digest, size_bytes = await asyncio.to_thread(_get_apk_checksum, path)

    return {
        # Same display name /apk/download hands the browser, so users can
        # match the file they saved against the checksum page 1:1.
        "filename": f"Magneetar-v{APP_VERSION}-release.apk",
        "version": APP_VERSION,
        "sha256": digest,
        "size_bytes": size_bytes,
    }


# ─── Source Tarball (per-release open source — repo is private) ─────────────


@router.get("/apk/source")
async def source_tarball():
    """Download the source of THIS release as a clean tarball.

    The git repo is private (commit diary not exposed), so "open source" is
    honored per-release: each tagged release ships its tree snapshot + SHA-256
    here, verifiable against the checksum below — the same way many security
    tools publish. No signed ticket needed: this is deliberately public.
    """
    path = _source_tarball_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Source tarball not found on server")
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=f"magneetar-v{APP_VERSION}-source.tar.gz",
    )


@router.get("/apk/source/checksum")
async def source_tarball_checksum():
    """SHA-256 + size for the exact tarball /apk/source serves."""
    path = _source_tarball_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Source tarball not found on server")
    digest, size_bytes = await asyncio.to_thread(_get_apk_checksum, path)
    return {
        "filename": f"magneetar-v{APP_VERSION}-source.tar.gz",
        "version": APP_VERSION,
        "sha256": digest,
        "size_bytes": size_bytes,
    }


# ─── APK Version Check (for background update checks) ─────────────────────


@router.get("/apk/version")
async def apk_version_check(
    current_version: str = Query("", description="Currently installed version"),
    build_type: str = Query("sideload", description="Build type: sideload or play"),
):
    """Check if a newer version is available.

    Used by the Android app's background update checker (WorkManager).
    Returns minimal info needed for the update decision:
    - latest_version: the current release version
    - update_available: true if current_version != latest_version
    - download_url: URL to download the update (with ticket)
    - sha256: checksum for verification
    - size_bytes: APK size for progress display
    - min_android_version: minimum supported Android SDK
    - release_notes: brief changelog (optional)
    """
    path = _resolve_apk()
    if path is None:
        return {
            "latest_version": APP_VERSION,
            "update_available": False,
            "error": "APK not found on server",
        }

    digest, size_bytes = await asyncio.to_thread(_get_apk_checksum, path)

    # Determine if update is available (semantic version comparison)
    def _parse_ver(v: str):
        try:
            return tuple(int(x) for x in v.split(".")[:3])
        except (ValueError, AttributeError):
            return (0,)

    try:
        update_available = current_version != "" and _parse_ver(APP_VERSION) > _parse_ver(current_version)
    except Exception:
        # Fallback: string inequality (conservative — may show false positive)
        update_available = current_version != APP_VERSION and current_version != ""

    # Generate a download URL (the app will need to fetch a ticket first)
    download_url = "/apk/ticket"  # App fetches ticket from here

    return {
        "latest_version": APP_VERSION,
        "update_available": update_available,
        "download_url": download_url,
        "sha256": digest,
        "size_bytes": size_bytes,
        "filename": f"Magneetar-v{APP_VERSION}-release.apk",
        "build_type": build_type,
        "min_android_version": 24,  # minSdk = 24 (Android 7.0)
        "release_notes": "",  # Can be populated from CHANGELOG.md
    }
