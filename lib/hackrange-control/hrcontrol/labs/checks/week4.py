"""Week 4 lab checks: identity, the front door, observability, compliance, and the capstone.

Week 4's labs build a lot of things that do not survive the day on purpose:
Day 16 deletes its identity namespace, Day 18 deletes its whole observability
namespace, Day 19's cloud account lives in an emulator that is stopped at the
end, and Day 20 deletes the capstone namespace.  So these checks read what
does survive: the files each lab commits to the student's repository (on main
once merged, or on the lab's own branch or pull request before that), the
pull requests and branch rules on the lab Git server, and the few cluster
objects Day 17 tells the student to leave running.

Everything that exists only on the student's screen (an HTTP answer, a count,
an error message) is ticked by the student instead.

Author: Tim Rice
"""

from __future__ import annotations

import json
import re

from .registry import check


# ---------------------------------------------------------------- helpers

def _pr_heads(ctx) -> list:
    """Every branch a pull request was ever opened from, newest first.

    A merged branch is often deleted afterwards, but the pull request still
    remembers its name, so this is how a check finds work that is on its way.
    """
    out = []
    for p in ctx.pulls("all"):
        ref = (p.get("head") or {}).get("ref") or ""
        if ref and ref not in out:
            out.append(ref)
    return out


def _find(ctx, path: str, branches=()) -> tuple:
    """(text, ref) for a file on main, else on the lab's branch, else on any PR branch.

    main comes first because once a pull request merges, main holds the final
    version.  Before that, the lab's own branch is the next best place.
    """
    refs = ["main"]
    # Not every branch in the repository: a month of labs leaves dozens, and a
    # missing file would then cost one request per branch.
    for ref in list(branches) + _pr_heads(ctx):
        if ref and ref not in refs:
            refs.append(ref)
    for ref in refs:
        text = ctx.file(path, ref)
        if text is not None:
            return text, ref
    return None, ""


def _where(ref: str) -> str:
    return "on main" if ref == "main" else f"on branch {ref}"


def _pull_from(ctx, branch: str):
    """The newest pull request opened from this branch, or None."""
    for p in ctx.pulls("all"):
        if (p.get("head") or {}).get("ref") == branch:
            return p
    return None


def _pr_state(p) -> str:
    if p.get("merged"):
        return "merged"
    return "open" if p.get("state") == "open" else "closed without merging"


# ---------------------------------------------------------------- Day 16: Who Goes There

SHOP = "services/shopfront"


@check("d16_injection_rule")
def d16_injection_rule(ctx):
    rule, ref = _find(ctx, f"{SHOP}/rules/sql-string-building.yaml", ["feat/identity"])
    if rule is None:
        return False, (f"{SHOP}/rules/sql-string-building.yaml is not in your repository.  "
                       "Stop 7 writes it; Stop 11 commits and pushes it on feat/identity.")
    if "taint" not in rule or not re.search(r"\.(prepare|exec)\(", rule):
        return False, (f"The Semgrep rule {_where(ref)} is there, but it is not the taint rule "
                       "from Stop 7 (mode: taint, with prepare() and exec() as sinks).")
    return True, f"Your Semgrep taint rule for SQL built from a value is {_where(ref)}."


@check("d16_xss_fixed")
def d16_xss_fixed(ctx):
    text, ref = _find(ctx, f"{SHOP}/render.js", ["feat/identity"])
    if text is None:
        return False, f"{SHOP}/render.js is not in your repository.  Stops 6 and 10 write it; Stop 11 pushes it."
    missing = [e for e in ("&amp;", "&lt;", "&quot;") if e not in text]
    if missing:
        return False, (f"render.js {_where(ref)} does not escape {', '.join(missing)} yet.  "
                       "Stop 10 replaces it with the version that escapes every value.")
    # The name must no longer be pasted into the inline script as a string.
    if re.search(r"<script>[^<]*\$\{\s*name\s*\}", text):
        return False, (f"render.js {_where(ref)} still puts the name inside the <script> block.  "
                       "Stop 10 moves it into a data-name attribute.")
    return True, f"render.js {_where(ref)} escapes for HTML and keeps the name out of the script."


@check("d16_idor_fixed")
def d16_idor_fixed(ctx):
    orders, ref = _find(ctx, f"{SHOP}/orders.js", ["feat/identity"])
    if orders is None:
        return False, f"{SHOP}/orders.js is not in your repository.  Stops 6 and 10 write it; Stop 11 pushes it."
    if "getOrderFor" not in orders or not re.search(r"customer_id\s*=\s*\?", orders):
        return False, (f"orders.js {_where(ref)} still looks orders up by id alone.  Stop 10 adds "
                       "getOrderFor(), with the customer in the WHERE clause.")
    server = ctx.file(f"{SHOP}/server.js", ref) or ""
    if not re.search(r"getOrderFor\([^)]*customer_id", server):
        return False, (f"orders.js is fixed, but server.js {_where(ref)} does not pass the token's "
                       "customer_id to getOrderFor().  Run the two sed lines in Stop 10.")
    return True, f"Orders are looked up by id AND the token's customer_id {_where(ref)}."


@check("d16_tests")
def d16_tests(ctx):
    names = ["search", "render", "orders", "auth"]
    found, total, where = [], 0, ""
    for n in names:
        text, ref = _find(ctx, f"{SHOP}/test/{n}.test.js", ["feat/identity"])
        if text is not None:
            found.append(n)
            total += len(re.findall(r"\btest\(", text))
            where = where or ref
    missing = [f"test/{n}.test.js" for n in names if n not in found]
    if missing:
        return False, (f"Missing from {SHOP}: {', '.join(missing)}.  Stop 10 writes all four "
                       "test files; Stop 11 pushes them.")
    if total < 11:
        return False, f"The four test files hold {total} tests; Stop 10 writes 11."
    return True, f"All four test files are {_where(where)}, with {total} tests."


@check("d16_two_prs")
def d16_two_prs(ctx):
    service = _pull_from(ctx, "feat/identity")
    log = _pull_from(ctx, "docs/day16")
    problems = []
    if not service:
        problems.append("no pull request from feat/identity (Stop 11 opens it)")
    if not log and not ctx.log_has_day(16):
        problems.append("no pull request from docs/day16 with your Day 16 log (end of Stop 11)")
    if problems:
        return False, "Not yet: " + "; ".join(problems) + "."
    parts = [f"service PR #{service.get('number')} ({_pr_state(service)})"]
    parts.append(f"log PR #{log.get('number')} ({_pr_state(log)})" if log else "Day 16 log on main")
    return True, "Found your " + " and ".join(parts) + "."


# ---------------------------------------------------------------- Day 17: Guard the Front Door

GW = "k8s/gateway"


@check("d17_kong_pinned")
def d17_kong_pinned(ctx):
    text, ref = _find(ctx, f"{GW}/versions.env", ["k8s/front-door"])
    if text is None:
        return False, f"{GW}/versions.env is not in your repository.  Stop 2 writes it; Stop 11 commits it."
    m = re.search(r"^KONG_CHART=\S*kong-(\d+\.\d+\.\d+)\.tgz", text, re.M)
    if not m:
        return False, f"versions.env {_where(ref)} does not pin KONG_CHART to a kong-X.Y.Z.tgz URL (Stop 2)."
    # Kong was left running on purpose (end of Stop 11), so its Services can be read.
    body = ctx.kjson("get", "svc", "-n", "kong")
    svcs = (body or {}).get("items") or []
    exposed = [s["metadata"]["name"] for s in svcs
               if (s.get("spec") or {}).get("type") in ("NodePort", "LoadBalancer")]
    if exposed:
        return False, (f"Kong has Services that are not ClusterIP: {', '.join(exposed)}.  "
                       "Stop 2 installs it with proxy.type=ClusterIP and manager.type=ClusterIP.")
    tail = f", and {len(svcs)} ClusterIP Services in namespace kong" if svcs else ""
    return True, f"Kong chart {m.group(1)} is pinned in versions.env {_where(ref)}{tail}."


@check("d17_gateway_programmed")
def d17_gateway_programmed(ctx):
    gw = ctx.kjson("get", "gateway", "shop-gw", "-n", "shop")
    if not gw:
        return False, ("There is no Gateway shop-gw in namespace shop.  Stop 7 creates it, and "
                       "Stop 11 says to leave the shop running.")
    ann = (gw.get("metadata") or {}).get("annotations") or {}
    conds = {c.get("type"): c.get("status") for c in (gw.get("status") or {}).get("conditions") or []}
    if "konghq.com/gateway-unmanaged" not in ann:
        return False, "shop-gw has no konghq.com/gateway-unmanaged annotation yet.  Stop 7 adds it."
    if conds.get("Programmed") != "True":
        return False, (f"shop-gw is Programmed={conds.get('Programmed', 'Unknown')}.  Check both "
                       "annotations in Stop 7, including the one on the GatewayClass.")
    return True, "Gateway shop-gw is annotated as unmanaged and Programmed=True."


@check("d17_netpol")
def d17_netpol(ctx):
    base = "k8s/netpol/manifests"
    need = ["00-namespace.yaml", "20-default-deny.yaml", "30-db-allow-api.yaml", "40-api-egress-db.yaml"]
    texts, where = {}, ""
    for n in need:
        text, ref = _find(ctx, f"{base}/{n}", ["k8s/front-door"])
        if text is not None:
            texts[n] = text
            where = where or ref
    missing = [n for n in need if n not in texts]
    if missing:
        return False, (f"Missing from {base}: {', '.join(missing)}.  Stop 10 writes them; "
                       "Stop 11 commits k8s/netpol.")
    deny = texts["20-default-deny.yaml"]
    if "Ingress" not in deny or "Egress" not in deny:
        return False, "20-default-deny.yaml must deny both Ingress and Egress (Stop 10)."
    egress = texts["40-api-egress-db.yaml"]
    if "Egress" not in egress or "5432" not in egress:
        return False, "40-api-egress-db.yaml must allow the api pod's egress to the db on 5432 (Stop 10)."
    return True, f"All four NetworkPolicy manifests, including the egress rule, are {_where(where)}."


@check("d17_log")
def d17_log(ctx):
    if ctx.log_has_day(17):
        return True, "Your Day 17 entry is in docs/learning-log.md on main."
    return False, ("No \"## Day 17:\" heading in docs/learning-log.md on main.  Merge "
                   "k8s/front-door, then open and merge the docs/day17 pull request (Stop 11).")


# ---------------------------------------------------------------- Day 18: See Everything

OBS = "observability"


@check("d18_collector_hardened")
def d18_collector_hardened(ctx):
    text, ref = _find(ctx, f"{OBS}/otel-base.yaml", ["obs/see-everything"])
    if text is None:
        return False, f"{OBS}/otel-base.yaml is not in your repository.  Stop 3 writes it; Stop 11 commits it."
    open_ports = [p for p in ("jaeger-compact", "jaeger-thrift", "jaeger-grpc", "zipkin")
                  if not re.search(rf"^\s*{p}:\s*\{{\s*enabled:\s*false\s*\}}", text, re.M)]
    if open_ports:
        return False, (f"otel-base.yaml {_where(ref)} does not switch off these ports: "
                       f"{', '.join(open_ports)} (Stop 3).")
    live = [r for r in ("jaeger", "zipkin") if not re.search(rf"^\s*{r}:\s*null", text, re.M)]
    if live:
        return False, (f"otel-base.yaml {_where(ref)} still leaves these receivers on: "
                       f"{', '.join(live)}.  Set them to null (Stop 3).")
    return True, f"otel-base.yaml {_where(ref)} turns off the Jaeger and Zipkin receivers and their ports."


@check("d18_tempo_datasource")
def d18_tempo_datasource(ctx):
    text, ref = _find(ctx, f"{OBS}/grafana-values.yaml", ["obs/see-everything"])
    if text is None:
        return False, f"{OBS}/grafana-values.yaml is not in your repository.  Stop 7 writes it; Stop 11 commits it."
    if re.search(r"tempo[\w.-]*:3100", text):
        return False, (f"grafana-values.yaml {_where(ref)} still points Tempo at port 3100.  "
                       "Run the sed line in Stop 7, then commit again.")
    if not re.search(r"tempo[\w.-]*:3200", text):
        return False, f"grafana-values.yaml {_where(ref)} has no Tempo datasource on port 3200 (Stop 7)."
    return True, f"The Tempo datasource is fixed to port 3200 in grafana-values.yaml {_where(ref)}."


@check("d18_events_feed")
def d18_events_feed(ctx):
    text, ref = _find(ctx, f"{OBS}/otel-events.yaml", ["obs/see-everything"])
    if text is None:
        return False, f"{OBS}/otel-events.yaml is not in your repository.  Stop 8 writes it; Stop 11 commits it."
    if "k8sobjects" not in text or "k8s-events" not in text:
        return False, (f"otel-events.yaml {_where(ref)} needs the k8sobjects receiver and the "
                       "service.name k8s-events (Stop 8).")
    resources = set()
    for block in re.findall(r"resources:\s*\[([^\]]*)\]", text):
        resources |= {r.strip().strip("\"'") for r in block.split(",") if r.strip()}
    if not resources:
        return False, f"otel-events.yaml {_where(ref)} has no ClusterRole rules (Stop 8)."
    if resources != {"events"}:
        extra = ", ".join(sorted(resources - {"events"}))
        return False, (f"The collector's ClusterRole in otel-events.yaml can read more than events: {extra}.  "
                       "Stop 8 limits it to events only.")
    return True, f"Events feed to k8s-events, with a ClusterRole limited to events, {_where(ref)}."


# ---------------------------------------------------------------- Day 19: The Self-Healing Cloud

COMP = "compliance"


@check("d19_gate")
def d19_gate(ctx):
    gate, ref = _find(ctx, f"{COMP}/gate.sh", ["compliance/self-healing"])
    if gate is None:
        return False, f"{COMP}/gate.sh is not in your repository.  Stop 4 writes it; Stop 10 commits it."
    checks = ctx.file(f"{COMP}/gate-checks.json", ref)
    try:
        agreed = (json.loads(checks) if checks else {}).get("aws") or []
    except (ValueError, AttributeError):
        agreed = []
    if len(agreed) < 5:
        return False, (f"{COMP}/gate-checks.json {_where(ref)} should list your five agreed checks "
                       "under \"aws\" (Stop 2).")
    # Failing closed is the substance: no report must mean exit 2, not a pass.
    if not re.search(r"-s\s+\"?\$OUT/posture\.ocsf\.json", gate) or not re.search(r"^\s*exit 2\b", gate, re.M):
        return False, (f"gate.sh {_where(ref)} does not fail closed: it must check the report exists "
                       "and exit 2 when it does not (Stop 4).")
    if "exceptions.json" not in gate:
        return False, f"gate.sh {_where(ref)} does not read compliance/exceptions.json (Stop 4)."
    return True, f"gate.sh {_where(ref)} runs {len(agreed)} agreed checks and exits 2 on a missing report."


@check("d19_guardrails")
def d19_guardrails(ctx):
    text, ref = _find(ctx, f"{COMP}/custodian/guardrails.yml", ["compliance/self-healing"])
    if text is None:
        return False, f"{COMP}/custodian/guardrails.yml is not in your repository.  Stop 5 writes it; Stop 10 commits it."
    problems = []
    if not re.search(r"remove-permissions[\s\S]{0,80}ingress:\s*matched", text):
        problems.append("the SSH policy should remove-permissions with ingress: matched")
    if "mark-for-op" not in text or "c7n-close-me" not in text:
        problems.append("the RDP policy should mark-for-op with tag c7n-close-me")
    if problems:
        return False, f"guardrails.yml {_where(ref)}: " + "; ".join(problems) + " (Stop 5)."
    return True, f"guardrails.yml {_where(ref)} closes port 22 (matched only) and marks 3389 with c7n-close-me."


@check("d19_exception")
def d19_exception(ctx):
    text, ref = _find(ctx, f"{COMP}/exceptions.json", ["compliance/self-healing"])
    if text is None:
        return False, f"{COMP}/exceptions.json is not in your repository.  Stops 4 and 6 write it."
    try:
        rows = (json.loads(text) or {}).get("exceptions") or []
    except (ValueError, AttributeError):
        return False, f"{COMP}/exceptions.json {_where(ref)} is not valid JSON."
    good = [r for r in rows if isinstance(r, dict)
            and str(r.get("check", "")).strip() and str(r.get("reason", "")).strip()
            and str(r.get("owner", "")).strip()
            and re.match(r"^\d{4}-\d{2}-\d{2}$", str(r.get("review", "")).strip())]
    if not good:
        return False, (f"exceptions.json {_where(ref)} has no exception with a check, a reason, an "
                       "owner and a review date (YYYY-MM-DD).  Stop 6 writes one.")
    r = good[0]
    return True, f"Exception for {r['check']} owned by {r['owner']}, review {r['review']}, {_where(ref)}."


@check("d19_runbook")
def d19_runbook(ctx):
    text, ref = _find(ctx, f"{COMP}/runbook.sh", ["compliance/self-healing"])
    if text is None:
        return False, f"{COMP}/runbook.sh is not in your repository.  Stop 7 writes it; Stop 10 commits it."
    missing = [w for w in ("CHECK", "CHANGE", "CONFIRM") if f"{w}:" not in text]
    if missing:
        return False, f"runbook.sh {_where(ref)} does not print {', '.join(missing)} (Stop 7)."
    # The exit code must come from asking the account, so the last line is the test.
    last = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if "describe-security-groups" not in text or not (last and last[-1].startswith("[")):
        return False, (f"runbook.sh {_where(ref)} must end on the CONFIRM test that asks the account "
                       "whether port 22 is still open (Stop 7).")
    return True, f"runbook.sh {_where(ref)} has CHECK, CHANGE and CONFIRM, and ends on the confirm test."


@check("d19_log")
def d19_log(ctx):
    if ctx.log_has_day(19):
        return True, "Your Day 19 entry is in docs/learning-log.md on main."
    return False, ("No \"## Day 19:\" heading in docs/learning-log.md on main.  Merge "
                   "compliance/self-healing, then open and merge docs/day19 (Stop 10).")


# ---------------------------------------------------------------- Day 20: Prove It

GATES = ("secrets", "deps", "code", "image", "iac", "admission", "exceptions")


@check("d20_gate")
def d20_gate(ctx):
    gate, ref = _find(ctx, "capstone/gate.sh", ["capstone/prove-it", "docs/day20"])
    if gate is None:
        return False, "capstone/gate.sh is not in your repository.  Stop 2 writes it; Stop 3 commits it."
    missing = [g for g in GATES if not re.search(rf"^gate_{g}\(\)", gate, re.M)]
    if missing:
        return False, f"capstone/gate.sh {_where(ref)} is missing these gates: {', '.join(missing)} (Stop 2)."
    if "RELEASE GATE: BLOCKED" not in gate:
        return False, f"capstone/gate.sh {_where(ref)} never prints RELEASE GATE: BLOCKED (Stop 2)."
    evidence, eref = _find(ctx, "docs/capstone/evidence.md", ["capstone/prove-it", "docs/day20"])
    if not evidence or "BLOCKED" not in evidence:
        return False, ("The gate is there, but docs/capstone/evidence.md does not record the first "
                       "run being BLOCKED.  Stop 3 starts the record with Finding 0.")
    return True, f"capstone/gate.sh {_where(ref)} has all seven gates, and your record shows the first run BLOCKED."


@check("d20_exception")
def d20_exception(ctx):
    reg, ref = _find(ctx, "capstone/exceptions.md", ["capstone/prove-it", "docs/day20"])
    if reg is None:
        return False, "capstone/exceptions.md is not in your repository.  Stops 2 and 10 write it."
    row = next((ln for ln in reg.splitlines() if re.match(r"^\|\s*EX-001\s*\|", ln)), "")
    cells = [c.strip() for c in row.strip().strip("|").split("|")] if row else []
    expires = cells[6] if len(cells) > 6 else ""
    if not row or not re.match(r"^\d{4}-\d{2}-\d{2}$", expires):
        return False, (f"capstone/exceptions.md {_where(ref)} has no EX-001 row with a readable "
                       "Expires date.  Stop 10 adds it.")
    ignore = ctx.file("capstone/policy/trivyignore", ref) or ""
    tagged = [ln for ln in ignore.splitlines() if "EX-001" in ln and "exp:" in ln]
    if not tagged:
        return False, (f"capstone/policy/trivyignore {_where(ref)} has no line suppressed as EX-001 "
                       "with an exp: date.  Stop 10 writes those lines.")
    return True, f"EX-001 is registered {_where(ref)}, expires {expires}, with {len(tagged)} dated suppression{'' if len(tagged) == 1 else 's'}."


@check("d20_merge_gate")
def d20_merge_gate(ctx):
    rule = next((b for b in ctx.branch_protections()
                 if (b.get("rule_name") or b.get("branch_name")) == "main"), None)
    if not rule:
        return False, "main has no branch rule you can read.  Stop 11 updates it."
    contexts = rule.get("status_check_contexts") or []
    if not rule.get("enable_status_check") or not any(c.startswith("release-gate") for c in contexts):
        return False, ("main's branch rule does not require release-gate / gates (pull_request).  "
                       "Run the branch protection block in Stop 11.")
    if ctx.file(".forgejo/workflows/release-gate.yml") is None:
        return False, ".forgejo/workflows/release-gate.yml is not on main yet.  Stop 11 adds it."
    pr = _pull_from(ctx, "capstone/prove-it")
    if not pr or not pr.get("merged"):
        return False, ("The release gate is required, but the capstone/prove-it pull request is "
                       "not merged yet.  Remove the secret and merge it (end of Stop 11).")
    return True, f"main requires the release-gate check, and PR #{pr.get('number')} merged through it."


@check("d20_evidence")
def d20_evidence(ctx):
    text = ctx.file("docs/capstone/evidence.md")
    if text is None:
        return False, ("docs/capstone/evidence.md is not on main.  Merge docs/day20 (end of Stop 12); "
                       "main is protected, so a pull request is the only way in.")
    m = re.search(r"^#+\s*Not covered[^\n]*\n(.*?)(?=^#+\s|\Z)", text, re.M | re.S | re.I)
    if not m:
        return False, "docs/capstone/evidence.md on main has no \"Not covered\" section (Stop 12)."
    points = [ln for ln in m.group(1).splitlines() if re.match(r"^\s*[-*]\s+\S", ln)]
    if not points:
        return False, "The \"Not covered\" section on main is empty.  Write down what the gate does not prove."
    return True, f"docs/capstone/evidence.md is on main with a Not covered section of {len(points)} points."
