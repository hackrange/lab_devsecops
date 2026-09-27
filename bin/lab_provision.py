#!/usr/bin/env python3
"""
Lab identity service for the DevSecOps course.

The LMS calls this when a student opens a lab.  One call creates (or returns)
everything that student needs: their own virtual Kubernetes cluster, an account
on the lab Git server, and a token for the lab package registry.  A second call
removes it all when their enrolment ends.

It listens only on the lab network and only answers requests carrying the shared
secret, because it hands out credentials.  Student ids are checked against a
strict pattern before they reach a shell, a URL, or a Kubernetes name.

Author: Tim Rice
"""

from __future__ import annotations

import json
import os
import re
import secrets
import ssl
import time
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = ("0.0.0.0", 9500)
SECRET_FILE = "/etc/rancher/lab-provision-secret"
STATE_DIR = "/etc/rancher/lab-identities"
GIT_URL = "https://labgit.lab:8444"
REGISTRY_URL = "https://labrepo.lab:8443"
NODE_IP = "10.10.10.70"
FORGEJO_ADMIN = "labadmin"
FORGEJO_PW_FILE = "/etc/rancher/forgejo-admin-password"
VCLUSTER = "/usr/local/sbin/lab-vcluster"
REGISTRY_SCRIPT = "/usr/local/sbin/lab-student-registry.sh"
# Git Code Review, the findings platform Day 19 uses.  It is served on the
# node's IP rather than a name because the lab CA's private key is gone and no
# certificate can be signed for a new host name; both existing certificates
# carry this IP as a subject alternative name, so it still validates.
SAST_URL = "https://10.10.10.70:8445"
SAST_ADMIN = "admin"
SAST_ADMIN_FILE = "/etc/rancher/gcr-admin"   # two lines: password, then TOTP secret
# The package registry's own portal.  A student needs an account there from
# Day 6 on, to read the rules that refused a package and see why.
REGISTRY_ADMIN = "admin"
REGISTRY_ADMIN_PW_FILE = "/etc/rancher/forgerepo-admin-password"
# The shared application whose rules Day 10 contrasts with a student's own.
APP_DEMO = "secure-build-lab"
APP_TOKEN_ID = "shared-secure-build-lab"
APP_TOKEN_FILE = os.path.join(STATE_DIR, "_shared-app-token")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,30}$")


def read(path: str) -> str:
    with open(path) as fh:
        return fh.read().strip()


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def forgejo(method: str, path: str, body: dict | None = None, auth: tuple[str, str] | None = None):
    """Call the lab Git server's API.  TLS is verified against the lab CA."""
    user, pw = auth or (FORGEJO_ADMIN, read(FORGEJO_PW_FILE))
    req = urllib.request.Request(
        f"{GIT_URL}/api/v1{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    import base64
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode())
    ctx = ssl.create_default_context(cafile="/etc/nginx/labtls/lab-ca.crt")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw[:300]}


def shared_app_token() -> str:
    """The class's one token for the shared secure-build-lab application.

    Minted on first use and kept, because minting again would revoke the copy
    every running lab is already holding.  Returns an empty string when the
    registry scripts are not installed, the same way a student token does.
    """
    if not os.path.exists(REGISTRY_SCRIPT):
        return ""
    if os.path.exists(APP_TOKEN_FILE):
        return read(APP_TOKEN_FILE)
    rc, out = run([REGISTRY_SCRIPT, "create", APP_TOKEN_ID, "dev", APP_DEMO])
    tok = re.search(r"TOKEN=(\S+)", out)
    if not tok:
        return ""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(APP_TOKEN_FILE, "w") as fh:
        fh.write(tok.group(1))
    os.chmod(APP_TOKEN_FILE, 0o600)
    return tok.group(1)


def _totp_now(secret: str) -> str:
    """A six digit code for a base32 secret, with no third party library.

    The findings platform makes every local account enrol a second factor and
    gives no way to turn that off, so the administrator this provisioner signs
    in as has one too.  Nothing here is clever: it is RFC 6238 with the default
    thirty second step.
    """
    import base64, hmac, hashlib, struct, time
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    counter = struct.pack(">Q", int(time.time()) // 30)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return "%06d" % code


def _open_patiently(opener, req, timeout=60):
    """Open a request, waiting out the platform's rate limiter.

    Git Code Review allows twelve authentication requests a minute from one
    address, which is a sensible defence and an awkward fit for a provisioner:
    every student costs an administrator sign in plus a sign in of their own,
    so a class of twenty arriving together runs into it and accounts come out
    half made.  The limit is per minute, so waiting is the whole fix.  Raising
    it would trade a real brute force control for impatience.
    """
    delay = 20
    for attempt in range(4):
        try:
            return opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(delay)
            delay += 20
    raise RuntimeError("unreachable")


def _sast_session():
    """Sign in as the findings platform's administrator and return an opener.

    There is no API for creating an account or minting a token there: both are
    browser forms, so this drives the same forms a person would.  That is why
    the flow looks long.  It is the documented behaviour, not a workaround.
    """
    import http.cookiejar
    if not os.path.exists(SAST_ADMIN_FILE):
        return None
    lines = read(SAST_ADMIN_FILE).splitlines()
    if len(lines) < 2:
        return None
    password, totp_secret = lines[0].strip(), lines[1].strip()

    ctx = ssl.create_default_context(cafile="/etc/nginx/labtls/lab-ca.crt")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ctx),
    )

    def get(path):
        req = urllib.request.Request(f"{SAST_URL}{path}")
        with _open_patiently(opener, req, 30) as r:
            return r.read().decode("utf-8", "replace")

    def post(path, fields):
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(f"{SAST_URL}{path}", data=data, method="POST")
        try:
            with _open_patiently(opener, req, 60) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.url, e.read().decode("utf-8", "replace")

    def csrf(html):
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        return m.group(1) if m else ""

    post("/auth/login", {"username": SAST_ADMIN, "password": password,
                         "csrf_token": csrf(get("/login"))})
    # Enrolled administrators are asked for the second factor on every sign in.
    page = get("/auth/totp")
    if "csrf_token" in page:
        post("/auth/totp", {"code": _totp_now(totp_secret), "csrf_token": csrf(page)})
    return get, post, csrf


def _sast_activate(student: str, starting: str) -> dict:
    """Do the whole first sign in for a student, and keep what they will need.

    Git Code Review puts two chores between a new account and the tool: a
    second factor, which every local account must enrol before it can reach
    anything, and a password somebody else chose, which must be replaced.  Both
    are right for a real installation.  In a two hour lab they are a QR code, a
    phone, and a form standing where the exercise should be.

    So the provisioner does them, once, here.  The enrolment has to come first:
    until it is done the session is only half authenticated and every other
    page, including the password form, quietly redirects to the login screen.
    That is what made an earlier version of this hand out a password that had
    never actually been set.

    Returns the password and the TOTP secret, so the lab can show the learner a
    working code instead of asking them to set one up.  Returns {} if anything
    goes wrong, and the caller falls back to the starting password: more work
    for the student, but never a dead account.
    """
    import http.cookiejar
    if not starting:
        return {}
    try:
        final = secrets.token_urlsafe(12)
        ctx = ssl.create_default_context(cafile="/etc/nginx/labtls/lab-ca.crt")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ctx),
        )

        def get(path):
            req = urllib.request.Request(f"{SAST_URL}{path}")
            with _open_patiently(opener, req, 30) as r:
                return r.read().decode("utf-8", "replace")

        def post(path, fields):
            data = urllib.parse.urlencode(fields).encode()
            req = urllib.request.Request(f"{SAST_URL}{path}", data=data, method="POST")
            try:
                with _open_patiently(opener, req, 60) as r:
                    return r.geturl(), r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return (e.url or ""), ""

        def csrf(html):
            mm = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
            return mm.group(1) if mm else ""

        post("/auth/login", {"username": student, "password": starting,
                             "csrf_token": csrf(get("/login"))})

        # The second factor, first.  The secret is handed out on the setup page
        # and only written to the account once a code proves it was received.
        page = get("/auth/totp-setup")
        secret = ""
        for c in jar:
            if c.name == "gcr_totp_enroll":
                secret = c.value
        if not secret:
            mm = re.search(r"[A-Z2-7]{16,}", page)
            secret = mm.group(0) if mm else ""
        if not secret:
            return {}
        url, _ = post("/auth/totp-setup", {"code": _totp_now(secret),
                                           "csrf_token": csrf(page)})
        if "error=" in (url or ""):
            return {}

        # Now the session is whole, the password form is reachable.
        page = get("/account/password")
        url, _ = post("/account/password", {
            "current_password": starting,
            "new_password": final,
            "confirm_password": final,
            "csrf_token": csrf(page),
        })
        # Only one thing counts as success, and it is not "no error in the URL":
        # a request that landed back on the login page has neither.
        if "/account?msg=" not in (url or ""):
            return {}
        return {"sast_password": final, "sast_totp_secret": secret}
    except Exception:
        return {}


def sast_account(student: str) -> dict:
    """A developer account on the findings platform, scoped to this student.

    Returns {} when the platform is not configured here, so a node without it
    still provisions a working lab rather than failing the whole request.
    """
    session = _sast_session()
    if session is None:
        return {}
    get, post, csrf = session
    try:
        page = get("/users")
        if student in page:                      # already made on an earlier run
            return {"sast_url": SAST_URL, "sast_user": student, "sast_password": ""}
        status, url, _ = post("/users/add", {
            "username": student,
            "role": "developer",
            "email": f"{student}@lab.local",
            "csrf_token": csrf(page),
        })
        # The starting password is shown once, in the message on the redirect.
        m = re.search(r"starting%20password%20is%20(\S+?)%20", url) or \
            re.search(r"starting password is (\S+?) ", urllib.parse.unquote(url))
        first = m.group(1) if m else ""
        # Spend the starting password and the enrolment here, rather than
        # making the learner do both before they have seen the tool.
        out = {"sast_url": SAST_URL, "sast_user": student,
               "sast_password": first, "sast_totp_secret": ""}
        out.update(_sast_activate(student, first))
        return out
    except Exception:
        # Never fail a lab because the findings platform is having a bad day.
        return {}


def sast_reset_password(student: str) -> dict:
    """Give an existing account a password the student can actually be told.

    Accounts made before the provisioner started spending the starting password
    are stranded: the password was shown once, to nobody, and the identity file
    carries an empty string, so the lab has nothing to print on the start page
    and the learner cannot get in at all.  An administrator reset is the only
    way back, because no password is recoverable, only replaceable.

    Only ever called when the stored password is empty, so a student who has
    since chosen their own is left alone.
    """
    session = _sast_session()
    if session is None:
        return {}
    get, post, csrf = session
    try:
        page = get("/users")
        token = csrf(page)
        # Each row carries the username in its first cell and the account id in
        # the action of the forms beside it.
        user_id = ""
        for row in page.split("<tr")[1:]:
            cell = re.search(r'<td[^>]*>\s*([A-Za-z0-9._-]+)\s*</td>', row)
            if cell and cell.group(1) == student:
                ident = re.search(r"/users/(\d+)/", row)
                user_id = ident.group(1) if ident else ""
                break
        if not user_id:
            return {}
        _, url, _ = post(f"/users/{user_id}/password", {"csrf_token": token})
        plain = urllib.parse.unquote(url or "")
        m = re.search(rf"New password for {re.escape(student)}: (\S+?) ", plain)
        first = m.group(1) if m else ""
        if not first:
            return {}
        out = {"sast_url": SAST_URL, "sast_user": student,
               "sast_password": first, "sast_totp_secret": ""}
        out.update(_sast_activate(student, first))
        return out
    except Exception:
        return {}


# The address the findings platform uses to reach the lab Git server.  NOT
# GIT_URL: that name resolves inside a lab container and on this host, and the
# platform runs in Kubernetes where it does not resolve at all.  The
# certificate carries 10.10.10.70 as a subject alternative name, so the IP
# verifies against the same lab CA.
SAST_GIT_URL = "https://10.10.10.70:8444"


def _forgejo_scan_token(student: str, password: str) -> str:
    """A read only Git token for the findings platform, minted as the student.

    Made with the student's own credentials rather than the administrator's, so
    what the platform can read is exactly what that learner can read.  An
    administrator token here would quietly give one student's connection the
    run of everybody's repositories.
    """
    try:
        status, body = forgejo(
            "POST", f"/users/{student}/tokens",
            {"name": f"code-review-{int(time.time())}",
             "scopes": ["read:repository", "read:user"]},
            auth=(student, password))
        if status in (200, 201) and isinstance(body, dict):
            return str(body.get("sha1") or "")
    except Exception:
        pass
    return ""


def sast_connection(student: str, git_password: str) -> dict:
    """Point the findings platform at this student's own repositories.

    Without this the platform has nothing in it.  A developer account can run a
    scan and read findings, but only an administrator may add the account the
    scan reads from, so a student cannot create this for themselves and should
    not be made an administrator to work around that: one installation serves
    the whole class, and an administrator there sees every other learner's
    findings and can sign in as them.

    So the connection is made here, on their behalf, scoped to their Forgejo
    account, and their user scope is set to match.  They stay a developer and
    see exactly their own work.
    """
    session = _sast_session()
    if session is None or not git_password:
        return {}
    get, post, csrf = session
    try:
        page = get("/connections")
        if re.search(rf">\s*{re.escape(student)}\s*<", page):
            return {}                      # made on an earlier run

        token = _forgejo_scan_token(student, git_password)
        if not token:
            return {}

        post("/connections/save", {
            "name": student,
            "provider": "forgejo",
            "auth_method": "pat",
            "api_url": SAST_GIT_URL,
            "web_url": SAST_GIT_URL,
            "token": token,
            # Deliberately NOT naming an organization.  Naming one sets
            # auto_discover_orgs and include_collaborator_repos to false (see
            # scanner_config.py), which is right for GitHub and wrong here: a
            # Forgejo personal namespace is a USER, not an organization, so the
            # scan then looks up /orgs/<student>/repos, finds nothing, and
            # reports "there is nothing in it" while the repositories sit
            # there.  Left empty, the scan enumerates what the credential can
            # reach, and the credential is this student's own read only token,
            # so that is exactly their own repositories and nothing else.
            "organizations": "",
            "enabled": "on",
            "csrf_token": csrf(page),
        })

        # And let them see what was imported.  A developer sees nothing until a
        # scope says otherwise, which is the right default and means this step
        # is not optional: without it the scan runs and the learner opens an
        # empty page.
        page = get("/users")
        user_id = ""
        for row in page.split("<tr")[1:]:
            cell = re.search(r'<td[^>]*>\s*([A-Za-z0-9._-]+)\s*</td>', row)
            if cell and cell.group(1) == student:
                ident = re.search(r"/users/(\d+)/", row)
                user_id = ident.group(1) if ident else ""
                break
        if user_id:
            post(f"/users/{user_id}/save", {
                "role": "developer",
                "display_name": student,
                "email": f"{student}@lab.local",
                "github_login": student,
                "scopes": student,
                "csrf_token": csrf(page),
            })
        return {"sast_connection": student}
    except Exception:
        return {}


def registry_account(student: str) -> dict:
    """A portal account on the package registry, scoped to this student.

    Separate from their npm and pip token, which is minted elsewhere and is what
    the clients use.  This is so a learner can open the portal and read the rule
    that refused a package, rather than being told what it says.

    Returns {} if the registry is not configured here, so a node without it
    still provisions a working lab.
    """
    if not os.path.exists(REGISTRY_ADMIN_PW_FILE):
        return {}
    try:
        ctx = ssl.create_default_context(cafile="/etc/nginx/labtls/lab-ca.crt")
        jar = __import__("http.cookiejar", fromlist=["CookieJar"]).CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ctx),
        )

        def api(path, body=None, method=None, csrf=""):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(f"{REGISTRY_URL}/_api{path}", data=data,
                                         method=method or ("POST" if data else "GET"))
            req.add_header("content-type", "application/json")
            if csrf:
                req.add_header("X-CSRF-Token", csrf)
            with opener.open(req, timeout=30) as r:
                return json.loads(r.read().decode() or "{}")

        signin = api("/login", {"username": REGISTRY_ADMIN,
                                "password": read(REGISTRY_ADMIN_PW_FILE)})
        csrf = signin.get("csrf", "")

        existing = api("/users", csrf=csrf).get("users", [])
        if any(u.get("username") == student for u in existing):
            # Made on an earlier run.  The password was shown once and is in the
            # state file; nothing here can read it back.
            return {"registry_user": student, "registry_password": ""}

        password = secrets.token_urlsafe(12)
        api("/users", {"username": student, "password": password,
                       "role": "developer", "full_name": f"Student {student}"},
            csrf=csrf)
        return {"registry_user": student, "registry_password": password}
    except Exception:
        # A lab is worth more than a portal account.
        return {}


def provision(student: str) -> dict:
    """Create everything this student needs.  Safe to call again: each step is
    skipped when it already exists, so a retry after a half-finished run works."""
    state_path = os.path.join(STATE_DIR, f"{student}.json")
    if os.path.exists(state_path):
        known = json.loads(read(state_path))
        # A token is shown once, so an identity created before the registry
        # scripts existed (or one whose token was revoked) has an empty string
        # here.  Mint a replacement rather than handing back a lab that quietly
        # talks to the registry as nobody.
        if not known.get("registry_token") and os.path.exists(REGISTRY_SCRIPT):
            rc, out = run([REGISTRY_SCRIPT, "create", student])
            tok = re.search(r"TOKEN=(\S+)", out)
            if tok:
                known["registry_token"] = tok.group(1)
                known.setdefault("registry_url", REGISTRY_URL)
                with open(state_path, "w") as fh:
                    json.dump(known, fh)
        if not known.get("registry_token_app"):
            known["registry_token_app"] = shared_app_token()
            known["registry_app"] = APP_DEMO
        # Same reason as the registry token above: an identity made before the
        # findings platform existed has none of its keys, and would be handed
        # back that way forever.  Day 19 would then die at its first step for a
        # student whose only mistake was starting the course early.
        if not known.get("registry_user"):
            added = registry_account(student)
            if added:
                known.update(added)
                with open(state_path, "w") as fh:
                    json.dump(known, fh)
                os.chmod(state_path, 0o600)
        # Each of these fills one gap, and they run in order rather than as
        # alternatives: an account made before any of this existed is missing
        # all three, and a chain of elif would fix one gap per lab launch.
        changed = False
        if not known.get("sast_url"):
            added = sast_account(student)
            if added:
                known.update(added)
                changed = True
        elif not known.get("sast_password") or not known.get("sast_totp_secret"):
            # Made before the provisioner did the first sign in, so either
            # there is no password anybody can be told, or no second factor the
            # lab can show a code for.  Either way the account is one a learner
            # cannot actually use.  Reset it once and record the result.
            fixed = sast_reset_password(student)
            if fixed.get("sast_password"):
                known.update(fixed)
                changed = True

        if known.get("sast_password") and not known.get("sast_connection"):
            # The account is fine; it simply has nothing to scan yet.
            added = sast_connection(student, known.get("git_password", ""))
            if added:
                known.update(added)
                changed = True

        if changed:
            with open(state_path, "w") as fh:
                json.dump(known, fh)
            os.chmod(state_path, 0o600)
        return known

    identity: dict[str, str] = {"student": student}

    # 1. the student's own virtual Kubernetes cluster
    rc, out = run([VCLUSTER, "create", student])
    if rc != 0:
        raise RuntimeError(f"cluster: {out[-400:]}")
    m = re.search(r"API (https://\S+)", out)
    identity["k8s_api"] = m.group(1) if m else ""
    kube = f"/etc/rancher/student-kubeconfigs/{student}.yaml"
    identity["kubeconfig"] = read(kube) if os.path.exists(kube) else ""

    # 2. an account on the lab Git server
    git_pw = secrets.token_urlsafe(16)
    status, body = forgejo("POST", "/admin/users", {
        "username": student,
        "email": f"{student}@lab.local",
        "password": git_pw,
        "must_change_password": False,
    })
    if status not in (201, 422):          # 422 = the user already exists
        raise RuntimeError(f"git user: {status} {body}")
    if status == 422:                      # reset the password so we know it
        forgejo("PATCH", f"/admin/users/{student}", {"login_name": student, "password": git_pw,
                                                     "must_change_password": False})
    identity["git_url"] = GIT_URL
    identity["git_user"] = student
    identity["git_password"] = git_pw

    # 3. a token for the lab package registry, scoped to this student so their
    #    allow and deny rules never reach a classmate
    if os.path.exists(REGISTRY_SCRIPT):
        rc, out = run([REGISTRY_SCRIPT, "create", student])
        tok = re.search(r"TOKEN=(\S+)", out)
        identity["registry_token"] = tok.group(1) if tok else ""
    else:
        identity["registry_token"] = ""

    # 4. a second token, scoped to the shared secure-build-lab application.
    #    Day 10 uses the two side by side to show that a rule limited to one
    #    application follows the token and nothing else.  There is nothing
    #    student specific in it, so the whole class shares one: tokens are
    #    limited to twenty live ones per portal account, and one per student
    #    here would halve the class size for no benefit.
    identity["registry_token_app"] = shared_app_token()
    identity["registry_app"] = APP_DEMO
    identity["registry_url"] = REGISTRY_URL
    identity["services_ip"] = NODE_IP

    # 5. an account on the findings platform, scoped to this student.  Day 19
    #    signs in with it in a browser, mints its own API token and reads its
    #    own findings; another student's finding id answers 404, not 403.
    identity.update(sast_account(student))

    # 5b. and something for that platform to scan.  A developer account may run
    #     a scan but may not add the account it reads from, so this is made for
    #     them, against their own Git namespace only.
    identity.update(sast_connection(student, identity.get("git_password", "")))

    # 6. an account on the package registry's portal, so Day 6 can read the rule
    #    that refused a package rather than be told what it says.
    identity.update(registry_account(student))

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path, "w") as fh:
        json.dump(identity, fh)
    os.chmod(state_path, 0o600)
    return identity


def deprovision(student: str) -> dict:
    run([VCLUSTER, "delete", student])
    forgejo("DELETE", f"/admin/users/{student}?purge=true")
    if os.path.exists(REGISTRY_SCRIPT):
        run([REGISTRY_SCRIPT, "delete", student])
    p = os.path.join(STATE_DIR, f"{student}.json")
    if os.path.exists(p):
        os.remove(p)
    return {"student": student, "removed": True}


class Handler(BaseHTTPRequestHandler):
    server_version = "lab-provision/1.0"

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        # An empty or missing secret file must lock the door, not open it: an
        # empty header would otherwise compare equal to an empty secret.
        try:
            secret = read(SECRET_FILE).strip()
        except OSError:
            return False
        return bool(secret) and secrets.compare_digest(self.headers.get("X-Lab-Secret", ""), secret)

    def _student(self) -> str | None:
        name = self.path.rstrip("/").rsplit("/", 1)[-1]
        return name if ID_RE.match(name) else None

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            return self._reply(200, {"ok": True})
        if not self._authorized():
            return self._reply(401, {"error": "unauthorized"})
        student = self._student()
        if not student:
            return self._reply(400, {"error": "bad student id"})
        p = os.path.join(STATE_DIR, f"{student}.json")
        if not os.path.exists(p):
            return self._reply(404, {"error": "no identity"})
        self._reply(200, json.loads(read(p)))

    def do_POST(self) -> None:
        if not self._authorized():
            return self._reply(401, {"error": "unauthorized"})
        student = self._student()
        if not student:
            return self._reply(400, {"error": "bad student id"})
        try:
            self._reply(200, provision(student))
        except Exception as exc:  # report the failure, never a half-truth
            self._reply(500, {"error": str(exc)[:500]})

    def do_DELETE(self) -> None:
        if not self._authorized():
            return self._reply(401, {"error": "unauthorized"})
        student = self._student()
        if not student:
            return self._reply(400, {"error": "bad student id"})
        try:
            self._reply(200, deprovision(student))
        except Exception as exc:
            self._reply(500, {"error": str(exc)[:500]})

    def log_message(self, fmt: str, *args) -> None:  # one tidy line per request
        print("lab-provision: " + fmt % args, flush=True)


if __name__ == "__main__":
    os.makedirs(STATE_DIR, exist_ok=True)
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()
