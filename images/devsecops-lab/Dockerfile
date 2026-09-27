# DevSecOps workstation lab for "Learning the Software Build Process".
#
# One SSH box with the whole toolchain the course teaches: git + gh, Node 24,
# Python 3 (pipx tools), OpenJDK + Maven, the scanners (Semgrep, Gitleaks,
# Trivy, Syft, Grype, Checkov, hadolint, pip-audit), supply-chain tools
# (cosign, crane), policy engines (OPA, Conftest, Kyverno CLI), IaC (OpenTofu,
# Terraform, Packer, Checkov), Vault, a local AWS emulator (Moto) with the AWS
# CLI, Cloud Custodian, Prowler, Ansible, Cinc Auditor (the open-source build
# of InSpec), and the Kubernetes clients (kubectl, Helm, Kustomize,
# kubeconform, kube-linter).
#
# Practicing what the course preaches: the release binaries (gitleaks, syft,
# grype, trivy, cosign, crane, conftest, opa, OpenTofu, kustomize, kubeconform,
# kyverno, hadolint, gh, actionlint, helm, kubectl, vault, terraform, packer)
# are checked against the checksum file their project publishes, Falco against
# a pinned SHA-256, and the build fails if one does not match.  A few inputs
# are NOT verified this way, and are named here so nobody assumes they are:
# NodeSource's apt setup script, the Cinc Auditor installer (optional: the
# build goes on without it), the AWS CLI zip, kube-linter and yq, the Python
# tools pipx installs, and Verdaccio from npm.  This image is a training
# workstation built on a machine you control; do not reuse it as a production
# base.  Versions are pinned below so a rebuild is deliberate, never a surprise.
#
# LOCAL LAB COPY.  This is the hosted image's Dockerfile with one change: it
# builds for the processor it is built on, 64 bit Intel/AMD (amd64) or ARM
# (arm64, including Apple Silicon virtual machines).  The same versions, the
# same checksum checks, the same files.  Each project names its downloads its
# own way, so the names are worked out once, at the top of the install step.
#
# Lessons run this lab on an ALLOWLIST: it reaches the lab package registry, the
# lab git server, the student's Kubernetes cluster, GitHub, the Debian mirrors
# and the OpenTofu registry, and nothing else.  Anything a lab needs from
# anywhere else has to be baked in here, because at lab time it cannot be
# fetched.
# Author: Tim Rice

# netpolicy (np-guard netpol-analyzer) answers "can this pod reach that one"
# from manifests alone, with no cluster.  Day 17 needs it because a student's
# NetworkPolicies are NOT enforced in the shared lab cluster, so the only honest
# way to prove one works is to analyse it.  Built here rather than vendored: a
# 60MB binary does not belong in the repository, and this way the version is
# pinned and reproducible.
FROM golang:1.23-bookworm AS netpolicy-build
ARG NETPOLICY=1.4.4
RUN GOFLAGS=-ldflags="-s -w" GOBIN=/out \
      go install github.com/np-guard/netpol-analyzer/cmd/netpolicy@v${NETPOLICY}

FROM debian:13-slim

ARG GITLEAKS=8.30.1 SYFT=1.52.0 GRYPE=0.119.0 TRIVY=0.74.0 COSIGN=3.1.3 \
    CRANE=0.22.1 CONFTEST=0.70.1 OPA=1.20.2 TOFU=1.12.6 KUSTOMIZE=5.8.1 \
    KUBECONFORM=0.8.0 KUBELINTER=0.8.3 KYVERNO=1.19.1 HADOLINT=2.15.1 GH=2.101.0 \
    HELM=4.3.0 YQ=4.53.6 VAULT=2.1.1 TERRAFORM=1.16.3 PACKER=1.16.1 KUBECTL=1.37.0 \
    ACTIONLINT=1.7.12 FALCO=0.44.1

ENV DEBIAN_FRONTEND=noninteractive \
    PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin \
    SEMGREP_SEND_METRICS=off CHECKOV_RUN_SCA_PACKAGE_SCAN=false \
    DISABLE_AUTOUPDATER=1 VAULT_ADDR=http://127.0.0.1:8200

# The toolchain comes first so that editing a fixture or a helper script only
# rebuilds the small COPY layers at the end, not the multi-minute RUN steps or
# the vulnerability database download.  See the note beside those COPY lines.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      openssh-server ca-certificates tini sudo curl wget gnupg less vim nano procps \
      git git-lfs jq unzip zip tree file make bsdextrautils netcat-openbsd dnsutils iputils-ping \
      python3 python3-venv python3-pip pipx \
      openjdk-21-jdk-headless maven \
      shellcheck sqlite3 rpm python3-apt; \
    # Node 24 LTS from NodeSource.  The apt source is removed straight after the
    # install: Node is baked in, nothing at lab time needs it, and a filtered lab
    # cannot reach nodesource, so leaving it would make every student's
    # `apt-get update` print a 403 warning that has nothing to do with them.
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    rm -f /etc/apt/sources.list.d/nodesource.list /etc/apt/sources.list.d/nodesource.sources; \
    \
    # ---- verified release downloads ------------------------------------------
    # One name per spelling a project uses for this processor.
    A="$(dpkg --print-architecture)"; \
    case "$A" in \
      amd64) GL=x64;   TV=64bit; X86=x86_64; KL=kube-linter-linux.tar.gz;       AA=x86_64; \
             FALCO_SHA=bc5b7a3bdf26fc91e520fc20b3461613c6e725148437121697a8d20243132127 ;; \
      arm64) GL=arm64; TV=ARM64; X86=arm64;  KL=kube-linter-linux_arm64.tar.gz; AA=aarch64; \
             FALCO_SHA=17ff67764cb84374ca0fcc98a733316f973a90f3457495df35a24bd839b4ce87 ;; \
      *) echo "unsupported architecture: $A" >&2; exit 1 ;; \
    esac; \
    W=/tmp/dl; mkdir -p $W; cd $W; \
    gh_rel() { curl -fsSLo "$3" "https://github.com/$1/releases/download/$2/$3"; }; \
    check() { grep -E "[[:space:]]\*?$2\$" "$1" | sha256sum -c -; }; \
    \
    gh_rel gitleaks/gitleaks v$GITLEAKS gitleaks_${GITLEAKS}_linux_${GL}.tar.gz; \
    gh_rel gitleaks/gitleaks v$GITLEAKS gitleaks_${GITLEAKS}_checksums.txt; \
    check gitleaks_${GITLEAKS}_checksums.txt gitleaks_${GITLEAKS}_linux_${GL}.tar.gz; \
    tar -xzf gitleaks_${GITLEAKS}_linux_${GL}.tar.gz -C /usr/local/bin gitleaks; \
    \
    for t in syft:$SYFT grype:$GRYPE; do n=${t%%:*}; v=${t##*:}; \
      gh_rel anchore/$n v$v ${n}_${v}_linux_${A}.tar.gz; gh_rel anchore/$n v$v ${n}_${v}_checksums.txt; \
      check ${n}_${v}_checksums.txt ${n}_${v}_linux_${A}.tar.gz; \
      tar -xzf ${n}_${v}_linux_${A}.tar.gz -C /usr/local/bin $n; done; \
    \
    gh_rel aquasecurity/trivy v$TRIVY trivy_${TRIVY}_Linux-${TV}.tar.gz; \
    gh_rel aquasecurity/trivy v$TRIVY trivy_${TRIVY}_checksums.txt; \
    check trivy_${TRIVY}_checksums.txt trivy_${TRIVY}_Linux-${TV}.tar.gz; \
    tar -xzf trivy_${TRIVY}_Linux-${TV}.tar.gz -C /usr/local/bin trivy; \
    \
    gh_rel sigstore/cosign v$COSIGN cosign-linux-${A}; gh_rel sigstore/cosign v$COSIGN cosign_checksums.txt; \
    check cosign_checksums.txt cosign-linux-${A}; install -m 755 cosign-linux-${A} /usr/local/bin/cosign; \
    \
    gh_rel google/go-containerregistry v$CRANE go-containerregistry_Linux_${X86}.tar.gz; \
    gh_rel google/go-containerregistry v$CRANE checksums.txt; mv checksums.txt crane.sums; \
    check crane.sums go-containerregistry_Linux_${X86}.tar.gz; \
    tar -xzf go-containerregistry_Linux_${X86}.tar.gz -C /usr/local/bin crane; \
    \
    gh_rel open-policy-agent/conftest v$CONFTEST conftest_${CONFTEST}_Linux_${X86}.tar.gz; \
    gh_rel open-policy-agent/conftest v$CONFTEST checksums.txt; mv checksums.txt conftest.sums; \
    check conftest.sums conftest_${CONFTEST}_Linux_${X86}.tar.gz; \
    tar -xzf conftest_${CONFTEST}_Linux_${X86}.tar.gz -C /usr/local/bin conftest; \
    \
    gh_rel open-policy-agent/opa v$OPA opa_linux_${A}_static; gh_rel open-policy-agent/opa v$OPA opa_linux_${A}_static.sha256; \
    echo "$(cut -d' ' -f1 opa_linux_${A}_static.sha256)  opa_linux_${A}_static" | sha256sum -c -; \
    install -m 755 opa_linux_${A}_static /usr/local/bin/opa; \
    \
    gh_rel opentofu/opentofu v$TOFU tofu_${TOFU}_linux_${A}.tar.gz; gh_rel opentofu/opentofu v$TOFU tofu_${TOFU}_SHA256SUMS; \
    check tofu_${TOFU}_SHA256SUMS tofu_${TOFU}_linux_${A}.tar.gz; \
    tar -xzf tofu_${TOFU}_linux_${A}.tar.gz -C /usr/local/bin tofu; \
    \
    curl -fsSLo kustomize.tgz "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv${KUSTOMIZE}/kustomize_v${KUSTOMIZE}_linux_${A}.tar.gz"; \
    curl -fsSLo kustomize.sums "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv${KUSTOMIZE}/checksums.txt"; \
    echo "$(grep "linux_${A}.tar.gz" kustomize.sums | cut -d' ' -f1)  kustomize.tgz" | sha256sum -c -; \
    tar -xzf kustomize.tgz -C /usr/local/bin kustomize; \
    \
    gh_rel yannh/kubeconform v$KUBECONFORM kubeconform-linux-${A}.tar.gz; gh_rel yannh/kubeconform v$KUBECONFORM CHECKSUMS; \
    check CHECKSUMS kubeconform-linux-${A}.tar.gz; tar -xzf kubeconform-linux-${A}.tar.gz -C /usr/local/bin kubeconform; \
    \
    gh_rel stackrox/kube-linter v$KUBELINTER $KL; \
    tar -xzf $KL -C /usr/local/bin kube-linter; \
    \
    gh_rel kyverno/kyverno v$KYVERNO kyverno-cli_v${KYVERNO}_linux_${X86}.tar.gz; \
    gh_rel kyverno/kyverno v$KYVERNO checksums.txt; mv checksums.txt kyverno.sums; \
    check kyverno.sums kyverno-cli_v${KYVERNO}_linux_${X86}.tar.gz; \
    tar -xzf kyverno-cli_v${KYVERNO}_linux_${X86}.tar.gz -C /usr/local/bin kyverno; \
    \
    gh_rel hadolint/hadolint v$HADOLINT hadolint-linux-${X86}; gh_rel hadolint/hadolint v$HADOLINT checksums.sha256; \
    check checksums.sha256 hadolint-linux-${X86}; install -m 755 hadolint-linux-${X86} /usr/local/bin/hadolint; \
    \
    gh_rel cli/cli v$GH gh_${GH}_linux_${A}.tar.gz; gh_rel cli/cli v$GH gh_${GH}_checksums.txt; \
    check gh_${GH}_checksums.txt gh_${GH}_linux_${A}.tar.gz; \
    tar -xzf gh_${GH}_linux_${A}.tar.gz --strip-components=2 -C /usr/local/bin gh_${GH}_linux_${A}/bin/gh; \
    \
    gh_rel rhysd/actionlint v$ACTIONLINT actionlint_${ACTIONLINT}_linux_${A}.tar.gz; \
    gh_rel rhysd/actionlint v$ACTIONLINT actionlint_${ACTIONLINT}_checksums.txt; \
    check actionlint_${ACTIONLINT}_checksums.txt actionlint_${ACTIONLINT}_linux_${A}.tar.gz; \
    tar -xzf actionlint_${ACTIONLINT}_linux_${A}.tar.gz -C /usr/local/bin actionlint; \
    \
    gh_rel mikefarah/yq v$YQ yq_linux_${A}; \
    install -m 755 yq_linux_${A} /usr/local/bin/yq; \
    \
    # Falco (Day 15 runtime-security lab).  Falco cannot run live in the
    # student's cluster (Pod Security Admission 'baseline' rejects the
    # privileges any syscall agent needs), so the lab has students write and
    # tune rules against a recorded capture that Falco replays with
    # engine.kind=replay -- the same "replay a baked capture" pattern the
    # packet-capture lab uses because NET_RAW is dropped.  We ship only what an
    # offline replay needs: the falco binary, the container plugin (so
    # container.id-based rules resolve), and the stock rules/config.  falcoctl
    # and the kernel-driver sources are omitted -- the lab never loads a driver
    # and, being egress-filtered, never fetches rules or plugins at run time.
    # download.falco.org publishes no per-file checksum, so the SHA256 is pinned
    # here, one per processor (same style as the opa/kubectl/helm downloads above).
    curl -fsSLo falco.tgz https://download.falco.org/packages/bin/${AA}/falco-${FALCO}-${AA}.tar.gz; \
    echo "${FALCO_SHA}  falco.tgz" | sha256sum -c -; \
    mkdir -p falco && tar -xzf falco.tgz -C falco --strip-components=1; \
    install -m 755 falco/usr/bin/falco /usr/local/bin/falco; \
    mkdir -p /usr/share/falco/plugins /etc/falco/config.d /etc/falco/rules.d; \
    cp falco/usr/share/falco/plugins/libcontainer.so /usr/share/falco/plugins/; \
    cp falco/etc/falco/falco.yaml falco/etc/falco/falco_rules.yaml falco/etc/falco/falco_rules.local.yaml /etc/falco/; \
    printf '%s\n' 'load_plugins: [container]' > /etc/falco/config.d/container_plugin.yaml; \
    \
    curl -fsSLo helm.tgz https://get.helm.sh/helm-v${HELM}-linux-${A}.tar.gz; \
    curl -fsSLo helm.sha https://get.helm.sh/helm-v${HELM}-linux-${A}.tar.gz.sha256sum; \
    echo "$(cut -d' ' -f1 helm.sha)  helm.tgz" | sha256sum -c -; \
    tar -xzf helm.tgz --strip-components=1 -C /usr/local/bin linux-${A}/helm; \
    \
    curl -fsSLo kubectl "https://dl.k8s.io/release/v${KUBECTL}/bin/linux/${A}/kubectl"; \
    curl -fsSLo kubectl.sha256 "https://dl.k8s.io/release/v${KUBECTL}/bin/linux/${A}/kubectl.sha256"; \
    echo "$(cat kubectl.sha256)  kubectl" | sha256sum -c -; install -m 755 kubectl /usr/local/bin/kubectl; \
    \
    for t in vault:$VAULT terraform:$TERRAFORM packer:$PACKER; do n=${t%%:*}; v=${t##*:}; \
      curl -fsSLo ${n}.zip https://releases.hashicorp.com/$n/$v/${n}_${v}_linux_${A}.zip; \
      curl -fsSLo ${n}.sums https://releases.hashicorp.com/$n/$v/${n}_${v}_SHA256SUMS; \
      echo "$(grep "linux_${A}.zip" ${n}.sums | cut -d' ' -f1)  ${n}.zip" | sha256sum -c -; \
      unzip -oq ${n}.zip $n -d /usr/local/bin; done; \
    \
    curl -fsSLo awscli.zip https://awscli.amazonaws.com/awscli-exe-linux-${AA}.zip; \
    unzip -q awscli.zip; ./aws/install; \
    \
    # Cinc Auditor: the free, community build of Chef InSpec (Day 12)
    curl -fsSL https://omnitruck.cinc.sh/install.sh | bash -s -- -P cinc-auditor || echo "cinc-auditor unavailable"; \
    \
    # Packer plugins the Day 12 lab uses (amazon for the spot-the-bug template), pre-installed to a shared path so a class
    # behind one public IP never trips GitHub's anonymous API rate limit.
    mkdir -p /opt/packer-plugins; \
    for pl in github.com/hashicorp/qemu github.com/hashicorp/ansible github.com/hashicorp/inspec github.com/hashicorp/amazon; do \
      PACKER_PLUGIN_PATH=/opt/packer-plugins packer plugins install "$pl"; done; \
    chmod -R a+rX /opt/packer-plugins; \
    \
    # ---- Python tools, each in its own isolated venv via pipx -----------------
    # A compiler for the few that have no prebuilt wheel for this processor
    # (on arm64, zstd, which Prowler needs), removed again once they are built.
    apt-get install -y --no-install-recommends gcc libc6-dev python3-dev; \
    for p in semgrep checkov pre-commit pip-audit pip-tools 'moto[server]' c7n ansible-core prowler zizmor check-jsonschema; do \
      pipx install --pip-args=--no-cache-dir "$p"; done; \
    apt-get purge -y --auto-remove gcc libc6-dev python3-dev; \
    \
    # ---- student account and sshd ---------------------------------------------
    mkdir -p /run/sshd; \
    useradd -m -s /bin/bash student; \
    printf 'student ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/student; chmod 440 /etc/sudoers.d/student; \
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config; \
    printf 'LANG=C.UTF-8\n' > /etc/default/locale; \
    printf '%s\n' \
      '' \
      '  DevSecOps workstation.  Your fixtures are in ~/fixtures.' \
      '  This lab is disposable: push your work to GitHub before you log off.' \
      '  Tool versions: run  lab-versions' \
      '' > /etc/motd; \
    # Shared tools live in /opt/pipx (root-owned); each user's own pipx installs go
    # to their home, so students can still pipx install extra tools.
    printf '%s\n' 'export PATH=$PATH:/opt/cinc-auditor/bin:$HOME/.local/bin' 'export SEMGREP_SEND_METRICS=off' \
      'export VAULT_ADDR=http://127.0.0.1:8200' \
      'export PIPX_HOME=$HOME/.local/share/pipx PIPX_BIN_DIR=$HOME/.local/bin' \
      'export PACKER_PLUGIN_PATH=/opt/packer-plugins' > /etc/profile.d/devsecops.sh; \
    \
    # ---- editors (same fixes as every lab image) ------------------------------
    update-alternatives --set vi /usr/bin/vim.basic || true; \
    rm -rf /usr/share/vim/vim*/lang; \
    printf '%s\n' 'let g:skip_defaults_vim = 1' 'set nocompatible' 'set backspace=indent,eol,start' \
      'syntax on' 'filetype plugin indent on' 'set ruler' 'set showcmd' 'set incsearch' 'set hlsearch' \
      'set wildmenu' 'set scrolloff=3' 'set mouse=' 'set ttimeout' 'set ttimeoutlen=100' \
      'autocmd FileType python setlocal expandtab tabstop=4 shiftwidth=4 softtabstop=4' \
      'autocmd FileType yaml setlocal expandtab tabstop=2 shiftwidth=2 softtabstop=2' > /etc/vim/vimrc.local; \
    printf '%s\n' '' '## Lab terminal defaults.' 'bind ^J enter main' 'unset breaklonglines' \
      'set tabsize 2' 'set tabstospaces' 'unset autoindent' >> /etc/nanorc; \
    \
    # ---- clean up in the same layer --------------------------------------------
    cd /; rm -rf /tmp/dl /aws /root/.cache; \
    apt-get clean; rm -rf /var/lib/apt/lists/*

# The lab certificate authority, which the trust step below reads.  It changes
# only when the CA is regenerated, so it sits above the slow layers rather than
# with the files that change every day.
COPY ca/lab-ca.crt /usr/local/share/ca-certificates/lab-ca.crt

# Vulnerability databases, downloaded once at build time and shared by every
# student.  Without this each lab container pulls about 3.5GB of its own (Grype
# 2.1GB, Trivy 1.4GB), which fills a lab node with a class on it and makes the
# first scan of the day a two minute wait.  They refresh themselves when stale.
RUN set -eux; \
    trivy image --download-db-only --cache-dir /opt/lab/trivy-cache >/dev/null 2>&1 || true; \
    GRYPE_DB_CACHE_DIR=/opt/lab/grype-db grype db update >/dev/null 2>&1 || true; \
    # Trivy writes into its cache directory (it creates fanal/ there), so the
    # shared copy must be writable: one student per container makes that safe.
    chmod -R a+rwX /opt/lab/trivy-cache 2>/dev/null || true; \
    chmod -R a+rX /opt/lab/grype-db 2>/dev/null || true; \
    printf '%s\n' \
      'export TRIVY_CACHE_DIR=/opt/lab/trivy-cache' \
      'export GRYPE_DB_CACHE_DIR=/opt/lab/grype-db' \
      'export GRYPE_DB_VALIDATE_AGE=false' \
      '# Trivy refreshes a stale database from ghcr.io, which the lab allowlist' \
      '# already permits (its default, mirror.gcr.io, is not on it).' \
      'export TRIVY_DB_REPOSITORY=ghcr.io/aquasecurity/trivy-db:2' \
      'export TRIVY_JAVA_DB_REPOSITORY=ghcr.io/aquasecurity/trivy-java-db:1' \
      '# The scanners ask the internet for a newer version of themselves and of' \
      '# the database on every run; in the lab that only prints alarming errors.' \
      'export GRYPE_CHECK_FOR_APP_UPDATE=false' \
      'export SYFT_CHECK_FOR_APP_UPDATE=false' \
      'export GRYPE_DB_AUTO_UPDATE=false' \
      > /etc/profile.d/lab-scanner-db.sh; \
    # Checkov downloads Prisma Cloud guideline links on every run and prints a
    # long traceback when it cannot reach them; the checks do not need them.
    printf 'skip-download: true\n' > /home/student/.checkov.yaml; \
    # Verdaccio, the small npm proxy Day 10's Test 8 stands up as an upstream
    # that can be switched off.  Baked in because the lab network (rightly)
    # cannot reach registry.npmjs.org to fetch it on the day.
    npm install -g --no-fund --no-audit verdaccio@6 >/dev/null; \
    npm cache clean --force >/dev/null 2>&1; \
    chown 1000:1000 /home/student/.checkov.yaml; \
    du -sh /opt/lab/trivy-cache /opt/lab/grype-db 2>/dev/null || true

# Trust the lab CA in every place this toolchain looks for one: the system
# store (git, curl, apt, crane, trivy, syft, cosign), Node, and Python.  Without
# this, every lab command would need an --insecure flag, which is exactly the
# habit the course tells students not to build.
RUN set -eux; \
    update-ca-certificates; \
    printf '%s\n' \
      'export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt' \
      'export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt' \
      'export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt' \
      'export PIP_CERT=/etc/ssl/certs/ca-certificates.crt' \
      > /etc/profile.d/lab-ca.sh

# LAST, and deliberately so.  Everything above is slow and rarely changes: the
# toolchain, and two vulnerability databases that are about 3.5GB to fetch.
# Everything here is small and changes constantly, because it is the course
# itself.  Docker rebuilds every layer below the first one that changed, so a
# COPY placed above those databases means a one line fix to a helper script
# re-downloads them, which took this image from seconds to many minutes per
# edit.  The header comment above has claimed this ordering for some time; it
# is now actually true.  If you add a step here, ask whether it belongs above
# the databases instead.
#
# Helper scripts (lab-entrypoint, lab-env, lab-totp, lab-versions) and the
# course fixtures.  File modes come from the repository, so no chmod layer is
# needed.  netpolicy is built in the first stage: see the note at the top.
COPY --from=netpolicy-build /out/netpolicy /usr/local/bin/netpolicy
COPY bin/ /usr/local/bin/
COPY fixtures/ /opt/lab/fixtures/

EXPOSE 22
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/lab-entrypoint"]
