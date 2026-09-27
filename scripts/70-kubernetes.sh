#!/usr/bin/env bash
# Step 70: Kubernetes, the way the hosted lab node runs it.
#
# k3s on this machine, and the vcluster tool that carves the student's own
# virtual cluster out of it (step 90 makes the cluster).  The student gets a
# virtual cluster rather than the k3s cluster itself because the lessons are
# written against its behavior: the quota that refuses NodePort, the Pod
# Security rules that leave a privileged pod Pending, the missing metrics API.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Installing Kubernetes (k3s $K3S_VERSION)"
arch="$(hr_arch)"

install -m 644 "$HR_ROOT/config/k3s/90-lab-inotify.conf" /etc/sysctl.d/90-lab-inotify.conf
quiet sysctl --system || true

# Configuration first, so k3s starts the right way the first time.
install -d -m 755 /etc/rancher/k3s
install -m 644 "$HR_ROOT/config/k3s/config.yaml"     /etc/rancher/k3s/config.yaml
install -m 644 "$HR_ROOT/config/k3s/registries.yaml" /etc/rancher/k3s/registries.yaml
certs_d="/var/lib/rancher/k3s/agent/etc/containerd/certs.d/labrepo.lab:8443"
install -d -m 755 "$certs_d"
install -m 644 "$HR_ROOT/config/k3s/hosts.toml" "$certs_d/hosts.toml"

# k3s talks to the lab registry at 10.10.10.70, which lab0 provides.
install -d -m 755 /etc/systemd/system/k3s.service.d
printf '[Unit]\nAfter=hackrange-labnet.service\nWants=hackrange-labnet.service\n' \
    > /etc/systemd/system/k3s.service.d/hackrange.conf

# On a first install there is no k3s yet, and with pipefail that failure would
# end this step without a word, so an empty answer is fine here.
have="$(k3s --version 2>/dev/null | awk 'NR==1 {print $3}')" || true
if [ "$have" = "$K3S_VERSION" ] && systemctl is-active --quiet k3s; then
    ok "k3s $have already installed"
else
    # The install script from the pinned release's own tag, checked against a
    # known SHA-256 before it runs as root (get.k3s.io changes over time).  The
    # script then checks the k3s binary against the release's checksums.
    k3s_script="https://raw.githubusercontent.com/k3s-io/k3s/$(printf '%s' "$K3S_VERSION" | sed 's/+/%2B/')/install.sh"
    retry 3 curl -fsSL -o /tmp/k3s-install.sh "$k3s_script" || die "Could not download the k3s installer."
    echo "$K3S_INSTALL_SHA256  /tmp/k3s-install.sh" | sha256sum -c - >> "$HR_LOG" 2>&1 ||
        die "The k3s installer did not match its expected checksum; not running it."
    INSTALL_K3S_VERSION="$K3S_VERSION" retry 2 quiet sh /tmp/k3s-install.sh ||
        die "Installing k3s failed.  See $HR_LOG"
    rm -f /tmp/k3s-install.sh
fi
systemctl daemon-reload
quiet systemctl enable k3s
systemctl is-active --quiet k3s || quiet systemctl restart k3s

node_ready() { kubectl_host get nodes --no-headers 2>/dev/null | grep -qw Ready; }
wait_for 300 "Kubernetes to be ready" node_ready || die "Kubernetes did not become ready.  See: sudo journalctl -u k3s"
ok "Kubernetes is ready"

# ---- vcluster --------------------------------------------------------------------
if [ "$(vcluster --version 2>/dev/null | awk '{print $NF}')" = "$VCLUSTER_VERSION" ]; then
    ok "vcluster $VCLUSTER_VERSION already installed"
else
    tmp="$(mktemp -d)"
    base="https://github.com/loft-sh/vcluster/releases/download/v${VCLUSTER_VERSION}"
    retry 3 curl -fsSL -o "$tmp/vcluster-linux-$arch" "$base/vcluster-linux-$arch" || die "Could not download vcluster."
    retry 3 curl -fsSL -o "$tmp/checksums.txt" "$base/checksums.txt" || die "Could not download vcluster's checksums."
    ( cd "$tmp" && grep -E " vcluster-linux-$arch\$" checksums.txt | sha256sum -c - ) >> "$HR_LOG" 2>&1 ||
        die "The vcluster download did not match its published checksum."
    install -m 755 "$tmp/vcluster-linux-$arch" /usr/local/bin/vcluster
    rm -rf "$tmp"
    ok "vcluster $VCLUSTER_VERSION installed (checksum verified)"
fi

# The script that makes the student's cluster, and the values it uses.
install -m 755 "$HR_ROOT/bin/lab-vcluster" /usr/local/sbin/lab-vcluster
install -m 644 "$HR_ROOT/config/k3s/student-vcluster-values.yaml" /etc/rancher/student-vcluster-values.yaml

# A cluster made before these values changed keeps the old ones until it is
# upgraded, and the provisioner never re-creates a cluster that exists.  The
# upgrade keeps everything in the cluster; it only restarts its control plane.
sum="$(sha256sum /etc/rancher/student-vcluster-values.yaml | cut -c1-64)"
mark=/var/lib/hackrange/vcluster-values.sha256
install -d -m 700 /var/lib/hackrange
if kubectl_host get namespace "$HR_STUDENT" >/dev/null 2>&1 && [ "$(cat "$mark" 2>/dev/null)" != "$sum" ]; then
    say "Applying new settings to your Kubernetes cluster (what is in it is kept)"
    quiet /usr/local/sbin/lab-vcluster create "$HR_STUDENT" || warn "Could not apply the new cluster settings; it keeps the old ones."
fi
echo "$sum" > "$mark"
