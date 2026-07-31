# PDC Scavenger Hunt

A mobile-first scavenger hunt application for the Phoenixville Democratic
Committee. Players join games by invitation, choose clues from a list, and
reveal answers by entering the unique code found at each stop.

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
- Each account is identified by a full name and unique email address.
- A user sees only non-draft games to which they are assigned.
- Games may be `draft`, `open`, or `closed`; more than one game can be open.
- Clues have a numbered order that administrators can rearrange.
- A player can see every clue headline and choose the clues in any order.
- A clue's answer remains absent from player API responses until its code has
  been entered correctly.
- Closed games preserve revealed clues but do not accept new completions.
- Administrators are ordinary users with `is_admin` enabled and may also play.

Codes are trimmed, case-insensitive, and globally unique. The app stores both a
keyed fingerprint for player validation and a normalized display value for
admin-only views. Codes created before migration `20260728_0004` have only a
fingerprint and must be replaced once before they can be displayed or copied.

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
Email:    admin@pdc.test
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
3. Add clues and answers. Each code must be unique. After saving a clue, reopen
   it to optionally attach one photo and one video.
4. Assign active players to the game.
5. Change the game status to **Open**.
6. Drag clues by their grip handles to change the order; up/down buttons remain
   available as an accessible fallback.
7. Copy current codes from the clue list.
8. Use the Progress tab to monitor players, mark a run of clues complete, return
   a player to a completed clue, or restart their entire game. Every progress
   adjustment requires an audit reason.

Invitation links expire after 24 hours, can be used once, and are invalidated
when a replacement link is generated. No email provider is included; links
should be sent through a trusted channel.

## Clue photos and videos

Each clue can have at most one photo and one video. Media is shown only to a
signed-in player assigned to that clue's game. Administrators can upload,
replace, preview, and remove attachments from the clue editor.

- Photos: JPEG, PNG, or WebP, up to 8 MiB
- Videos: MP4 or MOV, up to 100 MiB

Photos and videos are uploaded through the Render web service to avoid mobile
browser cross-origin upload failures. Render sends photos to a private
Cloudflare R2 bucket and videos to Cloudflare Stream, which encodes them and
supplies an adaptive browser player. Render relays each upload in memory and
never stores media on its filesystem.

The application keeps media metadata and clue access rules in PostgreSQL. When a
player reaches a clue, the application redirects the photo to a short-lived
signed R2 URL or redirects the video player to a short-lived private Stream
token. Processing videos remain hidden from players until Stream reports that
they are ready.

The default video duration limit is five minutes in addition to the 100 MiB file
limit. The size and duration limits can be changed with
`PDC_PHOTO_MAX_BYTES`, `PDC_VIDEO_MAX_BYTES`, and
`PDC_VIDEO_MAX_DURATION_SECONDS`.

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

The checked-in `render.yaml` creates a paid Starter Docker web service and a
private Basic PostgreSQL 17 database in Virginia. It runs Alembic before each
deploy, seeds the first administrator after the initial deployment, checks
database readiness at `/api/ready`, and deploys from `main` only after GitHub CI
passes. No Render disk is needed.

Before the first Blueprint sync, provide these secret values in Render:

- `PDC_PUBLIC_BASE_URL`: the final HTTPS origin, without a trailing slash, path,
  query, or fragment
- `PDC_SEED_ADMIN_EMAIL`
- `PDC_SEED_ADMIN_PASSWORD`: at least 12 characters
- `PDC_SEED_ADMIN_NAME`
- `PDC_CLOUDFLARE_ACCOUNT_ID`
- `PDC_CLOUDFLARE_API_TOKEN`: an API token with Stream Read and Stream Write
- `PDC_CLOUDFLARE_R2_ACCESS_KEY_ID`
- `PDC_CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `PDC_CLOUDFLARE_R2_BUCKET`

The Stream customer subdomain is already set in `render.yaml`.

Render generates separate session-signing and clue-code secrets. Never change
`PDC_CLUE_CODE_SECRET` after clues have been created: changing it invalidates all
existing clue codes. Keep the web service and database in the same region so the
application uses Render's private connection string.

## Cloudflare setup

1. Enable Cloudflare R2 and create a private Standard bucket, for example
   `pdc-clue-media`.
2. Create an R2 API token scoped to Object Read & Write for that bucket. Copy its
   access key ID and secret access key into the corresponding Render variables.
3. Enable Cloudflare Stream and create an API token with Stream Read and Stream
   Write. Copy the full Stream customer subdomain shown in the Stream dashboard.
4. Create a Stream webhook targeting
   `https://your-app.example/api/v1/media/cloudflare-stream/webhook`. Copy its
   signing secret into a new secret Render environment variable named
   `PDC_CLOUDFLARE_STREAM_WEBHOOK_SECRET`, then redeploy. This step happens after
   Render has assigned the service its final hostname.

Keep the R2 bucket private. The browser receives time-limited presigned URLs, not
the R2 credentials, and Stream videos require signed playback URLs. An R2 CORS
rule and a `pending/photos/` lifecycle rule are no longer required because photo
uploads pass through Render.

Create the GitHub repository, push this project to its `main` branch, connect the
repository to a new Render Blueprint, and populate the prompted secrets.

After the first deployment:

1. Open `/api/ready` on the Render URL and confirm `{"status":"ready"}`.
2. Sign in with the seeded administrator and immediately change its password.
3. Remove both `PDC_SEED_ADMIN_EMAIL` and `PDC_SEED_ADMIN_PASSWORD` from the
   service environment after confirming access. They are needed only by the
   one-time initial deploy hook.
4. Create a draft test game, assign the administrator, and verify the complete
   clue/code/answer flow before inviting players.
5. If adding a custom domain, update `PDC_PUBLIC_BASE_URL` to that HTTPS origin
   and redeploy before generating invitation links.

## Security and recovery

- Passwords use scrypt with a unique salt.
- Sessions are signed, HttpOnly, SameSite cookies and are Secure in production.
- Every authenticated mutation requires a CSRF token.
- Sign-in and clue-code submissions are rate limited.
- Account/password changes invalidate existing sessions.
- Authentication, administration, rejected codes, and completions are audited.
- Clue media uploads, replacements, and removals are audited.
- Authorization and clue ordering are enforced by the API, never by the browser.
- API responses use `Cache-Control: no-store`; production responses also set
  HSTS and a restrictive Content Security Policy.
- Admin-visible clue codes are stored in the private PostgreSQL database. Keep
  database public access disabled and restrict administrator accounts carefully.

To recover administrator access, set a new `PDC_SEED_ADMIN_EMAIL` and
`PDC_SEED_ADMIN_PASSWORD` in Render and run:

```bash
python -m pdcscavengerhunt.seed
```

The command is idempotent and creates the account only when the normalized
email address does not exist.
