# Contributing to Shelfpass

Thank you for helping books reach people inside. There are two ways to contribute:

1. **Facility rules and rejection reports** go in the open dataset. No coding needed.
2. **Code, design and docs** go in the Django app.

Please never include names, ID numbers or other personal details of incarcerated people in
issues, pull requests, test data or screenshots. The demo data is entirely fictional; keep it that way.

## Facility rules (dataset)

Read [dataset/README.md](dataset/README.md). In short:

- One JSON file per facility in `dataset/facilities/<state>/`, validated by
  [`dataset/schema/dataset.schema.json`](dataset/schema/dataset.schema.json).
- Every rule needs a **source**: a published policy, an inmate handbook, a mailroom letter or
  a return slip. Set `last_verified` to the date you checked.
- Leave out anything you don't know. A missing rule means "unknown", not "allowed".
- Never rename a facility `id`.
- The easiest route is the *Suggest a correction* / *Contribute it* button on any facility
  page in Shelfpass. It opens GitHub with the file already filled in.

Validate locally with `make dataset`. CI runs the same check on every pull request.

## Code

### Setup

```bash
# needs https://docs.astral.sh/uv/
make install      # dependencies into .venv
make demo         # SQLite + fictional demo data on http://127.0.0.1:8000 (demo / shelfpass-demo)
```

Postgres is what production uses. To test against it:

```bash
export DATABASE_URL=postgres://shelfpass:shelfpass@localhost:5432/shelfpass
make test
```

### Before you open a pull request

```bash
make format   # ruff fix + format
make check    # lint, tests (coverage must stay ≥ 90%), dataset, migrations
```

- Add tests for behaviour changes. View tests live in `tests/test_views.py`, domain logic
  in `tests/test_services.py` and `tests/test_text_and_rules.py`.
- If you change models, run `uv run python manage.py makemigrations` and commit the migration.
- Add a line to `CHANGELOG.md` under **Unreleased**.
- Keep pages working without JavaScript. Scripts are progressive enhancement only.
- Group-owned data must always be filtered by `request.organization`.

### Project layout

| Path | What's there |
|---|---|
| `shelfpass/facilities/rules.py` | The rules engine: merging, badges and package checks |
| `shelfpass/facilities/dataset.py` | Dataset loading, validation, import and export |
| `shelfpass/shipping/services.py` | Package lifecycle (stock, statuses, returns) |
| `shelfpass/inventory/matching.py` | Shelf suggestions |
| `shelfpass/templates/` | All pages, including print layouts under `shipping/print/` |
| `shelfpass/core/static/shelfpass/` | CSS and JS (no build step, no CDN) |
| `dataset/` | The open dataset (CC BY-SA 4.0) |

## Releases

Maintainers: see [docs/releasing.md](docs/releasing.md).

## License of contributions

By contributing you agree that code is licensed under AGPL-3.0-or-later and dataset changes
under CC BY-SA 4.0.
