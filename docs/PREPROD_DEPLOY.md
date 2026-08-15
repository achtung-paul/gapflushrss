# Deploying an internet-facing pre-production host

For a Cloudflare-Tunnel-fronted host, distinct from `CLAUDE.md`'s "Deploying
to the test LXC" (`192.168.4.226`, LAN-only, unaffected by anything here).
Same codebase, same `docker-compose.yml` -- this is an additive overlay
(`docker-compose.preprod.yml`) plus a host-specific `.env`, not a fork.

```
User Browser ──> Cloudflare (WAF, TLS, DDoS) ──> Cloudflare Tunnel ──> Nginx ──> backend / Postgres / MinIO
   yourdomain.com                                  (cloudflared)      (this repo's docker-compose stack)
```

## What this repo gives you, and what's on you

Handled by this repo's config, once you follow the steps below: the
tunnel-specific rate-limiting fix (`nginx/nginx.conf`), TLS on the bundled
Postgres/MinIO, `cookie_secure`, no Mailhog, no `uvicorn --reload`.

**Not handled here, and this deploy is not safe without them:**
- The Cloudflare Tunnel itself (`cloudflared` install, tunnel creation, DNS
  record, ideally a Cloudflare Access policy) -- Cloudflare dashboard/CLI
  work, outside this repo.
- **The DNS record must be proxied (orange cloud), not DNS-only.** A grey-cloud
  record bypasses Cloudflare's WAF/DDoS protection entirely for a Tunnel-only
  setup.
- **Nothing but `cloudflared` may be able to reach this host's port 80.**
  `nginx.conf`'s `X-Real-IP` fix trusts the `CF-Connecting-IP` header
  unconditionally -- that's only safe because the tunnel is the sole path in.
  If this host's firewall/router also forwards `80`/`443` to it directly, an
  attacker reaching nginx that way can forge `CF-Connecting-IP` and route
  around every rate limit in the app.
- A real SMTP relay's credentials -- this deploy never starts Mailhog, so
  invite/password-reset emails go nowhere until `.env`'s `SMTP_*` values point
  at something real.

## First-time setup

### 1. Generate self-signed certs for the bundled Postgres and MinIO

Nothing generates these automatically -- run once, on the host, before the
first `docker compose up`:

```bash
cd /opt/gapflushrss   # or wherever this repo lives on the host
mkdir -p postgres/certs minio/certs

openssl req -new -x509 -days 825 -nodes \
  -out postgres/certs/server.crt -keyout postgres/certs/server.key \
  -subj "/CN=postgres"
openssl req -new -x509 -days 825 -nodes \
  -out minio/certs/public.crt -keyout minio/certs/private.key \
  -subj "/CN=minio"

chmod 600 postgres/certs/server.key minio/certs/private.key
```

Postgres refuses to start with a key file it doesn't own. Bring `postgres`
up once first (`docker compose -f docker-compose.yml -f
docker-compose.preprod.yml up -d postgres`), check the UID it actually runs
as (`docker compose exec postgres id`), then `chown` `postgres/certs/server.key`
to match on the host before the next restart. (`minio` runs as root inside
its own container and is less picky, but keep the key file `600` regardless.)

`sslmode=require` (set in `.env`, next step) encrypts the connection but does
**not** verify the server's identity -- `verify-full` needs a properly
managed CA, which this self-signed setup doesn't have. Known, accepted gap;
see `CLAUDE.md`'s production checklist.

Both cert directories are gitignored (private keys) -- regenerate them if
this host is ever rebuilt from scratch.

### 2. Create this host's `.env`

```bash
cp .env.preprod.example .env
chmod 600 .env
```

Fill in every blank -- real Postgres/MinIO passwords (not
`.env.example`'s placeholders), a real `SERVICE_CREDENTIAL_KEY` and
`MINIO_LOG_WEBHOOK_TOKEN` (generation commands are in `.env.preprod.example`'s
comments, same as `.env.example`), the real domain for `FRONTEND_ORIGIN`, and
real SMTP relay credentials. Leave `COOKIE_SECURE`, `POSTGRES_SSLMODE`, and
`MINIO_SECURE` as `.env.preprod.example` already sets them (`true` / `require`
/ `true`) -- see that file's comments for why each one has an ordering
dependency on the steps above.

### 3. Bring the stack up

```bash
docker compose -f docker-compose.yml -f docker-compose.preprod.yml \
  up -d postgres minio backend frontend nginx
```

Mailhog is deliberately not named -- it's never started on this host (see
`docker-compose.yml`'s comment on `backend`'s `depends_on`).

Check `docker compose logs postgres` and `docker compose logs minio` both
show TLS active, then `docker compose logs backend` for a clean boot (the
central connection now requires TLS -- a cert problem shows up here as a
connection failure, not a silent fallback to plaintext).

### 4. Point the Cloudflare Tunnel at this host's nginx (port 80)

Cloudflare dashboard/CLI, not this repo. `cloudflared` should reach nginx
either via `localhost:80` (if `cloudflared` runs on the same host) or the
docker network directly, matching whichever bridging approach you set up the
tunnel with.

## Redeploying after a code change

Same procedure as the test LXC (`CLAUDE.md`) -- rsync or scp the changed
files, then rebuild and restart with **both** compose files:

```bash
docker compose -f docker-compose.yml -f docker-compose.preprod.yml \
  build backend frontend
docker compose -f docker-compose.yml -f docker-compose.preprod.yml \
  up -d postgres minio backend frontend nginx
```

Forgetting the second `-f` silently drops back to the base file's dev
command (`--reload`, no Postgres SSL flags) without erroring -- Compose just
merges whatever files you give it.

A migration in `alembic/versions/` applies automatically on backend boot,
same as the test LXC. A migration in `alembic_project/` still needs the
admin "Initialize" button per affected Postgres service, same as everywhere
else.

## Still open after this deploy

Carried forward from `CLAUDE.md`'s production checklist, not addressed by
this doc: migrating the Default Client off the shared central database, and
tightening host-level access control on the `backups` Docker volume. Neither
is specific to internet exposure -- both are pre-existing structural debt.
