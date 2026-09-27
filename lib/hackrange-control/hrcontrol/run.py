"""Run a command without a shell, with a time limit, and never raise.

Every command the control panel runs goes through here: arguments are a list
(nothing a request sends ever reaches a shell), and a command that hangs is
cut off rather than hanging the page.

Author: Tim Rice
"""

from __future__ import annotations

import subprocess

HOST_KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"
KUBECTL = "/usr/local/bin/kubectl"
VCLUSTER = "/usr/local/bin/vcluster"
DOCKER = "docker"


def run(cmd: list[str], timeout: int = 20, env: dict | None = None) -> tuple[int, str]:
    """Return (exit code, combined output).  Exit code 124 means it timed out."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as exc:
        return 127, str(exc)


def host_kubectl(*args: str, timeout: int = 20) -> tuple[int, str]:
    """kubectl against the machine's own k3s (where the student's cluster runs)."""
    return run([KUBECTL, "--kubeconfig", HOST_KUBECONFIG, *args], timeout=timeout)


def student_kubectl(kubeconfig: str, *args: str, timeout: int = 20) -> tuple[int, str]:
    """kubectl inside the student's own virtual cluster."""
    return run([KUBECTL, "--kubeconfig", kubeconfig, "--request-timeout=15s", *args], timeout=timeout)
