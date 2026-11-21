<div align="center">

<img src="docs/images/wordmark.svg" alt="Shelfpass" width="340">

### Request tracking for books-to-prisoners groups, with a shared, open dataset of prison mail rules.

[![CI](https://github.com/lobojoel2003/Shelfpass/actions/workflows/ci.yml/badge.svg)](https://github.com/lobojoel2003/Shelfpass/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/lobojoel2003/Shelfpass?sort=semver&color=1f5f4a)](https://github.com/lobojoel2003/Shelfpass/releases/latest)
[![CodeQL](https://github.com/lobojoel2003/Shelfpass/actions/workflows/codeql.yml/badge.svg)](https://github.com/lobojoel2003/Shelfpass/actions/workflows/codeql.yml)
[![Container](https://img.shields.io/badge/ghcr.io-shelfpass-1f5f4a?logo=docker&logoColor=white)](https://github.com/lobojoel2003/Shelfpass/pkgs/container/shelfpass)
<br>
[![App license: AGPL-3.0](https://img.shields.io/badge/app-AGPL--3.0-c8752a)](LICENSE)
[![Dataset license: CC BY-SA 4.0](https://img.shields.io/badge/dataset-CC%20BY--SA%204.0-c8752a)](dataset/LICENSE)
[![Python 3.12 | 3.13](https://img.shields.io/badge/python-3.12%20%7C%203.13-3776ab?logo=python&logoColor=white)](pyproject.toml)
[![Django 5.2 LTS](https://img.shields.io/badge/django-5.2%20LTS-0c4b33?logo=django&logoColor=white)](https://www.djangoproject.com/)

[Quick start](#quick-start) · [Features](#what-it-does) · [The open dataset](#the-open-dataset) · [Deploy](docs/deployment.md) · [Releases](#versions-builds-and-releases) · [Contribute](CONTRIBUTING.md)

<br>

<img src="docs/images/request.png" alt="A letter from Marcus asking for a GED guide, The Hobbit and a Spanish dictionary. Shelfpass flags that the facility is paperback-only with no used books, warns The Hobbit was already sent in July, and suggests allowed books from the shelf." width="900">

</div>

---

## Why

Volunteer **books-to-prisoners** groups answer letters from incarcerated people who ask for books: a GED guide, a dictionary, a fantasy series. Every prison has different mail rules. Some accept paperbacks only. Some refuse used books. Some take books only from approved vendors, require an invoice, or ban certain content. A package that breaks a rule is marked *refused*, destroyed, or simply vanishes.

Most groups track requests in spreadsheets and pass mail rules around by word of mouth. The Women's Prison Book Project alone ships over 20,000 books a year to more than 30 states. Book Riot's [*Request Denied (Again)*](https://bookriot.com/navigating-prison-censorship-from-the-outside/) describes returns stamped "refused (no reason)" and "unauthorized sender". In Pennsylvania, central screening makes tracking a "black hole". [PEN America](https://pen.org/?p=11176) and [American Libraries](https://americanlibrariesmagazine.org/2016/10/31/freedom-of-reading-books-to-prisoners/) document how much the rules vary between facilities. The field's shared directory, the [National Prison Resource List](https://prisonbookprogram.org/wp-content/uploads/2024/04/NPRL-2024-4-1.pdf), is a PDF.

A few groups have written their own tools, such as [btp-lemur](https://github.com/wiltzius/btp-lemur) for inventory and private portals, but **no shared tool combines request tracking with a crowd-maintained, per-facility rules dataset.** Shelfpass does both.

## What it does

A volunteer types in a letter: the person's name and ID, the facility, and the books they asked for. Shelfpass then:

| | |
|---|---|
| **Shows the facility's rules as you type.** For example: "paperback only, no used books, max 3 per package, invoice required", along with the facility's notes and the correct mailing address (including central processing centres). | <img src="docs/images/intake.png" alt="Log a letter form with the facility rules panel and a returning-reader match" width="420"> |
| **Recognises returning readers** from their ID number and **warns when a book was already sent**, both while you type and on the request page. | |
| **Suggests what's on the shelf** for each request ("GED study guide" → *GED Test Prep Plus*). Books the facility would refuse are marked *Not allowed here* and sorted last. | <img src="docs/images/package.png" alt="Package page with a rule check and shipping form" width="420"> |
| **Checks every package before it ships.** It blocks hardcovers at paperback-only prisons, used books where only new are accepted, over-limit packages, banned titles and vendor-only rules. It warns about restricted content (maps, martial arts, RPGs …). Shipping despite a block requires a written reason. | |
| **Prints packing slips and labels in the right format.** Slips print on US Letter, with an *Invoice / Packing slip* header where an invoice is required. Labels print on 4×6 thermal stock with the facility's recipient-line format (`{name} #{id}` or `{name}, {id}, {housing}`) and *MEDIA MAIL* marking. | <img src="docs/images/slip.png" alt="Printed invoice / packing slip" width="420"> |
| **Logs returns with a reason.** Choose from *refused (no reason)*, *unauthorized sender*, *hardcover*, *used book*, *content*, *vanished* and more. Books go back on the shelf. | <img src="docs/images/label.png" alt="4x6 shipping label" width="420"> |
| **Shares rejection history across groups.** Every group sees each facility's returns, anonymised. Over time this becomes a public dataset of prison book censorship ([CSV / JSON export](#the-open-dataset)). | <img src="docs/images/facility.png" alt="Facility page with rules and rejection history" width="420"> |

It also includes a shelf inventory with [Open Library](https://openlibrary.org/developers/api) lookup by ISBN or title and CSV import/export, reader history, a multi-group team with coordinator and volunteer roles, a dashboard with the oldest waiting letters, and a full Django admin.

<details>
<summary><b>More screenshots</b></summary>

| Dashboard | Facility directory |
|---|---|
| <img src="docs/images/dashboard.png" alt="Dashboard"> | <img src="docs/images/facilities.png" alt="Facility directory with rule chips"> |
| **Rejection data** | **Shelf** |
| <img src="docs/images/rejections.png" alt="Public rejection data page"> | <img src="docs/images/shelf.png" alt="Shelf inventory"> |
| **Volunteer log in** | |
| <img src="docs/images/login.png" alt="Login page"> | |

</details>

## Quick start

### Try the demo with Docker

```bash
git clone https://github.com/lobojoel2003/Shelfpass.git && cd Shelfpass
cp .env.example .env
```

Set `SHELFPASS_SECRET_KEY` in `.env`, add `SHELFPASS_DEMO=1`, then:

```bash
docker compose up --build
```

Open <http://localhost:8000> and log in as **`demo` / `shelfpass-demo`**. Every person, group and facility in the demo is fictional.

### Run the released image

```bash
docker run -d --name shelfpass -p 8000:8000 \
  -e SHELFPASS_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
  -e DATABASE_URL=postgres://user:password@db-host:5432/shelfpass \
  -e SHELFPASS_ALLOWED_HOSTS=books.example.org \
  -e SHELFPASS_CSRF_TRUSTED_ORIGINS=https://books.example.org \
  ghcr.io/lobojoel2003/shelfpass:1
```

On start-up the container runs migrations and imports the bundled dataset. To create your group and first coordinator account:

```bash
docker exec -it -e SHELFPASS_BOOTSTRAP_PASSWORD='choose-a-long-password' shelfpass \
  shelfpass-entrypoint manage bootstrap_group --name "Riverside Books to Prisoners" --username alex --superuser
```

See **[docs/deployment.md](docs/deployment.md)** for HTTPS, backups, upgrades and every setting.

### Develop locally

You need [uv](https://docs.astral.sh/uv/). Postgres is optional; SQLite works out of the box.

```bash
make demo
```

This installs the dependencies, creates `db.sqlite3`, seeds the fictional demo and starts http://127.0.0.1:8000.

```bash
make test
```

The test suite has more than 90 tests with coverage above 95%. Set `DATABASE_URL=postgres://…` to run it against Postgres.

```bash
make check
```

This runs lint, format check, tests, dataset validation and the migrations check (everything CI does).

## How it works

```mermaid
flowchart LR
    L["✉️ Letter arrives"] --> I["Log the letter<br/><small>name · ID · facility · requests</small>"]
    I -->|rules + history live| R["Request page<br/><small>shelf suggestions<br/>already-sent warnings</small>"]
    R --> P["Package<br/><small>rule check</small>"]
    P -->|print| S["Slip + label"]
    S --> M(("📬 Mailroom"))
    M -->|delivered| D["Done"]
    M -->|refused / vanished| X["Log return<br/><small>reason + book</small>"]
    X --> H[("Shared rejection<br/>history")]
    H -.->|warns the next volunteer| I
    DS[("Open dataset<br/><small>facility rules</small>")] -.->|sync_dataset| I
    H -.->|export_rejections → PR| DS
```

| App | Responsibility |
|---|---|
| `shelfpass.orgs` | Groups, volunteers, coordinator/volunteer roles. Every group's data is isolated. |
| `shelfpass.facilities` | Jurisdictions and facilities (shared), the **rules engine** (`rules.py`), dataset import/export, rejection history |
| `shelfpass.correspondence` | People, letters (`BookRequest`) and requested items, reader history |
| `shelfpass.inventory` | The shelf, Open Library client, shelf matching |
| `shelfpass.shipping` | Packages, package items, returns, printing, and the package lifecycle (`services.py`) |
| `shelfpass.core` | Dashboard, health/version endpoints, templates, static files, demo seeding |

Rules are **layered**. A facility inherits its jurisdiction's rules (a state DOC, the federal BOP) and adds or overrides its own. The merged `RuleSet` drives the badges, shelf filtering, package checks and label format.

## The open dataset

[`dataset/`](dataset/) holds a **separately licensed (CC BY-SA 4.0)**, JSON-Schema-validated record of prison book mail rules and anonymised rejection reports:

```
dataset/
├── schema/dataset.schema.json      # validates every file
├── jurisdictions/us-bop.json       # system-wide rules, with sources
├── facilities/<state>/<id>.json    # one file per facility (contributions welcome!)
├── rejections/*.json               # anonymised, month-precision rejection reports
└── sample/                         # fictional records for the demo and tests
```

- **Edit by pull request.** Each facility page has *Suggest a correction* and *Contribute it* buttons that open GitHub with the JSON already filled in. CI validates every change against the schema.
- **Sync into any instance** with `python manage.py sync_dataset`. The container image does this on start.
- **Export your group's returns** for the public record with `python manage.py export_rejections` or `/facilities/data/rejections.json` / `.csv`. Groups opt in. Names, ID numbers and free-text notes are never included.
- **Download a bundle.** Every release attaches `shelfpass-dataset-<version>.zip` with merged `facilities.json`, `jurisdictions.json` and `rejections.json`.

> [!NOTE]
> v1.0.0 ships the schema, the tooling, one sourced federal record (28 CFR 540.71) and a fictional sample set. Real facility rules are added by volunteers with sources. See [dataset/README.md](dataset/README.md) to contribute.

## Configuration

All settings are environment variables. [`.env.example`](.env.example) lists every one. The most important:

| Variable | Default | Purpose |
|---|---|---|
| `SHELFPASS_SECRET_KEY` | — (required) | Django secret key |
| `DATABASE_URL` | SQLite file | `postgres://user:pass@host:5432/db` |
| `SHELFPASS_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated host names |
| `SHELFPASS_CSRF_TRUSTED_ORIGINS` | — | e.g. `https://books.example.org` |
| `SHELFPASS_HTTPS` / `SHELFPASS_SSL_REDIRECT` / `SHELFPASS_HSTS_SECONDS` | `1` / `0` / `0` | Cookie security, redirect and HSTS |
| `SHELFPASS_PUBLIC_DATA` | `1` | Facility pages and rejection data readable without logging in |
| `SHELFPASS_DATASET_DIR` | `./dataset` | Where `sync_dataset` reads from |
| `SHELFPASS_OPENLIBRARY_ENABLED` | `1` | Open Library book lookup |

## Versions, builds and releases

Shelfpass follows **[Semantic Versioning](https://semver.org/)**. Every running instance shows its version, build number and commit in the sidebar and at `/version.json` (also included in `/healthz`):

```json
{"version": "1.0.0", "build_number": "14", "commit": "3f2c9ab…", "label": "v1.0.0 · build 14 · 3f2c9ab"}
```

- **Version** comes from `shelfpass/__init__.py` and must match the git tag and a `CHANGELOG.md` section. CI enforces this with `scripts/check_version.py`.
- **Build number** is the commit count of the built revision (`git rev-list --count HEAD`), so it increases monotonically along `main`. It is baked into the image at build time.
- **Tags:** pushing `vX.Y.Z` runs the [release workflow](.github/workflows/release.yml). It runs the full CI pipeline, builds the wheel, sdist and dataset bundle, and pushes a multi-arch (amd64/arm64) image with build provenance attestation. Then it creates the GitHub Release with notes taken from the changelog and `SHA256SUMS.txt`.
- **Container tags:** `X.Y.Z`, `X.Y`, `X`, `latest` and `build-N` for releases. Every green push to `main` publishes `edge`, `sha-<commit>` and `X.Y.Z-build.N`.

| Workflow | Trigger | What it does |
|---|---|---|
| [CI](.github/workflows/ci.yml) | push, PR | ruff lint and format, `check --deploy`, migrations check, tests on Python 3.12 and 3.13 × Postgres 16 (plus SQLite), dataset validation and bundle, wheel smoke test, Docker build and container smoke test, `edge` image publish |
| [Release](.github/workflows/release.yml) | tag `v*` | version check → CI → artifacts → GHCR image with attestation → GitHub Release |
| [CodeQL](.github/workflows/codeql.yml) | push, PR, weekly | Static security analysis of Python, JavaScript and workflows |
| [Dependabot](.github/dependabot.yml) | weekly | uv, GitHub Actions and Docker base image updates |

Release steps for maintainers are in [docs/releasing.md](docs/releasing.md).

## Privacy and safety

Shelfpass stores personal data about incarcerated people, so:

- People, letters, packages and free-text notes are visible **only to the group that created them**. Tests cover tenant isolation.
- Public pages and exports contain **facility, month, reason and book only**: never names, ID numbers, housing or notes.
- Production defaults: secure cookies, `X-Frame-Options: DENY`, no-sniff, same-origin referrer policy, and HSTS and SSL redirect as settings. CodeQL scans every change.
- Please report vulnerabilities privately. See [SECURITY.md](SECURITY.md).

## Contributing

Contributions of every size are welcome, especially **facility rules with sources**. Start with [CONTRIBUTING.md](CONTRIBUTING.md). Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

- **Application code:** [GNU AGPL-3.0-or-later](LICENSE). If you run a modified Shelfpass for others, share your changes.
- **Dataset (`dataset/`):** [CC BY-SA 4.0](dataset/LICENSE).

Book data and covers come from [Open Library](https://openlibrary.org/), whose data is openly licensed. Facility rules are crowd-maintained and may be wrong or out of date, so always confirm with the facility before you ship.
