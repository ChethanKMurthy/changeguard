# Deployment

ChangeGuard runs at zero cost in three ways, each with your own accounts. Pick
by who should reach it.

What has been verified, and what has not: the engine and web app run locally,
the engine was installed exactly as its image installs it (non-editable, outside
the source tree) and served the sample correctly, and the web app's standalone
server was run as its image runs it. The images themselves are built in CI; they
were not built locally because no Docker daemon was available. `render.yaml`
and the Vercel and Hugging Face steps below have not been deployed from this
repository.

| Option | Cost | Who can reach it | Reports persist? |
|--------|------|------------------|------------------|
| A. Docker Compose on your machine or a VM | free | you (ports bind to localhost) | yes, in a Docker volume |
| B. Engine on Render (free) + web app on Vercel (Hobby) | free | anyone with the URL | no, Render's free disk is ephemeral |
| C. Engine on Hugging Face Spaces (Docker) + web app on Vercel | free | anyone with the URL | no, unless you add paid storage |

Vercel's Hobby plan is for non-commercial use. Free tiers change; check the
providers' current terms.

## A. Docker Compose

```bash
cp .env.example .env      # optional
docker compose up --build
```

- Web app: http://localhost:3000, engine API docs: http://localhost:8000/api/docs.
- Reports live in the `engine-data` volume (`/data/changeguard.db`). Back up by
  copying that file while the engine is stopped, or with `sqlite3 .backup`.
- To expose it beyond localhost, put it behind a reverse proxy with TLS and
  authentication (Caddy, nginx, Cloudflare Tunnel with Access), and set
  `CHANGEGUARD_API_KEY` in `.env`.
- Local AI: `docker compose --profile ai up --build`, then
  `docker compose exec ollama ollama pull llama3.2:3b`, and set
  `CHANGEGUARD_AI_PROVIDER=ollama` and `CHANGEGUARD_AI_MODEL=llama3.2:3b` in `.env`.

## B. Render (engine) + Vercel (web app)

### 1. Engine on Render

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository. `render.yaml`
   defines a free Docker web service built from `backend/Dockerfile`, with a
   health check on `/api/v1/health`, a generated `CHANGEGUARD_API_KEYS`,
   `CHANGEGUARD_TRUST_PROXY_HEADERS=true`, and the API docs turned off.
3. After the first deploy, copy the generated `CHANGEGUARD_API_KEYS` value from
   the service's Environment page, and note the service URL
   (`https://changeguard-engine-xxxx.onrender.com`).

Free-plan behaviour to expect: the service sleeps after a period without
traffic, so the first request afterwards can take close to a minute; its disk is
reset on every deploy and restart, so stored reports disappear. The web app's
static pages (landing, guided experience, evaluation, method, and the recorded
sample report) keep working while the engine sleeps.

### 2. Web app on Vercel

1. **Add New → Project**, import the repository, and set **Root Directory** to
   `frontend`. Vercel detects Next.js.
2. Environment variables (Production and Preview):
   - `CHANGEGUARD_API_URL` = the Render URL
   - `CHANGEGUARD_API_KEY` = the key from step 1.3
3. Deploy. Browsers only talk to the Vercel origin; the API proxy adds the key
   server-side and gives each browser its own workspace.

### Public deployments: what to decide

- **Anyone with the URL can run analyses**, within the per-client rate limit
  (20 per minute by default) and the input size limits. To restrict access, turn
  on Vercel's deployment protection or put the app behind your SSO.
- **Each browser sees only its own reports.** Workspaces are a privacy boundary
  between visitors, not authentication: anyone who obtains a browser's cookie
  sees that browser's reports. For a team that should share reports, set
  `CHANGEGUARD_WORKSPACES=shared` on the web app and protect it with SSO.
- **Hosted models cost money and send the redacted evidence pack to the
  provider.** Keep `CHANGEGUARD_AI_PROVIDER=none` for a public demo unless you
  accept both.

## C. Hugging Face Spaces (engine)

1. Create a Space with the **Docker** SDK.
2. Copy the contents of `backend/` into the Space repository, and add this front
   matter at the top of its `README.md`:

   ```yaml
   ---
   title: ChangeGuard engine
   sdk: docker
   app_port: 8000
   ---
   ```

3. In the Space settings, add secrets `CHANGEGUARD_API_KEYS` (a long random
   string) and `CHANGEGUARD_TRUST_PROXY_HEADERS=true`.
4. Point the Vercel web app's `CHANGEGUARD_API_URL` at
   `https://<user>-<space>.hf.space` and set `CHANGEGUARD_API_KEY` to the same key.

## Operations

| Concern | How |
|---------|-----|
| Health | `GET /api/v1/health` (engine), `GET /` (web app); both images define a `HEALTHCHECK` |
| Logs | stdout of both processes; unexpected engine errors include the request ID returned in `X-Request-ID` |
| Upgrades | Database migrations run automatically on start and are forward-only. Back up the SQLite file first. |
| Interrupted analyses | On restart, analyses that were queued or running are marked failed with a clear message |
| Capacity | `CHANGEGUARD_WORKER_THREADS` analyses run concurrently; each is capped by `CHANGEGUARD_ANALYSIS_TIMEOUT_SECONDS` |
| Retention | The newest `CHANGEGUARD_MAX_STORED_ANALYSES` analyses are kept |

## Building the images yourself

```bash
docker build -t changeguard-engine backend
docker build -t changeguard-web --build-arg CHANGEGUARD_API_URL=http://engine:8000 frontend
```

The engine image runs as an unprivileged user with the database under `/data`
and honours `PORT`. The web image is a Next.js standalone server
(`node server.js`) that also runs unprivileged. `CHANGEGUARD_API_URL` is read at
runtime by the API proxy; the build argument only affects the `/api/docs`
pass-through.
