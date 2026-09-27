"""Week 1 lab checks: Days 1 to 5 (the repository, change control, CI, SAST, secrets).

Every check reads something that outlives the lab box: the student's
repository on the lab Git server (files on main, merged pull requests, branch
protections) or their public GitHub repository through GitHub's public API.
Anything that only ever existed in a terminal, a browser tab, or a scratch
folder the lab deletes is left for the student to tick instead.

GitHub allows about sixty unauthenticated lookups an hour from one address,
so each check asks for as little as it can, and the Context caches every
answer for the length of one "Check my work".

Author: Tim Rice
"""

from __future__ import annotations

import re

from .registry import check

REPO = "secure-build-lab"


# ---------------------------------------------------------------- small helpers

def _norm(text: str) -> str:
    """Lower case with runs of whitespace squeezed, so 'Node /  Test' matches 'node / test'."""
    return " ".join(str(text or "").lower().split())


def _day_re(day: int):
    # Matches "Log Day 2", "docs/day2-log", "day-02"; the (?!\d) keeps day 2 from matching day 20.
    return re.compile(rf"day[\s_-]*0?{day}(?!\d)", re.I)


def _log_detail(ctx, day: int, stop: str) -> tuple[bool, str]:
    if ctx.log_has_day(day):
        return True, f"docs/learning-log.md on main has a '## Day {day}:' entry."
    if not ctx.exists("docs/learning-log.md"):
        return False, ("docs/learning-log.md is not on main of secure-build-lab on the lab Git server. "
                       "Day 1 Stop 7 creates it; push it with git push.")
    return False, (f"docs/learning-log.md on main has no '## Day {day}:' entry yet. {stop} writes it; "
                   "merge its pull request and push main to the lab Git server.")


# ---------------------------------------------------------------- GitHub helpers

def _gh(ctx, path: str, missing: str = "") -> tuple[object, str]:
    """(body, "") on success, or (None, a sentence saying what went wrong)."""
    repo = ctx.github_repo()
    if not repo:
        return None, "Enter your GitHub username at the top of this page first."
    status, body = ctx.github(path.replace("{repo}", repo))
    if status == 200 and body is not None:
        return body, ""
    if status == 404:
        # A 404 on the repository itself and a 404 on something inside it read the
        # same to GitHub, so say both: the caller's hint first, then the repository.
        return None, (missing or f"GitHub has nothing at that address for {repo}.") + (
            f" If github.com/{repo} does not exist or is private, Day 2 Stop 1 creates it as a public repository.")
    if status in (403, 429):
        return None, ("GitHub asked the lab to slow down (it allows about 60 lookups an hour without "
                      "signing in). Try Check my work again in a few minutes.")
    if status == 0:
        return None, "The lab could not reach api.github.com. Try again in a minute."
    return None, f"GitHub answered HTTP {status} for {repo}. Try again in a minute."


def _gh_merged_pulls(ctx) -> tuple[list, str]:
    body, err = _gh(ctx, "/repos/{repo}/pulls?state=closed&base=main&per_page=100")
    if err:
        return [], err
    return [p for p in body if isinstance(p, dict) and p.get("merged_at")], ""


def _gh_closed_unmerged_pulls(ctx) -> tuple[list, str]:
    body, err = _gh(ctx, "/repos/{repo}/pulls?state=closed&base=main&per_page=100")
    if err:
        return [], err
    return [p for p in body if isinstance(p, dict) and not p.get("merged_at")], ""


def _gh_rules(ctx) -> tuple[list, str]:
    """The rules that actually apply to main right now (active rulesets only)."""
    body, err = _gh(ctx, "/repos/{repo}/rules/branches/main")
    if err:
        return [], err
    return [r for r in body if isinstance(r, dict)], ""


def _gh_required_checks(ctx) -> tuple[list, str]:
    rules, err = _gh_rules(ctx)
    out = []
    for r in rules:
        if r.get("type") == "required_status_checks":
            for c in (r.get("parameters") or {}).get("required_status_checks") or []:
                if isinstance(c, dict) and c.get("context"):
                    out.append(c["context"])
    return out, err


def _gh_runs(ctx, workflow: str, query: str = "", pages: int = 3) -> tuple[list, str]:
    """Runs of one workflow file, newest first, a few pages deep so Day 3's runs survive Day 20."""
    runs = []
    for page in range(1, pages + 1):
        body, err = _gh(ctx, f"/repos/{{repo}}/actions/workflows/{workflow}/runs?per_page=100&page={page}{query}",
                        missing=f"GitHub has no workflow named .github/workflows/{workflow} yet.")
        if err:
            return runs, ("" if runs else err)
        batch = body.get("workflow_runs") if isinstance(body, dict) else None
        if not isinstance(batch, list):
            break
        runs += [r for r in batch if isinstance(r, dict)]
        if len(batch) < 100:
            break
    return runs, ""


def _pr_label(p: dict) -> str:
    return f"#{p.get('number')} ({(p.get('head') or {}).get('ref', '?')})"


def _gh_log_pr(ctx, day: int, stop: str) -> tuple[bool, str]:
    """Day N's log entry is on main AND arrived through a merged GitHub pull request."""
    ok, detail = _log_detail(ctx, day, stop)
    if not ok:
        return ok, detail
    pulls, err = _gh_merged_pulls(ctx)
    if err:
        return False, err
    pat = _day_re(day)
    hit = next((p for p in pulls
                if pat.search((p.get("head") or {}).get("ref", "")) or pat.search(p.get("title") or "")), None)
    if not hit:
        return False, (f"The Day {day} log entry is on main, but no merged GitHub pull request for it was found "
                       f"(expected a branch like docs/day{day}-log). {stop} sends it through a pull request.")
    return True, f"The Day {day} log entry is on main, merged through GitHub pull request {_pr_label(hit)}."


def _in_history(ctx, sha: str, pages: int = 10) -> bool:
    """Is this commit somewhere in the lab's main (newest 500 commits)?"""
    for page in range(1, pages + 1):
        batch = ctx.commits("main", limit=50, page=page)
        if any(c.get("sha") == sha for c in batch):
            return True
        if len(batch) < 50:
            return False
    return False


def _in_sync(ctx, stop: str, day: int = 0) -> tuple[bool, str]:
    lab = ctx.main_sha()
    if not lab:
        return False, "The lab Git server has no main branch for secure-build-lab yet."
    body, err = _gh(ctx, "/repos/{repo}/branches/main", missing="GitHub has no main branch yet.")
    if err:
        return False, err
    gh = ((body or {}).get("commit") or {}).get("sha", "")
    if gh and gh == lab:
        return True, f"main is on {lab[:7]} on both the lab Git server and GitHub."
    # From Day 5 on the course works on the lab Git server alone, so the lab's
    # main moves ahead of GitHub's by design.  What the sync step protects is
    # that nothing merged on GitHub is missing from the lab: GitHub's main must
    # be somewhere in the lab's main history.
    if gh and _in_history(ctx, gh):
        return True, (f"Everything merged on GitHub (main {gh[:7]}) is on the lab Git server's main, "
                      f"which has moved on to {lab[:7]}.")
    # Later in the course GitHub moves on too (Weeks 2's pipeline work is merged
    # there), so what this day's wrap up promised is narrower: the merge of this
    # day's log pull request reached the lab's main.
    if day:
        pulls, _ = _gh_merged_pulls(ctx)
        pat = _day_re(day)
        hit = next((p for p in pulls if pat.search((p.get("head") or {}).get("ref", ""))
                    or pat.search(p.get("title") or "")), None)
        sha = (hit or {}).get("merge_commit_sha") or ""
        if sha and _in_history(ctx, sha):
            return True, (f"The Day {day} log merge from GitHub ({sha[:7]}) is on the lab Git server's main, "
                          "so both homes had the same history at the end of the day.")
    return False, (f"main differs: lab Git server {lab[:7]}, GitHub {gh[:7] or 'unknown'}, and GitHub's main is "
                   f"not in the lab's history. {stop}: run git fetch github, git merge --ff-only github/main, "
                   "then git push origin main.")


# ---------------------------------------------------------------- Day 1: Make It Run

@check("d01_repo")
def d01_repo(ctx):
    if not ctx.repo_info():
        return False, ("There is no secure-build-lab repository on the lab Git server yet. "
                       "Stop 5 creates it with one curl POST, then git push -u origin main.")
    n = len(ctx.commits("main"))
    if n == 0:
        return False, "secure-build-lab exists but main has no commits. Stop 5 ends with git push -u origin main."
    if n < 2:
        return False, ("secure-build-lab has 1 commit on main. Stop 7 makes the second one "
                       "(workflow map and learning log); commit it and git push.")
    shown = f"{n}+" if n >= 50 else str(n)
    return True, f"secure-build-lab is on the lab Git server with {shown} commits on main."


@check("d01_log")
def d01_log(ctx):
    return _log_detail(ctx, 1, "Stop 7")


# ---------------------------------------------------------------- Day 2: The Reviewed Change

@check("d02_merged_prs")
def d02_merged_prs(ctx):
    pulls, err = _gh_merged_pulls(ctx)
    if err:
        return False, err
    described = [p for p in pulls if (p.get("body") or "").strip()]
    if len(described) >= 2:
        # Oldest first, so the student sees their first two, not whatever merged last.
        first = sorted(described, key=lambda p: p.get("merged_at") or "")[:2]
        return True, "Merged pull requests with descriptions: " + ", ".join(_pr_label(p) for p in first) + "."
    if len(pulls) >= 2:
        return False, (f"{len(pulls)} pull requests are merged, but only {len(described)} has a description. "
                       "Edit the empty one on GitHub and write what changed, how it was tested, and how to roll it back.")
    return False, (f"{len(pulls)} merged pull request(s) into main on GitHub; two are needed. "
                   "Stop 3 merges docs/explain-running and Stop 4 merges chore/review-controls.")


@check("d02_review_files")
def d02_review_files(ctx):
    missing = [p for p in (".github/pull_request_template.md", ".github/CODEOWNERS") if not ctx.exists(p)]
    if missing:
        return False, (f"Missing on main of the lab Git server: {', '.join(missing)}. Stop 4 adds both; "
                       "after merging on GitHub, run git push origin main.")
    owners = ctx.file(".github/CODEOWNERS") or ""
    if "YOUR-GITHUB-USERNAME" in owners:
        return False, ".github/CODEOWNERS still says @YOUR-GITHUB-USERNAME. Stop 4 says to put your real GitHub username there."
    if not re.search(r"^\s*\*\s+@\S+", owners, re.M):
        return False, ".github/CODEOWNERS has no catch-all line (* @your-username). Stop 4 shows the whole file."
    return True, "main has .github/pull_request_template.md and .github/CODEOWNERS."


@check("d02_ruleset")
def d02_ruleset(ctx):
    rules, err = _gh_rules(ctx)
    if err:
        return False, err
    types = {r.get("type") for r in rules}
    need = {"pull_request": "Require a pull request before merging",
            "non_fast_forward": "Block force pushes",
            "deletion": "Restrict deletions"}
    missing = [label for t, label in need.items() if t not in types]
    if not types:
        return False, ("No active ruleset protects main on GitHub. Stop 4 creates protect-main; "
                       "make sure Enforcement status is Active, not Evaluate.")
    if missing:
        return False, "The ruleset on main is missing: " + ", ".join(missing) + ". Stop 4 lists every setting."
    return True, "An active ruleset on main requires a pull request and blocks force pushes and deletion."


@check("d02_log")
def d02_log(ctx):
    return _gh_log_pr(ctx, 2, "The Day 2 wrap up")


@check("d02_in_sync")
def d02_in_sync(ctx):
    return _in_sync(ctx, "The Day 2 wrap up", 2)


# ---------------------------------------------------------------- Day 3: Green, Red, Green

@check("d03_ci_green")
def d03_ci_green(ctx):
    if not ctx.exists(".github/workflows/ci.yml"):
        return False, (".github/workflows/ci.yml is not on main of the lab Git server. Stop 2 writes it and "
                       "Stop 4 merges it; then run git push origin main.")
    runs, err = _gh_runs(ctx, "ci.yml", "&branch=main&event=push&status=success", pages=1)
    if err:
        return False, err
    if not runs:
        return False, ("ci.yml is merged, but GitHub has no green run on main triggered by push. "
                       "Merging the Stop 4 pull request starts one; check the Actions tab.")
    return True, f"ci.yml is on main and GitHub has a green push run on main (run #{runs[0].get('run_number')})."


@check("d03_red_then_green")
def d03_red_then_green(ctx):
    runs, err = _gh_runs(ctx, "ci.yml")
    if err:
        return False, err
    by_branch: dict = {}
    for r in runs:
        if r.get("head_branch") and r.get("head_branch") != "main":
            by_branch.setdefault(r["head_branch"], []).append(r)
    for branch, rs in by_branch.items():
        rs.sort(key=lambda r: r.get("created_at") or "")
        failed = [i for i, r in enumerate(rs) if r.get("conclusion") == "failure"]
        if failed and any(r.get("conclusion") == "success" for r in rs[failed[0] + 1:]):
            return True, f"On {branch}, a ci run went red and a later run went green again."
    return False, ("No branch has a red ci run followed by a green one. Stop 4 breaks a test, pushes it, "
                   "then reverts it with git revert and pushes again.")


@check("d03_required_check")
def d03_required_check(ctx):
    checks, err = _gh_required_checks(ctx)
    if err:
        return False, err
    if not checks:
        return False, ("protect-main does not require any status check yet. Stop 5 turns on "
                       "Require status checks to pass and adds the test check.")
    closed, err = _gh_closed_unmerged_pulls(ctx)
    if err:
        return False, err
    runs, err = _gh_runs(ctx, "ci.yml", "&event=pull_request")
    if err:
        return False, err
    red = {r.get("head_branch") for r in runs if r.get("conclusion") == "failure"}
    proof = next((p for p in closed if (p.get("head") or {}).get("ref") in red), None)
    if not proof:
        return False, ("A status check is required, but there is no closed, unmerged pull request with a red ci run. "
                       "Stop 5 opens prove/red-blocks, watches the merge refuse, and closes it.")
    return True, (f"main requires {', '.join(checks)}, and red pull request {_pr_label(proof)} "
                  "was closed without merging.")


@check("d03_reusable")
def d03_reusable(ctx):
    if not ctx.exists(".github/workflows/node-test.yml"):
        return False, (".github/workflows/node-test.yml is not on main of the lab Git server. Stop 6 adds it; "
                       "merge the pull request and run git push origin main.")
    ci = ctx.file(".github/workflows/ci.yml") or ""
    if not re.search(r"uses:\s*['\"]?\./\.github/workflows/node-test\.ya?ml", ci):
        return False, "ci.yml on main does not call ./.github/workflows/node-test.yml. Stop 6 shrinks ci.yml to that call."
    checks, err = _gh_required_checks(ctx)
    if err:
        return False, err
    names = {_norm(c) for c in checks}
    if "node / test" not in names:
        return False, ("protect-main does not require node / test yet. Stop 6: add node / test "
                       "under Require status checks to pass, then remove test.")
    if "test" in names:
        return False, ("protect-main still requires plain test, which nothing reports anymore. "
                       "Stop 6: remove test and keep node / test.")
    return True, "ci.yml calls node-test.yml, and protect-main requires node / test."


@check("d03_log")
def d03_log(ctx):
    return _gh_log_pr(ctx, 3, "The Day 3 wrap up")


@check("d03_in_sync")
def d03_in_sync(ctx):
    return _in_sync(ctx, "The Day 3 wrap up", 3)


# ---------------------------------------------------------------- Day 4: Stop It Before It Lands

@check("d04_semgrep_rules")
def d04_semgrep_rules(ctx):
    text = ctx.file(".semgrep/lab.yml")
    if text is None:
        return False, (".semgrep/lab.yml is not on main of the lab Git server. Stops 2 and 3 write it, "
                       "and the Stop 8 pull request merges it; then run git push origin main.")
    missing = [rid for rid in ("lab-no-eval", "lab-exec-taint")
               if not re.search(rf"id:\s*['\"]?{rid}\b", text)]
    if missing:
        return False, ".semgrep/lab.yml has no rule with id " + " or ".join(missing) + ". Stops 2 and 3 show both rules."
    if not re.search(r"mode:\s*taint", text):
        return False, "lab-exec-taint is there but has no mode: taint line. Stop 3 shows the full rule."
    return True, ".semgrep/lab.yml on main has lab-no-eval and the taint rule lab-exec-taint."


@check("d04_precommit")
def d04_precommit(ctx):
    text = ctx.file(".pre-commit-config.yaml")
    if text is None:
        return False, (".pre-commit-config.yaml is not on main of the lab Git server. Stop 4 writes it, "
                       "and the Stop 8 pull request merges it.")
    if "gitleaks" not in text.lower():
        return False, ".pre-commit-config.yaml has no Gitleaks hook. Stop 4 shows the gitleaks-system hook."
    if "semgrep" not in text.lower():
        return False, ".pre-commit-config.yaml has no Semgrep hook. Stop 4 shows the semgrep-lab hook."
    # Without --error Semgrep exits 0 on findings and the hook never blocks (the Day 4 spot the bug).
    for line in text.splitlines():
        if re.search(r"entry:.*semgrep", line) and "--error" not in line:
            return False, "The Semgrep hook's entry: line has no --error, so it can never block a commit. Stop 4 shows the line."
    return True, ".pre-commit-config.yaml on main has a Gitleaks hook and a Semgrep hook."


@check("d04_bypass_caught")
def d04_bypass_caught(ctx):
    runs, err = _gh_runs(ctx, "sast.yml", "&event=pull_request")
    if err:
        return False, err
    red = [r for r in runs if r.get("conclusion") == "failure"]
    if not red:
        return False, ("No sast run on a pull request has failed yet. Stop 9 commits the calculator with "
                       "--no-verify on demo/bypass and opens a pull request so CI catches it.")
    return True, f"CI caught the bypass: the sast check failed on {red[-1].get('head_branch') or 'a pull request'}."


@check("d04_sast_required")
def d04_sast_required(ctx):
    if not ctx.exists(".github/workflows/sast.yml"):
        return False, (".github/workflows/sast.yml is not on main of the lab Git server. Stop 8 merges it; "
                       "then run git push origin main.")
    checks, err = _gh_required_checks(ctx)
    if err:
        return False, err
    if "semgrep (repo rules)" not in {_norm(c) for c in checks}:
        return False, ("sast.yml is merged, but protect-main does not require semgrep (repo rules). "
                       "The end of Stop 8 adds it under Require status checks to pass.")
    return True, "sast.yml is on main, and protect-main requires semgrep (repo rules)."


@check("d04_log")
def d04_log(ctx):
    return _gh_log_pr(ctx, 4, "The Day 4 wrap up")


# ---------------------------------------------------------------- Day 5: Lock It in the Vault

@check("d05_gitleaks_config")
def d05_gitleaks_config(ctx):
    text = ctx.file(".gitleaks.toml")
    if text is None:
        return False, (".gitleaks.toml is not on main of the lab Git server. Stop 3 writes it, and the "
                       "Stop 6 pull request merges it.")
    if not re.search(r"""id\s*=\s*['"]lab-synthetic-secret['"]""", text):
        return False, ".gitleaks.toml has no rule with id = \"lab-synthetic-secret\". Stop 3 shows the rule."
    if not (re.search(r"^\s*\[extend\]", text, re.M) and re.search(r"useDefault\s*=\s*true", text)):
        return False, (".gitleaks.toml is missing [extend] useDefault = true, so the built-in rules are off. "
                       "Stop 3 shows why that loses the GitHub token.")
    return True, ".gitleaks.toml on main has lab-synthetic-secret and [extend] useDefault = true."


@check("d05_secret_scan")
def d05_secret_scan(ctx):
    if not any(ctx.exists(f".forgejo/workflows/secret-scan.{ext}") for ext in ("yml", "yaml")):
        return False, ".forgejo/workflows/secret-scan.yml is not on main. Stop 6 writes it and merges it through a pull request."
    merged = [p for p in ctx.merged_pulls()
              if "secret" in ((p.get("head") or {}).get("ref", "") + " " + (p.get("title") or "")).lower()]
    if not merged:
        return False, ("secret-scan.yml is on main, but no merged pull request for it was found on the lab Git server. "
                       "Stop 6 merges it from security/secret-scanning.")
    want = "secret-scan / gitleaks (pull_request)"
    for bp in ctx.branch_protections():
        if (bp.get("rule_name") or bp.get("branch_name")) != "main":
            continue
        if bp.get("enable_status_check") and want in {_norm(c) for c in bp.get("status_check_contexts") or []}:
            return True, (f"Pull request #{merged[0].get('number')} merged secret-scan.yml, and main requires "
                          "secret-scan / gitleaks (pull_request).")
    return False, ("secret-scan.yml is merged, but no branch rule on main requires "
                   "secret-scan / gitleaks (pull_request). The end of Stop 6 creates it.")


@check("d05_drill")
def d05_drill(ctx):
    text = ctx.file("docs/drills/day5-rotation-drill.md")
    if text is None:
        return False, ("docs/drills/day5-rotation-drill.md is not on main. Stop 10 writes it; "
                       "merge the docs/day5-drill pull request.")
    # The template ships with every Action cell and "What we learned" empty; a completed
    # drill fills the Revoke row or writes something under What we learned.
    filled = False
    for line in text.splitlines():
        if re.match(r"\s*\|\s*1\s*Revoke", line, re.I):
            cells = line.strip().strip("|").split("|")
            filled = len(cells) > 2 and bool(cells[2].strip())
            break
    learned = re.split(r"^##\s*What we learned\s*$", text, flags=re.M | re.I)
    if len(learned) > 1 and learned[1].strip():
        filled = True
    if not filled:
        return False, ("day5-rotation-drill.md is on main but still looks like the blank template. "
                       "Stop 10: fill in the Revoke action and the rest of the plan.")
    return True, "docs/drills/day5-rotation-drill.md is on main and filled in. Your spot-the-bug split belongs in your log."
