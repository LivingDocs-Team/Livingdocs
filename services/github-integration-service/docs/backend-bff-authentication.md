# Backend BFF authentication contract

The browser calls the Backend under the same `/api` origin. The Backend validates its existing
Spring Security session, resolves the numeric LivingDocs user ID from the authenticated principal
and user database, and proxies GitHub Integration requests. The browser must not use
`X-User-Id` as identity evidence.

## Proxied routes

The Backend proxies `GET`, `POST`, and `DELETE` requests under:

- `/api/github/**`
- `/api/workspaces/**`
- `/api/repositories/**`
- `/api/documentation/**`

It forwards only content negotiation/body data plus a server-derived `X-User-Id`. It replaces
the Authorization header with the internal service credential and does not forward browser
cookies or caller-supplied identity/authorization headers. An expired or absent Backend session
returns HTTP 401; an unavailable GitHub Integration returns HTTP 502.

## Service credential

Set `GITHUB_INTEGRATION_INTERNAL_SECRET` in the runtime environment used by both Backend and
GitHub Integration. Docker Compose requires the variable and passes it to both services. The
value must be a high-entropy secret supplied by the deployment environment; do not commit it,
reuse `TOKEN_ENCRYPTION_KEY`, or place it in frontend build variables. GitHub Integration rejects
protected requests when the credential is missing, blank, or incorrect. It compares credentials
without logging them.

Compose puts Backend and GitHub Integration on `github-internal`; the frontend is attached only to
`backend-network`. The GitHub Integration host port is bound to loopback by default because the
current OAuth redirect is `http://localhost:8082/api/github/callback`. Set
`GITHUB_CALLBACK_BIND_ADDRESS` only when the browser must reach a different host interface; keep
the GitHub OAuth App callback URL and this bind address aligned. Do not expose the service port
for general API access.

## OAuth callback

`GET /api/github/callback` remains the only unauthenticated application route in GitHub
Integration. The authorize URL is available only through the authenticated Backend BFF. Its
opaque state is generated with `SecureRandom`, bound server-side to the Backend-derived user ID,
expires after ten minutes, and is consumed once by the callback. Invalid, expired, or reused state
is rejected. State is held in memory, so a service restart invalidates pending OAuth attempts.

The callback is a browser redirect from GitHub to the current localhost URI, not a server-to-server
call. Changing the redirect URI or callback route requires updating the registered GitHub OAuth
App configuration as well; this contract keeps the existing URI unchanged.

## Session and CSRF

Mutating Backend API calls require the `X-XSRF-TOKEN` value issued by `GET /api/auth/csrf`; the
Backend stores the corresponding CSRF cookie. The frontend sends the cookie and token header for
login, registration, logout, and GitHub Integration mutations. The Backend uses explicit CORS
origins with credentials and does not allow wildcard origins. Logout invalidates the Backend
session. The frontend clears its cached display/workspace ID after successful logout or a BFF 401.

## Ownership and MVP limits

GitHub Integration accepts identity headers only after service credential validation. Its current
workspace model is a personal `ws-{userId}` identifier; server code checks that identifier against
the verified user and filters repositories by that user's GitHub connection. Repository detail,
disconnect, sync, snapshot, and documentation job access check the same connection/job owner.
This MVP does not model shared workspaces. Sync snapshots and documentation job ownership remain
in memory, so restart loses them and multiple replicas are unsupported.
