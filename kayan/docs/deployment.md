# Deployment

## 1. Containers

`infrastructure/docker-compose.yml` starts four services:

| Service | Image / build | Port | Purpose |
| --- | --- | --- | --- |
| `db` | `postgres:16-alpine` | internal 5432 | Database with a named volume `kayan_pgdata` |
| `api` | `backend/Dockerfile` | internal 8000 | FastAPI + Uvicorn (2 workers), runs migrations before serving |
| `web` | `infrastructure/web.Dockerfile` | internal 80 | Flutter web build served by Nginx |
| `edge` | `nginx:1.27-alpine` | `${HTTP_PORT:-8080}` | Reverse proxy: `/` → web, `/api`, `/docs`, `/health` → api |

```bash
cp infrastructure/.env.example .env      # then edit the secrets
docker compose -f infrastructure/docker-compose.yml up --build -d
docker compose -f infrastructure/docker-compose.yml logs -f api
```

Health checks are declared for `db` (`pg_isready`), `api` (`/health`) and the edge proxy, and
`api` waits for `db` before starting.

## 2. Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` disables the demo seed and enforces secret validation |
| `DEBUG` | `false` | Never enable in production |
| `HTTP_PORT` | `8080` | Published port of the edge proxy |
| `DATABASE_URL` | `sqlite:///./kayan_dev.db` | Compose injects `postgresql+psycopg://…` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `kayan` / `kayan` / — | Database credentials |
| `SECRET_KEY` | — | **Must** be a long random string in production |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `14` | |
| `PASSWORD_MIN_LENGTH`, `LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`, `BCRYPT_ROUNDS` | `8`, `5`, `15`, `12` | |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `600` | |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | `20` | |
| `CORS_ORIGINS` | `*` | Set the real origin(s) in production |
| `CORS_ALLOW_CREDENTIALS` | `true` | |
| `STORAGE_DIR` | `./storage` | Attachments; mount a volume |
| `MAX_UPLOAD_SIZE_MB` | `25` | |
| `ALLOWED_UPLOAD_EXTENSIONS` | `pdf,jpg,…,zip` | |
| `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, `BACKUP_SCHEDULE_CRON` | `./backups`, `14`, `0 2 * * *` | |
| `SEED_DEMO_DATA` | `false` | Development/demo only |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` | `admin@kayan.local`, `Admin@12345` | First administrator; rotate immediately |
| `API_BASE_URL` | `/api/v1` | Injected into the Flutter web build as `--dart-define` |

Secrets are never committed: `.env` is git-ignored, `.env.example` holds placeholders only,
and `SECRET_KEY` must be overridden outside development.

## 3. Deploying an update

```bash
git pull
docker compose -f infrastructure/docker-compose.yml build
docker compose -f infrastructure/docker-compose.yml run --rm api alembic upgrade head
docker compose -f infrastructure/docker-compose.yml up -d
```

The API container applies migrations on start as well, so the explicit `run` step is a
safety net when you want migrations to complete before any worker serves traffic
(zero-downtime ordering: migrate → start new API → reload edge → retire old API).

## 4. TLS and the edge proxy

`infrastructure/nginx.conf` terminates HTTP, sets security headers (HSTS, `X-Content-Type-Options`,
`X-Frame-Options`, referrer policy), gzips JSON/JS/CSS, proxies `/api` and `/health` to the
API with `X-Forwarded-*` headers, and serves the Flutter web build with a SPA fallback.

For public deployments put TLS in front of the edge (a load balancer, Cloudflare, or a
certbot sidecar) and forward `X-Forwarded-Proto`; the API trusts the forwarded scheme for
absolute download URLs.

## 5. Backups

| Layer | Mechanism |
| --- | --- |
| Database | `pg_dump` (scheduled by the platform or by `BACKUP_SCHEDULE_CRON` inside the app's backup service) |
| Application backups | `/data-tools/backup` creates a verified logical backup (checksum + row counts); `/data-tools/backup/{id}/verify` re-checks it; `/download` fetches it; `/restore-instructions` returns the exact restore procedure |
| Attachments | Mount `STORAGE_DIR` on persistent storage and include it in the volume snapshot |
| Retention | `BACKUP_RETENTION_DAYS` prunes old artefacts; pruning is audited |

Restore procedure (also returned by the API):

1. Stop the API and any worker: `docker compose stop api`.
2. Restore the database: `pg_restore -d kayan --clean --if-exists backup.dump` (or
   `psql -f backup.sql`).
3. Restore attachments into `STORAGE_DIR` from the snapshot.
4. Start the API, then verify: `/health/ready`, `GET /api/v1/version`, log in and run
   `GET /reports/run/trial_balance` — debits must equal credits.

## 6. Production checklist

- [ ] `SECRET_KEY` is a unique 64+ character random value; `DEBUG=false`; `ENVIRONMENT=production`
- [ ] `SEED_DEMO_DATA=false`; the bootstrap administrator password rotated on first login
- [ ] `CORS_ORIGINS` lists the real web origin(s) only
- [ ] TLS terminated in front of the edge proxy, HTTP redirected to HTTPS
- [ ] PostgreSQL not published outside the compose network; dedicated database user
- [ ] `STORAGE_DIR` and `BACKUP_DIR` on persistent, snapshotted volumes
- [ ] Rate limits sized for the tenant; login limit kept strict
- [ ] Migrations applied and verified (`alembic current` equals `alembic heads`)
- [ ] Backups running on schedule and a restore rehearsed at least once
- [ ] Logs collected (`X-Request-Id` is present on every response for correlation)
- [ ] Monitoring on `/health` and `/health/ready`
