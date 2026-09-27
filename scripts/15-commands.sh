#!/usr/bin/env bash
# Step 15: the student's commands, installed straight after the checks.
#
# They go in this early so that if a later step stops, "hackrange-lab diag"
# is already there to save a diagnostics file.  Installing them again on every
# run keeps them up to date with this copy of the lab.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

install -m 755 "$HR_ROOT/bin/hackrange-diag" /usr/local/sbin/hackrange-diag
install -m 755 "$HR_ROOT/bin/hackrange-lab" /usr/local/bin/hackrange-lab
install -m 755 "$HR_ROOT/bin/hackrange-access" /usr/local/sbin/hackrange-access
install -m 755 "$HR_ROOT/bin/hackrange-reset" /usr/local/sbin/hackrange-reset
log "installed hackrange-lab and hackrange-diag"
