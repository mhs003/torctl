---
name: torctl
description: Use when traffic must leave from an untracked IP instead of the machine's own address — security testing, scraping a site that rate-limits or blocks you, or any request where "who is this coming from" matters. Also use when the user mentions Tor, SOCKS5, exit nodes, rotating IPs, getting blocked, or "don't use my real IP". Gives a userspace Tor tunnel with exit rotation, a curl wrapper, and a Python session needing no PySocks.
---

# torctl

A userspace Tor tunnel plus helpers, so agent-driven requests leave from an IP that has no history with the target.

No root. No PySocks. No systemd. Runs entirely out of a working directory.

## Why this exists

The IP attached to your first request is attached to every request after it. Web servers log `remote_addr`, timestamp, URI, and user-agent. A successful run from a residential IP is a permanent, chronological record of everything you did — enumeration, the reset chain, the large pulls. Cleaning rows afterwards does not remove that.

Decide the egress before the first request. Retrofitting a tunnel protects nothing that already happened.

## Setup

```bash
scripts/torctl up          # start, wait for bootstrap, print exit IP
scripts/torctl status      # show state + current exit
scripts/torctl down        # stop via PID file
```

Requires `tor` and `curl` on PATH. Everything lives in `~/.cache/torctl/` by default — override with `TORCTL_HOME`.

`up` blocks until `Bootstrapped 100%` and verifies egress through `check.torproject.org`. It prints the exit IP. If that line is missing or not `IsTor: true`, stop and fix the tunnel before touching the target.

## Rotating the exit

A single Tor circuit reuses one exit node. That's fine for a short job, wrong for anything sustained — many hosts count hits per IP.

```bash
scripts/tor-curl -n https://api.ipify.org    # fresh circuit, then request
scripts/tor-curl https://api.ipify.org       # reuse circuit
```

`-n` sends `SIGNAL NEWNYM` over the control port first, then waits a second for the new circuit.

## Python

`scripts/torsess.py` gives a session that shells out to `scripts/tor-curl`. This matters because `requests` cannot speak SOCKS without PySocks, and PySocks often can't be installed (no pip, externally-managed environment, no root).

```python
from torsess import TorSession

s = TorSession(rotate=True)          # new circuit per session
r = s.get("https://example.com")
print(r.status_code, len(r.text))

r = s.post("https://example.com/login",
           data={"_token": tok, "email": e, "password": p},
           allow_redirects=True)
```

Cookies persist across calls on the same `TorSession` (curl cookie jar). Redirects follow by default. `r.headers` is a lowercase dict. `r.content` is bytes, `r.text` is decoded.

For per-request rotation inside one session, set `Rotate on a per-request basis` by passing `rotate` yourself — or construct a new `TorSession` per operation. Simpler and always correct.

## Checking egress

```bash
scripts/tor-curl https://check.torproject.org/api/ip
# {"IsTor":true,"IP":"192.42.116.19"}
```

Confirm `IsTor` is `true` before relying on it. `IsTor:false` means the request bypassed the proxy entirely.

## Failure modes that look like target bugs

Tor exits are frequently blocked, rate-limited, or geo-fenced. Symptom: `403`, `429`, `503`, or slow timeouts on requests that worked from a direct connection.

Before concluding a target is broken or defended against you:

1. Retry with `-n` for a different exit.
2. Check the request actually went through Tor with `scripts/tor-curl https://check.torproject.org/api/ip`.
3. Compare one direct request with one tunnelled request to the same URL.

Admin panels behind Cloudflare often refuse exit nodes outright. That's the exit, not the target.

## Do not use a broad pkill

`pkill -f tor` matches the shell that contains that string, including your own. The PID file exists so you never need pattern matching:

```bash
scripts/torctl down     # kill $(cat $TORCTL_HOME/tor.pid)
```

## Reference

- `references/opsec.md` — what a target logs, what a tunnel does and does not hide, and the decisions to make before the first request.
