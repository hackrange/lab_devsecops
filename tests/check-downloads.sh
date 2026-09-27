#!/usr/bin/env bash
# Prove the workstation image's downloads work for a processor, without
# building the whole 13GB image or owning that kind of machine.
#
#   tests/check-downloads.sh amd64
#   tests/check-downloads.sh arm64
#
# It takes the "verified release downloads" section of the real Dockerfile,
# exactly as written, and runs it in a throwaway Debian container with
# `dpkg --print-architecture` answering the processor asked for.  Every file is
# fetched, every checksum is checked, and every archive has the member the
# Dockerfile extracts.  Only the three steps that would RUN a downloaded
# program (Packer's plugin install, the AWS CLI installer, and Cinc's
# installer) are skipped, because an arm64 program cannot run on an amd64
# machine; their downloads are still fetched and checked.
#
# Author: Tim Rice
set -euo pipefail

ARCH="${1:?usage: check-downloads.sh amd64|arm64}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DF="$HERE/images/devsecops-lab/Dockerfile"

# The pinned versions, from the ARG line of the final stage.
args="$(awk '/^ARG GITLEAKS=/,/[^\\]$/' "$DF" | sed 's/^ARG //; s/\\$//' | tr -s ' \n' ' ')"

# The download section: from its heading to the Python tools.  Comment lines
# are dropped the way Docker drops them, and the trailing "\" continuations are
# kept, so the text runs as one command exactly as it does in the build.
section="$(awk '/# ---- verified release downloads/{on=1} /# ---- Python tools/{on=0} on' "$DF" |
    grep -vE '^[[:space:]]*#' |
    sed -e 's#^\([[:space:]]*\)PACKER_PLUGIN_PATH=/opt/packer-plugins packer plugins install "\$pl"; done; \\#\1echo "skip plugin $pl"; done; \\#' \
        -e 's#unzip -q awscli.zip; ./aws/install; \\#unzip -q awscli.zip; test -x aws/install; \\#' \
        -e 's#curl -fsSL https://omnitruck.cinc.sh/install.sh | bash -s -- -P cinc-auditor || echo "cinc-auditor unavailable"; \\#curl -fsSL -o /dev/null https://omnitruck.cinc.sh/install.sh; \\#')"

script="$(mktemp)"
trap 'rm -f "$script"' EXIT
cat > "$script" <<EOF
set -eux
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends curl ca-certificates unzip xz-utils >/dev/null
dpkg() { if [ "\${1:-}" = --print-architecture ]; then echo $ARCH; else command dpkg "\$@"; fi; }
export $args
mkdir -p /usr/local/bin /usr/share/falco/plugins /etc/falco/config.d /etc/falco/rules.d
$section
true
# Each binary really is for this processor: the ELF header's machine field is
# 0x3e for x86-64 and 0xb7 for arm64.
want=\$( [ $ARCH = arm64 ] && echo b7 || echo 3e )
for b in /usr/local/bin/*; do
    m=\$(od -An -tx1 -j18 -N1 "\$b" | tr -d ' ')
    [ "\$m" = "\$want" ] || { echo "WRONG ARCH: \$b (\$m)"; exit 1; }
done
echo
echo "ALL DOWNLOADS VERIFIED FOR $ARCH: \$(ls /usr/local/bin | wc -l) programs, all the right processor"
EOF

docker run --rm -v "$script:/check.sh:ro" debian:13-slim bash /check.sh
