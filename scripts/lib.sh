#!/usr/bin/env bash
# The settings in this file are read by the step scripts that source it.
# shellcheck disable=SC2034
# Shared helpers for the Local Lab installer.  Every step script sources this.
#
# The rules every step follows:
#   - It is safe to run again.  Each step checks what is already there and
#     only does what is missing, so a failed install is fixed by running the
#     same one line command again.
#   - It says what it is doing in plain words, because the person reading the
#     screen is a student, not an administrator.
#   - The full detail goes to the log, so a failure can be diagnosed later.
#
# Author: Tim Rice

set -Eeuo pipefail

HR_ROOT="${HR_ROOT:-/opt/hackrange-labs}"      # this repository, once installed
HR_ETC=/etc/hackrange                          # generated settings and secrets
HR_LOG="${HR_LOG:-/var/log/hackrange-install.log}"
HR_SERVICES_IP=10.10.10.70                     # where the lab services answer
HR_STUDENT="${HR_STUDENT:-student01}"          # the one learner; lessons print this name
LABTLS=/etc/nginx/labtls                       # the lab CA and service certificate

# shellcheck source=../versions.env
. "$HR_ROOT/versions.env"

# ---------------------------------------------------------------- output

if [ -t 1 ]; then
    C_BOLD=$'\e[1m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_DIM=$'\e[2m'; C_OFF=$'\e[0m'
else
    C_BOLD=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_DIM=''; C_OFF=''
fi

log()   { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$HR_LOG"; }
step()  { printf '\n%s==> %s%s\n' "$C_BOLD" "$*" "$C_OFF"; log "STEP $*"; }
say()   { printf '    %s\n' "$*"; log "$*"; }
ok()    { printf '    %s[ok]%s %s\n' "$C_GREEN" "$C_OFF" "$*"; log "OK $*"; }
warn()  { printf '    %s[warning]%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; log "WARN $*"; }
die() {
    printf '\n%s[stopped]%s %s\n' "$C_RED" "$C_OFF" "$*" >&2
    printf '\n    Nothing is broken: run the same install command again and it\n' >&2
    printf '    picks up where it stopped.  The full log is %s\n' "$HR_LOG" >&2
    if command -v hackrange-lab >/dev/null 2>&1; then
        printf '    If it stops again, run  hackrange-lab diag  and send the file it saves.\n' >&2
    fi
    printf '\n' >&2
    # One line, whatever the message: setup.sh reads the last log line to
    # tell a stop it explained from one it did not.
    log "DIE $(printf '%s' "$*" | tr -s '\n ' ' ')"
    exit 1
}

# Run a command with its output in the log rather than on the screen.  On
# failure, the last lines are shown so the student sees why.
quiet() {
    local out rc=0
    log "RUN $*"
    out="$(mktemp)"
    "$@" > "$out" 2>&1 || rc=$?
    cat "$out" >> "$HR_LOG"
    if [ "$rc" -ne 0 ]; then
        printf '%s' "$C_DIM" >&2
        tail -n 12 "$out" | sed 's/^/      /' >&2
        printf '%s' "$C_OFF" >&2
    fi
    rm -f "$out"
    return "$rc"
}

# retry N CMD...  for anything that talks to the internet.
retry() {
    local n="$1" i; shift
    for i in $(seq 1 "$n"); do
        "$@" && return 0
        [ "$i" -lt "$n" ] && { log "retry $i/$n failed: $*"; sleep $((i * 5)); }
    done
    return 1
}

# wait_for SECONDS DESCRIPTION CMD...  poll until CMD succeeds.
wait_for() {
    local limit="$1" what="$2" waited=0; shift 2
    until "$@" >/dev/null 2>&1; do
        waited=$((waited + 5))
        [ "$waited" -ge "$limit" ] && return 1
        [ $((waited % 30)) -eq 0 ] && say "still waiting for $what ($waited s)"
        sleep 5
    done
}

# ---------------------------------------------------------------- the machine

# Debian-style names, which is what every download in this project uses.
hr_arch() {
    case "$(uname -m)" in
        x86_64|amd64)  echo amd64 ;;
        aarch64|arm64) echo arm64 ;;
        *)             echo unsupported ;;
    esac
}

# The desktop session's user, if there is one: the person who ran sudo.
hr_desktop_user() {
    local u="${SUDO_USER:-}"
    [ -n "$u" ] && [ "$u" != root ] && { echo "$u"; return; }
    logname 2>/dev/null || true
}

has_desktop() {
    [ -n "${XDG_CURRENT_DESKTOP:-}" ] && return 0
    systemctl list-units --type=service --state=running 2>/dev/null | grep -qE 'gdm|lightdm|sddm' && return 0
    dpkg -l ubuntu-desktop ubuntu-desktop-minimal 2>/dev/null | grep -q '^ii'
}

# A secret that survives re-runs: generated once, then read back.
hr_secret() {
    local file="$1" len="${2:-24}"
    if [ ! -s "$file" ]; then
        install -d -m 700 "$(dirname "$file")"
        ( umask 077; openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$len" > "$file" )
    fi
    cat "$file"
}

compose() { docker compose --project-directory "$HR_ETC" -f "$HR_ROOT/config/compose.yml" --env-file "$HR_ETC/services.env" "$@"; }

kubectl_host() { /usr/local/bin/kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "$@"; }
