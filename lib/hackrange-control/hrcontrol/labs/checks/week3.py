"""Week 3 lab checks: infrastructure as code, golden images, and Kubernetes.

Days 11 to 15.  Most of this week happens on a disposable lab box or inside a
cluster that the lab itself tears down at the end (every Kubernetes lab this
week finishes by deleting its namespaces), so nothing here looks at the
cluster.  What survives is what the student pushed to the lab Git server:
the OpenTofu code and its Checkov gate, the Packer template and the threat
model, the Kubernetes manifests, the admission policies, the Falco rules,
and the learning log.  Those are graded here, on main or on the branch or
pull request the lesson told the student to use.  Everything a student only
saw on a screen is left for them to tick.

Author: Tim Rice
"""

from __future__ import annotations

import re

from .registry import check

# The branch each lab tells the student to push.  A file is looked for on
# main first (most labs merge before the log), then on this branch, then on
# the head of any open or merged pull request, so a renamed branch still counts.
BRANCH = {
    11: "infra/network",
    12: "golden/day12",
    13: "k8s/first-contact",
    15: "k8s/admission",
}


# ------------------------------------------------------------------ helpers

def _live_pulls(ctx) -> list:
    """Pull requests that still count: open, or merged.  Closed unmerged ones do not."""
    return [p for p in ctx.pulls("all") if p.get("state") == "open" or p.get("merged")]


def _find(ctx, path: str, day: int) -> tuple[str | None, str]:
    """(text, where) for a file on main, the lab's branch, or any live pull request."""
    text = ctx.file(path, "main")
    if text is not None:
        return text, "on main"
    branch = BRANCH.get(day)
    if branch:
        text = ctx.file(path, branch)
        if text is not None:
            return text, f"on branch {branch}"
    for p in _live_pulls(ctx):
        sha = (p.get("head") or {}).get("sha")
        if not sha:
            continue
        text = ctx.file(path, sha)
        if text is not None:
            return text, f"in pull request #{p.get('number')}"
    return None, ""


def _pr_files(ctx, pr: dict) -> list[str]:
    """Every file a pull request changes (works after the branch is deleted, too)."""
    out: list[str] = []
    # The server caps a page at 50 no matter what we ask for, so walk a few pages.
    for page in range(1, 6):
        status, body = ctx.git(f"/repos/{ctx.repo}/pulls/{pr.get('number')}/files?limit=50&page={page}")
        if status != 200 or not isinstance(body, list):
            break
        out += [f.get("filename", "") for f in body if isinstance(f, dict)]
        if len(body) < 50:
            break
    return out


def _pr_changing(ctx, want) -> dict | None:
    """The first open or merged pull request whose changed files satisfy want(files)."""
    for p in _live_pulls(ctx):
        if want(_pr_files(ctx, p)):
            return p
    return None


def _state(pr: dict) -> str:
    return "merged" if pr.get("merged") else "open"


def _log_check(ctx, day: int, stop: str) -> tuple[bool, str]:
    """A merged learning-log entry for a day, with a useful hint if it is only on a branch."""
    if ctx.log_has_day(day):
        return True, f"docs/learning-log.md on main has a \"## Day {day}:\" entry."
    heading = f"## Day {day}:"
    for p in _live_pulls(ctx):
        sha = (p.get("head") or {}).get("sha")
        if sha and heading in (ctx.file("docs/learning-log.md", sha) or ""):
            return False, (f"Your Day {day} entry is in pull request #{p.get('number')}, "
                           f"but it is not on main yet.  Get it approved and merge it ({stop}).")
    return False, (f"No \"## Day {day}:\" heading in docs/learning-log.md on main.  "
                   f"Write it on a branch, open a pull request, and merge it ({stop}).")


def _section(text: str, start: str, end: str | None = None) -> str:
    """The text between a heading that matches start and the next one that matches end."""
    m = re.search(start, text, re.I | re.M)
    if not m:
        return ""
    rest = text[m.end():]
    if end:
        e = re.search(end, rest, re.I | re.M)
        if e:
            rest = rest[:e.start()]
    return rest


def _table_rows(text: str) -> list[list[str]]:
    """Markdown table rows as lists of stripped cells, without header separators."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


# ------------------------------------------------------------------ Day 11

@check("d11_state_ignored")
def d11_state_ignored(ctx):
    # The jq output is something only the student saw.  The .gitignore that
    # came out of it, and the absence of any state file in Git, both persist.
    text, where = _find(ctx, "infra/.gitignore", 11)
    if text is None:
        text, where = _find(ctx, ".gitignore", 11)
    if text is None or not re.search(r"^\s*\*\.tfstate\s*$", text, re.M):
        return False, ("No .gitignore with a *.tfstate line was found in infra/.  "
                       "Create infra/.gitignore as shown in Stop 4 and push it with your infrastructure code.")
    committed = []
    status, body = ctx.git(f"/repos/{ctx.repo}/git/trees/main?recursive=true&per_page=10000")
    if status == 200 and isinstance(body, dict):
        committed += [t.get("path", "") for t in body.get("tree") or [] if isinstance(t, dict)]
    for p in _live_pulls(ctx):
        committed += _pr_files(ctx, p)
    leaked = sorted({f for f in committed if re.search(r"\.tfstate(\.|$)", f)})
    if leaked:
        return False, (f"A state file is in Git: {leaked[0]}.  State holds secrets in plain text.  "
                       "Remove it, keep the *.tfstate lines in infra/.gitignore (Stop 4), and treat anything in it as leaked.")
    return True, f"infra/.gitignore keeps *.tfstate out of Git ({where}), and no state file was committed."


@check("d11_checkov_gate")
def d11_checkov_gate(ctx):
    gate, where = _find(ctx, "infra/.checkov.yaml", 11)
    if gate is None:
        return False, "infra/.checkov.yaml is missing.  Stop 6 writes the gate as a Checkov config file."
    if "CKV_AWS_24" not in gate:
        return False, (f"infra/.checkov.yaml ({where}) does not list CKV_AWS_24, the SSH-from-anywhere check.  "
                       "Use the check list from Stop 6.")
    storage, _ = _find(ctx, "infra/storage.tf", 11)
    m = re.search(r"checkov:skip=(CKV\w+)\s*:\s*([^\n]+)", storage or "")
    if not m:
        return False, ("infra/.checkov.yaml is there, but infra/storage.tf has no checkov:skip comment.  "
                       "Stop 6 adds one justified suppression for CKV_AWS_144 inside the bucket resource.")
    reason = m.group(2).strip()
    if len(reason) < 20:
        return False, (f"Your suppression of {m.group(1)} has almost no reason (\"{reason}\").  "
                       "Give it a specific reason, an owner, and a review date (Stop 6).")
    return True, f"Gate file infra/.checkov.yaml ({where}) and a justified suppression of {m.group(1)} in storage.tf."


@check("d11_house_rule")
def d11_house_rule(ctx):
    policy, where = _find(ctx, "policies/checkov/owner_tag.yaml", 11)
    if policy is None or "CKV2_SBL_1" not in policy:
        return False, "policies/checkov/owner_tag.yaml with id CKV2_SBL_1 was not found.  Stop 7 writes it."
    if "owner" not in policy:
        return False, "Your CKV2_SBL_1 policy does not look for an owner tag.  Compare it with Stop 7."
    locals_tf, _ = _find(ctx, "infra/locals.tf", 11)
    if not locals_tf or not re.search(r"\bowner\s*=", locals_tf):
        return False, ("The policy is there, but infra/locals.tf has no owner tag, so the rule cannot pass.  "
                       "Add the locals block and use local.tags everywhere (Stop 7).")
    gate, _ = _find(ctx, "infra/.checkov.yaml", 11)
    if "CKV2_SBL_1" not in (gate or ""):
        return False, ("CKV2_SBL_1 passes, but it is not in infra/.checkov.yaml, so the gate does not enforce it.  "
                       "Add it with the sed line at the end of Stop 7.")
    return True, f"CKV2_SBL_1 policy ({where}), an owner tag in locals.tf, and the rule is in the gate."


@check("d11_module_refactor")
def d11_module_refactor(ctx):
    net, where = _find(ctx, "infra/network.tf", 11)
    if net is None or not re.search(r'module\s+"network"', net):
        return False, "infra/network.tf does not call module \"network\".  Stop 9 moves the network into a module."
    moved = len(re.findall(r"^\s*moved\s*\{", net, re.M))
    if not moved or "module.network.aws_vpc.main" not in net.replace(" ", ""):
        return False, ("infra/network.tf has no moved block for the VPC, so OpenTofu would destroy and rebuild "
                       "the whole network.  Add the moved blocks from Stop 9.")
    variables, _ = _find(ctx, "infra/modules/network/variables.tf", 11)
    if not variables or "validation" not in variables or "0.0.0.0/0" not in variables:
        return False, ("The module's variables.tf has no validation rule refusing 0.0.0.0/0 for admin_cidr.  "
                       "Copy the variables file from Stop 9.")
    return True, f"module \"network\" with {moved} moved blocks ({where}), and admin_cidr refuses 0.0.0.0/0."


@check("d11_infra_pr")
def d11_infra_pr(ctx):
    def wanted(files):
        return (any(f.startswith("infra/") and f.endswith(".tf") for f in files)
                and ".github/workflows/iac.yml" in files)
    pr = _pr_changing(ctx, wanted)
    if not pr:
        if _pr_changing(ctx, lambda fs: any(f.startswith("infra/") and f.endswith(".tf") for f in fs)):
            return False, ("Your infrastructure pull request does not include .github/workflows/iac.yml.  "
                           "Add the workflow from Stop 11, commit it, and push the branch again.")
        return False, ("No open or merged pull request carries infra/*.tf and .github/workflows/iac.yml.  "
                       "Push infra/network and open the pull request at the end of Stop 11.")
    wf, _ = _find(ctx, ".github/workflows/iac.yml", 11)
    if wf is not None and "checkov" not in wf.lower():
        return False, "Your .github/workflows/iac.yml never runs Checkov.  Compare it with Stop 11."
    return True, (f"Pull request #{pr.get('number')} ({_state(pr)}) carries your infrastructure code and "
                  "the iac workflow.  Keep your Azure review table in your log.")


@check("d11_log")
def d11_log(ctx):
    return _log_check(ctx, 11, "Wrap up")


# ------------------------------------------------------------------ Day 12

def _packer_ansible_aligned(hcl: str) -> bool:
    """True when the ansible provisioner's = signs line up, the way packer fmt leaves them.

    The lab ships that block misaligned on purpose, so this is the one place a
    template that skipped packer fmt shows.  Anything we cannot parse passes.
    """
    m = re.search(r'provisioner\s+"ansible"\s*\{(.*?)\n\s*\}', hcl, re.S)
    if not m:
        return True
    cols = set()
    for line in m.group(1).splitlines():
        a = re.match(r"^(\s*[A-Za-z_][\w-]*)(\s*)=", line)
        if a:
            cols.add(len(a.group(1)) + len(a.group(2)))
    return len(cols) <= 1


@check("d12_packer")
def d12_packer(ctx):
    hcl, where = _find(ctx, "infra/golden/golden.pkr.hcl", 12)
    if hcl is None:
        return False, ("infra/golden/golden.pkr.hcl was not found on main or on a pull request.  "
                       "Stop 6 writes it; the wrap up commits and pushes it.")
    missing = [what for what, pat in (
        ("a qemu source", r'source\s+"qemu"'),
        ("the ansible provisioner", r'provisioner\s+"ansible"'),
        ("the inspec provisioner", r'provisioner\s+"inspec"'),
        ("a sensitive build_password variable", r'variable\s+"build_password"[^}]*sensitive\s*=\s*true'),
    ) if not re.search(pat, hcl, re.S)]
    if missing:
        return False, f"golden.pkr.hcl ({where}) is missing {', '.join(missing)}.  Compare it with Stop 6."
    if not _packer_ansible_aligned(hcl):
        return False, ("golden.pkr.hcl is not formatted: the ansible provisioner's = signs do not line up.  "
                       "Run packer fmt golden.pkr.hcl (Stop 6), then commit and push again.")
    doc, _ = _find(ctx, "docs/golden-image-pipeline.md", 12)
    if doc is None:
        return False, "golden.pkr.hcl is good, but docs/golden-image-pipeline.md is missing.  The end of Stop 6 writes it."
    if len([r for r in _table_rows(doc) if len([c for c in r if c]) >= 2]) < 5:
        return False, "docs/golden-image-pipeline.md has no real stage table.  Use the sketch from the end of Stop 6."
    return True, f"golden.pkr.hcl is formatted with all three provisioners ({where}), plus docs/golden-image-pipeline.md."


_AC_PARTS = ("prevent", "detect", "recover", "residual")


@check("d12_threat_model")
def d12_threat_model(ctx):
    text, where = _find(ctx, "docs/threat-model.md", 12)
    if text is None:
        return False, "docs/threat-model.md was not found.  Stop 7 copies the template into docs/."
    # The DFD is question 1.  The template has exactly one example arrow, so
    # a real diagram has many more flows and at least a couple of boundaries.
    dfd = _section(text, r"^#+\s*1\.", r"^#+\s*2\.") or text
    flows = len(re.findall(r"-+>|→", dfd))
    boundaries = len(re.findall(r"boundary", dfd, re.I))
    if flows < 6 or boundaries < 2:
        return False, (f"The data-flow diagram under question 1 has {flows} arrows and {boundaries} trust boundaries.  "
                       "Draw the whole system with labeled arrows and boundaries (Stop 7).")
    # Each abuse case is a heading like "### AC-2: ...".  A complete one answers
    # all four questions with something written after the colon.
    parts = re.split(r"^#{2,4}\s*AC-?\s*\d+", text, flags=re.M | re.I)[1:]
    complete = 0
    for body in parts:
        body = re.split(r"^#{1,2}\s", body, flags=re.M)[0]
        if all(re.search(rf"\b{kw}[^:\n]{{0,25}}:[\s*_]*\w", body, re.I) for kw in _AC_PARTS):
            complete += 1
    if complete < 5:
        return False, (f"{complete} of your abuse cases have prevention, detection, recovery, and residual risk "
                       "all filled in; five are needed.  Finish AC-2 to AC-5 (Stop 8).")
    return True, f"docs/threat-model.md ({where}) has a DFD with {flows} flows and {complete} complete abuse cases."


@check("d12_requirements")
def d12_requirements(ctx):
    text, where = _find(ctx, "docs/security-requirements.md", 12)
    if text is None:
        return False, "docs/security-requirements.md was not found.  Stop 7 copies the template into docs/."
    rows = _table_rows(text)
    # SR-02 to SR-05 arrive empty; a filled row has a control, a verification, and an owner.
    sr = {r[0].upper(): r for r in rows if r and re.fullmatch(r"SR-\d+", r[0], re.I)}
    empty = [k for k in ("SR-02", "SR-03", "SR-04", "SR-05")
             if k not in sr or sum(1 for c in sr[k][1:] if c) < 4]
    if empty:
        return False, f"The matrix rows {', '.join(empty)} still need a control, a verification, and an owner (Stop 9)."
    own = _table_rows(_section(text, r"^#+\s*Ownership", r"^#+\s"))
    owned = [r for r in own if r and r[0].lower().startswith("who") and len(r) > 1 and r[-1]]
    if len(owned) < 4:
        return False, f"{len(owned)} of the four ownership questions have an owner.  Fill in all four (Stop 9)."
    risks = _section(text, r"^#+\s*Accepted risk", r"^#+\s")
    if not re.search(r"\b20\d\d-\d\d-\d\d\b", risks):
        return False, "No accepted risk with an expiry date (like 2027-03-01) in the Accepted risks table (Stop 9)."
    asvs = _table_rows(_section(text, r"^#+\s*ASVS requirements", r"^#+\s"))
    picked = [r for r in asvs if r and re.fullmatch(r"V?\d+\.\d+\.\d+", r[0], re.I) and sum(1 for c in r if c) >= 3]
    if len(picked) < 5 or "5.0.0" not in text:
        return False, (f"{len(picked)} ASVS 5.0.0 requirements are listed with how you verified them; five are needed.  "
                       "Add a row for each command you ran in Stop 9.")
    if "SR-06" not in text.upper():
        return False, "SR-06 (a name must contain a visible character) is not written down yet (end of Stop 9)."
    test, _ = _find(ctx, "test/business-rules.test.js", 12)
    if test is None or "todo" not in test:
        return False, "test/business-rules.test.js with the SR-06 todo test was not found (end of Stop 9)."
    return True, (f"docs/security-requirements.md ({where}): matrix, owners, a dated accepted risk, "
                  f"{len(picked)} ASVS 5.0.0 requirements, and SR-06 with its todo test.")


@check("d12_log_pr")
def d12_log_pr(ctx):
    # Day 12 ends with the log on an open pull request, not a merge, so an
    # open one is enough.  A log already on main counts too.
    for p in _live_pulls(ctx):
        sha = (p.get("head") or {}).get("sha")
        if sha and "## Day 12:" in (ctx.file("docs/learning-log.md", sha) or ""):
            return True, f"Pull request #{p.get('number')} ({_state(p)}) carries your Day 12 log entry."
    if ctx.log_has_day(12):
        return True, "Your Day 12 log entry is on main."
    return False, ("No open or merged pull request carries a \"## Day 12:\" log entry.  "
                   "Commit it on golden/day12, push, and open the pull request (Wrap up).")


# ------------------------------------------------------------------ Day 13

@check("d13_drift_fixed")
def d13_drift_fixed(ctx):
    # The diff output is gone with the lab box.  What persists is the fix:
    # the ServiceAccount written into the file instead of only patched live.
    dep, where = _find(ctx, "k8s/base/deployment.yaml", 13)
    if dep is None:
        return False, "k8s/base/deployment.yaml was not found.  Stop 3 writes it; Stop 11 commits it."
    if not re.search(r"serviceAccountName:\s*greeter", dep):
        return False, ("k8s/base/deployment.yaml still does not mention serviceAccountName, so the kubectl patch "
                       "drift lives only in the cluster.  Write it into the file (end of Stop 8).")
    sa, _ = _find(ctx, "k8s/base/serviceaccount.yaml", 13)
    if not sa or not re.search(r"automountServiceAccountToken:\s*false", sa):
        return False, ("The Deployment names its ServiceAccount, but k8s/base/serviceaccount.yaml does not turn off "
                       "the token mount.  Add automountServiceAccountToken: false (end of Stop 8).")
    return True, f"The patch is written into the files ({where}): serviceAccountName greeter, token mount off."


@check("d13_overlays")
def d13_overlays(ctx):
    base, where = _find(ctx, "k8s/base/kustomization.yaml", 13)
    if base is None:
        return False, "k8s/base/kustomization.yaml was not found.  Stop 9 turns k8s/base into a Kustomize base."
    ns = {}
    for env in ("dev", "stage"):
        k, _ = _find(ctx, f"k8s/overlays/{env}/kustomization.yaml", 13)
        if k is None:
            return False, f"k8s/overlays/{env}/kustomization.yaml was not found.  Stop 9 writes both overlays."
        if "base" not in k:
            return False, f"The {env} overlay does not use ../../base as a resource.  Compare it with Stop 9."
        m = re.search(r"^namespace:\s*(\S+)", k, re.M)
        ns[env] = m.group(1) if m else ""
    if not ns["dev"] or ns["dev"] == ns["stage"]:
        return False, "Your dev and stage overlays do not set two different namespaces.  Compare them with Stop 9."
    return True, f"One base ({where}) and two overlays, for {ns['dev']} and {ns['stage']}."


@check("d13_chart_lint")
def d13_chart_lint(ctx):
    chart, where = _find(ctx, "charts/greeter/Chart.yaml", 13)
    if chart is None:
        return False, "charts/greeter/Chart.yaml was not found.  Stop 10 builds the chart; Stop 11 commits it."
    tpl, _ = _find(ctx, "charts/greeter/templates/deployment.yaml", 13)
    if tpl is None:
        return False, "The chart has no templates/deployment.yaml.  Stop 10 writes three templates."
    dep, _ = _find(ctx, "k8s/base/deployment.yaml", 13)
    missing = [f for f in ("runAsNonRoot: true", "readOnlyRootFilesystem: true")
               if not re.search(f.replace(" ", r"\s*"), dep or "")]
    if missing:
        return False, (f"k8s/base/deployment.yaml is missing {' and '.join(missing)}, the two kube-linter fixes.  "
                       "Run the Python fix in Stop 11 and commit again.")
    return True, f"charts/greeter ({where}), and the Deployment carries the kube-linter fixes."


@check("d13_pr_and_log")
def d13_pr_and_log(ctx):
    pr = _pr_changing(ctx, lambda fs: any(f.startswith("k8s/") for f in fs)
                      and any(f.startswith("charts/") for f in fs))
    if not pr:
        return False, ("No open or merged pull request carries both k8s/ and charts/.  "
                       "Commit both on k8s/first-contact and open the pull request (end of Stop 11).")
    ok, detail = _log_check(ctx, 13, "end of Stop 11")
    if not ok:
        return False, f"Pull request #{pr.get('number')} is there.  {detail}"
    return True, f"Pull request #{pr.get('number')} ({_state(pr)}) carries k8s/ and charts/, and {detail[0].lower()}{detail[1:]}"


# ------------------------------------------------------------------ Day 14

@check("d14_log")
def d14_log(ctx):
    # Everything else on Day 14 lives in a namespace the lab deletes at the
    # end, so only the log can be checked.
    return _log_check(ctx, 14, "Stop 8")


# ------------------------------------------------------------------ Day 15

@check("d15_hardened_pod")
def d15_hardened_pod(ctx):
    # The pod itself is deleted with the guard namespace.  The manifest that
    # made restricted let it in is committed, and every field can be read.
    web, where = _find(ctx, "k8s/admission/web.yaml", 15)
    if web is None:
        return False, "k8s/admission/web.yaml was not found.  Stop 4 writes it; Stop 12 commits it."
    need = (
        ("runAsNonRoot: true", r"runAsNonRoot:\s*true"),
        ("a non-root runAsUser", r"runAsUser:\s*[1-9]\d*"),
        ("allowPrivilegeEscalation: false", r"allowPrivilegeEscalation:\s*false"),
        ("readOnlyRootFilesystem: true", r"readOnlyRootFilesystem:\s*true"),
        ("capabilities drop ALL", r"drop:\s*(?:\[\s*|-\s*)[\"']?ALL"),
        ("seccompProfile RuntimeDefault", r"seccompProfile:\s*\{?\s*type:\s*RuntimeDefault"),
    )
    missing = [label for label, pat in need if not re.search(pat, web)]
    if missing:
        return False, f"k8s/admission/web.yaml ({where}) is missing {', '.join(missing)}.  Compare it with Stop 4."
    return True, f"k8s/admission/web.yaml ({where}) sets all five restricted fields plus a read-only root filesystem."


@check("d15_falco_rules")
def d15_falco_rules(ctx):
    tmp, where = _find(ctx, "falco/tmp-exec.yaml", 15)
    if tmp is None:
        return False, "falco/tmp-exec.yaml was not found.  Stop 11 writes it; Stop 12 commits it."
    if not re.search(r"proc\.(aname|pname|anames)", tmp):
        return False, ("falco/tmp-exec.yaml is still the first, noisy version.  Tune it by ancestry "
                       "(proc.aname[2] = \"httpd\") so it fires once, as in Stop 11.")
    ssh, _ = _find(ctx, "falco/ssh-key-persistence.yaml", 15)
    if ssh is None or "authorized_keys" not in ssh or "rule:" not in ssh:
        return False, "falco/ssh-key-persistence.yaml with your authorized_keys rule was not found (end of Stop 11)."
    return True, f"Your tuned /tmp rule and your authorized_keys rule are committed ({where})."


@check("d15_log")
def d15_log(ctx):
    return _log_check(ctx, 15, "Stop 12")
