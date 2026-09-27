#!/usr/bin/env bash
# Step 50: build and fetch every container image the lab runs.
#
# Built here, on this machine, for this machine's processor:
#   devsecops-lab       the student workstation (every course tool)
#   devsecops-lab-gui   the same, with a desktop, Firefox and VS Code
#   lab-forgerepo       the lab package registry, from its public source
#   github-code-review  the SAST platform, from its public source plus patches
#
# The workstation is built rather than downloaded because it trusts this
# machine's own lab CA, which did not exist until step 40.  The first build is
# the slow part of the whole install.  Each image is stamped with a fingerprint
# of what went into it, so running the installer again rebuilds only what
# changed.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

SRC=/var/cache/hackrange/src
install -d -m 755 "$SRC"
arch="$(hr_arch)"
export DOCKER_BUILDKIT=1

# fingerprint TEXT...  a short, stable hash of everything an image depends on.
fingerprint() { printf '%s\n' "$@" | sha256sum | cut -c1-16; }

current() { docker image inspect -f '{{ index .Config.Labels "org.hackrange.inputs" }}' "$1" 2>/dev/null || true; }

# build IMAGE FINGERPRINT CONTEXT [docker build args...]
build() {
    local image="$1" fp="$2" ctx="$3"; shift 3
    if [ "$(current "$image")" = "$fp" ]; then
        ok "$image is up to date"
        return
    fi
    say "building $image (this can take a while; progress is in $HR_LOG)"
    retry 2 quiet docker build --pull --progress=plain \
        --build-arg "TARGETARCH=$arch" \
        --label "org.hackrange.inputs=$fp" \
        -t "$image" "$@" "$ctx" || die "Building $image failed."
    ok "$image built"
}

# The files of a directory in this repository, as git sees them, plus any
# local edits, so a changed fixture means a rebuild.
tree_of() {
    ( cd "$HR_ROOT" && { git ls-files -s -- "$1" 2>/dev/null; git diff --no-color -- "$1" 2>/dev/null; } ) | sha256sum | cut -c1-16
}

# fetch_source URL REF DIR  a clean checkout of one commit.
fetch_source() {
    local url="$1" ref="$2" dir="$3"
    if [ ! -d "$dir/.git" ]; then
        rm -rf "$dir"
        retry 3 quiet git clone -q "$url" "$dir" || die "Could not download $url"
    fi
    if ! git -C "$dir" cat-file -e "$ref^{commit}" 2>/dev/null; then
        retry 3 quiet git -C "$dir" fetch -q origin || die "Could not update $url"
    fi
    quiet git -C "$dir" reset -q --hard || true
    quiet git -C "$dir" clean -qfdx || true
    quiet git -C "$dir" checkout -q --detach "$ref" || die "$url has no commit $ref"
}

step "Building the lab images (the first time takes 30 to 90 minutes)"

ca_fp="$(openssl x509 -noout -fingerprint -sha256 -in "$LABTLS/lab-ca.crt" | cut -d= -f2)"

# ---- the workstation, then its desktop edition on top of it -------------------
lab_fp="$(fingerprint "$arch" "$ca_fp" "$(tree_of images/devsecops-lab)")"
build "$LAB_IMAGE" "$lab_fp" "$HR_ROOT/images/devsecops-lab"

base_id="$(docker image inspect -f '{{.Id}}' "$LAB_IMAGE")"
gui_fp="$(fingerprint "$arch" "$base_id" "$(tree_of images/devsecops-lab-gui)")"
# No --pull here: the base is the image just built, which is not on any registry.
if [ "$(current "$LAB_GUI_IMAGE")" = "$gui_fp" ]; then
    ok "$LAB_GUI_IMAGE is up to date"
else
    say "building $LAB_GUI_IMAGE"
    retry 2 quiet docker build --progress=plain --build-arg "BASE=$LAB_IMAGE" \
        --label "org.hackrange.inputs=$gui_fp" -t "$LAB_GUI_IMAGE" "$HR_ROOT/images/devsecops-lab-gui" ||
        die "Building $LAB_GUI_IMAGE failed."
    ok "$LAB_GUI_IMAGE built"
fi

# ---- the package registry ------------------------------------------------------
fr_fp="$(fingerprint "$arch" "$FORGEREPO_REF")"
if [ "$(current "$FORGEREPO_IMAGE")" != "$fr_fp" ]; then
    fetch_source "$FORGEREPO_REPO" "$FORGEREPO_REF" "$SRC/npm-repo"
fi
build "$FORGEREPO_IMAGE" "$fr_fp" "$SRC/npm-repo"

# ---- the SAST platform, with the fixes the hosted labs run ----------------------
gcr_fp="$(fingerprint "$arch" "$GCR_REF" "$(tree_of patches/github-code-review)")"
if [ "$(current "$GCR_IMAGE")" != "$gcr_fp" ]; then
    fetch_source "$GCR_REPO" "$GCR_REF" "$SRC/github-code-review"
    for p in "$HR_ROOT"/patches/github-code-review/*.patch; do
        quiet git -C "$SRC/github-code-review" apply --whitespace=nowarn "$p" ||
            die "Could not apply $(basename "$p") to Git Code Review."
    done
fi
build "$GCR_IMAGE" "$gcr_fp" "$SRC/github-code-review"

# ---- images used as they are published ----------------------------------------------
for img in "$FORGEJO_IMAGE" "$RUNNER_JOB_IMAGE" "$GUACAMOLE_IMAGE" "$GUACD_IMAGE" \
           "$KEYCLOAK_IMAGE" "$KONG_IMAGE" postgres:16-alpine "$GRAFANA_IMAGE" "$LOKI_IMAGE" "$TEMPO_IMAGE"; do
    retry 3 quiet docker pull "$img" || die "Could not download $img"
done
ok "Forgejo, the CI job image, the web desktop, Keycloak, Kong and Grafana downloaded"

# ---- an ARM machine running x86 programs, for two lessons ----------------------------
# The Day 5 and Day 20 workflows download the x86 build of gitleaks and check
# it against a pinned checksum, exactly as a real pipeline pins a tool.  On an
# ARM machine that program cannot run natively, so QEMU's user mode emulation
# is registered with the kernel: the x86 program then just runs, slower, and
# the lesson works as written.
if [ "$arch" = arm64 ]; then
    # Newer Ubuntu releases (26.04) split the package, and qemu-user-static is
    # then only a name that other packages provide, which apt will not install.
    # Ask apt which one this release has, rather than failing on the old name.
    if apt-cache policy qemu-user-static 2>/dev/null | grep -q 'Candidate: [0-9]'; then
        qemu_pkgs=(qemu-user-static binfmt-support)
    else
        qemu_pkgs=(qemu-user-binfmt)
    fi
    retry 3 quiet apt-get install -y "${qemu_pkgs[@]}" ||
        die "Could not install x86 emulation (${qemu_pkgs[0]})."
    systemctl restart systemd-binfmt.service 2>/dev/null || update-binfmts --enable qemu-x86_64 2>/dev/null || true
    # Emulated x86 Go programs, gitleaks among them, crash with "fatal error:
    # lfstack.push" on arm64: Linux hands out memory from the top of a 48 bit
    # address space, QEMU passes those addresses on, and Go's x86 runtime only
    # works below 47 bits.  The bottom up layout keeps them low (and is still
    # randomized).  It has to be machine wide, because the lesson's workflow
    # runs the program inside a job container.
    printf '# x86 Go programs under QEMU need addresses below 47 bits.\nvm.legacy_va_layout = 1\n' \
        > /etc/sysctl.d/90-hackrange-x86-emulation.conf
    quiet sysctl -p /etc/sysctl.d/90-hackrange-x86-emulation.conf ||
        warn "Could not set vm.legacy_va_layout; x86 Go programs such as gitleaks may crash."
    # Prove it with the lessons' own case, not a toy: the x86 gitleaks the Day 5
    # and Day 20 pipelines download, checked against its published checksum the
    # same way, run inside the native CI job image as a job would run it.  A
    # program that is not written in Go (hello-world, once) passes even while
    # every Go program crashes, and the crash is intermittent, so it runs five
    # times.  If it fails the install stops here, with the reason, rather than
    # in the middle of a lesson a week later.
    gl="$LESSON_GITLEAKS_VERSION"
    gl_file="gitleaks_${gl}_linux_x64.tar.gz"
    gl_base="https://github.com/gitleaks/gitleaks/releases/download/v${gl}"
    gl_dir="$(mktemp -d)"
    retry 3 curl -fsSL -o "$gl_dir/$gl_file" "$gl_base/$gl_file" &&
    retry 3 curl -fsSL -o "$gl_dir/sums" "$gl_base/gitleaks_${gl}_checksums.txt" ||
        die "Could not download gitleaks to test x86 emulation.  Is this machine online?"
    ( cd "$gl_dir" && grep " ${gl_file}\$" sums | sha256sum -c - ) >> "$HR_LOG" 2>&1 ||
        die "The gitleaks download did not match its published checksum."
    tar -xzf "$gl_dir/$gl_file" -C "$gl_dir" gitleaks
    for i in 1 2 3 4 5; do
        out="$(docker run --rm -v "$gl_dir/gitleaks:/usr/local/bin/gitleaks-x86:ro" \
                   "$RUNNER_JOB_IMAGE" gitleaks-x86 version 2>&1)" || true
        log "x86 gitleaks run $i: $(printf '%s' "$out" | head -3 | tr '\n' ' ')"
        if ! printf '%s' "$out" | grep -qx "$gl"; then
            rm -rf "$gl_dir"
            die "x86 programs do not run correctly under emulation on this machine
    (run $i of 5 of the x86 gitleaks failed: $(printf '%s' "$out" | head -1)).
    The Day 5 and Day 20 pipelines need them.  Send the output of
    hackrange-lab diag to your instructor."
        fi
    done
    rm -rf "$gl_dir"
    ok "x86 programs run under emulation (the lessons' x86 gitleaks, 5 of 5)"
fi

# The build leaves intermediate layers behind; the finished images keep what
# they need.  Only unused cache is removed.
quiet docker builder prune -f || true
quiet docker image prune -f || true
