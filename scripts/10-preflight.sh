#!/usr/bin/env bash
# Step 10: check the machine before changing anything on it.
#
# Everything here is a question with a plain answer the student can act on:
# is there enough memory, processor and disk, can we reach the internet, and
# is anything already sitting where the lab needs to go.  Set HR_SKIP_CHECKS=1
# to install anyway on a machine below the minimum (it will be slow, and the
# Kubernetes days may not fit).
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Checking this machine"

# The minimum and recommended sizes, matching the README.
MIN_CPU=4;  REC_CPU=8
MIN_RAM=16; REC_RAM=24     # GB
MIN_DISK=100; REC_DISK=150 # GB free, for a first install

short=0
note_short() { warn "$1"; short=1; }

# ---- not a container or WSL ---------------------------------------------------
if grep -qi microsoft /proc/version 2>/dev/null; then
    die "This looks like Windows Subsystem for Linux (WSL).  The lab needs a real
    Ubuntu virtual machine (VirtualBox, VMware Workstation or Hyper-V), because
    it runs its own Kubernetes cluster and network services.  See the README."
fi
if [ "$(ps -p 1 -o comm= 2>/dev/null)" != systemd ]; then
    die "This system is not running systemd, which the lab needs to keep its services
    running.  Install inside a normal Ubuntu virtual machine, not a container."
fi

# ---- size -------------------------------------------------------------------
arch="$(hr_arch)"
[ "$arch" = unsupported ] && die "This processor ($(uname -m)) is not supported."
cpus=$(nproc)
# The memory the VM was given, not MemTotal: Ubuntu 26.04 sets aside 512 MB of
# a 16 GB VM for crash dumps, so MemTotal reads about 15 GB on a machine sized
# exactly as the README asks.  The kernel's memory blocks count all of it.
# Without them, add the crash dump reservation back to MemTotal.
ram_kb() {
    local mem=/sys/devices/system/memory blocks
    blocks=$(grep -lx online "$mem"/memory*/state 2>/dev/null | wc -l)
    if [ "$blocks" -gt 0 ] && [ -r "$mem/block_size_bytes" ]; then
        echo $(( blocks * 16#$(cat "$mem/block_size_bytes") / 1024 ))
    else
        echo $(( $(awk '/MemTotal/ { print $2 }' /proc/meminfo) +
                 $(cat /sys/kernel/kexec_crash_size 2>/dev/null || echo 0) / 1024 ))
    fi
}
ram_kb=$(ram_kb)
ram_gb=$(awk -v kb="$ram_kb" 'BEGIN { printf "%d", kb / 1024 / 1024 + 0.5 }')
disk_gb=$(df -BG --output=avail /var/lib | tail -1 | tr -dc 0-9)

say "processor:  $(uname -m) ($arch), $cpus cores"
say "memory:     ${ram_gb} GB"
say "free disk:  ${disk_gb} GB"

[ "$cpus" -ge "$MIN_CPU" ] || note_short "Only $cpus processor cores.  The lab needs at least $MIN_CPU ($REC_CPU recommended)."
# A VM given 16 GB reports a little under that, so allow half a gigabyte.
[ "$(awk -v kb="$ram_kb" 'BEGIN { print int(kb / 1024 / 1024 * 10) }')" -ge $((MIN_RAM * 10 - 5)) ] ||
    note_short "Only ${ram_gb} GB of memory.  The lab needs at least ${MIN_RAM} GB (${REC_RAM} GB recommended)."

# Disk matters most on a first install, when every image is built.
if ! docker image inspect "$LAB_GUI_IMAGE" >/dev/null 2>&1; then
    [ "$disk_gb" -ge "$MIN_DISK" ] ||
        note_short "Only ${disk_gb} GB of free disk.  A first install needs at least ${MIN_DISK} GB free (${REC_DISK} GB recommended)."
fi

if [ "$short" = 1 ]; then
    if [ "${HR_SKIP_CHECKS:-0}" = 1 ]; then
        warn "Continuing anyway because HR_SKIP_CHECKS=1.  Expect it to be slow."
    else
        die "This virtual machine is smaller than the lab needs.  Shut it down, give it
    more memory, processors or disk in your virtualization app (the README lists
    the sizes), start it again, and run the install command again."
    fi
fi
[ "$cpus" -ge "$REC_CPU" ] && [ "$ram_gb" -ge "$REC_RAM" ] ||
    say "That meets the minimum.  More memory and cores make the Kubernetes days faster."

# ---- the address and ports the lab uses ---------------------------------------
# The lab services answer on 10.10.10.70 on a private interface of this machine.
# If the machine's real network already uses that exact address, the two would
# fight over it.
if ip -4 -o addr show | grep -v ' lab0 ' | grep -q " ${HR_SERVICES_IP}/"; then
    die "This machine's own network address is ${HR_SERVICES_IP}, which the lab needs for
    its services.  Change the virtual machine's network (a NAT network is best)
    so it gets a different address, and run the install again."
fi

# Ports the lab needs.  If something else holds one, say which, rather than
# failing later with a confusing error.  The lab's own holders are fine: a
# re-run finds its services already there.
#   docker-proxy: loopback ports the services and the lab session sit behind
#   nginx:        the web desktop (8446), SSH (2222), Remote Desktop (13389)
for port in 13000 14444 18080 18081 12222 13390 18448 18449 18450 18451 18452 \
            8443 8444 8445 8446 8447 8448 8449 8450 8451 8452 2222 13389; do
    holder=$(ss -Hltnp "sport = :$port" 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -1)
    # The lab's own holders are fine on a re-run: its services behind Docker, and
    # nginx.
    if [ -n "$holder" ] && [ "$holder" != docker-proxy ] && [ "$holder" != nginx ]; then
        die "Port $port is already used by '$holder'.  The lab needs it.  Stop that
    program (or remove it) and run the install again."
    fi
done

# ---- the internet ---------------------------------------------------------------
for url in https://github.com https://registry-1.docker.io/v2/ https://codeberg.org https://get.k3s.io; do
    curl -fsS -o /dev/null -m 20 "$url" 2>/dev/null ||
    curl -sS -o /dev/null -m 20 -w '%{http_code}' "$url" 2>/dev/null | grep -qE '^[1-4]' ||
        die "Cannot reach $url.  The installer downloads the lab from the internet;
    check that this virtual machine is online (try opening a web page in it)."
done
ok "enough room, and online"
