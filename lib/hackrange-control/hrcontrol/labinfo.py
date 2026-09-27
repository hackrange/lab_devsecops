"""What the student needs to get into their lab and its services.

Read fresh on every request from the files the installer and hackrange-access
keep current, so the page never shows a password that has since changed.

Author: Tim Rice
"""

from __future__ import annotations

import ipaddress
import subprocess
import sys
import time

sys.path.insert(0, "/usr/local/lib/hackrange")

LAB_ENV = "/etc/hackrange/lab.env"
ACCESS_ENV = "/etc/hackrange/access.env"
LAB_IP = "10.10.10.70"


def _read_env(path: str) -> dict:
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k] = v
    except OSError:
        pass
    return out


def access_password() -> str:
    return _read_env(ACCESS_ENV).get("LAB_ACCESS_PASSWORD", "")


def machine_ip() -> str:
    """This machine's address on its own network, if it is a private one."""
    try:
        out = subprocess.run(["ip", "-4", "route", "get", "1.1.1.1"], capture_output=True, text=True, timeout=5).stdout
        ip = out.split(" src ")[1].split()[0]
        return ip if ipaddress.ip_address(ip).is_private else ""
    except (IndexError, ValueError, OSError, subprocess.SubprocessError):
        return ""


def _totp(secret: str) -> dict:
    if not secret:
        return {}
    try:
        import lab_provision  # the hosted provisioner, installed alongside
        return {"code": lab_provision._totp_now(secret), "seconds": 30 - int(time.time()) % 30}
    except Exception:
        return {}


def info() -> dict:
    env = _read_env(LAB_ENV)
    ip = machine_ip()
    host = ip or "127.0.0.1"
    pw = access_password()
    return {
        "machine_ip": ip,
        "access": {
            "username": "student",
            "password": pw,
            "web_host": f"https://{host}:8446",
            "ssh_host": f"ssh -p 2222 student@{host}",
            "ssh_local": "ssh -p 2222 student@127.0.0.1",
            "rdp_host": f"{host}:13389",
        },
        "services": [
            {"id": "forgejo", "name": "Git server (Forgejo)",
             "inside": "https://labgit.lab:8444", "outside": f"https://{host}:8444",
             "creds": [["username", env.get("LAB_GIT_USER", "")], ["password", env.get("LAB_GIT_PASSWORD", "")]]},
            {"id": "forgerepo", "name": "Package registry (ForgeRepo)",
             "inside": "https://labrepo.lab:8443/admin/", "outside": f"https://{host}:8443/admin/",
             "creds": [["username", env.get("LAB_REGISTRY_USER", "")], ["password", env.get("LAB_REGISTRY_PASSWORD", "")],
                       ["npm and pip token", env.get("LAB_REGISTRY_TOKEN", "")]]},
            {"id": "gcr", "name": "Code review (Git Code Review)",
             "inside": f"https://{LAB_IP}:8445", "outside": f"https://{host}:8445",
             "creds": [["username", env.get("LAB_SAST_USER", "")], ["password", env.get("LAB_SAST_PASSWORD", "")]],
             "totp": _totp(env.get("LAB_SAST_TOTP", ""))},
            {"id": "keycloak", "name": "Keycloak",
             "inside": "https://10.10.10.70:8448", "outside": f"https://{host}:8448",
             "creds": [["username", env.get("LAB_KEYCLOAK_USER", "")], ["password", env.get("LAB_KEYCLOAK_PASSWORD", "")]]},
            {"id": "kong", "name": "Kong",
             "inside": "https://10.10.10.70:8449", "outside": "",
             "creds": [["admin API", env.get("LAB_KONG_ADMIN_URL", "")], ["gateway", env.get("LAB_KONG_PROXY_URL", "")]],
             "note": ("Kong Manager and its admin API have no login, so they open only inside the lab desktop.  "
                      f"The gateway itself is also at https://{host}:8451 from your own computer.")},
            {"id": "grafana", "name": "Grafana",
             "inside": "https://10.10.10.70:8452", "outside": f"https://{host}:8452",
             "creds": [["username", env.get("LAB_GRAFANA_USER", "")], ["password", env.get("LAB_GRAFANA_PASSWORD", "")]],
             "note": "Loki (logs) and Tempo (traces) are already connected: open Explore."},
            {"id": "cluster", "name": "Kubernetes cluster",
             "inside": "", "outside": "",
             "creds": [["API", env.get("LAB_K8S_API", "")]],
             "note": "kubectl in the lab terminal is already set up for it."},
        ],
    }
