#!/usr/bin/env bash
# Step 60: start the lab services and set each one up the way the course uses it.
#
#   Forgejo      an administrator account for the provisioner, Actions on
#   ForgeRepo    the course's package types, upstreams, applications and rules
#   GitSAST      its first administrator, signed in once, second factor enrolled
#
# then nginx in front of all three on the lab address.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Starting the lab services"

install -d -m 700 "$HR_ETC" "$HR_ETC/secrets" /etc/rancher
FORGEJO_PW="$(hr_secret "$HR_ETC/secrets/forgejo-admin" 24)"
FORGEREPO_PW="$(hr_secret "$HR_ETC/secrets/forgerepo-admin" 24)"
GCR_SECRET_KEY="$(hr_secret "$HR_ETC/secrets/gcr-secret-key" 48)"
GCR_ENCRYPTION_KEY="$(hr_secret "$HR_ETC/secrets/gcr-encryption-key" 48)"
KEYCLOAK_ADMIN_PASSWORD="$(hr_secret "$HR_ETC/secrets/keycloak-admin" 20)"
GRAFANA_ADMIN_PASSWORD="$(hr_secret "$HR_ETC/secrets/grafana-admin" 20)"
KONG_PG_PASSWORD="$(hr_secret "$HR_ETC/secrets/kong-db" 24)"

# Where the provisioner (bin/lab_provision.py) reads the admin passwords, which
# are the same paths the hosted lab node uses.
( umask 077
  printf '%s\n' "$FORGEJO_PW"   > /etc/rancher/forgejo-admin-password
  printf '%s\n' "$FORGEREPO_PW" > /etc/rancher/forgerepo-admin-password )

( umask 077
  cat > "$HR_ETC/services.env" <<EOF
# Written by the Local Lab installer.  Holds secrets: root only.
FORGEJO_IMAGE=$FORGEJO_IMAGE
FORGEREPO_IMAGE=$FORGEREPO_IMAGE
GCR_IMAGE=$GCR_IMAGE
GUACAMOLE_IMAGE=$GUACAMOLE_IMAGE
GUACD_IMAGE=$GUACD_IMAGE
KEYCLOAK_IMAGE=$KEYCLOAK_IMAGE
KONG_IMAGE=$KONG_IMAGE
GRAFANA_IMAGE=$GRAFANA_IMAGE
LOKI_IMAGE=$LOKI_IMAGE
TEMPO_IMAGE=$TEMPO_IMAGE
HR_ROOT=$HR_ROOT
HR_GUAC_GID=$(getent group hackrange-guac >/dev/null || groupadd --system hackrange-guac; getent group hackrange-guac | cut -d: -f3)
KEYCLOAK_ADMIN_PASSWORD=$KEYCLOAK_ADMIN_PASSWORD
GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD
KONG_PG_PASSWORD=$KONG_PG_PASSWORD
FORGEREPO_ADMIN_PASSWORD=$FORGEREPO_PW
GCR_SECRET_KEY=$GCR_SECRET_KEY
GCR_ENCRYPTION_KEY=$GCR_ENCRYPTION_KEY
EOF
)

# The web desktop's login file has to exist before its service starts.  A first
# install makes the first password here; every new session makes a new one.
[ -s "$HR_ETC/guacamole/user-mapping.xml" ] || quiet hackrange-access rotate ||
    die "Could not make the lab password."
# An install from before the login file had its own group: move it over.
chgrp hackrange-guac "$HR_ETC/guacamole" "$HR_ETC/guacamole/user-mapping.xml" 2>/dev/null || true

# The web desktop's HackRange branding: an extension Guacamole loads when it
# starts.  Built from config/guacamole-branding with fixed timestamps, so the
# same source always makes the same file, and Guacamole is restarted only when
# the branding really changed.
brand_jar="$HR_ETC/guacamole/extensions/hackrange-branding.jar"
install -d -m 750 "$HR_ETC/guacamole/extensions"
chown root:hackrange-guac "$HR_ETC/guacamole/extensions"
python3 - "$HR_ROOT/config/guacamole-branding" "$brand_jar.new" <<'PY' || die "Could not package the web desktop's branding."
import os, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in sorted(os.walk(src)):
        for f in sorted(files):
            path = os.path.join(root, f)
            info = zipfile.ZipInfo(os.path.relpath(path, src), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, open(path, "rb").read())
PY
brand_changed=0
if ! cmp -s "$brand_jar.new" "$brand_jar"; then
    mv "$brand_jar.new" "$brand_jar"; brand_changed=1
else
    rm -f "$brand_jar.new"
fi
chown root:hackrange-guac "$brand_jar"; chmod 640 "$brand_jar"

quiet compose up -d --remove-orphans || die "The lab services would not start.  See: sudo docker compose -p hackrange logs"

# A running Guacamole reads extensions only when it starts.
if [ "$brand_changed" = 1 ]; then quiet docker restart hackrange-guacamole || true; fi

healthy() { [ "$(docker inspect -f '{{.State.Health.Status}}' "$1" 2>/dev/null)" = healthy ]; }
for c in hackrange-forgejo hackrange-forgerepo hackrange-gcr hackrange-kong; do
    wait_for 600 "$c" healthy "$c" || die "$c did not become healthy.  See: sudo docker logs $c"
done
ok "Forgejo, ForgeRepo, Git Code Review and Kong are running"

# The Week 4 services' logins, for the start page, lab-env and the control
# panel.  hackrange-provision adds them to the lab session's environment.
( umask 027
  {
    printf 'LAB_KEYCLOAK_URL=https://10.10.10.70:8448\n'
    printf 'LAB_KEYCLOAK_USER=admin\n'
    printf 'LAB_KEYCLOAK_PASSWORD=%s\n' "$KEYCLOAK_ADMIN_PASSWORD"
    printf 'LAB_KONG_URL=https://10.10.10.70:8449\n'
    printf 'LAB_KONG_ADMIN_URL=https://10.10.10.70:8450\n'
    printf 'LAB_KONG_PROXY_URL=https://10.10.10.70:8451\n'
    printf 'LAB_GRAFANA_URL=https://10.10.10.70:8452\n'
    printf 'LAB_GRAFANA_USER=admin\n'
    printf 'LAB_GRAFANA_PASSWORD=%s\n' "$GRAFANA_ADMIN_PASSWORD"
  } > "$HR_ETC/week4.env"
)

# ---------------------------------------------------------------- nginx

step "Putting the services on the lab address"

# A lab session started by an older version of the Local Lab published SSH and
# Remote Desktop on this machine's ports itself.  nginx now owns those ports,
# and could not start while the session holds them, taking every lab service
# down with it.  The session may hold unpushed work, so it is never stopped
# for the student: they are asked to push and stop it.
for p in 2222 13389; do
    if docker port hackrange-lab 2>/dev/null | grep -qE "(0\.0\.0\.0|127\.0\.0\.1):$p\$"; then
        die "Your lab session was started by an older version of the Local Lab.
    Push your work to the lab Git server, run  hackrange-lab stop -y
    and then run the install command again."
    fi
done

install -m 644 "$HR_ROOT/config/nginx/hackrange-hostcheck.conf" /etc/nginx/conf.d/hackrange-hostcheck.conf
install -m 644 "$HR_ROOT/config/nginx/hackrange-lab.conf" /etc/nginx/conf.d/hackrange-lab.conf
# The ways into the lab (web desktop, SSH, Remote Desktop): private networks only.
install -m 644 "$HR_ROOT/config/nginx/hackrange-private-only.conf" /etc/nginx/hackrange-private-only.conf
install -m 644 "$HR_ROOT/config/nginx/hackrange-access.conf" /etc/nginx/conf.d/hackrange-access.conf
# The lab services on the VM's own address, for the student's own computer.
install -m 644 "$HR_ROOT/config/nginx/hackrange-host-access.conf" /etc/nginx/conf.d/hackrange-host-access.conf
# Keycloak, Kong and Grafana.
install -m 644 "$HR_ROOT/config/nginx/hackrange-week4.conf" /etc/nginx/conf.d/hackrange-week4.conf
# HackRange's icon for the web desktop's browser tab.
install -d -m 755 /etc/nginx/hackrange-brand
install -m 644 "$HR_ROOT/config/guacamole-branding/images/favicon-64.png" \
               "$HR_ROOT/config/guacamole-branding/images/favicon-144.png" /etc/nginx/hackrange-brand/
quiet hackrange-access cert || die "Could not make the web desktop's certificate."
install -m 644 "$HR_ROOT/config/systemd/hackrange-access.service" /etc/systemd/system/hackrange-access.service
install -d -m 755 /etc/nginx/stream.d
# The stream block belongs at the top level of nginx's configuration, which on
# Ubuntu is where modules-enabled is included.  "99" sorts it after the line
# that loads the stream module.
install -m 644 "$HR_ROOT/config/nginx/hackrange-stream.conf" /etc/nginx/modules-enabled/99-hackrange-stream.conf

# nginx listens on 10.10.10.70, which exists only once hackrange-labnet has run.
install -d -m 755 /etc/systemd/system/nginx.service.d
printf '[Unit]\nAfter=hackrange-labnet.service\nWants=hackrange-labnet.service\n' \
    > /etc/systemd/system/nginx.service.d/hackrange.conf
systemctl daemon-reload

quiet nginx -t || die "nginx's configuration has an error.  See: sudo nginx -t"
quiet systemctl enable nginx hackrange-access.service
# Reloaded, not restarted, when it is already running: a restart cuts every
# open connection, and a student updating the lab would be thrown out of the
# web desktop and their SSH sessions.  A reload takes the new configuration
# (new ports included) and lets the open connections finish in peace.
if systemctl is-active --quiet nginx; then
    quiet systemctl reload nginx || die "nginx would not take its new configuration.  See: sudo journalctl -u nginx"
else
    quiet systemctl restart nginx || die "nginx would not start.  See: sudo journalctl -u nginx"
fi

lab_up() { curl -fsS -o /dev/null --cacert "$LABTLS/lab-ca.crt" "$1"; }
wait_for 120 "https://labgit.lab:8444"  lab_up https://labgit.lab:8444/api/healthz     || die "https://labgit.lab:8444 is not answering."
wait_for 120 "https://labrepo.lab:8443" lab_up https://labrepo.lab:8443/               || die "https://labrepo.lab:8443 is not answering."
wait_for 120 "https://${HR_SERVICES_IP}:8445" lab_up "https://${HR_SERVICES_IP}:8445/healthz" || die "https://${HR_SERVICES_IP}:8445 is not answering."
ok "https://labgit.lab:8444, https://labrepo.lab:8443 and https://${HR_SERVICES_IP}:8445 answer with a trusted certificate"
wait_for 180 "the web desktop" lab_up https://127.0.0.1:8446/guacamole/ || die "The web desktop (https://127.0.0.1:8446) is not answering.  See: sudo docker logs hackrange-guacamole"
ok "the web desktop answers at https://127.0.0.1:8446"
# Keycloak takes a minute to start the first time (it builds its database).
wait_for 300 "Keycloak" lab_up https://10.10.10.70:8448/realms/master || die "Keycloak is not answering.  See: sudo docker logs hackrange-keycloak"
wait_for 120 "Kong Manager" lab_up https://10.10.10.70:8449/kconfig.js || die "Kong Manager is not answering.  See: sudo docker logs hackrange-kong"
wait_for 180 "Grafana" lab_up https://10.10.10.70:8452/api/health || die "Grafana is not answering.  See: sudo docker logs hackrange-grafana"
ok "Keycloak (8448), Kong (8449 to 8451) and Grafana with Loki and Tempo (8452) answer"

# ---------------------------------------------------------------- Forgejo

step "Setting up the lab Git server"

fj() { docker exec -u git hackrange-forgejo forgejo "$@"; }
if fj admin user list --admin 2>/dev/null | awk '{print $2}' | grep -qx labadmin; then
    # Put the password back to the one on file, in case it drifted.
    quiet fj admin user change-password --username labadmin --password "$FORGEJO_PW" --must-change-password=false ||
        die "Could not reset the Forgejo administrator's password."
else
    quiet fj admin user create --admin --username labadmin --password "$FORGEJO_PW" \
        --email labadmin@lab.local --must-change-password=false ||
        die "Could not create the Forgejo administrator."
fi
ok "Forgejo administrator ready"

# ---------------------------------------------------------------- ForgeRepo

step "Setting up the lab package registry"

export FR_URL="https://labrepo.lab:8443" FR_IP="$HR_SERVICES_IP" FR_CA="$LABTLS/lab-ca.crt" FR_PASSWORD="$FORGEREPO_PW"
quiet bash "$HR_ROOT/bin/seed-lab-registry.sh" || die "Could not configure the package registry's rules."
ok "package types, upstream registries and the course's rules are in place"

# ---------------------------------------------------------------- Git Code Review

step "Setting up the SAST platform"

if [ -s /etc/rancher/gcr-admin ]; then
    ok "Git Code Review administrator already set up"
else
    # The app makes its first administrator at start-up and leaves the starting
    # password in a file, which it deletes once that password is changed.
    first=""
    for _ in $(seq 1 30); do
        first="$(docker exec hackrange-gcr sh -c 'cat /data/first-admin.txt 2>/dev/null' | sed -n 's/^ *password: *//p')"
        [ -n "$first" ] && break
        sleep 2
    done
    [ -n "$first" ] || die "Git Code Review did not create its first administrator.  See: sudo docker logs hackrange-gcr"

    # Sign in once as that administrator, enrol the second factor and set a new
    # password, with the same code the provisioner uses for a student.
    creds="$(FIRST="$first" python3 - "$HR_ROOT/bin" <<'EOF'
import os, sys
sys.path.insert(0, sys.argv[1])
import lab_provision as lp
out = lp._sast_activate("admin", os.environ["FIRST"])
if not out.get("sast_password"):
    sys.exit(1)
print(out["sast_password"])
print(out["sast_totp_secret"])
EOF
)" || die "Could not finish setting up the Git Code Review administrator."
    ( umask 077; printf '%s\n' "$creds" > /etc/rancher/gcr-admin )
    ok "Git Code Review administrator set up"
fi
