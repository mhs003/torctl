#!/usr/bin/env python3
"""
torsess — a session that routes through torctl's SOCKS proxy.

Built for environments where PySocks is unavailable (no pip, externally managed
Python, no root). Instead of a SOCKS adapter it shells out to the bundled
``tor-curl`` wrapper, so anything curl supports — multipart, cookies,
redirects — works the same way.

    from torsess import TorSession

    s = TorSession(rotate=True)
    r = s.get("https://example.com")
    print(r.status_code, len(r.text))

    r = s.post("https://example.com/login",
               data={"_token": tok, "email": e, "password": p})

Cookies persist across calls. Redirects follow by default.
"""

from __future__ import annotations

import atexit
import json as _json
import os
import shutil
import subprocess
import tempfile

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

_TOR_CURL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tor-curl")


def _resolve_tor_curl() -> str:
    env = os.environ.get("TORCTL_TOR_CURL")
    if env:
        return env
    if os.path.exists(_TOR_CURL):
        return _TOR_CURL
    found = shutil.which("tor-curl")
    if found:
        return found
    raise RuntimeError(
        "tor-curl not found; set TORCTL_TOR_CURL or keep it beside torsess.py"
    )


class Response:
    def __init__(self, header_lines: list[str], body: bytes, status: int, url: str):
        self._header_lines = header_lines
        self.content = body
        self.status_code = status
        self.url = url

    @property
    def headers(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in self._header_lines:
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip().lower()] = v.strip()
        return out

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def __repr__(self) -> str:
        return f"<Response [{self.status_code}] {self.url}>"


class TorSession:
    """HTTP session over the torctl tunnel."""

    def __init__(
        self,
        rotate: bool = True,
        user_agent: str = DEFAULT_UA,
        timeout: int = 60,
    ):
        self.rotate = rotate
        self.user_agent = user_agent
        self.timeout = timeout
        self.headers: dict[str, str] = {}
        self._tor_curl = _resolve_tor_curl()

        self._jar = tempfile.NamedTemporaryFile(delete=False, suffix=".jar").name
        self._hdr = tempfile.NamedTemporaryFile(delete=False, suffix=".hdr").name
        atexit.register(self._cleanup)

    def _cleanup(self) -> None:
        for p in (self._jar, self._hdr):
            if os.path.exists(p):
                os.unlink(p)

    def request(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        files: dict | None = None,
        headers: dict | None = None,
        json: dict | None = None,
        allow_redirects: bool = True,
    ) -> Response:
        method = method.upper()

        cmd = [self._tor_curl]
        if self.rotate:
            cmd.append("-n")

        cmd += [
            "-b", self._jar,
            "-c", self._jar,
            "-m", str(self.timeout),
            "-A", self.user_agent,
        ]

        if allow_redirects:
            cmd.append("-L")
        else:
            cmd += ["--max-redirs", "0"]

        merged = dict(self.headers)
        if headers:
            merged.update(headers)
        for k, v in merged.items():
            cmd += ["-H", f"{k}: {v}"]

        # Deliberately avoid `-X POST`. curl's -X pins the method across every
        # redirect hop, so a 302 that follows a form submission is re-sent as a
        # second POST — a one-shot CSRF token is then already spent and the
        # server answers 419. Letting curl choose the method from --data gives
        # the standard POST-then-GET behaviour.
        payload_handled = False
        if json is not None:
            cmd += ["-H", "Content-Type: application/json", "--data-binary", _json.dumps(json)]
            payload_handled = True
        elif data is not None:
            for k, v in data.items():
                cmd += ["--data-urlencode", f"{k}={v}"]
            payload_handled = True

        temp_paths: list[str] = []
        if files:
            for field, val in files.items():
                if isinstance(val, tuple):
                    name, blob, ctype = val
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".up")
                    tmp.write(blob)
                    tmp.close()
                    temp_paths.append(tmp.name)
                    cmd += ["-F", f"{field}=@{tmp.name};filename={name};type={ctype}"]
                else:
                    cmd += ["-F", f"{field}={val}"]
            payload_handled = True

        if not payload_handled and method != "GET":
            cmd += ["-X", method]

        cmd += ["-D", self._hdr, "-o", "-", "-w", "__STATUS__%{http_code}", url]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=self.timeout + 20
            )
        finally:
            for p in temp_paths:
                if os.path.exists(p):
                    os.unlink(p)

        out = proc.stdout
        status = 0
        if b"__STATUS__" in out:
            out, tail = out.rsplit(b"__STATUS__", 1)
            try:
                status = int(tail.strip()[:3])
            except ValueError:
                status = 0

        header_lines: list[str] = []
        if os.path.exists(self._hdr):
            with open(self._hdr, "rb") as fh:
                header_lines = fh.read().decode("latin-1", "replace").split("\r\n")
            # keep only the final response block on redirect chains
            last = []
            for line in header_lines:
                if line.startswith("HTTP/"):
                    last = []
                last.append(line)
            header_lines = last

        if status == 0 and proc.stderr:
            raise RuntimeError(
                f"tor-curl failed: {proc.stderr.decode('utf-8', 'replace')[:400]}"
            )

        return Response(header_lines, out, status, url)

    def get(self, url: str, **kw) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> Response:
        return self.request("POST", url, **kw)


if __name__ == "__main__":
    s = TorSession(rotate=True)
    r = s.get("https://check.torproject.org/api/ip")
    print(r.status_code, r.text.strip())
