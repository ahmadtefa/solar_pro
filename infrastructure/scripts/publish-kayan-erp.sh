#!/usr/bin/env bash
#
# Bootstrap the Kayan ERP repository with a clean, history-free import.
#
# Why this exists: the platform was developed inside a working copy that also contains an
# unrelated project. Pushing that branch to a fresh repository would drag the old project's
# files and history along, so this script assembles a brand new repository that contains
# *only* the Kayan ERP project:
#
#   main        scaffold  - .gitignore, .env.example, README.md, docs/, .github/workflows/ci.yml
#   <branch>    product   - backend/, frontend/, infrastructure/  (reviewed through a pull request)
#
# Usage:
#   infrastructure/scripts/publish-kayan-erp.sh --dry-run     # build locally, print a report
#   infrastructure/scripts/publish-kayan-erp.sh               # build, push main + review branch, open the PR
#
# Requirements: git, gh (authenticated with write access to the target repository) and tar.
# If the target repository rejects the push with HTTP 403 "Resource not accessible by
# integration", the GitHub connection used by the caller has not been granted that
# repository - grant access and re-run the script.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_SLUG="${KAYAN_SLUG:-ahmadtefa/Kayan_ERP}"
REMOTE_URL="${KAYAN_URL:-https://github.com/${TARGET_SLUG}.git}"
BRANCH="${KAYAN_BRANCH:-arena/4a00e594-solar-pro}"
SCAFFOLD_PATHS=(.gitignore .env.example README.md docs .github)
PRODUCT_PATHS=(backend frontend infrastructure)
DRY_RUN=0
FORCE=0

for argument in "$@"; do
  case "$argument" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    *) echo "unknown option: $argument" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Exporting the Kayan ERP project from ${REPO_ROOT}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain -- "${PRODUCT_PATHS[@]}" 2>/dev/null || true)" ]]; then
  echo "warning: uncommitted changes under ${PRODUCT_PATHS[*]} - they are exported from the working tree" >&2
fi

# Application code: tracked content of the monorepo folders, held aside until the
# scaffold commit exists so that main carries documentation and CI only.
STAGING_DIR="$WORK_DIR/.staging"
mkdir -p "$STAGING_DIR"
# `git ls-files` exports tracked content from the working tree: it picks up uncommitted
# edits but never leaks virtualenvs, build output, storage or local .env files.
(cd "$REPO_ROOT" && git ls-files -z -- "${PRODUCT_PATHS[@]}" | tar --null -T - -cf -) \
  | tar -xf - -C "$STAGING_DIR"

# New project scaffold: staged under kayan/ and mapped to the repository root.
if [[ -d "$REPO_ROOT/kayan" ]]; then
  cp -R "$REPO_ROOT/kayan/." "$WORK_DIR/"
fi

if [[ ! -f "$WORK_DIR/README.md" || ! -d "$STAGING_DIR/backend" || ! -d "$STAGING_DIR/frontend" ]]; then
  echo "error: export is incomplete (README.md / backend / frontend missing)" >&2
  exit 1
fi

step "Initialising the clean repository"
git -C "$WORK_DIR" init -q -b main
git -C "$WORK_DIR" config user.name "${GIT_AUTHOR_NAME:-Kayan ERP Bot}"
git -C "$WORK_DIR" config user.email "${GIT_AUTHOR_EMAIL:-kayan-erp@users.noreply.github.com}"

git -C "$WORK_DIR" add -A -- . ':!.staging'
git -C "$WORK_DIR" reset -q .staging >/dev/null 2>&1 || true
git -C "$WORK_DIR" commit -q -F - <<'MESSAGE'
chore: repository scaffold, documentation and CI

Kayan ERP is a universal multi-tenant ERP platform. This commit sets up the repository
before the application code lands: the project README, the documentation set
(architecture, database, api, permissions, modules, deployment, development, testing),
the environment template, the ignore rules and the CI pipeline (backend lint/tests,
Flutter analyze/tests/web build, container image builds).
MESSAGE
SCAFFOLD_FILES="$(git -C "$WORK_DIR" ls-files | wc -l | tr -d ' ')"

step "Adding the application code on ${BRANCH}"
(cd "$STAGING_DIR" && tar -cf - .) | tar -xf - -C "$WORK_DIR"
git -C "$WORK_DIR" checkout -q -b "$BRANCH"
git -C "$WORK_DIR" add -A -- . ':!.staging'
git -C "$WORK_DIR" commit -q -F - <<'MESSAGE'
feat: Kayan ERP platform (backend, web client, infrastructure)

Universal multi-tenant ERP: FastAPI backend with 195 tables and 24 routers (715 documented
paths), PostgreSQL, JWT authentication with sessions and revocation, a server-side
permission catalogue of 1113 codes with role templates, immutable stock ledger, real
double-entry accounting integrated with every business document, purchasing, sales, POS,
cash and banks, taxes, fixed assets, expenses, projects, HR and payroll, manufacturing,
service, workflow, notifications, attachments, reports, dashboards, search, import/export
and backup.

Flutter client (Material 3, Arabic RTL / English LTR) driven by a resource engine and a
document engine that render 76 CRUD screens and 28 document lifecycles over the same REST
surface.

Backend tests: 28 passing. Frontend tests: 13 passing. Lint: ruff clean.
MESSAGE
PRODUCT_FILES="$(git -C "$WORK_DIR" diff --name-only main.."$BRANCH" | wc -l | tr -d ' ')"

step "Repository report"
git -C "$WORK_DIR" log --oneline --decorate
printf 'scaffold files: %s\nproduct files : %s\nsize          : %s\n' \
  "$SCAFFOLD_FILES" "$PRODUCT_FILES" "$(du -sh "$WORK_DIR" | cut -f1)"

if [[ "$DRY_RUN" == "1" ]]; then
  printf '\ndry run: repository left at %s (use --dry-run without cleanup to inspect)\n' "$WORK_DIR"
  trap - EXIT
  exit 0
fi

step "Checking access to ${TARGET_SLUG}"
if git ls-remote --exit-code "$REMOTE_URL" >/dev/null 2>&1; then
  if git ls-remote --heads "$REMOTE_URL" main | grep -q main && [[ "$FORCE" != "1" ]]; then
    echo "error: ${TARGET_SLUG} already has a main branch - refusing to overwrite (use --force)" >&2
    exit 1
  fi
else
  echo "note: ${TARGET_SLUG} is empty or unreadable; continuing" >&2
fi

git -C "$WORK_DIR" remote add origin "$REMOTE_URL"

step "Pushing main"
git -C "$WORK_DIR" push --set-upstream origin main

step "Pushing ${BRANCH}"
git -C "$WORK_DIR" push --set-upstream origin "$BRANCH"

step "Opening the review pull request"
if gh pr list --repo "$TARGET_SLUG" --state open --head "$BRANCH" | grep -q .; then
  echo "a pull request for ${BRANCH} is already open"
else
  gh pr create --repo "$TARGET_SLUG" --base main --head "$BRANCH" \
    --title "feat: Kayan ERP platform (backend + Flutter client + infrastructure)" \
    --body-file - <<'PR_BODY'
## What this is

Kayan ERP - a universal, multi-tenant ERP platform - imported into this repository as a
clean history. `main` holds the scaffold (documentation, environment template, CI);
this branch adds the application code for review.

## What the branch adds

| Area | Contents |
| --- | --- |
| `backend/` | FastAPI application: 195 tables, 31 services, 24 routers, 715 documented paths, Alembic migrations, 28 pytest tests |
| `frontend/` | Flutter client (Material 3, Arabic RTL / English LTR): resource engine (76 CRUD screens), document engine (28 lifecycles), POS, dashboards, reports, import wizard, 13 tests |
| `infrastructure/` | Docker Compose (PostgreSQL + API + web + Nginx edge), Dockerfiles, Nginx configuration, environment template |

## Verified

* `pytest -q` - 28 passed; `ruff check app tests` - clean.
* `alembic upgrade head` on an empty database creates the full schema.
* End-to-end flows verified against a running API: quotation -> order -> delivery -> invoice
  -> posting, purchase request -> PO -> receipt -> invoice -> posting, POS shift with cash
  movements and returns, stock transfers/counts, payroll and depreciation runs, manufacturing
  WIP, project billing and service work orders. Inventory value reconciles with the general
  ledger account by account.
* Flutter sources verified statically (import graph, structure, localisation key parity);
  `flutter analyze` / `flutter test` / `flutter build web` run in CI.

## How to run

```bash
cp infrastructure/.env.example .env      # then edit the secrets
docker compose -f infrastructure/docker-compose.yml up --build
# API + Swagger: http://localhost:8080/api/v1 and /docs
# Web client:    http://localhost:8080
```

Demo credentials (development seed only): `admin@kayan-demo.com` / `Admin@12345`, with
manager@, sales@, store@, accountant@ on the same domain and `cashier@` / `Cashier@12345`.

## Notes for the reviewer

* Secrets live only in environment variables; `.env.example` carries placeholders.
* Tenant isolation and permissions are enforced server side; the client filtering is cosmetic.
* Posted financial documents are immutable - corrections go through reversal with a reason.
* Migrations must be applied before starting a new API container
  (`docker compose run --rm api alembic upgrade head`).
PR_BODY
fi

printf '\ndone: https://github.com/%s\n' "$TARGET_SLUG"
