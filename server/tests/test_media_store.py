"""
Media Store Tests
────────────────
Locks the v1.4 media storage refactor contract:
- bytes are stored on DISK (file_path/file_size), not in SQLite base64
- per-type size caps are enforced (413) BEFORE any decode
- magic-byte validation rejects mismatched content (415)
- path traversal / unsafe device ids are refused
- read-back, deletion, and legacy base64 fallback all work

IMPORTANT: this file must NOT mutate MT_* env at module level — the other
test modules share the single `config.settings`/`database.DB_PATH` singletons
and a module-level env set here poisons them when this file is imported
first in a run. All env lives in per-test monkeypatch, and the app-level
media upload E2E tests live in test_api.py (which owns the shared client).
"""

import base64
import os
import secrets
import tempfile

import pytest

# ── Env BEFORE importing media_store (which imports config) ────────────────
# All server test modules share the single config.settings singleton, bound at
# FIRST import. They deliberately use IDENTICAL dummy API key / JWT secret
# values so authentication stays consistent whichever module imports config
# first. Setting them here (before the import below) makes this file
# order-safe: a run that imports it first must not bind an empty API key.
# The DB path is per-file (rebound by each module, see the other test files).
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = _test_db_path

from media_store import (  # noqa: E402 (env must be set above)
    MAX_BYTES_BY_TYPE,
    MediaValidationError,
    delete_media_file,
    load_media,
    media_bytes_for_row,
    save_media,
    validate_media_data,
)

VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
VALID_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
VALID_MP3 = b"ID3\x04\x00\x00\x00" + b"\x00" * 100
VALID_M4A = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 100


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class TestValidation:
    def test_accepts_real_magic_bytes(self):
        assert validate_media_data("photo", _b64(VALID_PNG)) == VALID_PNG
        assert validate_media_data("photo", _b64(VALID_JPEG)) == VALID_JPEG
        assert validate_media_data("audio", _b64(VALID_MP3)) == VALID_MP3
        assert validate_media_data("audio", _b64(VALID_M4A)) == VALID_M4A

    def test_rejects_wrong_magic_for_declared_type(self):
        """A PNG payload declared as 'audio' must be refused (415) — the
        evidence chain must never hold mislabeled content."""
        with pytest.raises(MediaValidationError) as exc:
            validate_media_data("audio", _b64(VALID_PNG))
        assert exc.value.status_code == 415

    def test_rejects_unknown_type(self):
        with pytest.raises(MediaValidationError) as exc:
            validate_media_data("document", _b64(VALID_PNG))
        assert exc.value.status_code == 415

    def test_rejects_garbage_bytes(self):
        with pytest.raises(MediaValidationError) as exc:
            validate_media_data("photo", _b64(b"\x00\x01\x02\x03" * 10))
        assert exc.value.status_code == 415

    def test_rejects_invalid_base64(self):
        with pytest.raises(MediaValidationError) as exc:
            validate_media_data("photo", "!!!not-base64!!!")
        assert exc.value.status_code == 400

    def test_rejects_empty_payload(self):
        with pytest.raises(MediaValidationError):
            validate_media_data("photo", _b64(b""))

    @pytest.mark.parametrize("mtype", ["photo", "audio", "video"])
    def test_rejects_oversized_before_decode(self, mtype):
        """A payload over the type cap is rejected with 413 — and the length
        check must fire on the base64 string so no full decode happens."""
        cap = MAX_BYTES_BY_TYPE[mtype]
        huge = b"x" * (cap + 1)
        with pytest.raises(MediaValidationError) as exc:
            validate_media_data(mtype, _b64(huge))
        assert exc.value.status_code == 413

    def test_video_webm_magic(self):
        webm = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01" + b"\x00" * 50
        assert validate_media_data("video", _b64(webm)) == webm


class TestSaveLoadDelete:
    def test_save_writes_file_with_metadata(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MT_MEDIA_DIR", str(tmp_path))
        stored = save_media("media-test-dev-1", "photo", _b64(VALID_PNG))
        assert stored["file_path"].startswith("media-test-dev-1/")
        assert stored["file_size"] == len(VALID_PNG)
        assert stored["file_path"].endswith(".png")

        full = tmp_path / stored["file_path"]
        assert full.is_file()
        assert full.read_bytes() == VALID_PNG
        assert load_media(stored["file_path"]) == VALID_PNG

    def test_save_audio_extension_detection(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MT_MEDIA_DIR", str(tmp_path))
        mp3 = save_media("audio-dev-2", "audio", _b64(VALID_MP3))
        assert mp3["file_path"].endswith(".mp3")
        m4a = save_media("audio-dev-2", "audio", _b64(VALID_M4A))
        assert m4a["file_path"].endswith(".m4a")

    def test_delete_removes_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MT_MEDIA_DIR", str(tmp_path))
        stored = save_media("media-test-dev-2", "photo", _b64(VALID_JPEG))
        full = tmp_path / stored["file_path"]
        assert full.is_file()
        delete_media_file(stored["file_path"])
        assert not full.exists()
        # Deleting a missing file is a no-op, never an error.
        delete_media_file(stored["file_path"])

    def test_unsafe_device_id_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MT_MEDIA_DIR", str(tmp_path))
        with pytest.raises(ValueError):
            save_media("../../etc", "photo", _b64(VALID_PNG))
        with pytest.raises(ValueError):
            save_media("dev with spaces!", "photo", _b64(VALID_PNG))

    def test_path_traversal_load_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MT_MEDIA_DIR", str(tmp_path))
        with pytest.raises((ValueError, FileNotFoundError)):
            load_media("../../etc/passwd")

    def test_media_bytes_for_row_prefers_disk(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MT_MEDIA_DIR", str(tmp_path))
        stored = save_media("media-test-dev-3", "photo", _b64(VALID_PNG))
        row = {"file_path": stored["file_path"], "data_b64": _b64(b"legacy")}
        assert media_bytes_for_row(row) == VALID_PNG

    def test_media_bytes_for_row_falls_back_to_legacy_b64(self):
        row = {"file_path": None, "data_b64": _b64(VALID_JPEG)}
        assert media_bytes_for_row(row) == VALID_JPEG

    def test_media_bytes_for_row_missing_both_raises(self):
        with pytest.raises(FileNotFoundError):
            media_bytes_for_row({"file_path": None, "data_b64": ""})
