#!/usr/bin/env bash
# Run every setup step, in order.  install.sh calls this; so can a student who
# wants to re-run the install from an existing copy:
#
#   sudo /opt/hackrange-labs/scripts/setup.sh
#
# Each step is its own script, numbered in the order they must run, and each
# one is safe to run again.
#
# Author: Tim Rice

set -Eeuo pipefail
HR_ROOT="${HR_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
export HR_ROOT
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo." >&2; exit 1; }

install -d -m 755 "$(dirname "$HR_LOG")"
touch "$HR_LOG"; chmod 600 "$HR_LOG"
log "==== setup started from $HR_ROOT ($(git -C "$HR_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown))"

started=$(date +%s)
for s in "$HR_ROOT"/scripts/[0-9][0-9]-*.sh; do
    rc=0; bash "$s" || rc=$?
    [ "$rc" -eq 0 ] && continue
    # A step that stops through die() has already said why, and logged it last.
    # Anything else stopped without a word, so say which step it was.
    [ "$(tail -n 1 "$HR_LOG" | cut -d' ' -f3)" = DIE ] && exit 1
    die "Step $(basename "$s" .sh) stopped unexpectedly (exit code $rc)."
done

mins=$(( ($(date +%s) - started) / 60 ))
log "==== setup finished in ${mins} min"

user="$(hr_desktop_user)"
printf '\n%s' "$C_GREEN$C_BOLD"
printf '==================================================================\n'
printf '  The Local Lab is installed.  (%s minutes)\n' "$mins"
printf '==================================================================%s\n' "$C_OFF"

# The web address, SSH command, username and password, exactly as
# show_information.sh prints them later.
/usr/local/sbin/hackrange-access info

printf '  Handy commands:\n'
printf '      /opt/hackrange-labs/show_information.sh   show all of this again\n'
printf '      hackrange-lab status                      is everything running?\n'
printf '      hackrange-lab reset                       a fresh lab, new password\n'
printf '      hackrange-lab help                        everything else\n\n'
if [ -n "$user" ]; then
    printf '  %s: log out of Ubuntu and back in once, so the lab commands work\n' "$user"
    printf '  without typing sudo.\n\n'
fi
