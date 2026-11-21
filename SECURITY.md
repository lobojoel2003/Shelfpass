# Security policy

Shelfpass stores personal information about incarcerated people. Please treat security issues seriously and privately.

## Reporting a vulnerability

**Do not open a public issue.** Report it through
[GitHub private vulnerability reporting](https://github.com/lobojoel2003/Shelfpass/security/advisories/new).
Include steps to reproduce and the version shown in the app's sidebar (or `/version.json`).

You should get a reply within a week. Fixes are released as patch versions and announced
in the release notes once groups have had a chance to upgrade.

## Supported versions

| Version | Supported |
|---|---|
| 1.x (latest minor) | ✅ |
| < 1.0 | ❌ |

## Hardening checklist for operators

- Serve over HTTPS only. Set `SHELFPASS_SSL_REDIRECT=1`, `SHELFPASS_HSTS_SECONDS`, and
  `SHELFPASS_CSRF_TRUSTED_ORIGINS`.
- Use a long random `SHELFPASS_SECRET_KEY` and keep it out of version control.
- Give each volunteer their own account, and remove people who leave the group.
- Back up the database, and encrypt the backups.
- Keep the container image up to date. `ghcr.io/lobojoel2003/shelfpass:1` follows the
  latest 1.x release.
