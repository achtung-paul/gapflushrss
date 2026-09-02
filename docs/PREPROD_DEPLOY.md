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
- A real Resend API key, **and** a sending domain verified in Resend's
  dashboard -- this deploy never starts Mailhog, so invite/password-reset
  emails go nowhere until `.env`'s `RESEND_API_KEY` is set to something real
  and `EMAIL_FROM_ADDRESS`'s domain is verified (see `core/email.py` and the
  "Verify a sending domain with Resend" section below).

## First-time setup

### 1. Generate self-signed certs for the bundled Postgres and MinIO

Nothing generates these automatically -- run once, on the host, before the
first `docker compose up`:

```bash
cd /opt/stackfitpro   # or wherever this repo lives on the host
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
a real `RESEND_API_KEY` (Resend dashboard: API Keys). `EMAIL_FROM_ADDRESS`
must be on a domain verified in Resend's dashboard first -- see the next
section for how to do that with Cloudflare DNS. Leave `EMAIL_PROVIDER=resend`,
`COOKIE_SECURE`, `POSTGRES_SSLMODE`, and `MINIO_SECURE` as
`.env.preprod.example` already sets them (`resend` / `true` / `require` /
`true`) -- see that file's comments for why each one has an ordering
dependency on the steps above.

### 3. Verify a sending domain with Resend (Cloudflare DNS)

Resend refuses to send from a domain it hasn't verified -- do this before
filling in `RESEND_API_KEY` above, since the key alone isn't enough.

1. In the Resend dashboard, go to **Domains > Add Domain** and enter the
   domain `EMAIL_FROM_ADDRESS` will send from (a subdomain like
   `mail.yourdomain.com` is fine, and keeps this separate from any other
   mail -- e.g. Google Workspace -- already using the root domain's MX
   record).
2. Resend shows a list of DNS records to add: an **MX** record, a **TXT**
   record for SPF, and one or more **CNAME** records for DKIM (exact names/
   values are generated per-domain in Resend's UI -- copy them from there,
   don't reuse an example from elsewhere).
3. Add each one in the Cloudflare dashboard, under **DNS > Records** for
   that domain -- same zone the Tunnel's own CNAME lives in.
   **Set every one of these records to DNS only (grey cloud), not Proxied.**
   Cloudflare's proxy (orange cloud) only ever applies to HTTP(S) traffic
   over `A`/`AAAA`/`CNAME` records pointed at a web server; it does nothing
   useful for mail records and breaks DKIM/SPF lookups if a CNAME ends up
   proxied, since the receiving mail server needs the real DNS answer, not
   Cloudflare's proxy IP. Cloudflare greys out MX and most TXT records
   automatically since they're never proxyable, but double-check any CNAME
   Resend gives you for DKIM -- those default to Proxied and must be flipped
   to DNS only by hand.
4. Optionally add a `DMARC` TXT record (`_dmarc.mail.yourdomain.com`, e.g.
   `v=DMARC1; p=none;` to start) -- not required by Resend to verify, but
   improves deliverability and gives you visibility into spoofing attempts
   against the domain.
5. Back in Resend's dashboard, click **Verify** (or wait -- Resend also
   polls periodically). DNS propagation is usually fast on Cloudflare but
   can take a few minutes; the domain's status shows "Verified" once all
   records check out.
6. Only once verified, set `EMAIL_FROM_ADDRESS` in `.env` to an address on
   that domain (e.g. `noreply@mail.yourdomain.com`) and fill in
   `RESEND_API_KEY` from **API Keys** in the dashboard.

### 4. Bring the stack up

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

### 5. Point the Cloudflare Tunnel at this host's nginx (port 80)

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
