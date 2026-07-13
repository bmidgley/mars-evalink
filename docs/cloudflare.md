# Cloudflare Access authentication

Evalink can authenticate users through **Cloudflare Access** (Zero Trust) so
they do not need a separate Django password. Cloudflare authenticates the user
at the edge; Django validates the signed JWT on each request and starts a
normal session.

This is SSO via Cloudflare Gateway/Access: users sign in once with your
configured identity provider (Google, Okta, one-time PIN, etc.) and are
automatically logged into evalink.

## How it works

```
User -> Cloudflare Access (IdP login) -> evalink (plain HTTP behind proxy)
              |
              +-- adds Cf-Access-Jwt-Assertion header (signed JWT)
```

1. A request reaches evalink through a Cloudflare Access application.
2. Cloudflare adds `Cf-Access-Jwt-Assertion` with a signed JWT.
3. Django middleware validates the JWT (signature, audience, issuer, expiry).
4. The `email` claim is used to find or create a Django user.
5. The user is logged in with a session cookie. Existing `@login_required`
   views work without changes.

New users are created as **non-admin** accounts (`is_staff=False`,
`is_superuser=False`) with **no usable password**. Admin accounts are still
created manually with `createsuperuser`.

## Cloudflare Gateway vs Access

**Cloudflare Gateway** (DNS filtering) does not send identity headers by itself.

**Cloudflare Access** (application protection on a hostname) is what adds
`Cf-Access-Jwt-Assertion`. Gateway identity-aware policies use the same Access
identity under the hood.

You need an **Access application** on your evalink hostname, not just an orange-cloud DNS record.

## Prerequisites

- Evalink is reachable through Cloudflare (proxied DNS record or `cloudflared`
  tunnel). See `deploy.md` for general Cloudflare wiring.
- `DJANGO_BEHIND_PROXY=1` is set so Django trusts `X-Forwarded-Proto`.
- Your public hostname is in `DJANGO_ALLOWED_HOSTS` and
  `DJANGO_CSRF_TRUSTED_ORIGINS`.

## Enable Access in Cloudflare

1. Open **Cloudflare One** -> **Access** -> **Applications**.
2. Add a **Self-hosted** application for your evalink hostname (for example
   `evalink.archresearch.net`).
3. Set the application URL to match how traffic reaches evalink (for example
   `https://evalink.archresearch.net`).
4. Attach an **Access policy** that allows your identity provider or login
   method (Google Workspace, Okta, one-time PIN, etc.).
5. From the application settings, note:
   - **Team domain** -- for example `myteam.cloudflareaccess.com` (the
     `myteam` part is enough for the env var below).
   - **Application AUD** -- the audience tag unique to this application.

## Enable SSO in evalink

Add these variables to `.env` (see `.env.docker.example`):

```bash
CLOUDFLARE_ACCESS_ENABLED=1
CLOUDFLARE_ACCESS_TEAM_DOMAIN=myteam
CLOUDFLARE_ACCESS_AUD=<application-aud-tag>
```

Restart the web container:

```bash
docker compose restart web
```

On first visit through Access, Django creates a user from the JWT `email`
claim and logs them in. No evalink password is required.

## Behavior

| Entry path | Result |
|------------|--------|
| Through Cloudflare Access | JWT validated; user auto-created or logged in |
| Direct LAN (`http://192.168.x.x:18000`) | No JWT header; existing password login still works |
| Django admin (`/admin/`) | Requires `is_staff=True`; create admins with `createsuperuser` |

Password login remains available as a break-glass or LAN fallback when
`Cf-Access-Jwt-Assertion` is not present (for example local development or
direct access to the host port).

## Security

- **Validate the JWT.** Evalink validates `Cf-Access-Jwt-Assertion` against
  Cloudflare's public keys. Do not trust `Cf-Access-Authenticated-User-Email`
  alone -- that header can be spoofed if a client reaches evalink without going
  through Cloudflare.
- **Direct port access bypasses Access.** The web service is exposed on host
  port 18000. Requests that hit that port directly do not carry Access
  headers. Keep `DJANGO_ALLOW_LAN=1` only on trusted networks, or bind the web
  port to localhost when Access is the sole public entry.
- **CSRF.** Include your public hostname in `DJANGO_CSRF_TRUSTED_ORIGINS`
  (with `https://`).

## Implementation reference

| Component | Location |
|-----------|----------|
| JWT validation and user provisioning | `evalink/evalink/cloudflare_access.py` |
| Request middleware | `evalink/evalink/middleware/cloudflare_access.py` |
| Settings | `CLOUDFLARE_ACCESS_*` in `evalink/evalink/settings.py` |
| Tests | `evalink/evalink/test_cloudflare_access.py` |

Middleware is disabled unless `CLOUDFLARE_ACCESS_ENABLED=1`. When enabled, it
runs after `AuthenticationMiddleware` so an existing session is respected, but
Access can replace the session if the identity changes.

## Troubleshooting

- **Redirect loop or login page after Access login** -- confirm
  `CLOUDFLARE_ACCESS_AUD` matches the application's audience tag exactly.
- **403 or invalid token in logs** -- confirm `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
  matches your Zero Trust team domain.
- **Works on public URL but not LAN** -- expected. LAN access has no Access
  JWT; use password login or disable Access for local testing.
- **User created but no admin access** -- expected. SSO users are non-admin.
  Promote users in Django admin or create a superuser for `/admin/`.
