# Commit Guidelines

Magneetar is a security product with a **public repository**. Every commit
message is read by the same audience as the source code: anyone. The commit
log is a live diary of our security posture — including the window between
"fix committed" and "fix deployed". Treat commit messages as **public
OPSEC material**, not internal notes.

## The one rule

> If you would not paste the message into a forum thread titled "how to
> attack Magneetar", it does not go in a commit message.

## Never include (operational detail)

| Category | Examples that have leaked before |
|---|---|
| Signing material | Signing key IDs (`024cbb34…`), cert SHA-1s (`13d2edc7…`), keystore names, keystore paths |
| Build metadata | `versionCode`, AAB/APK sizes, exact byte counts of artifacts |
| Live identifiers | Real device IDs (`mt-9be468c1`), account emails, phone numbers, FCM tokens |
| Deploy timing | "not yet deployed", "deploys at 20:00", commit→deploy windows, prod container restarts |
| Permission profiles | Which flavor carries which permission — that map is the Play-rejection and attack playbook |
| Internal architecture specifics | ADR implementation details, rate-limit exact values, authz decision tables (the *code* is public anyway — the message adds nothing but a searchable index) |
| Credential material | Any token, DSN, API key, or even a truncated form of one — if it looks like a secret, it is one |

## Keep

- **What + why**, at the code level: `fix: false teleport alerts — sentinel
  treated meters as km` is perfect.
- **S-IDs / G1-IDs / tracker references**: the S-ID workflow is our audit
  trail and stays. Reference the ID, not the implementation.
- **Test evidence at the suite level**: "89/89 Android unit tests pass, 554
  server tests pass" — fine. Not: which exact APK bytes were staged.
- A short body with root cause + fix. Two to six lines is ideal.

## Style

- Conventional Commits prefix: `feat(scope)`, `fix(scope)`, `security(scope)`,
  `docs`, `test`, `chore`, `ops(deploy)`.
- Imperative mood, lowercase after the prefix.
- One logical change per commit.

## Workflow

1. Run the project's commit template so the checklist is in front of you:
   `git config commit.template .gitmessage`
2. Before committing, re-read the message through the OPSEC lens above.
3. Never `git commit --amend` or rewrite messages after push (history rewrite
   on a public repo breaks the tracker trail).

## If in doubt

Two safe defaults:

- **Commit the code, put the detail in the tracker.** `docs/g1-validation-tracker.md`
  is private-ish by nature of being a single file you control; the commit log
  is public forever.
- **When a message needs operational detail to make sense, drop the detail,
  not the S-ID.** `security(api): gate sms_relay_number behind device auth (S-11)`
  is complete without the number.
