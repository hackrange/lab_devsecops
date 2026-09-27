#!/usr/bin/env python3
"""The Local Lab control panel.

    server.py              serve the panel on /run/hackrange/control.sock (nginx fronts it)
    server.py --start-all  start every part of the lab, then exit (run at boot)

The page shows how to get into the lab and its services, how hard the machine
and each part of the lab are working, and start and stop buttons for the
parts a student may want to pause to free up memory.

Standard library only: nothing to install, nothing to keep patched.

Author: Tim Rice
"""

from __future__ import annotations

import json
import os
import grp
import re
import socket
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hrcontrol import auth, components, labinfo, metrics  # noqa: E402
from hrcontrol import labs  # noqa: E402

# A Unix socket, not a TCP port: only root and nginx (group www-data) can open
# it, so nothing else on the machine, and no web page (DNS rebinding reaches
# TCP ports, never sockets), can talk to the panel except through nginx, which
# sets X-HR-Door and X-Real-IP itself.
SOCKET = "/run/hackrange/control.sock"
SOCKET_GROUP = "www-data"
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_FILES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "logo.png": "image/png",
    "favicon.png": "image/png",
}
COOKIE = "hrc_session"
ACTION_RE = re.compile(r"^/api/components/([a-z0-9-]+)/(start|stop|reset)$")
LAB_CHECK_RE = re.compile(r"^/api/labs/([0-9]{1,2})/check$")
LAB_CONFIRM_RE = re.compile(r"^/api/labs/([0-9]{1,2})/items/([a-z0-9-]{1,60})/confirm$")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                               "base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "hackrange-control"

    # ---- plumbing --------------------------------------------------------------

    def _door(self) -> str:
        # Set by nginx on each door, overwriting anything the browser sent.
        return "lab" if self.headers.get("X-HR-Door") == "lab" else "remote"

    def _client(self) -> str:
        return self.headers.get("X-Real-IP") or "local"

    def address_string(self) -> str:  # a Unix socket has no peer address to log
        return self._client()

    def _token(self) -> str:
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else ""

    def _authorized(self) -> bool:
        return self._door() == "lab" or auth.valid(self._token())

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None, cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=300" if cache else "no-store")
        for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict, extra: dict | None = None) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json", extra)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4096:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def _is_api_write(self) -> bool:
        """Every change must come from the page's own script: a custom header
        a form on another site cannot send, and JSON."""
        return (self.headers.get("X-HR-Request") == "1"
                and self.headers.get("Content-Type", "").startswith("application/json"))

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("hackrange-control: %s %s\n" % (self._client(), fmt % args))

    # ---- routes ---------------------------------------------------------------------

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/whoami":
            return self._json(200, {"door": self._door(), "authenticated": self._authorized()})
        if path == "/api/state":
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            return self._json(200, self._state())
        if path == "/api/labs":
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            return self._json(200, labs.overview())
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if not self._is_api_write():
            return self._json(403, {"error": "refused"})
        if path == "/api/login":
            if self._door() == "lab":
                return self._json(200, {"ok": True})
            body = self._body()
            if auth.locked_out(self._client()):
                return self._json(429, {"error": "Too many wrong passwords.  Wait five minutes and try again."})
            token = auth.login(self._client(), str(body.get("username", "")), str(body.get("password", "")))
            if not token:
                return self._json(401, {"error": "That username and password did not work.  Run show_information.sh on your Ubuntu machine to see the current password."})
            cookie = f"{COOKIE}={token}; Path=/control/; Secure; HttpOnly; SameSite=Strict; Max-Age={auth.SESSION_HOURS * 3600}"
            return self._json(200, {"ok": True}, {"Set-Cookie": cookie})
        if path == "/api/logout":
            auth.logout(self._token())
            return self._json(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}=; Path=/control/; Secure; HttpOnly; SameSite=Strict; Max-Age=0"})
        m = ACTION_RE.match(path)
        if m:
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            cid, action = m.group(1), m.group(2)
            if action == "reset":
                # Deleting data needs the page to repeat back exactly what it
                # asked the student to confirm, not just a click.
                if self._body().get("confirm") != cid:
                    return self._json(400, {"ok": False, "message": "not confirmed"})
                accepted, message = components.reset(cid)
            else:
                accepted, message = components.act(cid, action)
            return self._json(202 if accepted else 409, {"ok": accepted, "message": message})
        m = LAB_CHECK_RE.match(path)
        if m:
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            result = labs.check(int(m.group(1)))
            return self._json(400 if "error" in result else 200, result)
        m = LAB_CONFIRM_RE.match(path)
        if m:
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            result = labs.confirm(int(m.group(1)), m.group(2), bool(self._body().get("confirmed")))
            return self._json(400 if "error" in result else 200, result)
        if path == "/api/labs/github-user":
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            result = labs.set_github_user(str(self._body().get("github_user", ""))[:60])
            return self._json(400 if "error" in result else 200, result)
        if path == "/api/reset-all":
            if not self._authorized():
                return self._json(401, {"error": "sign in"})
            if self._body().get("confirm") != "RESET":
                return self._json(400, {"ok": False, "message": "not confirmed"})
            accepted, message = components.reset("all")
            return self._json(202 if accepted else 409, {"ok": accepted, "message": message})
        self._json(404, {"error": "not found"})

    # ---- pieces ---------------------------------------------------------------------

    def _static(self, name: str) -> None:
        if name not in STATIC_FILES:
            return self._json(404, {"error": "not found"})
        with open(os.path.join(STATIC, name), "rb") as fh:
            self._send(200, fh.read(), STATIC_FILES[name], cache=name != "index.html")

    def _state(self) -> dict:
        snap = metrics.snapshot()
        states = components.states()
        errors = components.last_errors()
        items = []
        for c in components.COMPONENTS:
            items.append({
                "id": c["id"], "name": c["name"], "week": c["week"], "desc": c["desc"],
                "kind": c["kind"], "state": states.get(c["id"], "unknown"),
                "resettable": c["id"] in components.RESETTABLE,
                "reset_also": components.RESET_ALSO.get(c["id"], []),
                "usage": metrics.usage_for(c, snap), "error": errors.get(c["id"], ""),
            })
        workstation = snap["containers"].get("hackrange-lab", {})
        cores = snap["host"].get("cores", 1) or 1
        return {
            "door": self._door(),
            "host": snap["host"],
            "sampled": snap["at"],
            "components": items,
            "workstation": {"cpu": round(workstation.get("cpu", 0.0) / cores, 1), "mem": workstation.get("mem", 0),
                            "running": "hackrange-lab" in snap["containers"]},
            "info": labinfo.info(),
            "reset": components.reset_status(),
        }


def main() -> None:
    if "--start-all" in sys.argv:
        components.start_all()
        return
    metrics.start()
    UnixHTTPServer(SOCKET, Handler).serve_forever()


class UnixHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_UNIX

    def server_bind(self) -> None:
        os.makedirs(os.path.dirname(SOCKET), mode=0o755, exist_ok=True)
        try:
            os.unlink(SOCKET)
        except FileNotFoundError:
            pass
        old = os.umask(0o117)
        try:
            self.socket.bind(SOCKET)
        finally:
            os.umask(old)
        os.chown(SOCKET, 0, grp.getgrnam(SOCKET_GROUP).gr_gid)
        os.chmod(SOCKET, 0o660)
        self.server_name, self.server_port = "localhost", 0


if __name__ == "__main__":
    main()
