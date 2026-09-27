"""The parts of the lab a student can start and stop, and how.

Three kinds:

- docker   a lab service: one or more containers (Forgejo, ForgeRepo, Git
           Code Review, and the always running Keycloak, Kong and Grafana).
           Started in the order listed and stopped in reverse, so a database
           is up before what uses it.  `docker stop` also keeps a service
           stopped across a reboot until started again.
- vcluster the student's whole Kubernetes cluster, paused and resumed with
           vcluster, which also stops everything running inside it.
- k8s      the copy of Keycloak, Kong or the Grafana stack the student
           installs in their own cluster in Week 4.  Stopped by scaling its
           workloads to zero, with the replica count kept in an annotation so
           starting puts back exactly what the student had.  Until the student
           installs it, it shows as "not installed yet".

Actions run in a background thread, one per component at a time, so a click
returns at once and the page shows "starting" or "stopping" until it is done.

Author: Tim Rice
"""

from __future__ import annotations

import json
import os
import threading
import time

from .run import DOCKER, VCLUSTER, host_kubectl, run, student_kubectl

STUDENT = os.environ.get("HR_STUDENT", "student01")
STUDENT_KUBECONFIG = f"/etc/rancher/student-kubeconfigs/{STUDENT}.yaml"
REPLICAS_ANNOTATION = "hackrange.io/replicas"

COMPONENTS = [
    {"id": "forgejo", "kind": "docker", "containers": ["hackrange-forgejo"],
     "name": "Git server (Forgejo)", "week": "All weeks",
     "desc": "Your repositories, pull requests and CI pipelines.  Stopping it also stops your pipelines."},
    {"id": "forgerepo", "kind": "docker", "containers": ["hackrange-forgerepo"],
     "name": "Package registry (ForgeRepo)", "week": "From Day 6",
     "desc": "Every npm, pip, Maven, apt and image download goes through it.  Stopping it stops installs."},
    {"id": "gcr", "kind": "docker", "containers": ["hackrange-gcr"],
     "name": "Code review (Git Code Review)", "week": "Days 4 and 19",
     "desc": "The SAST and secrets platform your repository is scanned into."},
    {"id": "keycloak", "kind": "docker", "containers": ["hackrange-keycloak"],
     "name": "Keycloak", "week": "Week 4",
     "desc": "The identity provider, always running.  Sign in to its admin console with the login below."},
    {"id": "kong", "kind": "docker", "containers": ["hackrange-kong-db", "hackrange-kong"],
     "name": "Kong", "week": "Week 4",
     "desc": "The API gateway, always running, with Kong Manager to add services, routes and plugins."},
    {"id": "grafana", "kind": "docker", "containers": ["hackrange-loki", "hackrange-tempo", "hackrange-grafana"],
     "name": "Grafana, Loki and Tempo", "week": "Week 4",
     "desc": "Dashboards, logs and traces, always running, with Loki and Tempo already connected."},
    {"id": "cluster", "kind": "vcluster",
     "name": "Kubernetes cluster", "week": "Weeks 3 and 4",
     "desc": "Your own cluster.  Stopping it pauses everything running inside it, Week 4 apps included."},
    {"id": "cluster-keycloak", "kind": "k8s", "namespace": "identity", "match": "keycloak",
     "name": "Keycloak in your cluster", "week": "Day 16",
     "desc": "The copy you install yourself in the namespace identity, in the Day 16 lab."},
    {"id": "cluster-kong", "kind": "k8s", "namespace": "kong", "match": "",
     "name": "Kong in your cluster", "week": "Day 17",
     "desc": "The copy you install yourself in the namespace kong, in the Day 17 lab."},
    {"id": "cluster-grafana", "kind": "k8s", "namespace": "observability", "match": "",
     "name": "Grafana stack in your cluster", "week": "Day 18",
     "desc": "The copies you install yourself in the namespace observability, in the Day 18 lab."},
]
BY_ID = {c["id"]: c for c in COMPONENTS}

_busy: dict[str, str] = {}          # component id -> "starting" | "stopping"
_last_error: dict[str, str] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------- state

def _container_state(name: str) -> str:
    rc, out = run([DOCKER, "inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                   name], timeout=10)
    if rc != 0:
        return "missing"
    status, _, health = out.partition(" ")
    if status == "running":
        return "running" if health in ("", "healthy") else "starting"
    if status in ("restarting", "created"):
        return "starting"
    return "stopped"


def _docker_state(c: dict) -> str:
    """One state for a service made of several containers."""
    each = {_container_state(n) for n in c["containers"]}
    if len(each) == 1:
        return each.pop()
    if "missing" in each:
        return "missing"
    return "starting"


def _cluster_state() -> str:
    rc, out = run([VCLUSTER, "list", "--output", "json"], timeout=20,
                  env={**os.environ, "KUBECONFIG": "/etc/rancher/k3s/k3s.yaml"})
    if rc != 0:
        return "unknown"
    try:
        entries = json.loads(out or "[]")
    except ValueError:
        return "unknown"
    for e in entries:
        if e.get("Name") == STUDENT:
            status = str(e.get("Status", "")).lower()
            if status in ("running",):
                return "running"
            if status in ("paused", "sleeping"):
                return "stopped"
            return "starting"
    return "missing"


def _workloads(c: dict) -> list[dict] | None:
    """The deployments and statefulsets of a Week 4 app, or None if the
    student's cluster cannot be asked."""
    rc, out = student_kubectl(STUDENT_KUBECONFIG, "get", "deployments,statefulsets",
                              "-n", c["namespace"], "-o", "json")
    if rc != 0:
        return [] if "NotFound" in out or "not found" in out else None
    try:
        items = json.loads(out).get("items", [])
    except ValueError:
        return None
    match = c.get("match") or ""
    return [i for i in items if match in i["metadata"]["name"]]


def _app_state(c: dict, cluster: str) -> str:
    if cluster != "running":
        return "cluster-stopped"
    items = _workloads(c)
    if items is None:
        return "unknown"
    if not items:
        return "not-installed"
    want = sum(i["spec"].get("replicas", 1) or 0 for i in items)
    ready = sum(i.get("status", {}).get("readyReplicas", 0) or 0 for i in items)
    if want == 0:
        return "stopped"
    return "running" if ready >= want else "starting"


def states() -> dict[str, str]:
    """Every component's state, as the page shows it."""
    out: dict[str, str] = {}
    cluster = _cluster_state()
    for c in COMPONENTS:
        if c["kind"] == "docker":
            s = _docker_state(c)
        elif c["kind"] == "vcluster":
            s = cluster
        else:
            s = _app_state(c, cluster)
        out[c["id"]] = _busy.get(c["id"], s)
    for cid in resetting():
        out[cid] = "resetting"
    return out


def last_errors() -> dict[str, str]:
    return dict(_last_error)


# ---------------------------------------------------------------- actions

def _docker(c: dict, action: str) -> tuple[bool, str]:
    names = c["containers"] if action == "start" else list(reversed(c["containers"]))
    rc, out = run([DOCKER, action, *names], timeout=180)
    return rc == 0, out


def _cluster(action: str) -> tuple[bool, str]:
    verb = "resume" if action == "start" else "pause"
    rc, out = run([VCLUSTER, verb, STUDENT, "--namespace", STUDENT], timeout=300,
                  env={**os.environ, "KUBECONFIG": "/etc/rancher/k3s/k3s.yaml"})
    if rc != 0:
        return False, out
    if action == "start":
        # Wait for the API to answer, so "running" means usable.
        for _ in range(60):
            if _cluster_state() == "running" and student_kubectl(STUDENT_KUBECONFIG, "get", "ns")[0] == 0:
                break
            time.sleep(5)
    return True, out


def _app(c: dict, action: str) -> tuple[bool, str]:
    items = _workloads(c)
    if items is None:
        return False, "Your Kubernetes cluster did not answer.  Is it running?"
    if not items:
        return False, "It is not installed yet: its lesson installs it."
    for i in items:
        kind = i["kind"].lower()
        name = i["metadata"]["name"]
        ns = c["namespace"]
        if action == "stop":
            replicas = i["spec"].get("replicas", 1) or 0
            if replicas == 0:
                continue
            student_kubectl(STUDENT_KUBECONFIG, "annotate", "--overwrite", "-n", ns, f"{kind}/{name}",
                            f"{REPLICAS_ANNOTATION}={replicas}")
            rc, out = student_kubectl(STUDENT_KUBECONFIG, "scale", "-n", ns, f"{kind}/{name}", "--replicas=0")
        else:
            saved = i["metadata"].get("annotations", {}).get(REPLICAS_ANNOTATION, "")
            replicas = int(saved) if saved.isdigit() and int(saved) > 0 else max(i["spec"].get("replicas", 1) or 1, 1)
            rc, out = student_kubectl(STUDENT_KUBECONFIG, "scale", "-n", ns, f"{kind}/{name}", f"--replicas={replicas}")
            student_kubectl(STUDENT_KUBECONFIG, "annotate", "-n", ns, f"{kind}/{name}", f"{REPLICAS_ANNOTATION}-")
        if rc != 0:
            return False, out
    return True, ""


def _do(cid: str, action: str) -> None:
    c = BY_ID[cid]
    try:
        if c["kind"] == "docker":
            ok, out = _docker(c, action)
        elif c["kind"] == "vcluster":
            ok, out = _cluster(action)
        else:
            ok, out = _app(c, action)
        if ok:
            _last_error.pop(cid, None)
        else:
            _last_error[cid] = (out or "it did not work")[-300:]
    finally:
        with _lock:
            _busy.pop(cid, None)


def act(cid: str, action: str) -> tuple[bool, str]:
    """Start or stop a component in the background.  Returns (accepted, message)."""
    if cid not in BY_ID or action not in ("start", "stop"):
        return False, "unknown component or action"
    with _lock:
        if cid in _busy:
            return False, "already " + _busy[cid]
        _busy[cid] = "starting" if action == "start" else "stopping"
    threading.Thread(target=_do, args=(cid, action), daemon=True).start()
    return True, _busy[cid]


def start_all() -> None:
    """Everything on: the lab's default, run at every boot.  The lab services,
    the cluster, and any Week 4 app the student installed and later stopped.
    An app the student has not installed yet stays not installed."""
    for c in COMPONENTS:
        if c["kind"] == "docker":
            _docker(c, "start")
    if _cluster_state() == "stopped":
        _cluster("start")
    for c in COMPONENTS:
        if c["kind"] == "k8s" and _app_state(c, _cluster_state()) == "stopped":
            _app(c, "start")


# ---------------------------------------------------------------- resets

# What a reset of each part also resets: Git Code Review scans the Git
# server's repositories, so a fresh Git server means a fresh Git Code Review.
RESETTABLE = {"forgejo", "forgerepo", "gcr", "cluster", "keycloak", "kong", "grafana"}
RESET_ALSO = {"forgejo": ["gcr"]}
RESET_STATUS = "/run/hackrange/reset.json"


def reset_status() -> dict:
    """{"target", "state": running|done|failed, "at"} of the last reset, or {}."""
    try:
        with open(RESET_STATUS) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def resetting() -> set[str]:
    """The components a running reset is working on."""
    st = reset_status()
    if st.get("state") != "running":
        return set()
    target = st.get("target", "")
    if target == "all":
        return {c["id"] for c in COMPONENTS if c["kind"] in ("docker", "vcluster")}
    return {target, *RESET_ALSO.get(target, [])}


def reset(target: str) -> tuple[bool, str]:
    """Start a reset as its own system job, so it outlives the panel (a reset
    of everything reruns the installer, which restarts the panel)."""
    if target != "all" and target not in RESETTABLE:
        return False, "that part cannot be reset"
    if reset_status().get("state") == "running":
        return False, "a reset is already running"
    unit = f"hackrange-reset-{int(time.time())}"
    rc, out = run(["systemd-run", "--unit", unit, "--collect", "--quiet",
                   "/usr/local/sbin/hackrange-reset", target, "--yes"], timeout=20)
    if rc != 0:
        return False, out or "the reset could not start"
    # Say "running" at once, before the job has written its own first line.
    try:
        os.makedirs(os.path.dirname(RESET_STATUS), exist_ok=True)
        with open(RESET_STATUS, "w") as fh:
            json.dump({"target": target, "state": "running", "at": int(time.time())}, fh)
    except OSError:
        pass
    return True, "resetting"
