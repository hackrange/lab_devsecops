#!/usr/bin/env bash
# Step 30: the lab services' address and names.
#
# In the hosted course the lab services live on a node at 10.10.10.70, and the
# lessons, the certificates and the Git server's own links all say so.  Rather
# than rewrite any of that, this machine gives itself that address on a private
# interface (lab0), and the names labgit.lab and labrepo.lab point at it.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Setting up the lab network address"

modprobe dummy 2>/dev/null || true
printf 'dummy\n' > /etc/modules-load.d/hackrange-labnet.conf
install -m 755 "$HR_ROOT/bin/hackrange-labnet" /usr/local/sbin/hackrange-labnet
install -m 644 "$HR_ROOT/config/systemd/hackrange-labnet.service" /etc/systemd/system/
systemctl daemon-reload
quiet systemctl enable --now hackrange-labnet.service ||
    die "Could not create the lab network interface.  See: sudo journalctl -u hackrange-labnet"
# Applied directly as well, rather than by restarting the unit: a restart would
# take lab0 down first, and every lab service with it, in the middle of an
# update.  "up" only adds what is missing.
quiet /usr/local/sbin/hackrange-labnet up || die "Could not set the lab network address."

ip -4 addr show lab0 | grep -q "$HR_SERVICES_IP" || die "The lab address did not come up on lab0."
grep -qE "^${HR_SERVICES_IP//./\\.}[[:space:]].*labgit\.lab" /etc/hosts || die "The lab names were not added to /etc/hosts."
ok "lab services will answer on $HR_SERVICES_IP (labgit.lab, labrepo.lab)"
