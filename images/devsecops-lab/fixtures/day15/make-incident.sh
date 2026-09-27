#!/bin/bash
# =============================================================================
# make-incident.sh  --  regenerate fixtures/day15/incident.scap from scratch
# =============================================================================
#
# Day 15 of the course teaches Falco.  Falco cannot run live inside a student's
# Kubernetes cluster (Pod Security Admission 'baseline' rejects the privileges
# every syscall-tracing agent needs -- privileged, hostPath, hostPID/hostNetwork
# and NET_ADMIN were each measured and each refused; the pod just sits Pending).
# So the lab has students write and TUNE Falco rules against a pre-recorded
# incident capture instead, exactly like the packet-capture lab replays a baked
# pcap because NET_RAW is dropped.
#
# This script records that capture.  It is a BUILD-HOST tool, not something a
# student runs: it needs Docker and a privileged recorder container, neither of
# which exists in the (deliberately unprivileged, egress-filtered) lab box.  Run
# it on the build host to reproduce fixtures/day15/incident.scap; the .scap is
# what ships in the image.
#
#   ./make-incident.sh              # writes ./incident.scap next to this script
#   OUT=/tmp/foo.scap ./make-incident.sh
#
# ------------------------------- how it works --------------------------------
# The story is scripted inside a throwaway container ("incident").  A recorder
# (the upstream sysdig image, which carries the same modern-eBPF driver Falco
# uses) captures that container's syscalls to a .scap file, which Falco replays
# with `-o engine.kind=replay`.
#
# Two things about the recording are fiddly and were learned the hard way; keep
# them or the capture comes out useless:
#
#   1. ANCESTRY.  Falco rules like "Run shell untrusted" match on a process's
#      ancestors (proc.aname).  If you start the recorder's live container-scope
#      filter at the same instant the container starts, the container's early
#      process-tree events are dropped before the runtime metadata resolves, and
#      every process's ancestry collapses to runc/init -- the httpd->bash link
#      vanishes and the rule never fires.  Fix: start the container FIRST, let it
#      settle so its long-lived httpd/ci-runner services are already in the
#      recorder's process snapshot, THEN start the capture, THEN trigger the
#      scripted activity.
#
#   2. CLEAN STOP.  A .scap is only readable if the recorder closes it cleanly.
#      `docker stop`/SIGKILL mid-write truncates it ("expecting N bytes, read M").
#      Signals also do not reach sysdig through a `bash -c` wrapper.  Reliable
#      recipe: run sysdig as the container's PID 1 and let its own `-M <seconds>`
#      timer end the capture and finalize the file.  But `-M` is fed by the event
#      stream, so a container-scoped filter that goes silent starves the timer --
#      hence the services keep a light heartbeat running until we tear them down.
#
# NOTE: `sysdig -r in.scap -w out.scap <filter>` (offline post-filtering) is
# BROKEN in the pinned sysdig build -- it writes only a header.  That is why the
# scoping is done live, via the container.id capture filter, not afterwards.
# =============================================================================
set -euo pipefail

SYSDIG_IMAGE="sysdig/sysdig:0.41.4"   # ships the modern-eBPF driver + libscap
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT:-$SCRIPT_DIR/incident.scap}"
WORK="$(mktemp -d)"
CAP_SECONDS="${CAP_SECONDS:-12}"      # capture window AFTER the driver attaches
trap 'rm -rf "$WORK"; docker rm -f incident incident-cap >/dev/null 2>&1 || true' EXIT

echo "==> building the scenario image"
# The kill-chain and the benign work each live in their own baked script, run as
# `httpd /opt/serve.sh` / `bash /opt/attack.sh` / `bash /opt/ci.sh`.  Keeping the
# commands in files (rather than one giant `-c` string) is what makes each alert's
# proc.cmdline read cleanly ("bash /opt/attack.sh", "cat /etc/shadow", ...) so a
# lesson can pipe the JSON to jq without a wall of escaped script text.

# --- the RCE kill-chain (what the "web server" runs on a request) ------------
cat > "$WORK/attack.sh" <<'ATTACK'
#!/bin/bash
echo "[shell] popped"
cat /etc/shadow > /dev/null                           # 2. read the password hashes            -> Read sensitive file untrusted
grep -rl "PRIVATE KEY" /root /home 2>/dev/null        # 3. hunt for private keys               -> Search Private Keys or Passwords
find / -name id_rsa 2>/dev/null | head -n1            #    (find variant of the same rule)
mkdir -p /tmp/.cache                                  # 4. drop an implant into /tmp and run it -> Drop and execute new binary in container
cp /bin/sleep /tmp/.cache/implant                     #    (also the target of the tuning exercise)
chmod +x /tmp/.cache/implant
/tmp/.cache/implant 0.2
mkdir -p /root/.ssh; chmod 700 /root/.ssh             # 5. persistence: add an attacker SSH key (no stock rule -- students write one)
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILEXAMPLEattackerkey attacker@evil" >> /root/.ssh/authorized_keys
ssh -p 443 -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=6 \
    beacon@github.com true 2>/dev/null                # 6. beacon out over SSH on a non-standard port -> Disallowed SSH Connection Non Standard Port
ATTACK

# --- the "web server": waits for a request, then spawns the attack shell ------
# `bash /opt/attack.sh` is FORKED (statements follow it), so the malicious shell
# keeps httpd as its parent.  If it were the last statement, bash would
# exec-replace httpd in place and the httpd ancestor would be lost -- and then
# "Run shell untrusted" would never fire.
cat > "$WORK/serve.sh" <<'SERVE'
#!/bin/bash
while [ ! -f /tmp/trigger ]; do sleep 0.3; done
echo "[httpd] serving request"
bash /opt/attack.sh                                   # 1. RCE: web proc spawns a shell        -> Run shell untrusted
echo "[httpd] request complete"
while true; do sleep 1; done                          # keep serving (feeds the recorder stop)
SERVE

# --- the benign CI runner (the background noise) ------------------------------
# A legitimate build step that "compiles" helper binaries into /tmp and runs
# them.  This is what makes a naive "any exec from /tmp" rule cry wolf: these
# temp binaries are expected, and their ancestry is the CI runner, not httpd.
cat > "$WORK/ci.sh" <<'CI'
#!/bin/bash
while [ ! -f /tmp/trigger ]; do sleep 0.3; done
for i in 1 2 3; do
  d=$(mktemp -d /tmp/ci-build.XXXXXX)
  cp /bin/true "$d/artifact"; chmod +x "$d/artifact"
  /usr/local/bin/ci-runner
  "$d/artifact"                                       # benign exec from /tmp  <- sloppy-rule false positive
done
cat /etc/hostname >/dev/null; cat /etc/passwd >/dev/null   # ordinary, non-sensitive reads
mkdir -p /srv/app && printf "log_level=info\n" >/srv/app/config.ini
grep -r "log_level" /srv/app >/dev/null               # benign grep (no key patterns)
while true; do /bin/true; sleep 1; done               # heartbeat
CI

# --- container init: bring up the two long-lived services --------------------
# They must be running before the recorder attaches so they land in its process
# snapshot with correct parent links (see make-incident.sh, note 1).
cat > "$WORK/run-scenario.sh" <<'SCENARIO'
#!/bin/bash
set -u
cp /bin/bash /usr/sbin/httpd            # the "web server": a renamed bash, so the process
                                        # tree carries a protected_shell_spawning_binary
cp /bin/true /usr/local/bin/ci-runner   # a benign build helper
/usr/sbin/httpd /opt/serve.sh &         # victim web service (cmdline: "httpd /opt/serve.sh")
bash /opt/ci.sh &                       # benign CI runner
wait
SCENARIO

cat > "$WORK/Dockerfile" <<'DOCKER'
FROM debian:13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-client netcat-openbsd procps grep findutils coreutils ca-certificates iproute2 \
    && rm -rf /var/lib/apt/lists/*
COPY run-scenario.sh /run-scenario.sh
COPY serve.sh attack.sh ci.sh /opt/
RUN chmod +x /run-scenario.sh /opt/serve.sh /opt/attack.sh /opt/ci.sh
CMD ["/run-scenario.sh"]
DOCKER

docker build -q -t incident-scenario:build "$WORK" >/dev/null

echo "==> pulling the recorder image if needed"
docker image inspect "$SYSDIG_IMAGE" >/dev/null 2>&1 || docker pull "$SYSDIG_IMAGE" >/dev/null

docker rm -f incident incident-cap >/dev/null 2>&1 || true
rm -f "$OUT"

echo "==> starting the scenario container and letting it settle"
docker run -d --name incident incident-scenario:build >/dev/null
sleep 3                                    # services resident + runtime metadata resolved
CID="$(docker inspect -f '{{.Id}}' incident | cut -c1-12)"
echo "    incident container id = $CID"

echo "==> starting the recorder (modern eBPF, scoped to this container, compressed)"
docker run -d --name incident-cap --privileged --network host --pid host \
  -v "$(dirname "$OUT")":/out -v /:/host -e HOST_ROOT=/host \
  --entrypoint sysdig "$SYSDIG_IMAGE" \
  --modern-bpf -z -M "$CAP_SECONDS" -w "/out/$(basename "$OUT")" "container.id=$CID" >/dev/null

echo "==> waiting for the driver to attach (snapshot flush), then triggering the story"
# The full-host process snapshot is written to the file the instant the capture
# goes live, so a file larger than the header means the driver has attached.
for i in $(seq 1 60); do
  sz="$(stat -c%s "$OUT" 2>/dev/null || echo 0)"
  [ "$sz" -gt 200000 ] && break
  sleep 1
done
sleep 2                                    # small margin past attach
docker exec incident touch /tmp/trigger

echo "==> letting the capture run out and finalize (this is the clean stop)"
docker wait incident-cap >/dev/null 2>&1 || true
docker rm -f incident >/dev/null 2>&1 || true
docker rm incident-cap >/dev/null 2>&1 || true

if [ ! -s "$OUT" ]; then
  echo "!! capture failed: $OUT is empty" >&2
  exit 1
fi
echo "==> wrote $OUT ($(du -h "$OUT" | cut -f1))"
echo "    verify with:  falco -o engine.kind=replay -o engine.replay.capture_file=$OUT"
