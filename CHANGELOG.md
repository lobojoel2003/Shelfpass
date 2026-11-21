# Changelog

All notable changes to Shelfpass are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The open dataset in `dataset/` is versioned separately (`YYYY.MM.N`, see
`dataset/dataset.json`).

## [Unreleased]

## [1.0.0] - 2026-11-21

The first public release.

### Added

- **Letter intake**: one form for the reader's name, ID number, facility, unit and every
  book or topic they asked for. The facility's mail rules, recent rejections and the correct
  recipient-line format appear as soon as a facility is chosen.
- **Returning readers** are recognised by ID number. Their history is shown during
  intake, and transfers update their current facility.
- **"Already sent" warnings** while typing, on the request page and on packages.
- **Shelf suggestions** for every requested title or topic (for example "GED study guide" or
  "a dictionary"), ranked by title, author, keyword and shelf category. Books the facility
  would refuse are marked *Not allowed here*.
- **Rules engine** with layered jurisdiction and facility rules: books accepted,
  paperback only, new only, vendor only, hardcovers from vendors only, invoice required,
  per-package book and weight limits, restricted content categories, banned titles,
  notes, recipient-line format and central book-processing addresses.
- **Packages**: pack from the shelf or record vendor orders, check against the
  facility's rules (blocking problems need a written override), and track shipping,
  delivery, returns and vanished packages. Stock levels update automatically.
- **Printing**: US Letter packing slips (*Invoice / Packing slip* where required),
  4×6 shipping labels with *Media Mail* marking, and batch printing for everything being packed.
- **Returns and rejection history**: 13 standard rejection reasons, shared across groups
  (anonymised) on every facility page, a public rejection-data page, and CSV/JSON exports.
- **Open dataset** (`dataset/`, CC BY-SA 4.0): JSON Schema, a sourced federal
  record (28 CFR 540.71), fictional sample facilities, `sync_dataset` import,
  one-click *Suggest a correction* / *Contribute it* links that open a pre-filled GitHub
  pull request, and `export_rejections` for contributing rejection reports.
- **Shelf inventory** with Open Library lookup by ISBN or title, content flags and
  CSV import/export.
- **Groups and volunteers**: multiple groups per instance with strict data isolation,
  coordinator and volunteer roles, team management and group settings.
- Dashboard, people directory, request and package lists, Django admin.
- `/healthz` and `/version.json` endpoints. Version, build number and commit are shown in the UI.
- Management commands: `sync_dataset`, `export_rejections`, `bootstrap_group`, `seed_demo`.
- Container image (Python 3.13, gunicorn, whitenoise) that runs as a non-root user and
  includes a health check. Docker Compose stack with Postgres 16.
- CI: lint, formatting, Django deploy checks, tests on Python 3.12 and 3.13 against
  Postgres 16 and SQLite, dataset validation, package and container smoke tests,
  `edge` images from `main`. Tag-driven release workflow publishing multi-arch
  images with build provenance, Python packages, dataset bundle and checksums. CodeQL and Dependabot.

[Unreleased]: https://github.com/lobojoel2003/Shelfpass/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lobojoel2003/Shelfpass/releases/tag/v1.0.0
