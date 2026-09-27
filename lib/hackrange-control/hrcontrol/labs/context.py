"""What a lab check can look at: the student's own lab, read as the student.

Every check asks questions of real things the student made, with the
student's own credentials, so a check can never see more than the student
could: their repository on the lab Git server (with its pull requests and
pipeline results), their Kubernetes cluster, the package registry's record of
what it served and refused, and their public GitHub repository.

Nothing here changes anything.  Answers are cached for the length of one
"Check my work", so ten checks that all read the learning log fetch it once.

Author: Tim Rice
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request

LAB_ENV = "/etc/hackrange/lab.env"
CA = "/etc/nginx/labtls/lab-ca.crt"
STUDENT = os.environ.get("HR_STUDENT", "student01")
KUBECONFIG = f"/etc/rancher/student-kubeconfigs/{STUDENT}.yaml"


def _env() -> dict:
    out = {}
    try:
        with open(LAB_ENV) as fh:
            for line in fh:
                if "=" in line and not line.startswith("#"):
                    k, v = line.rstrip("\n").split("=", 1)
                    out[k] = v
    except OSError:
        pass
    return out


class Context:
    def __init__(self, github_user: str = "") -> None:
        self.env = _env()
        self.user = self.env.get("LAB_GIT_USER", STUDENT)
        self.repo = f"{self.user}/secure-build-lab"
        self.github_user = github_user.strip()
        self._cache: dict = {}
        self._ssl = ssl.create_default_context(cafile=CA)

    # ---------------------------------------------------------- the lab Git server

    def _get(self, url: str, auth: str | None, ctx=None, raw: bool = False):
        key = ("GET", url)
        if key in self._cache:
            return self._cache[key]
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "hackrange-lab"})
        if auth:
            req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
                result = (r.status, body if raw else (json.loads(body) if body.strip() else None), dict(r.headers))
        except urllib.error.HTTPError as e:
            result = (e.code, None, dict(e.headers or {}))
        except (urllib.error.URLError, OSError, ValueError):
            result = (0, None, {})
        self._cache[key] = result
        return result

    def git(self, path: str, raw: bool = False):
        """(status, json-or-text) from the lab Git server's API, as the student."""
        auth = "Basic " + base64.b64encode(
            f"{self.user}:{self.env.get('LAB_GIT_PASSWORD', '')}".encode()).decode()
        status, body, _ = self._get(f"https://labgit.lab:8444/api/v1{path}", auth, self._ssl, raw)
        return status, body

    def file(self, path: str, ref: str = "main", repo: str | None = None) -> str | None:
        """A file's text on a branch of the student's repository, or None."""
        repo = repo or self.repo
        status, body = self.git(f"/repos/{repo}/raw/{urllib.parse.quote(path)}?ref={ref}", raw=True)
        return body if status == 200 else None

    def exists(self, path: str, ref: str = "main") -> bool:
        return self.file(path, ref) is not None

    def repo_info(self, repo: str | None = None) -> dict | None:
        status, body = self.git(f"/repos/{repo or self.repo}")
        return body if status == 200 else None

    def commits(self, ref: str = "main", limit: int = 50, repo: str | None = None, page: int = 1) -> list:
        status, body = self.git(f"/repos/{repo or self.repo}/commits?sha={ref}&limit={limit}&page={page}"
                                "&stat=false&files=false")
        return body if status == 200 and isinstance(body, list) else []

    def pulls(self, state: str = "all", repo: str | None = None) -> list:
        status, body = self.git(f"/repos/{repo or self.repo}/pulls?state={state}&limit=50")
        return body if status == 200 and isinstance(body, list) else []

    def merged_pulls(self) -> list:
        return [p for p in self.pulls("closed") if p.get("merged")]

    def statuses(self, ref: str) -> list:
        status, body = self.git(f"/repos/{self.repo}/commits/{ref}/statuses?limit=50")
        return body if status == 200 and isinstance(body, list) else []

    def all_statuses(self, limit_commits: int = 30) -> list:
        """Every pipeline result on the repository's recent commits, any branch."""
        out = []
        seen = set()
        for b in self.branches():
            for c in self.commits(b, limit=limit_commits):
                sha = c.get("sha")
                if sha and sha not in seen:
                    seen.add(sha)
                    out += self.statuses(sha)
        return out

    def branches(self) -> list:
        status, body = self.git(f"/repos/{self.repo}/branches?limit=50")
        return [b["name"] for b in body] if status == 200 and isinstance(body, list) else []

    def branch_protections(self) -> list:
        status, body = self.git(f"/repos/{self.repo}/branch_protections")
        return body if status == 200 and isinstance(body, list) else []

    def log_has_day(self, day: int) -> bool:
        text = self.file("docs/learning-log.md") or ""
        return f"## Day {day}:" in text or f"## Day {day} " in text

    def main_sha(self) -> str:
        c = self.commits("main", limit=1)
        return c[0]["sha"] if c else ""

    # ---------------------------------------------------------- the student's cluster

    def kubectl(self, *args: str) -> tuple[int, str]:
        try:
            p = subprocess.run(["/usr/local/bin/kubectl", "--kubeconfig", KUBECONFIG, "--request-timeout=15s", *args],
                               capture_output=True, text=True, timeout=30)
            return p.returncode, p.stdout
        except (OSError, subprocess.SubprocessError):
            return 1, ""

    def kjson(self, *args: str):
        rc, out = self.kubectl(*args, "-o", "json")
        try:
            return json.loads(out) if rc == 0 else None
        except ValueError:
            return None

    # ---------------------------------------------------------- GitHub (public)

    def github(self, path: str):
        """(status, json) from GitHub's public API for the student's account."""
        status, body, _ = self._get(f"https://api.github.com{path}", None, ssl.create_default_context())
        return status, body

    def github_repo(self) -> str:
        return f"{self.github_user}/secure-build-lab" if self.github_user else ""
