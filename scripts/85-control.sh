#!/usr/bin/env bash
# Step 85: the control panel, and "everything on" at every boot.
#
# The panel shows how to get into the lab and its services, how hard the
# machine and each part of the lab are working, and start and stop buttons.
# It is the lab desktop's start page (https://10.10.10.70:8447), and it is at
# https://<machine>:8446/control/ from the student's own computer.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Setting up the lab control panel"

install -d -m 755 /usr/local/lib/hackrange/control
cp -a "$HR_ROOT/lib/hackrange-control/." /usr/local/lib/hackrange/control/
find /usr/local/lib/hackrange/control -name '__pycache__' -prune -exec rm -rf {} +
chmod -R go-w /usr/local/lib/hackrange/control

# Only the lab session's own network may use the no-login door.
subnet="$(docker network inspect hackrange-access -f '{{(index .IPAM.Config 0).Subnet}}' 2>/dev/null)"
[ -n "$subnet" ] || die "The lab session's network (hackrange-access) is missing.  Run the installer again."
printf '# The lab session network, written by the installer.\nallow %s;\n' "$subnet" > /etc/nginx/hackrange-lab-subnet.conf
install -m 644 "$HR_ROOT/config/nginx/hackrange-control.conf" /etc/nginx/conf.d/hackrange-control.conf
quiet nginx -t || die "nginx's configuration has an error.  See: sudo nginx -t"
quiet systemctl reload nginx

for u in hackrange-control hackrange-autostart; do
    install -m 644 "$HR_ROOT/config/systemd/$u.service" "/etc/systemd/system/$u.service"
done
systemctl daemon-reload
quiet systemctl enable hackrange-control.service hackrange-autostart.service
quiet systemctl restart hackrange-control.service || die "The control panel would not start.  See: sudo journalctl -u hackrange-control"

panel_up() { curl -fsS -o /dev/null --cacert "$LABTLS/lab-ca.crt" https://10.10.10.70:8447/api/whoami; }
wait_for 60 "the control panel" panel_up || die "The control panel is not answering.  See: sudo journalctl -u hackrange-control"
ok "the control panel answers (https://10.10.10.70:8447 in the lab, /control/ on the web desktop)"
