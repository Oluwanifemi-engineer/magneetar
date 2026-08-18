# Magneetar v1.4.4 — GitHub Release (owner web-UI step)

> Everything is staged. This is a **web-UI-only** step — no code, no CLI,
> no secrets. The notes and artifacts below are ready to paste/upload.

## Artifacts (already staged, checksums verified — **v1.4.4 build 15, includes G1-17**)

| File | Path | SHA-256 |
|---|---|---|
| Source tarball | `dist/magneetar-1.4.4-source.tar.gz` | `69dcd993bc1a6e616bac760d144ccc1b7622b35d615f4663cb301268b7913449` |
| Checksum file | `dist/magneetar-1.4.4-source.tar.gz.sha256` | — (contains the line above) |
| Play-clean APK (download page, `magneetar-v1.4.4-release.apk` / `magneetar-latest.apk`) | `server/static/apk/` | `c114984af8bd54f27bd60d0e6aa7974249c3eaca66aa41b72df664be89db8a00` |
| Play AAB (internal testing, versionCode 15) | `server/static/apk/magneetar-v1.4.4-play.aab` | `ba55ef7d1150bac87dfef1c013029dd77ed2eed7cbf5b76cd15eda783842f433` |
| Sideload APK (SMS-capable, archived) | `server/static/apk/magneetar-v1.4.4-sideload-release.apk` | `b4eb1258c6aa82c6989b281b604f271980b6fd7b0885b14d454cf685aaa2a629` |

> G1-17 (2026-08-18): location MODE detection + heartbeat reporting (server
> persists `location_mode`), once-per-24h degraded-mode nudge, Wi-Fi RTT
> (802.11mc) indoor ranging, dashboard road-snapping (display-only) — see
> `docs/location-accuracy-research.md`. Live-verified: `/apk/checksum` =
> `c114984a…` (0 SMS perms, versionCode 15), `/apk/source/checksum` =
> `69dcd993…`. Source tarball integrity re-scanned clean (no backups/DBs/
> credentials — the make-source-tarball.sh strip list was hardened after a
> leak was caught in a draft build).

Upload the **source tarball + its .sha256** to the release (the APK/AAB live on
the product site and Play — don't duplicate them here; the release is the
source-transparency artifact per the "open source, release tarball" model).

## Steps (github.com → your repo → Releases)

1. **Releases → Draft a new release** (or New release).
2. **Tag:** `v1.4.4` (create on push or existing — pick the current `main`
   commit `1b9bd70` / whatever is HEAD at upload time).
3. **Target:** `main`.
4. **Title:** `v1.4.4 — armed evidence capture, bounded theft reactions, trigger-first audio`
5. **Notes:** paste `docs/release-notes-1.4.4.md` (the source doc is
   committed; the whole file is ready).
6. **Attach binaries:** drag in
   - `dist/magneetar-1.4.4-source.tar.gz`
   - `dist/magneetar-1.4.4-source.tar.gz.sha256`
7. **Set as pre-release?** NO for a real release; the Play AAB is internal
   testing only, so a full public release tag is fine (the tarball contains
   no secrets — verified in the S-10 secret-history scan).
8. **Publish release.**

## Post-upload check (30 seconds)

```bash
# The tarball on GitHub must match the staged one byte-for-byte:
curl -sL https://github.com/<owner>/magneetar/releases/download/v1.4.4/magneetar-1.4.4-source.tar.gz | sha256sum
# expect: 75dafdd256b12ffdd022567ccc19eefa07f7e935eb9d68e1faa00afff5ce8507
```

## Notes

- **2026-08-16 re-stage:** the staged AAB was rebuilt to **versionCode 12**
  because the first AAB (v11, 15:23) predated the G1-11 trigger-first audio
  change — the Play upload would have shipped the old always-on-mic
  behavior. Rebuilt with all fixes (G1-8/9/10/11), verified zero SMS + zero
  accessibility. The download-page APK was ALSO re-staged to the play-clean
  build (it had regressed to the sideload flavor, which Play Protect
  hard-blocks — G1#1); the SMS-capable sideload APK stays archived.
- The release notes doc mentions checksums for the APK + source; the live
  `/apk/download` page serves the same APK hash (`29d71ee5…`) so the GitHub
  release and the product site agree.
- The Play AAB (versionCode 12) is the internal-testing upload — it is NOT a
  GitHub release artifact.
- If the repo is private (owner decision), the release link is
  invite-only — the tarball keeps its value for G1/G2 testers and
  transparency checks.
