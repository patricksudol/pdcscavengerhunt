# PDC Scavenger Hunt

A mobile-first, sequential scavenger hunt application for the Phoenixville
Democratic Committee. Players join games by invitation and reveal clues in order
by entering the unique code found at each stop.

## Stack

- Python 3.14, Sanic 25.12 LTS, Pydantic, and SQLAlchemy 2
- PostgreSQL 17 with Psycopg 3 and Alembic migrations
- React 19, TypeScript, Vite, TanStack Query, and Vitest
- `uv` and `uv.lock` for Python; Node 24, npm, and `package-lock.json` for the SPA
- Docker Compose for local operation
- GitHub Actions and a Render Blueprint for production

Sanic serves both the versioned JSON API and the compiled frontend from one
container.

## Game rules

- Administrators create users and send them a single-use password invitation.
- A user sees only non-draft games to which they are assigned.
- Games may be `draft`, `open`, or `closed`; more than one game can be open.
- Clues have a fixed numbered order.
- Locked clue content is never included in an API response.
- A correct code completes and reveals the next clue only after all earlier clues
  have been completed.
- Closed games preserve revealed clues but do not accept new completions.
- Administrators are ordinary users with `is_admin` enabled and may also play.

Codes are trimmed, case-insensitive, globally unique, and stored as keyed
fingerprints rather than plaintext. An administrator can replace a code but
cannot retrieve its old value.

## Quick start with Docker

Copy the example environment and start the application:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

If port 8000 is already occupied, set a different host port:

```bash
PDC_PORT=18000 docker compose up --build -d
```

Compose binds the application to server loopback only. To access a development
instance on a remote server, forward the port over SSH:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 18000:127.0.0.1:18000 user@remote-server
```

The Compose service applies migrations and creates the configured initial
administrator before starting Sanic. The development defaults are:

```text
URL:      http://localhost:8000
Username: admin
Password: demo-scavenger-2026
```

Change these values in `.env` before using the app with real players.

Verify the service:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ready
```

Useful operations:

```bash
docker compose logs -f app
docker compose restart app
docker compose down
docker compose down -v
```

The last command deletes the local PostgreSQL volume and all game data.

## Native development

Install the locked Python environment:

```bash
uv python install 3.14
uv sync --all-groups --frozen
```

Install the frontend with Node 24:

```bash
nvm use
cd frontend
npm ci
```

Start PostgreSQL, apply migrations, and run Sanic:

```bash
docker compose up -d db
uv run alembic upgrade head
uv run python -m pdcscavengerhunt.seed
uv run sanic pdcscavengerhunt.app:app --dev --host 0.0.0.0 --port 8000
```

For Vite hot reload, run this in another terminal:

```bash
cd frontend
npm run dev
```

Vite listens on port 5173 and proxies `/api` to Sanic on port 8000.

## Administration

Sign in and open `/admin`.

1. Create player accounts under **Players** and copy each invitation link.
2. Create a draft game under **Games**.
3. Add clues in their required order. Each code must be unique.
4. Assign active players to the game.
5. Change the game status to **Open**.
6. Use the Progress tab to monitor completion totals.

Invitation links expire after 24 hours, can be used once, and are invalidated
when a replacement link is generated. No email provider is included; links
should be sent through a trusted channel.

## Verification

Backend:

```bash
uv run ruff check .
uv run pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npm test
npm audit --omit=dev
```

Production container:

```bash
docker compose build --no-cache app
docker compose up -d
curl --fail http://127.0.0.1:8000/api/ready
```

## Render and GitHub

The checked-in `render.yaml` creates a Docker web service and private PostgreSQL
17 database in Virginia. It runs Alembic before each deploy, seeds the first
administrator after the initial deployment, checks database readiness at
`/api/ready`, and deploys from `main` only after GitHub CI passes.

Before the first Blueprint sync, provide these secret values in Render:

- `PDC_PUBLIC_BASE_URL`: the final HTTPS origin, without a trailing slash
- `PDC_SEED_ADMIN_USERNAME`
- `PDC_SEED_ADMIN_PASSWORD`: at least 12 characters
- `PDC_SEED_ADMIN_NAME`

Render generates separate session-signing and clue-code secrets. Never change
`PDC_CLUE_CODE_SECRET` after clues have been created: changing it invalidates all
existing clue codes. Keep the web service and database in the same region so the
application uses Render's private connection string.

Create the GitHub repository, push this project to its `main` branch, connect the
repository to a new Render Blueprint, and populate the prompted secrets.

## Security and recovery

- Passwords use scrypt with a unique salt.
- Sessions are signed, HttpOnly, SameSite cookies and are Secure in production.
- Every authenticated mutation requires a CSRF token.
- Sign-in and clue-code submissions are rate limited.
- Account/password changes invalidate existing sessions.
- Authentication, administration, rejected codes, and completions are audited.
- Authorization and clue ordering are enforced by the API, never by the browser.

To recover administrator access, set a new `PDC_SEED_ADMIN_USERNAME` and
`PDC_SEED_ADMIN_PASSWORD` in Render and run:

```bash
python -m pdcscavengerhunt.seed
```

The command is idempotent and creates the account only when the normalized
username does not exist.
