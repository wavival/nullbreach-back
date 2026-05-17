# Contributing to NullBreach Backend

Thanks for your interest in contributing to `nullbreach-api`. This document covers
how to set up the project, the conventions we follow, and the workflow for
landing a change.

> If anything here is out of date, please open a PR fixing it, docs count.

## Table of Contents

1. [How to Contribute](#how-to-contribute)
2. [Local Setup](#local-setup)
3. [Code Conventions](#code-conventions)
4. [Testing](#testing)
5. [Git Workflow](#git-workflow)
6. [Pull Request Flow](#pull-request-flow)
7. [Issues](#issues)
8. [Deployment](#deployment)
9. [Questions](#questions)

## How to Contribute

- **Bug reports** → open a GitHub Issue with reproduction steps.
- **Features / design discussions** → open an Issue *before* writing code so we
  can agree on scope and approach.
- **Docs / typo fixes** → PR directly, no Issue needed.
- **Code changes** → fork the repo, branch off `main`, open a PR.

This project uses the **fork + pull request** model. Direct pushes to `main`
are not permitted; every change lands via PR with at least **one approving
review** and a green CI run, then gets **squash-merged**.

## Local Setup

### Requirements

- Python **3.11+** (the version pinned in `.python-version` is the build target)
- PostgreSQL is required for production; in dev, SQLite is the fallback if
  `DATABASE_URL` is unset.
- An [Anthropic API key](https://console.anthropic.com/) for any endpoint that
  calls Claude (chat, analyzer).

### Steps

```bash
# 1. Fork on GitHub, then clone your fork
git clone https://github.com/wavival/nullbreach-api.git
cd nullbreach-api

# 2. Add the upstream remote so you can sync with the canonical repo
git remote add upstream https://github.com/wavival/nullbreach-api.git

# 3. Create and activate a virtualenv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 4. Install runtime + dev dependencies
pip install -r requirements-dev.txt

# 5. Copy the env template and fill in the required values
cp .env.example .env
# Required in dev: SECRET_KEY. ANTHROPIC_API_KEY is required if you touch
# /chat or /analyzer endpoints. Generate a SECRET_KEY with:
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 6. Apply migrations and create the cache table used by DRF throttling
python manage.py migrate
python manage.py createcachetable

# 7. Install pre-commit hooks (runs black/isort/ruff on every commit)
pre-commit install

# 8. Run the dev server
python manage.py runserver          # http://localhost:8000
```

The API docs are served at `http://localhost:8000/api/docs/` (Swagger UI) and
the raw schema at `/api/schema/`.

## Code Conventions

### Formatting & linting

All formatting and linting is automated via **pre-commit**. The same tools run
on every PR, if pre-commit passes locally, CI will agree.

| Tool   | Purpose                          | Config             |
|--------|----------------------------------|--------------------|
| black  | Code formatter (line length 100) | `pyproject.toml`   |
| isort  | Import ordering (black profile)  | `pyproject.toml`   |
| ruff   | Linter (pycodestyle, pyflakes, bugbear, django, bandit, pyupgrade, comprehensions) | `pyproject.toml`   |

Run them manually:

```bash
black .
isort .
ruff check --fix .
```

Or run the whole pre-commit suite against every file:

```bash
pre-commit run --all-files
```

### Naming

- Modules, functions, variables: `snake_case`
- Classes: `PascalCase`
- Constants and settings keys: `UPPER_SNAKE_CASE`
- DRF view classes end in `View` or `ViewSet`; serializers end in `Serializer`.

### Comments

Comments are reserved for **non-obvious "why"**, well-named code is the
default documentation. Don't paraphrase what the code already says; explain
hidden constraints, workarounds, or business rules.

### Architecture rules (carry-overs from `CLAUDE.md`)

- All apps live under `apps/` and are imported as `apps.<name>`. New apps must
  be created with `python manage.py startapp <name> apps/<name>` and registered
  in `INSTALLED_APPS` as `apps.<name>`.
- Views are thin `APIView` subclasses. Business logic, especially Claude
  calls, belongs in helper modules (`claude.py` per app).
- Surface Claude/SDK failures as **HTTP 502**, never 500.
- Cross-user object access returns **404**, never 403, to avoid leaking
  existence. Filter by `user=request.user`.
- Every new Claude-backed view gets its own throttle scope in
  `config/settings.py` and a wired class in `apps/throttles.py`. Do not reuse
  the generic `user` scope for Claude endpoints.
- Use `@extend_schema(...)` on every new view so it appears correctly in
  Swagger UI.

See `CLAUDE.md` for the full architecture write-up.

## Testing

We use **Django's built-in test runner** (`APITestCase` from DRF), not pytest.
Tests live at the project root under `tests/`, not inside each app.

```bash
# Full suite
python manage.py test tests

# A single file / class / method
python manage.py test tests.test_chat
python manage.py test tests.test_chat.MessageTests
python manage.py test tests.test_chat.MessageTests.test_send_message_auto_titles_session

# With coverage (threshold is 80%)
coverage run --source='apps,config' manage.py test tests
coverage report
```

### Test rules

- **Mock Claude.** Anything that calls the Anthropic SDK must be patched at the
  call site, e.g. `apps.chat.views.<claude_function>`, so the suite stays
  offline and deterministic. See `tests/test_chat.py` and
  `tests/test_analyzer.py` for the pattern.
- Use `reverse()` for URL lookups, not hardcoded paths.
- Coverage threshold is **80%** (`fail_under = 80` in `pyproject.toml`).
  Adding new code without tests will drop coverage and may block the PR.
- New endpoints need both happy-path and unauthorized/cross-user/rate-limit
  cases where applicable.

## Git Workflow

### Branches

- `main` is the default branch and the source of truth. It is protected.
- Work happens on feature branches in your fork, off the latest `main`.

### Branch naming

Use a short, descriptive kebab-case name:

```
feature/<short-description>
fix/<short-description>
docs/<short-description>
refactor/<short-description>
chore/<short-description>
```

### Commit messages

We follow the existing repo style. Subjects use one of these prefixes:

```
[ADDING]    --<short-description>     # new feature or new file
[CREATING]  --<short-description>     # bootstrapping something from scratch
[UPDATING]  --<short-description>     # change to existing behavior
[FIXING]    --<short-description>     # bug fix
```

Examples from the actual history:

```
[ADDING] --auto-files-update-sync
[CREATING] --claude-file
[UPDATING] --chat-view
[UPDATING] --swagger-route
```

Keep subjects under ~72 characters. If the *why* isn't obvious from the
subject, add a short body explaining the motivation, not what the diff shows.

> The doc-sync workflow (`.github/workflows/sync-docs.yml`) commits with
> `docs: ...` and the trailing `[skip ci]` tag. That style is reserved for
> bot commits, human commits should use the bracketed prefixes above.

## Pull Request Flow

1. **Sync** with upstream before starting:

   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. **Branch** off `main`:

   ```bash
   git checkout -b feature/my-change
   ```

3. **Code, format, test:**

   ```bash
   pre-commit run --all-files
   python manage.py test tests
   ```

4. **Push** to your fork:

   ```bash
   git push origin feature/my-change
   ```

5. **Open a PR** against `wavival/nullbreach-back:main`. In the description:
   - What changed and why (link the related Issue with `Closes #N` if any).
   - Any migrations, env-var changes, or deploy notes.
   - Manual test steps if the change isn't fully covered by automated tests.

6. **CI must pass.** The doc-sync workflow may push a follow-up commit to
   `CLAUDE.md` / `README.md` when `apps/**/*.py`, `requirements.txt`, or
   `config/**` changed, that's expected.

7. **One approving review** is required.

8. **Squash merge** is the only merge strategy. Make sure the squash commit
   subject still follows the prefix convention above (edit it in the GitHub UI
   if needed), by default GitHub uses the PR title as the squash subject.

### What to avoid in a PR

- Drive-by refactors unrelated to the stated goal, open a separate PR.
- Bumping unrelated dependency versions.
- Committing `.env`, `db.sqlite3`, `.coverage`, or anything under `.venv/`.
  The `.gitignore` covers these, but double-check `git status` before
  pushing.
- Reintroducing `STATICFILES_STORAGE`, Django 5.1 uses `STORAGES` instead.
- Disabling `SECURE_PROXY_SSL_HEADER` handling or re-enabling
  `SECURE_SSL_REDIRECT` (it causes redirect loops behind Railway's proxy).

## Issues

When opening an Issue, include:

- **Bug**: Django/Python version, steps to reproduce, expected vs actual
  behavior, relevant log lines (the `audit` logger emits
  `METHOD PATH STATUS DURATIONms` for every request).
- **Feature**: the problem you're trying to solve, not just the proposed
  solution. Agreement on scope happens here, before code is written.

Mark in-progress work with the `wip` label or by opening a draft PR.

## Deployment

Deployment is **Railway-driven** and fully automated:

- Pushes to `main` trigger a Railway build using **Nixpacks**, with
  `.python-version` pinning the runtime.
- The `Procfile` declares:
  - `release: python manage.py migrate && python manage.py createcachetable`
  - `web: gunicorn config.wsgi:application --workers 2`
- `collectstatic` runs automatically during the Railway build; static files
  are served by **WhiteNoise** with `CompressedManifestStaticFilesStorage`.
- Production env vars (`SECRET_KEY`, `DATABASE_URL`, `ANTHROPIC_API_KEY`,
  `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, etc.) live in the Railway dashboard,
  not in any `.env` file.

Manual deploys aren't part of the contributor workflow. If a release requires
something out of band (data migration, env var change, downtime window), call
it out explicitly in the PR description.

## Questions

- Open a GitHub Issue or Discussion.
- Maintainer: [@wavival](https://github.com/wavival).
