# Opsec notes for tunnelled work

Short, practical. The point is to make the right decision *before* the first request, because most of it cannot be undone.

## What a target records

For every request, standard access logging captures:

- source IP (`remote_addr`, or `X-Forwarded-For` behind a proxy)
- timestamp with timezone
- method and full URI including query string
- user agent
- status code and bytes sent
- sometimes a request id that also appears in application logs

Application logs add the request body where the app logs it, plus the session id. Database logs add query text if slow-query or general logging is on.

Two consequences:

1. A sequence of requests is a narrative. `forgot-password` → `reset-password/store/<random>` → `login` → `admin/...` reads as one operation regardless of what rows remain.
2. Deleting the artifacts does not delete the requests. Row deletion is itself another logged request.

## What a tunnel hides and what it doesn't

Hides: the origin IP. The target sees a Tor exit address that many other people share.

Doesn't hide: request content, timing, cookies, session identifiers, user agent, ordering, or the account you authenticated as. If you log in as a named account, the session is tied to that identity no matter which IP carried it.

A tunnel makes attribution hard. It does not make activity invisible.

## Choose the egress first

If a target will be touched more than once, decide the exit path before request one. Moving to a tunnel mid-way produces a clean trail and a dirty trail, and the dirty part is permanent.

## Rotation vs one circuit

One circuit keeps one exit for the life of the circuit. Fine for a short, single-purpose job.

Rotate when the work involves volume, repetition, or anything a per-IP rate limit might count. `tor-curl -n` costs about a second and changes who the next request appears to come from.

Some targets count per-account rather than per-IP. Rotation does nothing for those.

## What to check before blaming the target

Node-fresh failures are common:

| symptom | likely cause |
|---|---|
| `403` on an admin panel | Cloudflare or WAF blocking exit nodes |
| `429` immediately | exit IP already rate-limited by other users |
| `503`, slow timeouts | overloaded exit |
| login works direct, fails tunnelled | cookie/session bound to IP, or bot protection |

Test the same URL directly and through the tunnel. If direct works and tunnelled fails, it's the exit.

## Process hygiene

- Never `pkill -f tor`. The pattern matches the shell holding the string, which is often your own command line. Use a PID file.
- Keep the tunnel state in a dedicated directory so cleanup is a single `rm -rf`, and so parallel jobs don't share a control cookie.
- Cookies from a tunnelled session should stay in that session. Mixing a direct-connection cookie jar into a tunnelled run leaks continuity between the two IPs.
