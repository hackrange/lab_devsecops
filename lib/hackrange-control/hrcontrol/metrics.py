"""How hard the lab is working: the whole machine, and each part of the lab.

A background thread samples every few seconds and keeps the latest numbers,
so a page load never waits on `docker stats` (which takes a couple of seconds)
or on the cluster.

- The machine: CPU from /proc/stat, memory from /proc/meminfo (what programs
  really hold, not the page cache), disk for the filesystem the lab lives on.
- Containers: `docker stats`.
- The student's cluster and each Week 4 app: `kubectl top` on the machine's
  own k3s, which sees every pod of the virtual cluster under a name ending in
  -x-<namespace>-x-<student>.

Author: Tim Rice
"""

from __future__ import annotations

import os
import shutil
import threading
import time

from .run import DOCKER, host_kubectl, run

STUDENT = os.environ.get("HR_STUDENT", "student01")
INTERVAL = 5

_latest: dict = {"host": {}, "containers": {}, "pods": {}, "at": 0}
_lock = threading.Lock()


def _cpu_times() -> tuple[int, int]:
    with open("/proc/stat") as fh:
        parts = [int(x) for x in fh.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    return sum(parts), idle


def _memory() -> dict:
    info = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) * 1024
    total = info.get("MemTotal", 0)
    used = total - info.get("MemAvailable", 0)
    return {"total": total, "used": used}


def _disk() -> dict:
    u = shutil.disk_usage("/var/lib")
    return {"total": u.total, "used": u.used}


def _size(text: str) -> int:
    """'512MiB' or '1.2GiB' or '300kB' as bytes."""
    text = text.strip()
    units = [("KiB", 1024), ("MiB", 1024 ** 2), ("GiB", 1024 ** 3), ("TiB", 1024 ** 4),
             ("kB", 1000), ("MB", 1000 ** 2), ("GB", 1000 ** 3), ("B", 1)]
    for unit, mult in units:
        if text.endswith(unit):
            try:
                return int(float(text[: -len(unit)]) * mult)
            except ValueError:
                return 0
    return 0


def _containers() -> dict:
    rc, out = run([DOCKER, "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"], timeout=30)
    result = {}
    if rc != 0:
        return result
    for line in out.splitlines():
        try:
            name, cpu, mem = line.split("\t")
            result[name] = {"cpu": float(cpu.rstrip("%") or 0), "mem": _size(mem.split("/")[0])}
        except ValueError:
            continue
    return result


def _pods(cores: int) -> dict:
    """{pod name: {cpu (percent of the machine), mem}} for the student's cluster."""
    rc, out = host_kubectl("top", "pods", "-n", STUDENT, "--no-headers", timeout=20)
    result = {}
    if rc != 0:
        return result
    for line in out.splitlines():
        f = line.split()
        if len(f) < 3:
            continue
        cpu_m = int(f[1].rstrip("m")) if f[1].endswith("m") else int(float(f[1]) * 1000)
        # kubectl says 123Mi or 1Gi (or bare bytes); _size wants 123MiB.
        mem = f[2] + "B" if f[2].endswith("i") or f[2].isdigit() else f[2]
        result[f[0]] = {"cpu": cpu_m / 10.0 / max(cores, 1), "mem": _size(mem)}
    return result


def _loop() -> None:
    cores = os.cpu_count() or 1
    prev = _cpu_times()
    while True:
        time.sleep(INTERVAL)
        now = _cpu_times()
        dt, di = now[0] - prev[0], now[1] - prev[1]
        prev = now
        host = {"cpu": round(100.0 * (dt - di) / dt, 1) if dt else 0.0, "cores": cores,
                "memory": _memory(), "disk": _disk(), "load": os.getloadavg()[0]}
        containers = _containers()
        pods = _pods(cores)
        with _lock:
            _latest.update(host=host, containers=containers, pods=pods, at=time.time())


def start() -> None:
    threading.Thread(target=_loop, daemon=True).start()


def snapshot() -> dict:
    with _lock:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in _latest.items()}


def usage_for(component: dict, snap: dict) -> dict:
    """CPU (percent of the whole machine) and memory for one component."""
    kind = component["kind"]
    if kind == "docker":
        cores = snap["host"].get("cores", 1) or 1
        parts = [snap["containers"].get(n, {}) for n in component["containers"]]
        return {"cpu": round(sum(p.get("cpu", 0.0) for p in parts) / cores, 1),
                "mem": sum(p.get("mem", 0) for p in parts)}
    pods = snap["pods"]
    if kind == "vcluster":
        chosen = pods.values()
    else:
        tag = f"-x-{component['namespace']}-x-"
        chosen = [v for k, v in pods.items() if tag in k]
    return {"cpu": round(sum(p["cpu"] for p in chosen), 1), "mem": sum(p["mem"] for p in chosen)}
