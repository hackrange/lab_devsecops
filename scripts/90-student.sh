#!/usr/bin/env bash
# Step 90: the student, their lab session, and the command they use.
#
# One student, created with the hosted course's own provisioner: a lab Git
# account, their virtual Kubernetes cluster, a package registry token and
# portal account, and a Git Code Review account with its second factor already
# enrolled.  The name is student01, because that is the name the lessons show
# in their example output.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Creating your lab accounts and your Kubernetes cluster"

# The provisioner and the scripts it calls, where it expects them.
install -d -m 755 /usr/local/lib/hackrange
install -m 644 "$HR_ROOT/bin/lab_provision.py" /usr/local/lib/hackrange/lab_provision.py
for f in lab-student-registry.sh forgerepo-lib.sh; do
    install -m 755 "$HR_ROOT/bin/$f" "/usr/local/sbin/$f"
done
install -m 755 "$HR_ROOT/bin/hackrange-provision" /usr/local/sbin/hackrange-provision

# What the registry scripts need to sign in.  A token lasts a year here rather
# than the hosted thirty days, because a student may take longer than a month
# and nobody else is issuing them a new one.
export FR_URL="https://labrepo.lab:8443" FR_IP="$HR_SERVICES_IP" FR_CA="$LABTLS/lab-ca.crt"
FR_PASSWORD="$(cat /etc/rancher/forgerepo-admin-password)"; export FR_PASSWORD
export TOKEN_DAYS=365

say "this takes a few minutes the first time (the cluster is being built)"
result="$(hackrange-provision "$HR_STUDENT" "$HR_ETC/lab.env" 2>>"$HR_LOG")" ||
    die "Creating the student accounts failed.  See $HR_LOG"
log "provision: $result"
missing="$(printf '%s' "$result" | python3 -c 'import json,sys; print(" ".join(json.load(sys.stdin)["missing"]))')"
if [ -n "$missing" ]; then
    # Anything missing is filled in by the next run, so say how, not just what.
    warn "Some accounts are not finished yet: $missing"
    warn "Run the install command again to complete them."
else
    ok "$HR_STUDENT has a Git account, a cluster, a registry token and a SAST account"
fi

# The session file is read by the docker command, run by the student, who is
# in the docker group.  Nobody else on the machine can read it.
chgrp docker "$HR_ETC/lab.env" && chmod 640 "$HR_ETC/lab.env"
chmod 755 "$HR_ETC"
install -d -m 700 "$HR_ETC/secrets"

# The lab workstation's SSH host keys, made once and given to every session, so
# a student's ssh never warns that the host key changed between sessions.
install -d -m 700 "$HR_ETC/ssh"
for t in ed25519 ecdsa rsa; do
    [ -s "$HR_ETC/ssh/ssh_host_${t}_key" ] ||
        quiet ssh-keygen -q -t "$t" -N '' -C "hackrange-lab" -f "$HR_ETC/ssh/ssh_host_${t}_key" ||
        die "Could not make the lab's SSH host keys."
done

# The ports a student uses.  nginx answers on them (private networks only) and
# passes them to the session, which itself listens on loopback only.
printf '# Local Lab settings for hackrange-lab.\nIMAGE=%s\nWEB_PORT=8446\nSSH_PORT=2222\nRDP_PORT=13389\n' \
    "$LAB_GUI_IMAGE" > "$HR_ETC/lab.conf"
chmod 644 "$HR_ETC/lab.conf"

# ---- a way in from the desktop -----------------------------------------------------
step "Adding the lab to this machine"
if has_desktop; then
    # An RDP client, so "hackrange-lab desktop" opens the lab in one step.
    quiet apt-get install -y freerdp3-x11 || quiet apt-get install -y freerdp2-x11 ||
        warn "No FreeRDP client could be installed; use any Remote Desktop app instead."
    cat > /usr/share/applications/hackrange-lab.desktop <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Hackrange Lab
Comment=Open your DevSecOps lab desktop
Exec=hackrange-lab desktop
Icon=utilities-terminal
Terminal=false
Categories=Development;Education;
EOF
    ok "\"Hackrange Lab\" is in the applications menu"
fi

# ---- a session, as a proof that everything fits together ---------------------------
# A session that is already running is never touched: it may hold work the
# student has not pushed yet.  If this install built a newer image, say so, and
# let the student move to it when they are ready.
if [ "$(docker inspect -f '{{.State.Running}}' hackrange-lab 2>/dev/null)" = true ]; then
    if [ "$(docker inspect -f '{{.Image}}' hackrange-lab)" != "$(docker image inspect -f '{{.Id}}' "$LAB_GUI_IMAGE")" ]; then
        warn "Your running lab session uses the previous version.  Push your work, then"
        warn "run  hackrange-lab reset  to move to the new one."
    fi
else
    quiet hackrange-lab start || die "The lab session would not start.  See $HR_LOG"
fi
env_ok() { docker exec -u student hackrange-lab bash -lc 'test -n "$LAB_GIT_URL" && git ls-remote "$LAB_GIT_URL/$LAB_GIT_USER/does-not-exist" 2>&1 | grep -qiE "not found|repository"'; }
if wait_for 60 "the session to reach the lab Git server" env_ok; then
    ok "a lab session is running and can reach the lab Git server"
else
    warn "The session started, but could not reach the lab Git server yet.  Try: hackrange-lab status"
fi

# The web desktop really accepts the current password (a token back means the
# login file, nginx and Guacamole all agree).
web_ok() {
    local pw; pw="$(sed -n 's/^LAB_ACCESS_PASSWORD=//p' "$HR_ETC/access.env")"
    curl -fsS -o /dev/null --data-urlencode username=student --data-urlencode "password=$pw" \
        https://127.0.0.1:8446/guacamole/api/tokens
}
if wait_for 60 "the web desktop login" web_ok; then
    ok "the web desktop accepts the lab password"
else
    warn "The web desktop did not accept the lab password yet.  Try: hackrange-lab reset"
fi
