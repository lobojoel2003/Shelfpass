# Shelfpass open dataset: prison book mail rules and rejections

This folder is a **crowd-maintained, machine-readable record of the rules US prisons and jails apply to book packages**, plus **anonymised reports of packages that were rejected**. Shelfpass imports it so every books-to-prisoners group sees the same rules. You can also use it on its own.

- **License:** [CC BY-SA 4.0](LICENSE). You can share and adapt it with attribution, and you must release changes under the same license. The Shelfpass app itself is AGPL-3.0.
- **Format:** one JSON file per record, validated against [`schema/dataset.schema.json`](schema/dataset.schema.json) (JSON Schema 2020-12).
- **Version:** see [`dataset.json`](dataset.json). The version is `YYYY.MM.N` and is bumped on release.

> [!IMPORTANT]
> Rules change without notice and differ from facility to facility. Treat every record as a starting point and check it against the facility's current policy. A record is only as good as its `sources` and `last_verified` date.

## Layout

```
dataset/
├── dataset.json                 # name, version, license
├── schema/dataset.schema.json   # JSON Schema for every file below
├── jurisdictions/               # system-wide rules (a state DOC, the federal BOP)
│   └── us-bop.json
├── facilities/<state>/          # one file per facility, folder = lowercase state code
│   └── pa/<facility-id>.json
├── rejections/                  # anonymised rejection reports, any number of files
└── sample/                      # FICTIONAL records used by the demo and the tests
    ├── jurisdictions/ facilities/ rejections/
```

Everything under `sample/` is invented and sets `"sample": true`. Shelfpass imports sample records only when asked to (`sync_dataset --include-samples` or `seed_demo`). Real records must never point at sample ones.

## Records

### Jurisdiction

A rule-setting authority. Its facilities inherit its rules.

```json
{
  "id": "us-bop",
  "name": "Federal Bureau of Prisons",
  "kind": "federal",
  "rules": { "hardcover_vendor_only": true, "notes": ["…"] },
  "sources": [{ "title": "28 CFR 540.71", "url": "https://www.ecfr.gov/…" }],
  "last_verified": "2026-11-01"
}
```

### Facility

```json
{
  "id": "pa-example-sci",
  "name": "SCI Example",
  "kind": "state-prison",
  "jurisdiction": "pa-doc",
  "address": { "street": ["1 Example Road"], "city": "Example", "state": "PA", "postal_code": "16000" },
  "rules": { "max_books_per_package": 5 },
  "sources": [{ "title": "Facility handbook, p. 12", "url": "https://…", "accessed": "2026-11-01" }],
  "last_verified": "2026-11-01"
}
```

A facility's `rules` override its jurisdiction's. `notes`, `banned_content` and `banned_titles` **add to** the jurisdiction's lists. Set `"active": false` when a facility closes. Never delete the file, because groups may still have history there.

### Rules

| Key | Type | Meaning |
| --- | --- | --- |
| `books_accepted` | bool | `false` if the facility refuses all book packages |
| `paperback_only` | bool | No hardcover or spiral-bound books |
| `new_only` | bool | Used books are refused |
| `vendor_only` | bool | Books must ship directly from a publisher or approved vendor |
| `hardcover_vendor_only` | bool | Hardcovers must come from a publisher, bookstore or book club |
| `approved_vendors` | string[] | Named vendors, when the facility lists them |
| `invoice_required` | bool | An invoice or receipt must be enclosed |
| `max_books_per_package` | int | Most books allowed in one package |
| `max_package_weight_lb` | number | Weight limit per package |
| `banned_content` | category[] | Content categories that are restricted (see schema `content_category`) |
| `banned_titles` | object[] | `{title, author?, isbn?, note?}` for specifically banned books |
| `notes` | string[] | Anything else, one rule per line |
| `recipient_format` | string | How to write the recipient line, using `{name}`, `{id}`, `{housing}` |
| `book_mail_address` | string[] | Central processing address for books, if different from the facility |

**Leave out anything you don't know.** A missing key means "unknown". It does not mean "allowed".

### Rejection reports

```json
{
  "reporter": "Example Books to Prisoners",
  "license": "CC-BY-SA-4.0",
  "reports": [
    {
      "facility": "pa-example-sci",
      "month": "2026-08",
      "reason": "hardcover",
      "book": { "title": "A Game of Thrones", "format": "hardcover", "condition": "used" },
      "detail": "Stamped: HARDCOVER NOT PERMITTED"
    }
  ]
}
```

Reports have **month precision only** and **must never contain names, ID numbers or housing details**. Shelfpass produces this file for you:

```bash
python manage.py export_rejections --reporter "Your group" -o dataset/rejections/your-group-2026-11.json
```

It also serves the same data at `/facilities/data/rejections.json`. The export includes only groups that opted in, and only facilities that exist in this dataset.

## Contributing

1. **Find a source.** Use the facility's or department's published mail policy, an inmate handbook, a letter from the mailroom, or a return slip. Link to it in `sources` and record when you checked it in `accessed` and `last_verified`.
2. **Edit or add the file.** In Shelfpass, a facility page has a *Suggest a correction* or *Contribute it* button. It opens GitHub with the JSON already filled in. You can also edit files by hand.
3. **Validate locally** (optional, CI does it too):
   ```bash
   python manage.py sync_dataset --check
   ```
4. **Open a pull request.** Say what changed and why. One facility per pull request is easiest to review.

Reviewers check that every rule has a source, that `id`s are stable (never rename one), and that no personal information is included.

## Using the data elsewhere

Every file is plain JSON, so any language can read it. To read everything at once, download the `shelfpass-dataset-<version>.zip` bundle attached to each [GitHub release](https://github.com/lobojoel2003/Shelfpass/releases). It contains `facilities.json`, `jurisdictions.json` and `rejections.json` (merged, samples excluded) alongside the raw files.
