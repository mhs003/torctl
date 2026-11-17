# torctl

A userspace Tor tunnel for agents. No root, no systemd, no PySocks.

Gives you a SOCKS5 egress with exit rotation, a `curl` wrapper, and a Python session that works even when `requests` can't speak SOCKS because PySocks won't install.

```
scripts/torctl up        # start, wait for bootstrap, verify egress
scripts/torctl status    # state + current exit IP
scripts/torctl rotate    # request a new circuit
scripts/torctl down      # stop via PID file
```

<br>

## Why

The IP on your first request is on every request after it. Servers log source address, timestamp, URI, and user agent. A run from a residential IP is a permanent ordered record of what you did, and deleting rows afterward doesn't touch it.

Pick the egress before request one. Retrofitting protects nothing that already happened.

<br>

## Install

Requires `tor` and `curl`.

```bash
# Debian/Ubuntu
sudo apt install tor curl netcat-openbsd

# macOS
brew install tor
```

As an agent skill, drop the folder in your skills directory:

```bash
git clone <this-repo> ~/.agents/skills/torctl
```

Or just use the scripts directly — they have no dependency on the skill layout.

<br>

## Usage

### Shell

```bash
scripts/torctl up
# started tor pid=12345
# bootstrapped 100%
# exit check: {"IsTor":true,"IP":"185.220.101.1"}

scripts/tor-curl https://api.ipify.org
scripts/tor-curl -n https://api.ipify.org    # fresh circuit first
```

### Python

```python
import sys; sys.path.insert(0, "scripts")
from torsess import TorSession

s = TorSession(rotate=True)          # new circuit per session
r = s.get("https://example.com")
print(r.status_code, len(r.text))

r = s.post("https://example.com/login",
           data={"_token": tok, "email": e, "password": p})
```

Cookies persist across calls on the same session. Redirects follow by default. `r.headers` is a lowercase dict, `r.content` is bytes, `r.text` is decoded.

`torsess` shells out to `tor-curl` rather than using a SOCKS adapter, which is why it works without PySocks. Anything curl supports — multipart uploads, custom headers, redirect policies — behaves the same way.

<br>

## Verify before trusting

```bash
scripts/tor-curl https://check.torproject.org/api/ip
# {"IsTor":true,"IP":"..."}
```

`IsTor:false` means the request bypassed the proxy. Check this before blaming a target for odd behaviour.

<br>

## When it looks like the target is broken

Tor exits are commonly blocked or rate-limited. Symptoms: `403` on admin panels, instant `429`, `503`, or slow timeouts on requests that worked directly.

Before concluding anything:

1. Retry with `-n` for a different exit.
2. Confirm egress is actually Tor.
3. Compare one direct request with one tunnelled request to the same URL.

If direct works and tunnelled fails, it's the exit.

<br>

## Rotation cost

`-n` takes about a second. A single circuit reuses one exit for its lifetime — fine for short jobs, wrong for volume or anything a per-IP counter might track.

Some targets limit per account rather than per IP. Rotation does nothing for those.

<br>

## Don't `pkill -f tor`

The pattern matches the shell holding that string, which is usually the command you just ran. The PID file exists so pattern matching is never needed.

<br>

## Layout

```
torctl/
├── SKILL.md
├── README.md
├── scripts/
│   ├── torctl        # controller
│   ├── tor-curl      # curl wrapper with -n rotation
│   └── torsess.py    # Python session
└── references/
    └── opsec.md      # what gets logged, what a tunnel hides
```

State lives in `~/.cache/torctl/` — override with `TORCTL_HOME`.

<br>

## License

MIT
