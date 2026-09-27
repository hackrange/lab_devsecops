"""Week 2 lab checks: dependencies, images, and the pipeline (Days 6 to 10).

Days 6 to 8 happen on the lab Git server: pull requests the student opens with
curl and merges there.  Days 9 and 10 build, sign, and attest images, which
only GitHub can do, so those checks read the student's PUBLIC GitHub
repository (anonymously, through GitHub's REST API) and GitHub Container
Registry (through the anonymous pull-token flow).

Most of what these labs teach happens in a disposable terminal: refusals,
exit codes, tampered hashes.  Those are ticked by the student.  A check here
only grades what persists, and it grades the pull request that made a change
rather than today's main whenever a later day rewrites the same file (Day 8
removes the is-number that Day 6 added, and Day 10 rewrites Day 9's image
workflow).

Author: Tim Rice
"""

from __future__ import annotations

import base64
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .registry import check

WORKFLOW_DIR = ".github/workflows"
HEX64 = re.compile(r"@sha256:[a-f0-9]{64}\b")


# ================================================================ small helpers

def _lines_of_section(text: str, day: int) -> str:
    """The learning-log text under "## Day N:", up to the next level-2 heading."""
    m = re.search(rf"^## Day {day}\b.*$", text or "", re.M)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def _table_rows(text: str) -> list[list[str]]:
    """Every Markdown table row as a list of stripped cells, separators dropped."""
    rows = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and any(cells):
            continue
        rows.append(cells)
    return rows


def _diff_changes(diff: str) -> dict[str, list[str]]:
    """{path: [added/removed lines, with their + or - sign]} from a unified diff."""
    out: dict[str, list[str]] = {}
    cur = None
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            cur = m.group(2) if m else None
            if cur:
                out.setdefault(cur, [])
        elif cur and line[:1] in "+-" and not line.startswith(("+++", "---")):
            out[cur].append(line)
    return out


# ================================================================ lab Git server

def _pr_diff(ctx, number) -> str:
    status, body = ctx.git(f"/repos/{ctx.repo}/pulls/{number}.diff", raw=True)
    return body if status == 200 and isinstance(body, str) else ""


def _find_merged_pr(ctx, wanted, prefer=lambda p: False, limit: int = 25):
    """The newest merged pull request whose diff satisfies wanted(changes).

    Likely candidates (by branch or title) are read first, so a normal student
    costs one or two diff requests, not twenty-five.
    """
    merged = ctx.merged_pulls()
    ordered = [p for p in merged if prefer(p)] + [p for p in merged if not prefer(p)]
    for p in ordered[:limit]:
        changes = _diff_changes(_pr_diff(ctx, p.get("number")))
        if changes and wanted(changes):
            return p, changes
    return None, {}


def _head_ref(p: dict) -> str:
    return ((p.get("head") or {}).get("ref") or "").lower()


def _pr_label(p: dict) -> str:
    return f"PR #{p.get('number')} \"{(p.get('title') or '').strip()}\""


# ================================================================ GitHub (public)

def _gh_problem(status: int, what: str) -> str:
    if status == 403 or status == 429:
        return "GitHub is limiting how often this lab may ask it questions.  Wait a few minutes and check again."
    if status == 404:
        return f"GitHub could not find {what}.  Check your GitHub username at the top of this page, and that the repository is public."
    if status == 0:
        return "This lab could not reach GitHub just now.  Check again in a minute."
    return f"GitHub answered {status} when asked for {what}."


def _gh_repo(ctx) -> str:
    return ctx.github_repo()


def _gh_main_sha(ctx) -> tuple[int, str]:
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/commits/main")
    if status == 200 and isinstance(body, dict):
        return 200, body.get("sha", "")
    return status, ""


def _gh_file(ctx, ref: str, path: str) -> str | None:
    """A file's text in the GitHub repository at a commit, or None.

    raw.githubusercontent.com does not count against the anonymous API limit
    (60 requests an hour), and asking for a commit SHA rather than a branch
    name dodges its five-minute cache.  The contents API is the fallback.
    """
    repo = _gh_repo(ctx)
    if not repo or not ref:
        return None
    key = ("GHRAW", repo, ref, path)
    if key in ctx._cache:
        return ctx._cache[key]
    text = None
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{urllib.parse.quote(path)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hackrange-lab"})
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=20) as r:
            text = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        status, body = ctx.github(f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}")
        if status == 200 and isinstance(body, dict) and body.get("content"):
            try:
                text = base64.b64decode(body["content"]).decode("utf-8", "replace")
            except (ValueError, TypeError):
                text = None
    ctx._cache[key] = text
    return text


def _gh_workflow_names(ctx, ref: str) -> list[str]:
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/contents/{WORKFLOW_DIR}?ref={ref}")
    if status != 200 or not isinstance(body, list):
        return []
    return sorted(i["name"] for i in body
                  if isinstance(i, dict) and i.get("type") == "file"
                  and i.get("name", "").endswith((".yml", ".yaml")))


def _gh_merged_pulls(ctx) -> tuple[int, list]:
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/pulls?state=closed&per_page=50")
    if status != 200 or not isinstance(body, list):
        return status, []
    return 200, [p for p in body if isinstance(p, dict) and p.get("merged_at")]


def _gh_pr_files(ctx, number) -> list:
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/pulls/{number}/files?per_page=100")
    return body if status == 200 and isinstance(body, list) else []


def _gh_find_pr(ctx, wanted, prefer=lambda p: False, limit: int = 6):
    """(status, pr, files) for the newest merged GitHub PR whose files satisfy wanted(paths).

    Every file list costs one anonymous API request, so this reads the likely
    candidates first and gives up after a handful.
    """
    status, merged = _gh_merged_pulls(ctx)
    if status != 200:
        return status, None, []
    ordered = [p for p in merged if prefer(p)] + [p for p in merged if not prefer(p)]
    for p in ordered[:limit]:
        files = _gh_pr_files(ctx, p.get("number"))
        paths = {f.get("filename", "") for f in files if isinstance(f, dict)}
        if wanted(paths):
            return 200, p, files
    return 200, None, []


def _gh_image_runs(ctx) -> tuple[int, list]:
    """Successful push runs of image.yml on main, newest first."""
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/actions/workflows/image.yml/runs"
                              "?branch=main&event=push&status=success&per_page=10")
    if status != 200 or not isinstance(body, dict):
        return status, []
    runs = [r for r in body.get("workflow_runs") or []
            if r.get("conclusion") == "success" and r.get("head_branch") == "main"]
    return 200, runs


# ================================================================ GHCR (anonymous)

_MANIFEST_TYPES = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def _ghcr_digest(ctx, ref: str) -> tuple[str, str]:
    """("ok", digest), ("missing", ""), ("private", "") or ("error", "") for
    ghcr.io/<github user>/secure-build-lab:<ref>, asked anonymously, exactly the
    way crane would without logging in."""
    name = _gh_repo(ctx).lower()
    if not name:
        return "error", ""
    key = ("GHCR", name, ref)
    if key in ctx._cache:
        return ctx._cache[key]
    tls = ssl.create_default_context()
    result = ("error", "")
    try:
        treq = urllib.request.Request(f"https://ghcr.io/token?scope=repository:{name}:pull",
                                      headers={"User-Agent": "hackrange-lab"})
        with urllib.request.urlopen(treq, context=tls, timeout=20) as r:
            token = json.loads(r.read().decode() or "{}").get("token", "")
        mreq = urllib.request.Request(f"https://ghcr.io/v2/{name}/manifests/{urllib.parse.quote(ref)}",
                                      headers={"User-Agent": "hackrange-lab", "Accept": _MANIFEST_TYPES,
                                               "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(mreq, context=tls, timeout=20) as r:
            digest = r.headers.get("Docker-Content-Digest", "")
            result = ("ok", digest) if digest.startswith("sha256:") else ("error", "")
    except urllib.error.HTTPError as e:
        # A private package (or none at all) refuses the anonymous token with
        # 401/403; a public package without this tag answers 404.
        result = ("missing", "") if e.code == 404 else ("private", "") if e.code in (401, 403) else ("error", "")
    except (urllib.error.URLError, OSError, ValueError):
        result = ("error", "")
    ctx._cache[key] = result
    return result


def _ghcr_problem(state: str) -> str:
    if state == "private":
        return ("GitHub Container Registry refused an anonymous pull, so the package is private or does not "
                "exist yet.  Make it public: Packages, secure-build-lab, Package settings, Change visibility "
                "(Day 9, Stop 7).")
    return "This lab could not reach GitHub Container Registry just now.  Check again in a minute."


# ================================================================ workflow text

USES_RE = re.compile(r"""^\s*(?:-\s+)?uses:\s*["']?([^\s"'#]+)["']?\s*(#.*)?$""")


def _unpinned_uses(text: str) -> list[str]:
    """Every uses: line not pinned to a full commit SHA with a version comment."""
    bad = []
    for line in (text or "").splitlines():
        m = USES_RE.match(line)
        if not m:
            continue
        ref, comment = m.group(1), (m.group(2) or "").lstrip("#").strip()
        if ref.startswith(("./", "$/")):
            continue  # a workflow in this same repository: nothing to pin
        if ref.startswith("docker://"):
            if not HEX64.search(ref):
                bad.append(ref)
            continue
        if not re.search(r"@[0-9a-f]{40}$", ref) or not comment:
            bad.append(ref)
    return bad


def _permissions_problem(text: str) -> str:
    """Why a workflow's permissions are not least privilege, or "" if they are."""
    if re.search(r"^\s*permissions:\s*write-all\b", text, re.M):
        return "grants write-all"
    if re.search(r"^permissions:", text, re.M):
        return ""
    # No workflow-wide default, so every job has to set its own.
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^jobs:\s*$", l))
    except StopIteration:
        return "has no permissions: block"
    jobs: dict[str, bool] = {}
    indent = None
    current = None
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        lead = len(line) - len(line.lstrip())
        if lead == 0:
            break
        if indent is None:
            indent = lead
        if lead == indent and re.match(r"^\s*[A-Za-z0-9_-]+:\s*$", line):
            current = line.strip().rstrip(":")
            jobs[current] = False
        elif current and re.match(r"^\s*permissions:", line) and lead > indent:
            if lead <= indent + 4:
                jobs[current] = True
    missing = [j for j, ok in jobs.items() if not ok]
    if not jobs or missing:
        return "has no permissions: block" + (f" for job {', '.join(missing)}" if missing else "")
    return ""


def _audit_workflows(ctx, ref: str) -> tuple[list[str], list[str]]:
    """(names, problems) for every workflow on GitHub at one commit."""
    names = _gh_workflow_names(ctx, ref)
    problems = []
    for n in names:
        text = _gh_file(ctx, ref, f"{WORKFLOW_DIR}/{n}")
        if text is None:
            problems.append(f"{n}: could not be read")
            continue
        bad = _unpinned_uses(text)
        if bad:
            problems.append(f"{n}: not pinned to a SHA with a version comment: {', '.join(bad[:3])}"
                            + (" and more" if len(bad) > 3 else ""))
        perm = _permissions_problem(text)
        if perm:
            problems.append(f"{n} {perm}")
    return names, problems


# ================================================================ Day 6

def _adds_is_number(changes: dict) -> bool:
    return any(l.startswith("+") and '"is-number"' in l for l in changes.get("package.json", []))


@check("d06_is_number_pr")
def d06_is_number_pr(ctx):
    pr, _ = _find_merged_pr(ctx, _adds_is_number,
                            prefer=lambda p: "is-number" in _head_ref(p) or "is-number" in (p.get("title") or "").lower())
    if not pr:
        open_one = [p for p in ctx.pulls("open") if "is-number" in _head_ref(p)]
        if open_one:
            return False, (f"{_pr_label(open_one[0])} is open but not merged yet.  Merge it once the secret scan "
                           "is green (Day 6, Stop 2).")
        return False, ("No merged pull request adds is-number to package.json.  Do Day 6, Stop 2: branch "
                       "deps/is-number, npm install --save-exact, open the PR, and merge it.")
    body = pr.get("body") or ""
    if "is-number" not in body.lower():
        return False, (f"{_pr_label(pr)} is merged, but its description never mentions is-number.  Edit the PR "
                       "description on the lab Git server and fill in the \"Dependencies changed\" section: what "
                       "you added (is-number 7.0.0), and why (Day 6, Stop 2).")
    return True, f"{_pr_label(pr)} added is-number and its description explains the dependency change."


@check("d06_inventory")
def d06_inventory(ctx):
    inv = ctx.file("docs/dependency-inventory.md")
    if inv is None:
        return False, ("docs/dependency-inventory.md is not on main.  Create it in the Day 6 wrap-up, open the "
                       "docs/day6 pull request, and merge it.")
    rows = _table_rows(inv)
    if len(rows) < 2 or not any("package" in c.lower() for c in rows[0]):
        return False, ("docs/dependency-inventory.md has no inventory table.  It needs a header row starting with "
                       "Package and at least one package row (Day 6 wrap-up).")
    if not ctx.log_has_day(6):
        return False, ("The inventory is there, but docs/learning-log.md on main has no \"## Day 6:\" entry.  "
                       "Merge the docs/day6 pull request (Day 6 wrap-up).")
    section = _lines_of_section(ctx.file("docs/learning-log.md") or "", 6)
    if "labrepo" not in section.lower() and not re.search(r"^\s*\d+\s+[\w.-]+\.[\w.:-]+\s*$", section, re.M):
        return False, ("The inventory is there, but your Day 6 log entry does not show where your bytes come from.  "
                       "Paste the output of the Stop 7 jq command (the host counts, such as labrepo.lab:8443) in "
                       "place of \"(paste the jq output)\" and merge that change.")
    return True, (f"docs/dependency-inventory.md lists {len(rows) - 1} package row(s), and your Day 6 log shows "
                  "where your bytes came from.")


# ================================================================ Day 7

def _worksheets(text: str) -> tuple[bool, bool]:
    """(identity worksheet filled in, firewall coverage worksheet filled in)."""
    rows = _table_rows(text)
    eco = re.compile(r"^\**(npm|pypi|maven|debian|rpm|oci)\b", re.I)
    ws1 = sum(1 for r in rows if r and eco.match(r[0]) and sum(1 for c in r if c) >= 3) >= 3
    ws2 = False
    for i, r in enumerate(rows):
        joined = " ".join(r).lower()
        if "maven" in joined and ("debian" in joined or "apt" in joined) and ("rpm" in joined or "dnf" in joined):
            filled = 0
            for nxt in rows[i + 1:i + 8]:
                if nxt and nxt[0] and sum(1 for c in nxt[1:] if c) >= 2:
                    filled += 1
            if filled >= 3:
                ws2 = True
                break
    return ws1, ws2


@check("d07_log_pr")
def d07_log_pr(ctx):
    cands = [p for p in ctx.pulls("all")
             if "day7" in _head_ref(p) or "day 7" in (p.get("title") or "").lower()]
    if not cands:
        return False, ("There is no Day 7 pull request on the lab Git server.  Push docs/day7 and open the pull "
                       "request with the curl command in the Day 7 wrap-up.")
    pr = next((p for p in cands if p.get("merged")), cands[0])
    ref = pr.get("merge_commit_sha") if pr.get("merged") else (pr.get("head") or {}).get("sha")
    log = ctx.file("docs/learning-log.md", ref=ref or "main") or ""
    if not re.search(r"^## Day 7\b", log, re.M):
        log = ctx.file("docs/learning-log.md") or ""
    section = _lines_of_section(log, 7)
    if not section:
        return False, (f"{_pr_label(pr)} exists, but its docs/learning-log.md has no \"## Day 7:\" entry.  Add "
                       "it as shown in the Day 7 wrap-up and push the branch again.")
    ws1, ws2 = _worksheets(section + "\n" + (pr.get("body") or ""))
    missing = []
    if not ws1:
        missing.append("Worksheet 1 (one identity per ecosystem, with your own column filled in)")
    if not ws2:
        missing.append("Worksheet 2 (package firewall coverage for Maven, APT, RPM and OCI, filled in)")
    if missing:
        return False, (f"{_pr_label(pr)} has your Day 7 log, but not {' or '.join(missing)}.  Paste the filled-in "
                       "tables into the Day 7 log entry (or the PR description) and push again.")
    state = "merged" if pr.get("merged") else "open"
    return True, f"{_pr_label(pr)} ({state}) carries your Day 7 log with both worksheets filled in."


# ================================================================ Day 8

def _check_triage(text: str) -> str:
    """Why docs/triage.md falls short, or "" if it has everything."""
    low = text.lower()
    decisions = 0
    for r in _table_rows(text):
        joined = " ".join(r).lower()
        if joined.startswith("#") or "decision" in joined and "finding" in joined:
            continue  # the header row
        if re.search(r"remediat|accept|not[ _]affected|tabletop|upgrade|fix now|mitigat", joined):
            decisions += 1
    if decisions < 3:
        return f"has {decisions} decision row(s); it needs three (Day 8, Stops 6 and 8)"
    if not re.search(r"expir\w*\W{0,6}\d{4}-\d{2}-\d{2}", low):
        return "has no exception with an expiry date (Expires: YYYY-MM-DD) (Day 8, Stop 8)"
    if "sbom record" not in low and not re.search(r"sbom[\w.-]*\.json", low):
        return "has no SBOM record section (Day 8, Stop 8)"
    return ""


def _check_vex(text: str) -> str:
    """Why the OpenVEX file falls short, or "" if it is a usable statement."""
    try:
        doc = json.loads(text)
    except ValueError:
        return "is not valid JSON"
    if not isinstance(doc, dict) or "openvex" not in str(doc.get("@context", "")):
        return "has no OpenVEX @context"
    stmts = doc.get("statements")
    if not isinstance(stmts, list) or not stmts:
        return "has no statements"
    for s in stmts:
        if not isinstance(s, dict) or not s.get("status"):
            return "has a statement with no status"
        if s.get("status") == "not_affected" and not (s.get("justification") or s.get("impact_statement")):
            return "says not_affected without a justification or impact_statement"
    ids = [str(p.get("@id", "")) for s in stmts for p in (s.get("products") or []) if isinstance(p, dict)]
    if not any("sha256:" in i for i in ids):
        return "names no product by digest (the pkg:oci/...@sha256: PURL from Stop 5)"
    return ""


@check("d08_triage_pr")
def d08_triage_pr(ctx):
    pr, changes = _find_merged_pr(
        ctx, lambda c: "docs/triage.md" in c or "vex/node-base.openvex.json" in c,
        prefer=lambda p: "triage" in _head_ref(p) or "triage" in (p.get("title") or "").lower())
    if not pr:
        return False, ("No merged pull request adds docs/triage.md and vex/node-base.openvex.json.  Commit both on "
                       "sec/day8-triage, open the PR, and merge it (Day 8, Stop 8).")
    ref = pr.get("merge_commit_sha") or "main"
    triage = ctx.file("docs/triage.md", ref=ref)
    vex = ctx.file("vex/node-base.openvex.json", ref=ref)
    if triage is None or vex is None:
        gone = [n for n, t in (("docs/triage.md", triage), ("vex/node-base.openvex.json", vex)) if t is None]
        return False, (f"{_pr_label(pr)} is merged, but {' and '.join(gone)} was not part of it.  Add the missing "
                       "file in a pull request of its own (Day 8, Stops 7 and 8).")
    why = _check_triage(triage)
    if why:
        return False, f"docs/triage.md in {_pr_label(pr)} {why}."
    why = _check_vex(vex)
    if why:
        return False, f"vex/node-base.openvex.json in {_pr_label(pr)} {why}."
    return True, (f"{_pr_label(pr)} merged docs/triage.md (three decisions, a dated exception, the SBOM record) "
                  "and a valid OpenVEX statement pinned to an image digest.")


def _removes_is_number(changes: dict) -> bool:
    return any(l.startswith("-") and '"is-number"' in l for l in changes.get("package.json", []))


@check("d08_remove_is_number")
def d08_remove_is_number(ctx):
    pr, _ = _find_merged_pr(ctx, _removes_is_number,
                            prefer=lambda p: "remove" in _head_ref(p) or "remove" in (p.get("title") or "").lower())
    if not pr:
        return False, ("No merged pull request removes is-number from package.json.  Do Day 8, Stop 9: branch "
                       "deps/remove-is-number, npm uninstall, open the PR, and merge it.")
    body = (pr.get("body") or "").lower()
    if "is-number" not in body or ("sbom" not in body and "pkg:npm" not in body):
        return False, (f"{_pr_label(pr)} removed is-number, but its description does not show the SBOM diff.  "
                       "Edit the description and paste the diff line (- pkg:npm/is-number@7.0.0) (Day 8, Stop 9).")
    return True, f"{_pr_label(pr)} removed is-number, with the SBOM diff in its description."


# ================================================================ Day 9

D09_PATHS = ("Dockerfile", "Dockerfile.distroless", ".dockerignore", ".github/workflows/image.yml")


def _d09_missing(paths: set) -> list[str]:
    missing = [p for p in D09_PATHS if p not in paths]
    if not any(p.startswith(".conftest/policy/") for p in paths):
        missing.append(".conftest/policy/")
    return missing


@check("d09_dockerfile_pr")
def d09_dockerfile_pr(ctx):
    status, pr, files = _gh_find_pr(
        ctx, lambda paths: not _d09_missing(paths),
        prefer=lambda p: "container" in ((p.get("head") or {}).get("ref") or "").lower()
        or "dockerfile" in (p.get("title") or "").lower())
    if status != 200:
        return False, _gh_problem(status, "the pull requests of " + _gh_repo(ctx))
    if not pr:
        return False, ("No merged pull request on GitHub adds all of Dockerfile, Dockerfile.distroless, "
                       ".dockerignore, .conftest/policy/ and .github/workflows/image.yml together.  Ship them in one "
                       "PR from container/dockerfile and merge it (Day 9, Stop 7).")
    docker = _gh_file(ctx, pr.get("merge_commit_sha") or "", "Dockerfile")
    if docker is None:
        docker = next((f.get("patch", "") for f in files if f.get("filename") == "Dockerfile"), "")
        docker = "\n".join(l[1:] for l in docker.splitlines() if l.startswith("+"))
    froms = [l for l in docker.splitlines() if re.match(r"^\s*FROM\s", l, re.I)]
    problems = []
    if not froms or not all(HEX64.search(l) for l in froms):
        problems.append("its FROM is not pinned by a real 64-character digest (Stop 5)")
    users = re.findall(r"^\s*USER\s+(\S+)", docker, re.I | re.M)
    if not users or not re.fullmatch(r"1000(:1000)?", users[-1]):
        problems.append("its last USER is not 1000:1000 (Stop 5)")
    if not re.search(r"^\s*HEALTHCHECK\s", docker, re.I | re.M):
        problems.append("it has no HEALTHCHECK (Stop 5)")
    if problems:
        return False, f"GitHub PR #{pr.get('number')} is merged, but the Dockerfile it merged: " + "; ".join(problems) + "."
    return True, (f"GitHub PR #{pr.get('number')} merged both Dockerfiles, .dockerignore, your policy and image.yml, "
                  "with the base pinned by digest, USER 1000:1000 and a HEALTHCHECK.")


def _policy_problem(tests: str | None, policy: str | None) -> str:
    if tests is None or policy is None:
        return "missing"
    names = re.findall(r"^\s*test_\w+", tests, re.M)
    if len(names) < 3:
        return f"dockerfile_test.rego has {len(names)} test(s); it needs three (Day 9, Stop 5)"
    if "REPLACE_ME" not in tests and "placeholder" not in tests.lower():
        return "dockerfile_test.rego has no placeholder-digest test (test_placeholder_digest_is_denied, Day 9, Stop 5)"
    if not re.search(r"\{64\}", policy):
        return ("dockerfile.rego still accepts any text after @sha256:.  Apply the Stop 5 fix that demands a "
                "64-character hex digest")
    return ""


@check("d09_policy_tests")
def d09_policy_tests(ctx):
    # The lab Git server first: it needs no GitHub username.  Day 9 merges on
    # GitHub, so fall back to GitHub's main when the lab copy has not caught up.
    t, p = ctx.file(".conftest/policy/dockerfile_test.rego"), ctx.file(".conftest/policy/dockerfile.rego")
    why, where = _policy_problem(t, p), "the lab Git server's main"
    if why and ctx.github_user:
        status, sha = _gh_main_sha(ctx)
        if sha:
            gt = _gh_file(ctx, sha, ".conftest/policy/dockerfile_test.rego")
            gp = _gh_file(ctx, sha, ".conftest/policy/dockerfile.rego")
            gwhy = _policy_problem(gt, gp)
            if not gwhy or why == "missing":
                why, where = gwhy, "GitHub's main"
    if why == "missing":
        return False, (".conftest/policy/dockerfile.rego and dockerfile_test.rego are not on main.  Write them in "
                       "Day 9, Stops 3 and 5, and merge them.  (If they are only on GitHub, enter your GitHub "
                       "username at the top of this page.)")
    if why:
        return False, f"On {where}, {why}."
    return True, (f"On {where}, your policy demands a real 64-character digest and dockerfile_test.rego has three "
                  "tests, including the placeholder-digest test.")


@check("d09_image_run")
def d09_image_run(ctx):
    status, runs = _gh_image_runs(ctx)
    if status == 404:
        return False, ("GitHub has no image.yml workflow in " + _gh_repo(ctx) + ".  Add .github/workflows/image.yml "
                       "and merge it (Day 9, Stop 7).")
    if status != 200:
        return False, _gh_problem(status, "the image workflow runs")
    if not runs:
        return False, ("There is no green run of the image workflow on main, triggered by a push.  Merge the Day 9 "
                       "PR and watch the run on main (Day 9, Stop 7).")
    last_state = ""
    for run in runs[:6]:
        sha = run.get("head_sha", "")
        s1, d1 = _ghcr_digest(ctx, sha)
        s2, d2 = _ghcr_digest(ctx, f"{sha}-distroless")
        if s1 == "ok" and s2 == "ok":
            return True, (f"Image run #{run.get('run_number')} on main is green, and ghcr.io serves both images for "
                          f"{sha[:7]}: {d1[:19]}... and {d2[:19]}... (distroless).")
        if "private" in (s1, s2) or "error" in (s1, s2):
            last_state = "private" if "private" in (s1, s2) else "error"
            break
    if last_state:
        return False, _ghcr_problem(last_state)
    return False, ("The image workflow is green on main, but ghcr.io does not have both the <sha> and the "
                   "<sha>-distroless tags for any recent green run.  Check that main's run pushed both images "
                   "(Day 9, Stop 7).")


@check("d09_required_check")
def d09_required_check(ctx):
    status, rules = ctx.github(f"/repos/{_gh_repo(ctx)}/rules/branches/main")
    if status != 200 or not isinstance(rules, list):
        return False, _gh_problem(status, "the rules on main")
    contexts = []
    for r in rules:
        if isinstance(r, dict) and r.get("type") == "required_status_checks":
            for c in (r.get("parameters") or {}).get("required_status_checks") or []:
                contexts.append(str(c.get("context", "")))
    if not contexts:
        return False, ("main has no ruleset that requires status checks.  Edit protect-main under Settings, Rules, "
                       "Rulesets (Day 3), then add dockerfile-policy (Day 9, Stop 7).")
    if not any("dockerfile-policy" in c for c in contexts):
        return False, (f"protect-main requires {', '.join(contexts)}, but not dockerfile-policy.  Add it to the "
                       "required status checks (Day 9, Stop 7).")
    return True, "main requires these checks: " + ", ".join(contexts) + "."


# ================================================================ Day 10

def _threat_model_pr(ctx):
    return _gh_find_pr(ctx, lambda paths: "docs/pipeline-threat-model.md" in paths,
                       prefer=lambda p: "day10" in ((p.get("head") or {}).get("ref") or "").lower()
                       or "harden" in (p.get("title") or "").lower())


@check("d10_pinned")
def d10_pinned(ctx):
    status, sha = _gh_main_sha(ctx)
    if not sha:
        return False, _gh_problem(status, "main of " + _gh_repo(ctx))
    names, problems = _audit_workflows(ctx, sha)
    if not names:
        return False, "GitHub's main has no workflows in .github/workflows.  Push your Day 9 work to GitHub first."
    if not problems:
        return True, (f"All {len(names)} workflows on main ({', '.join(names)}) pin every action to a SHA with a "
                      "version comment and set their own permissions.")
    # A later day may add a workflow; the hardened set merged on Day 10 still counts.
    _, pr, _ = _threat_model_pr(ctx)
    if pr and pr.get("merge_commit_sha"):
        old_names, old_problems = _audit_workflows(ctx, pr["merge_commit_sha"])
        if old_names and not old_problems:
            return True, (f"The workflows merged with GitHub PR #{pr.get('number')} ({', '.join(old_names)}) pin "
                          "every action to a SHA with a version comment and set their own permissions.")
    return False, "On GitHub's main: " + "; ".join(problems[:4]) + ".  Fix these in Day 10, Stop 5."


def _signing_steps(text: str) -> list[str]:
    """What the image workflow is missing for keyless signing and attestations."""
    missing = []
    if not re.search(r"cosign\s+sign\b", text):
        missing.append("a cosign sign step")
    if not re.search(r"uses:\s*actions/attest(-build-provenance)?@", text):
        missing.append("an actions/attest provenance step")
    if not re.search(r"cosign\s+attest\b|actions/attest-sbom@|sbom-path:", text):
        missing.append("an SBOM attestation step")
    if not re.search(r"id-token:\s*write", text):
        missing.append("id-token: write")
    return missing


@check("d10_signed_image")
def d10_signed_image(ctx):
    status, runs = _gh_image_runs(ctx)
    if status == 404:
        return False, "GitHub has no image.yml workflow.  Finish Day 9 first, then Day 10, Stop 7."
    if status != 200:
        return False, _gh_problem(status, "the image workflow runs")
    signing = [r for r in runs[:8]
               if not _signing_steps(_gh_file(ctx, r.get("head_sha", ""), f"{WORKFLOW_DIR}/image.yml") or "")]
    if not signing:
        status, sha = _gh_main_sha(ctx)
        text = _gh_file(ctx, sha, f"{WORKFLOW_DIR}/image.yml") if sha else None
        missing = _signing_steps(text or "")
        if text is not None and missing:
            return False, ("image.yml on main is missing " + ", ".join(missing) + ".  Add the Day 10, Stop 7 steps, "
                           "merge, and let it run on main.")
        return False, ("There is no green run on main of an image.yml that signs and attests.  Merge the Day 10, "
                       "Stop 7 changes and let the run on main finish green.")
    run = signing[0]
    sha = run.get("head_sha", "")
    state, digest = _ghcr_digest(ctx, sha)
    if state == "missing":
        return False, (f"Run #{run.get('run_number')} is green, but ghcr.io has no image tagged {sha[:7]}.  Check "
                       "that the build step pushes a tag named after the commit (Day 10, Stop 7).")
    if state != "ok":
        return False, _ghcr_problem(state)
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/attestations/{digest}")
    if status != 200 or not isinstance(body, dict):
        return False, _gh_problem(status, "the attestations for " + digest[:19] + "...")
    count = len(body.get("attestations") or [])
    if not count:
        return False, (f"Run #{run.get('run_number')} is green, but GitHub holds no attestation for the pushed "
                       f"digest {digest[:19]}....  Check the Attest build provenance step (Day 10, Stop 7).")
    return True, (f"Run #{run.get('run_number')} on main signed and attested {digest[:19]}..., and GitHub holds "
                  f"{count} attestation(s) for it.")


@check("d10_threat_model_pr")
def d10_threat_model_pr(ctx):
    status, pr, _ = _threat_model_pr(ctx)
    if status != 200:
        return False, _gh_problem(status, "the pull requests of " + _gh_repo(ctx))
    if not pr:
        return False, ("No merged pull request on GitHub adds docs/pipeline-threat-model.md.  Commit it on "
                       "docs/day10, open the PR with gh pr create, and merge it when green (Day 10, Stop 10).")
    text = _gh_file(ctx, pr.get("merge_commit_sha") or "", "docs/pipeline-threat-model.md") or ""
    rows = [r for r in _table_rows(text)[1:] if len([c for c in r if c]) >= 3]
    if len(rows) < 3:
        return False, (f"GitHub PR #{pr.get('number')} merged docs/pipeline-threat-model.md, but it has "
                       f"{len(rows)} complete threat row(s).  Each threat needs a control and a verification "
                       "(Day 10, Stop 10).")
    head = (pr.get("head") or {}).get("sha", "")
    status, body = ctx.github(f"/repos/{_gh_repo(ctx)}/commits/{head}/check-runs?per_page=100")
    if status != 200 or not isinstance(body, dict):
        return False, _gh_problem(status, "the checks on that pull request")
    checks = body.get("check_runs") or []
    bad = [c.get("name", "?") for c in checks
           if c.get("conclusion") not in ("success", "skipped", "neutral")]
    if not checks:
        return False, (f"GitHub PR #{pr.get('number')} was merged with no checks run on it.  Open the threat model "
                       "through a PR so your hardened workflows run on it (Day 10, Stop 10).")
    if bad:
        return False, (f"GitHub PR #{pr.get('number')} was merged, but these checks did not pass on it: "
                       f"{', '.join(bad[:5])}.  Fix them and merge a green PR (Day 10, Stop 10).")
    return True, (f"GitHub PR #{pr.get('number')} merged a threat model with {len(rows)} threats, and all "
                  f"{len(checks)} checks on it passed.")
