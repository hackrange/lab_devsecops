#!/usr/bin/env bash
# Step 20: the packages the lab stands on, and Docker.
#
# Docker is assumed NOT to be installed.  It comes from Docker's own apt
# repository, for this Ubuntu release and this processor, which is what
# Docker's documentation recommends and what gives BuildKit and the compose
# plugin.  A brand new Ubuntu release that Docker has not published packages
# for yet falls back to Ubuntu's own docker.io packages.  Either way the step
# ends by proving Docker works, rather than assuming it.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"
# shellcheck disable=SC1091
. /etc/os-release
export DEBIAN_FRONTEND=noninteractive

step "Installing system packages"

pkgs=(ca-certificates curl git jq openssl gnupg iproute2 xz-utils unzip openssh-client nftables
      python3 nginx libnginx-mod-stream)
# An RDP client for the lab desktop, when this machine has a desktop to show it on.
if has_desktop; then pkgs+=(remmina remmina-plugin-rdp); fi

# Ubuntu's own automatic updates hold the package lock for minutes after a
# boot; apt waits for them (install.sh writes this too, for its own first apt).
printf 'DPkg::Lock::Timeout "600";\n' > /etc/apt/apt.conf.d/90hackrange-wait-for-lock
if pgrep -x unattended-upgr >/dev/null 2>&1 || pgrep -f /usr/bin/unattended-upgrade >/dev/null 2>&1; then
    say "Ubuntu is installing its own updates first; this waits for them (a few minutes at most)."
fi
retry 3 quiet apt-get update || die "apt-get update failed.  Is this machine online?"
retry 3 quiet apt-get install -y --no-install-recommends "${pkgs[@]}" ||
    die "Could not install the system packages."

# nginx's stock site listens on port 80, which the lab does not use and a
# student may already have something on.  The lab's own sites go in later.
rm -f /etc/nginx/sites-enabled/default
ok "system packages"

# ---------------------------------------------------------------- Docker

step "Installing Docker"

docker_works() {
    docker info >/dev/null 2>&1 &&
    docker compose version >/dev/null 2>&1 &&
    docker buildx version >/dev/null 2>&1
}

if command -v snap >/dev/null && snap list docker >/dev/null 2>&1; then
    die "Docker is installed here as a snap.  The snap version cannot reach the folders
    the lab uses.  Remove it with:   sudo snap remove docker
    and run the install command again; the installer puts in the right one."
fi

fresh_docker=0
if docker_works; then
    ok "Docker is already installed ($(docker version --format '{{.Server.Version}}' 2>/dev/null))"
else
    fresh_docker=1
    arch="$(dpkg --print-architecture)"
    codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"

    # Old or partial installs that conflict with Docker's packages.  Only
    # removed when Docker is not working anyway, so nothing that works is lost.
    for p in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
        dpkg -s "$p" >/dev/null 2>&1 && quiet apt-get remove -y "$p" || true
    done

    if curl -fsSI -m 20 "https://download.docker.com/linux/ubuntu/dists/${codename}/Release" >/dev/null 2>&1; then
        say "from Docker's repository (Ubuntu $codename, $arch)"
        install -m 0755 -d /etc/apt/keyrings
        retry 3 curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc ||
            die "Could not download Docker's signing key."
        chmod a+r /etc/apt/keyrings/docker.asc
        printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
            "$arch" "$codename" > /etc/apt/sources.list.d/docker.list
        retry 3 quiet apt-get update || die "apt-get update failed after adding Docker's repository."
        retry 3 quiet apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin ||
            die "Could not install Docker."
    else
        say "Docker has no packages for Ubuntu $codename yet; using Ubuntu's own"
        rm -f /etc/apt/sources.list.d/docker.list
        retry 3 quiet apt-get install -y docker.io docker-compose-v2 docker-buildx ||
            die "Could not install Docker from Ubuntu's packages."
    fi
fi

# Keep container logs from filling the disk over a month of labs, but ONLY on a
# Docker this installer just put in.  A Docker that was already here may be
# running the student's own containers (or the agent they reach this machine
# through), and restarting it would stop them.  The lab's own containers set
# the same limits for themselves (config/compose.yml, hackrange-lab), so they
# are covered either way.
if [ "$fresh_docker" = 1 ] && [ ! -s /etc/docker/daemon.json ]; then
    install -d -m 755 /etc/docker
    printf '{\n  "log-driver": "json-file",\n  "log-opts": { "max-size": "10m", "max-file": "3" }\n}\n' \
        > /etc/docker/daemon.json
    systemctl restart docker 2>/dev/null || true
fi

quiet systemctl enable --now docker.service containerd.service || quiet systemctl enable --now docker.service ||
    die "Docker is installed but would not start.  See: sudo journalctl -u docker"
wait_for 60 "Docker to start" docker info || die "Docker did not start.  See: sudo journalctl -u docker"
docker_works || die "Docker is installed but its compose or buildx plugin is missing."

# Prove it can actually run a container, not just that the command exists.
retry 3 quiet docker run --rm hello-world || die "Docker is installed but cannot run a container."
ok "Docker $(docker version --format '{{.Server.Version}}') with compose and buildx"

# The student runs the lab commands without sudo, which needs the docker group.
user="$(hr_desktop_user)"
if [ -n "$user" ] && id "$user" >/dev/null 2>&1 && ! id -nG "$user" | grep -qw docker; then
    usermod -aG docker "$user"
    say "added $user to the docker group (takes effect at the next login)"
fi
