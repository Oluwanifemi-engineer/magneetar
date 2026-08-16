# Magneetar v1.4.4 — GitHub Release (owner web-UI step)

> Everything is staged. This is a **web-UI-only** step — no code, no CLI,
> no secrets. The notes and artifacts below are ready to paste/upload.

## Artifacts (already staged, checksums verified)

| File | Path | SHA-256 |
|---|---|---|
| Source tarball | `dist/magneetar-1.4.4-source.tar.gz` (1,426,805 B) | `3afe76e4065dbac0bff6a2f3142b1367c93b278913287927eac8bcca6a96789d` |
| Checksum file | `dist/magneetar-1.4.4-source.tar.gz.sha256` | — (contains the line above) |
| Sideload APK (reference) | `server/static/apk/magneetar-v1.4.4-release.apk` | `8639606a07e95a92e747820b597f9458abd79c95eeaab09117eb382adbf39b29` |
| Play AAB (reference, internal testing) | `server/static/apk/magneetar-v1.4.4-play.aab` | `6510cf4174769abe0278bdedebf6c052b897c02865f994b776da752f8fbd566f` |

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
# expect: 3afe76e4065dbac0bff6a2f3142b1367c93b278913287927eac8bcca6a96789d
```

## Notes

- The release notes doc mentions checksums for the APK + source; the live
  `/apk/download` page serves the same APK hash (`8639606a…`) so the GitHub
  release and the product site agree.
- The Play AAB (versionCode 11) is the internal-testing upload — it is NOT a
  GitHub release artifact.
- If the repo is private (owner decision), the release link is
  invite-only — the tarball keeps its value for G1/G2 testers and
  transparency checks.
