# Deploying Shelfpass

Shelfpass is a standard Django app packaged as a container image. A small group can run it on a $5–10/month VPS or any container platform (Fly.io, Render, Railway, a Kubernetes cluster) with a managed Postgres database.

## What you need

- PostgreSQL 14 or newer. SQLite works for trying things out, but use Postgres for real data.
- A domain name with HTTPS, terminated by your platform or a reverse proxy such as Caddy or nginx.
- The image `ghcr.io/lobojoel2003/shelfpass:<version>`. Pin a version (`1.0.0`) or follow a
  release line (`1.0` for patches only, `1` for minor releases too).

## Docker Compose on a single server

```bash
git clone https://github.com/lobojoel2003/Shelfpass.git && cd Shelfpass
cp .env.example .env
```

Edit `.env`:

```dotenv
SHELFPASS_SECRET_KEY=<python -c 'import secrets; print(secrets.token_urlsafe(50))'>
SHELFPASS_ALLOWED_HOSTS=books.example.org
SHELFPASS_CSRF_TRUSTED_ORIGINS=https://books.example.org
SHELFPASS_HTTPS=1
SHELFPASS_SSL_REDIRECT=1
SHELFPASS_HSTS_SECONDS=31536000
POSTGRES_PASSWORD=<another long random string>
SHELFPASS_TAG=1            # image tag to run
```

Start the stack without building locally:

```bash
docker compose pull web && docker compose up -d --no-build
```

Create your group and first coordinator:

```bash
docker compose exec -e SHELFPASS_BOOTSTRAP_PASSWORD='a-long-password' web \
  shelfpass-entrypoint manage bootstrap_group \
  --name "Riverside Books to Prisoners" \
  --return-address "Riverside Books to Prisoners\nPO Box 4410\nRiverside, PA 15000" \
  --username alex --email alex@example.org --superuser
```

Put a TLS-terminating proxy in front of port 8000. With Caddy, this is all it takes:

```caddyfile
books.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

The image sets `SHELFPASS_BEHIND_PROXY=1`, so Django trusts `X-Forwarded-Proto` from the proxy.

## What the container does on start

| Variable | Default | Effect |
|---|---|---|
| `SHELFPASS_MIGRATE` | `1` | Runs `manage.py migrate` |
| `SHELFPASS_SYNC_DATASET` | `1` | Imports the bundled `dataset/` (facility rules and rejection reports) |
| `SHELFPASS_DEMO` | `0` | Loads fictional demo data (published password, so **never in production**) |
| `WEB_CONCURRENCY` | `3` | gunicorn workers |
| `PORT` | `8000` | Listen port |

Other entrypoint commands:

```bash
docker run --rm --env-file .env ghcr.io/lobojoel2003/shelfpass:1 manage check --deploy
docker compose exec web shelfpass-entrypoint manage export_rejections --reporter "Our group"
```

The image has a `HEALTHCHECK` on `/healthz`, which returns `503` if the database is unreachable. Use the same path for load-balancer checks.

## Upgrading

```bash
docker compose pull web && docker compose up -d --no-build
```

Migrations and the dataset sync run automatically. Read the release notes for anything marked **Breaking**. Breaking changes only happen in major versions.

## Backups

All state is in Postgres. A nightly dump is enough for most groups:

```bash
docker compose exec -T db pg_dump -U shelfpass -Fc shelfpass > shelfpass-$(date +%F).dump
```

The database contains personal information about incarcerated people. **Encrypt backups** and limit who can read them.

## Without Docker

```bash
pip install shelfpass-1.0.0-py3-none-any.whl     # from the GitHub release
export DJANGO_SETTINGS_MODULE=shelfpass.settings SHELFPASS_SECRET_KEY=… DATABASE_URL=…
export SHELFPASS_STATIC_ROOT=/srv/shelfpass/static SHELFPASS_DATASET_DIR=/srv/shelfpass/dataset
django-admin collectstatic --noinput
django-admin migrate
django-admin sync_dataset
gunicorn shelfpass.wsgi:application --bind 127.0.0.1:8000
```

Unzip the dataset bundle from the release into `SHELFPASS_DATASET_DIR` (use its `raw/` folder).

## All settings

See [`.env.example`](../.env.example). Every setting has a safe default except `SHELFPASS_SECRET_KEY`, which is required whenever `SHELFPASS_DEBUG` is off.
