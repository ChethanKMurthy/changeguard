# Deployment

**Recommended free setup:** the web app on Vercel's Hobby plan and the engine on
Render's free plan (option B). Both are free with no end date and deploy from the
GitHub repository. The demo pages (landing, guided experience, recorded report,
evaluation, method) are static, so they load instantly even while the engine
sleeps; live analysis works once the engine has woken up, which takes about a
minute after 15 idle minutes.

What has been verified, and what has not: the engine and web app run locally,
both container images build in CI, the engine was installed exactly as its image
installs it and served the sample correctly, and the web app's standalone server
was run as its image runs it. The AWS template passes `cfn-lint` and its scripts
pass ShellCheck. None of the hosted options had been deployed when this was
written.

| Option | Cost | Lasts | Who can reach it | Reports persist? |
|--------|------|-------|------------------|------------------|
| B. Web app on Vercel (Hobby) + engine on Render (free) | free | no end date | anyone with the link | no: Render's free disk is wiped when the engine sleeps or restarts |
| Web app on Vercel only (demo without live analysis) | free | no end date | anyone with the link | n/a |
| AWS: EC2 + CloudFront ([`deploy/aws`](../deploy/aws/README.md)) | Free plan credits; about USD 13/month on a paid plan | until the AWS Free plan ends (six months after sign-up) | anyone with the HTTPS link | yes, on the instance's disk |
| A. Docker Compose on your machine or a VM | free | while it runs | you (ports bind to localhost) | yes, in a Docker volume |

Not free any more: Hugging Face now requires a paid plan to create Docker Spaces
(static Spaces remain free), so it is not listed. Vercel's Hobby plan is for
non-commercial use. Free tiers change; check the providers' current terms.

## AWS (Free plan)

`deploy/aws/deploy.sh` creates one CloudFormation stack: a `t3.micro` instance
that builds and runs both containers, and a CloudFront distribution that gives
it an HTTPS link. Only CloudFront can reach the instance, and shell access is
through Systems Manager rather than SSH. The script checks the account plan
first and will not deploy on a paid plan without `--accept-paid-plan`. Costs,
updates and teardown are in [`deploy/aws/README.md`](../deploy/aws/README.md).

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

Free-plan behaviour to expect: the service sleeps after 15 minutes without
traffic, and the first request afterwards takes about a minute while it wakes.
Its disk is wiped whenever it sleeps, restarts or redeploys, so reports people
create last only while the engine stays awake. The 750 free hours a month cover
one service running all month. The web app's static pages (landing, guided
experience, evaluation, method, and the recorded sample report) keep working
while the engine sleeps.

### 2. Web app on Vercel

1. **Add New → Project**, import the repository, and set **Root Directory** to
   `frontend`. Vercel detects Next.js.
2. Environment variables (Production and Preview):
   - `CHANGEGUARD_API_URL` = the Render URL
   - `CHANGEGUARD_API_KEY` = the key from step 1.3
3. Deploy. Browsers only talk to the Vercel origin; the API proxy adds the key
   server-side and gives each browser its own workspace.

Vercel limits a function's request and response bodies to 4.5 MB, so through a
Vercel-hosted web app an upload (patch, snapshot and coverage together) must stay
under that, even though the engine itself accepts up to 25 MB archives. Pasted
diffs and the samples are far below it.

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
