#!/usr/bin/env bash
# Step 80: the CI runner that executes the workflows students push to the lab
# Git server, from Day 5 on.
#
# Same runner, same version and same job settings as the hosted course; the
# only difference is that jobs run in Docker on this machine rather than in
# Podman on a runner VM.  Jobs are started for the label "docker" (the lessons
# say `runs-on: docker`) in node:24-bookworm.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Installing the CI runner (forgejo-runner $FORGEJO_RUNNER_VERSION)"
arch="$(hr_arch)"

if [ "$(forgejo-runner --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)" = "$FORGEJO_RUNNER_VERSION" ]; then
    ok "forgejo-runner $FORGEJO_RUNNER_VERSION already installed"
else
    tmp="$(mktemp -d)"
    f="forgejo-runner-${FORGEJO_RUNNER_VERSION}-linux-${arch}.xz"
    base="https://code.forgejo.org/forgejo/runner/releases/download/v${FORGEJO_RUNNER_VERSION}"
    retry 3 curl -fsSL -m 600 -o "$tmp/$f" "$base/$f" || die "Could not download forgejo-runner."
    retry 3 curl -fsSL -o "$tmp/$f.sha256" "$base/$f.sha256" || die "Could not download forgejo-runner's checksum."
    ( cd "$tmp" && echo "$(cut -d' ' -f1 "$f.sha256")  $f" | sha256sum -c - ) >> "$HR_LOG" 2>&1 ||
        die "The forgejo-runner download did not match its published checksum."
    xz -dc "$tmp/$f" > "$tmp/forgejo-runner"
    install -m 755 "$tmp/forgejo-runner" /usr/local/bin/forgejo-runner
    rm -rf "$tmp"
    ok "forgejo-runner installed (checksum verified)"
fi

install -d -m 755 /etc/forgejo-runner
install -m 644 "$HR_ROOT/config/runner/config.yml" /etc/forgejo-runner/config.yml
# lab-ca.crt was put here in step 40; jobs get it mounted as lab-runner-ca.crt.
[ -s /etc/forgejo-runner/lab-ca.crt ] || die "The lab CA is missing from /etc/forgejo-runner.  Run the installer again."

if [ ! -s /etc/forgejo-runner/.runner ]; then
    token="$(docker exec -u git hackrange-forgejo forgejo actions generate-runner-token 2>>"$HR_LOG" | tail -1)"
    [ -n "$token" ] || die "Could not get a runner registration token from Forgejo."
    ( cd /etc/forgejo-runner &&
      quiet forgejo-runner register --no-interactive \
          --config /etc/forgejo-runner/config.yml \
          --instance https://labgit.lab:8444 \
          --token "$token" \
          --name "hackrange-local" \
          --labels "docker:docker://${RUNNER_JOB_IMAGE}" ) ||
        die "The runner could not register with the lab Git server."
    chmod 600 /etc/forgejo-runner/.runner
    ok "runner registered with https://labgit.lab:8444"
fi

install -m 644 "$HR_ROOT/config/runner/forgejo-runner.service" /etc/systemd/system/forgejo-runner.service
systemctl daemon-reload
quiet systemctl enable forgejo-runner
quiet systemctl restart forgejo-runner || die "The runner would not start.  See: sudo journalctl -u forgejo-runner"

runner_up() { journalctl -u forgejo-runner --since "-2min" --no-pager 2>/dev/null | grep -qiE 'declare(d)? successfully|runner.*started'; }
if wait_for 60 "the runner to connect" runner_up; then
    ok "runner connected; jobs with runs-on: docker will run here"
else
    warn "The runner started but has not reported in yet.  Check later with: sudo journalctl -u forgejo-runner"
fi
