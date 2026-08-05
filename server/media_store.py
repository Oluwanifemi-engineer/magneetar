"""
Magneetar Media Storage
────────────────────────
Stores evidence media (photos / audio / video) on DISK instead of as base64
blobs inside the SQLite `media.data_b64` column.

Why this exists:
- A photo/audio as base64 TEXT in SQLite grows the single-file DB into
  gigabytes within months, slows every write (single-writer lock), bloats
  backups, and forces `base64.b64decode` memory spikes on upload/read.
- Files on disk keep the DB small (metadata only), backups cheap, and the
  door open for object storage (S3/R2) later — the column stays for legacy
  rows and API compatibility.

Security & validation:
- Per-type SIZE CAPS: photo <= 15MB, audio <= 10MB, video <= 100MB. An
  oversized payload is rejected with 413 BEFORE it is decoded (the base64
  length is checked first, so a huge upload cannot spike memory).
- MAGIC-BYTE validation: a photo must actually start with JPEG/PNG/WebP
  magic, audio with MP3/MP4/M4A/OGG/WAV/AMR magic, video with an MP4/3GP
  `ftyp` box or WebM EBML header. This blocks polyglot/random payloads
  being stored as "evidence".
- PATH SAFETY: file names are server-generated UUIDs under a per-device
  directory; readers resolve paths strictly beneath the media root and
  reject absolute paths / `..` traversal outright (defense in depth).

Config: `MT_MEDIA_DIR` (default `media/`, resolved live from the
environment so tests can point it at a temp dir without import-order
games). In Docker the path is `/app/media` on the `magneetar-media`
persisted volume.
"""

import base64
import os
import re
import uuid

from config import settings

# ─── Per-type limits (bytes) ────────────────────────────────────────────────
MAX_PHOTO_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_VIDEO_BYTES = 100 * 1024 * 1024  # 100 MB

MAX_BYTES_BY_TYPE = {
    "photo": MAX_PHOTO_BYTES,
    "audio": MAX_AUDIO_BYTES,
    "video": MAX_VIDEO_BYTES,
}

# ─── Magic-byte signatures ──────────────────────────────────────────────────
# (label, bytes-prefix-or-checker). The checkers are small callables so the
# MP4 'ftyp' and WebP 'RIFF....WEBP' structures can be verified positionally.


def _starts_with(*prefixes: bytes):
    def check(data: bytes) -> bool:
        return any(data.startswith(p) for p in prefixes)

    return check


def _is_mp4_or_3gp(data: bytes) -> bool:
    """MP4/M4A/3GP containers start with a 4-byte size + 'ftyp' brand box."""
    return len(data) >= 12 and data[4:8] == b"ftyp"


def _is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def _is_wav(data: bytes) -> bool:
    return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE"


MAGIC_CHECKERS = {
    "photo": _starts_with(b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"),
    # WebP is RIFF-based but must not be confused with WAV — separate checker.
    "audio": lambda d: (
        _starts_with(b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"OggS", b"#!AMR")(d)
        or _is_mp4_or_3gp(d)
        or _is_wav(d)
    ),
    "video": lambda d: _is_mp4_or_3gp(d) or (len(d) >= 4 and d.startswith(b"\x1aE\xdf\xa3")),
}


# ─── Media root ─────────────────────────────────────────────────────────────


def get_media_dir() -> str:
    """Resolve the media root directory (live env override for tests)."""
    return os.environ.get("MT_MEDIA_DIR") or settings.MEDIA_DIR


def _ensure_root(root: str) -> str:
    """Create the media root (and its per-device subdir) if missing."""
    os.makedirs(root, exist_ok=True)
    return root


def _safe_device_dir(root: str, device_id: str) -> str:
    """Per-device directory under the root; device ids are validated by the
    DEVICE_ID_RE charset in routes/devices.py, so they are path-safe here too.
    Defense in depth: only [A-Za-z0-9_-] may ever appear in the path."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$", device_id):
        raise ValueError(f"Unsafe device id for media path: {device_id!r}")
    return os.path.join(root, device_id)


def _resolve(root: str, rel_path: str) -> str:
    """Resolve a stored relative path to an absolute path, refusing any
    traversal outside the media root (defense in depth — file names are
    server-generated UUIDs, so this only guards against DB tampering)."""
    if not rel_path:
        raise FileNotFoundError(rel_path)
    full = os.path.realpath(os.path.join(root, rel_path))
    root_real = os.path.realpath(root)
    if os.path.commonpath([root_real, full]) != root_real:
        raise ValueError(f"Media path escapes the media root: {rel_path!r}")
    return full


def _detect_extension(media_type: str, data: bytes) -> str:
    """Pick a file extension from the detected signature (or type default)."""
    if media_type == "photo":
        if data.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if data.startswith(b"\x89PNG"):
            return "png"
        if _is_webp(data):
            return "webp"
    if media_type == "audio":
        if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
            return "mp3"
        if data.startswith(b"OggS"):
            return "ogg"
        if data.startswith(b"#!AMR"):
            return "amr"
        if _is_wav(data):
            return "wav"
        return "m4a"  # ftyp container
    return "mp4"  # video ftyp / WebM


# ─── Validate + save ────────────────────────────────────────────────────────


class MediaValidationError(Exception):
    """Invalid media payload. `status_code` drives the HTTP error (413/415).

    # noqa: B042 — the status_code kwarg is intentionally NOT forwarded to
    # Exception.args: str(e) must stay the clean message (it becomes the API
    # `detail`), not a tuple repr.
    """

    def __init__(self, message: str, status_code: int = 415):  # noqa: B042
        super().__init__(message)
        self.status_code = status_code


def validate_media_data(media_type: str, data_b64: str) -> bytes:
    """Validate a base64 media payload WITHOUT trusting the caller.

    Returns the decoded bytes. Raises MediaValidationError with an
    appropriate HTTP status on failure:
      - 413 when the declared size (or decoded size) exceeds the type cap —
        checked against the base64 length FIRST so an oversized upload is
        rejected before any full decode happens in memory.
      - 415 when the magic bytes don't match the declared type.
    """
    if media_type not in MAX_BYTES_BY_TYPE:
        raise MediaValidationError(f"Unsupported media type: {media_type!r}", status_code=415)

    max_bytes = MAX_BYTES_BY_TYPE[media_type]
    # Base64 adds ~33% overhead; reject before decoding when clearly over.
    if len(data_b64) > (max_bytes * 4 // 3) + 16:
        raise MediaValidationError(
            f"Media too large: {media_type} exceeds {max_bytes // (1024 * 1024)}MB",
            status_code=413,
        )

    try:
        data = base64.b64decode(data_b64, validate=True)
    except Exception:
        raise MediaValidationError("Invalid base64 media payload", status_code=400)

    if len(data) > max_bytes:
        raise MediaValidationError(
            f"Media too large: {media_type} exceeds {max_bytes // (1024 * 1024)}MB",
            status_code=413,
        )
    if not data:
        raise MediaValidationError("Empty media payload", status_code=400)

    checker = MAGIC_CHECKERS.get(media_type)
    if checker and not checker(data):
        raise MediaValidationError(f"File content does not match declared type '{media_type}'", status_code=415)
    return data


def save_media(device_id: str, media_type: str, data_b64: str) -> dict:
    """Validate and persist a media payload to disk.

    Returns {"file_path": rel, "file_size": int} for the DB row. Raises
    MediaValidationError on invalid payloads.
    """
    data = validate_media_data(media_type, data_b64)
    root = _ensure_root(get_media_dir())
    device_dir = _safe_device_dir(root, device_id)
    os.makedirs(device_dir, exist_ok=True)

    ext = _detect_extension(media_type, data)
    filename = f"{uuid.uuid4().hex}.{ext}"
    rel_path = os.path.join(device_id, filename)
    full = _resolve(root, rel_path)

    with open(full, "wb") as f:
        f.write(data)

    return {"file_path": rel_path, "file_size": len(data)}


def load_media(rel_path: str) -> bytes:
    """Read a stored media file's bytes (for API/PDF read-back)."""
    root = get_media_dir()
    full = _resolve(root, rel_path)
    with open(full, "rb") as f:
        return f.read()


def load_media_b64(rel_path: str) -> str:
    """Read a stored media file and return it base64-encoded (the legacy
    wire format the dashboard/PDF consumers still speak)."""
    return base64.b64encode(load_media(rel_path)).decode("ascii")


def delete_media_file(rel_path) -> None:
    """Best-effort deletion of a stored media file. Missing files are fine
    (the DB row is the source of truth for list endpoints)."""
    if not rel_path:
        return
    try:
        full = _resolve(get_media_dir(), rel_path)
        if os.path.isfile(full):
            os.remove(full)
    except (OSError, ValueError):
        pass  # never crash a delete/cascade over a file glitch


def media_bytes_for_row(row) -> bytes:
    """Return the raw bytes of a media row: from disk (file_path set) or
    the legacy base64 column (pre-refactor rows)."""
    file_path = row["file_path"] if "file_path" in row.keys() else None
    if file_path:
        return load_media(file_path)
    data_b64 = row["data_b64"] if "data_b64" in row.keys() else ""
    if data_b64:
        return base64.b64decode(data_b64)
    raise FileNotFoundError("Media row has neither file_path nor data_b64")
