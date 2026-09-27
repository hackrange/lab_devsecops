#!/usr/bin/env bash
# Remove the Hackrange Local Lab from this machine.
#
#   sudo /opt/hackrange-labs/uninstall.sh
#
# Removes the lab services and ALL of their data (your lab repositories, the
# package cache, your findings), the Kubernetes cluster, the CI runner, the
# lab network address, the lab certificate authority and the lab images.
# Docker itself is left installed, because other things may use it.
#
# Author: Tim Rice
set -uo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo." >&2; exit 1; }
HR_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HR_ETC=/etc/hackrange

if [ "${1:-}" != -y ] && [ "${1:-}" != --yes ]; then
    printf 'This removes the Local Lab and everything in it, including your lab\n'
    printf 'repositories on the lab Git server.  Anything you have not copied\n'
    printf 'elsewhere (for example to GitHub) is gone for good.\n\n'
    read -r -p 'Type REMOVE to continue: ' a < /dev/tty
    [ "$a" = REMOVE ] || { echo "Nothing was removed."; exit 0; }
fi

say() { printf '  %s\n' "$*"; }

say "stopping the lab session"
docker rm -f hackrange-lab >/dev/null 2>&1

say "removing the lab services and their data"
if [ -f "$HR_ETC/services.env" ]; then
    docker compose --project-directory "$HR_ETC" -f "$HR_ROOT/config/compose.yml" \
        --env-file "$HR_ETC/services.env" down -v --remove-orphans >/dev/null 2>&1
fi

say "removing the CI runner"
systemctl disable --now forgejo-runner >/dev/null 2>&1
rm -rf /etc/systemd/system/forgejo-runner.service /etc/forgejo-runner /usr/local/bin/forgejo-runner
# Job containers the runner left behind.
docker ps -aq --filter 'name=FORGEJO-ACTIONS-TASK' | xargs -r docker rm -f >/dev/null 2>&1

say "removing Kubernetes"
[ -x /usr/local/bin/k3s-uninstall.sh ] && /usr/local/bin/k3s-uninstall.sh >/dev/null 2>&1
rm -rf /etc/systemd/system/k3s.service.d /usr/local/bin/vcluster /usr/local/sbin/lab-vcluster \
       /etc/rancher /etc/sysctl.d/90-lab-inotify.conf
rmdir /var/lib/rancher 2>/dev/null
if [ -f /etc/sysctl.d/90-hackrange-x86-emulation.conf ]; then
    rm -f /etc/sysctl.d/90-hackrange-x86-emulation.conf
    sysctl -qw vm.legacy_va_layout=0
fi

say "removing nginx's lab sites"
rm -rf /etc/nginx/hackrange-brand
rm -f /etc/apt/apt.conf.d/90hackrange-wait-for-lock
rm -f /etc/nginx/conf.d/hackrange-lab.conf /etc/nginx/conf.d/hackrange-access.conf /etc/nginx/conf.d/hackrange-hostcheck.conf \
      /etc/nginx/conf.d/hackrange-host-access.conf /etc/nginx/conf.d/hackrange-week4.conf \
      /etc/nginx/hackrange-private-only.conf /etc/nginx/modules-enabled/99-hackrange-stream.conf
systemctl disable hackrange-access >/dev/null 2>&1
rm -f /etc/systemd/system/hackrange-access.service /usr/local/sbin/hackrange-access
rm -rf /etc/nginx/stream.d /etc/nginx/labtls /etc/systemd/system/nginx.service.d/hackrange.conf
systemctl reload nginx >/dev/null 2>&1 || true

say "removing the control panel"
systemctl disable --now hackrange-control hackrange-autostart >/dev/null 2>&1
rm -f /etc/systemd/system/hackrange-control.service /etc/systemd/system/hackrange-autostart.service \
      /etc/nginx/conf.d/hackrange-control.conf /etc/nginx/hackrange-lab-subnet.conf
rm -rf /usr/local/lib/hackrange/control
systemctl reload nginx >/dev/null 2>&1 || true

say "removing the lab network address and names"
systemctl disable --now hackrange-labnet >/dev/null 2>&1
command -v nft >/dev/null 2>&1 && nft delete table inet hackrange_guard 2>/dev/null || true
rm -f /etc/systemd/system/hackrange-labnet.service /etc/modules-load.d/hackrange-labnet.conf /usr/local/sbin/hackrange-labnet
kept="$(grep -v '# Hackrange Local Lab$' /etc/hosts)"; printf '%s\n' "$kept" > /etc/hosts

say "removing the lab certificate authority from this machine's trust"
rm -f /usr/local/share/ca-certificates/hackrange-lab-ca.crt
update-ca-certificates --fresh >/dev/null 2>&1

say "removing the lab images"
for i in devsecops-lab-gui:latest devsecops-lab:latest lab-forgerepo:latest github-code-review:review-1.0.4; do
    docker rmi -f "$i" >/dev/null 2>&1
done
# And the published images the lab downloaded.  Without -f: Docker refuses to
# remove an image a container still uses, so a student's own containers keep
# theirs.
if [ -f "$HR_ROOT/versions.env" ]; then
    # shellcheck disable=SC1091
    . "$HR_ROOT/versions.env"
    # debian:13-slim and golang:1.23-bookworm are the workstation build's bases.
    for i in "${FORGEJO_IMAGE:-}" "${RUNNER_JOB_IMAGE:-}" "${GUACAMOLE_IMAGE:-}" "${GUACD_IMAGE:-}" \
             "${KEYCLOAK_IMAGE:-}" "${KONG_IMAGE:-}" postgres:16-alpine "${GRAFANA_IMAGE:-}" "${LOKI_IMAGE:-}" "${TEMPO_IMAGE:-}" \
             hello-world:latest debian:13-slim golang:1.23-bookworm; do
        [ -n "$i" ] && docker rmi "$i" >/dev/null 2>&1
    done
fi
docker image prune -f >/dev/null 2>&1
# The build cache the image builds left behind, about 20 GB.  It is only a
# cache: a student's own images and containers are not touched, and their
# own builds simply rebuild what they need.
docker builder prune -af >/dev/null 2>&1

say "removing the lab's files"
rm -rf "$HR_ETC" /var/cache/hackrange /var/lib/hackrange /usr/local/lib/hackrange \
       /usr/local/sbin/hackrange-provision /usr/local/sbin/hackrange-diag /usr/local/sbin/hackrange-reset /usr/local/sbin/lab-student-registry.sh /usr/local/sbin/forgerepo-lib.sh \
       /usr/local/bin/hackrange-lab /usr/share/applications/hackrange-lab.desktop
groupdel hackrange-guac 2>/dev/null || true
systemctl daemon-reload

# Last, because this script lives there.
[ "$HR_ROOT" = /opt/hackrange-labs ] && rm -rf /opt/hackrange-labs

printf '\nThe Local Lab has been removed.  Docker is still installed.\n'
