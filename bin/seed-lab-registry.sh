#!/usr/bin/env bash
# Configure the lab package registry (ForgeRepo) for the DevSecOps course.
#
# Everything the course labs install has to be allowed by name, because the box
# runs in whitelist mode: a package with no rule is refused, and the refusal is
# part of the teaching.  This script turns on the package types the course uses,
# points each one at its public registry, and writes the allow rules, the
# deliberate deny rules and the one application scoped rule that the lessons
# demonstrate.
#
# It is safe to run again.  Rules are saved by their key (type, pattern, kind,
# version range, scope), so re-running updates them in place rather than piling
# up duplicates.  Registries, applications and environments are created only
# when a box does not already have one by that name, and nothing here deletes
# anything.
#
# Per student tokens are NOT made here.  Run lab-student-registry.sh for those.
#
# Usage:  seed-lab-registry.sh [--dry-run]
# Author: Tim Rice
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=forgerepo-lib.sh
. "$HERE/forgerepo-lib.sh"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# ---------------------------------------------------------------- small helpers

# set_setting KEY VALUE.  Only sends what is not already that value.
declare -A CURRENT_SETTINGS=()

load_settings() {
    local json
    json="$(fr_api GET /settings)"
    while IFS=$'\t' read -r key value; do
        CURRENT_SETTINGS["$key"]="$value"
    done < <(printf '%s' "$json" | jq -r '.settings | to_entries[] | [.key, (.value|tostring)] | @tsv')
}

want_settings() {
    local body='{}' key value changed=0
    for pair in "$@"; do
        key="${pair%%=*}"; value="${pair#*=}"
        if [ "${CURRENT_SETTINGS[$key]:-}" != "$value" ]; then
            body="$(printf '%s' "$body" | jq --arg k "$key" --arg v "$value" '. + {($k): $v}')"
            changed=1
        fi
    done
    if [ "$changed" = 0 ]; then fr_say 'already set the way the course wants it'; return; fi
    if [ "$DRY_RUN" = 1 ]; then fr_say "would set: $(printf '%s' "$body" | jq -c .)"; return; fi
    fr_say "set: $(fr_api PUT /settings "$body" | jq -r '.changed | join(", ")')"
}

# want_upstream NAME ECOSYSTEM URL [PATTERN] [PRIORITY] [OPTIONS-JSON]
want_upstream() {
    local name="$1" eco="$2" url="$3" pattern="${4:-}" priority="${5:-100}" options="${6:-}" body
    if printf '%s' "$UPSTREAMS" | jq -e --arg n "$name" '.upstreams[] | select(.name == $n)' >/dev/null; then
        fr_say "registry $name: already there"
        return
    fi
    body="$(jq -n --arg n "$name" --arg e "$eco" --arg u "$url" --arg p "$pattern" --argjson pr "$priority" \
        '{name:$n, ecosystem:$e, url:$u, priority:$pr} + (if $p == "" then {} else {pattern:$p} end)')"
    [ -n "$options" ] && body="$(printf '%s' "$body" | jq --argjson o "$options" '. + {options:$o}')"
    if [ "$DRY_RUN" = 1 ]; then fr_say "would add registry $name"; return; fi
    fr_api POST /upstreams "$body" >/dev/null
    fr_say "registry $name: added ($eco, ${pattern:-everything else} -> $url)"
    UPSTREAMS="$(fr_api GET /upstreams)"
}

# want_label applications|environments NAME NOTE [production]
want_label() {
    local kind="$1" name="$2" note="$3" production="${4:-false}" body existing
    existing="$(fr_api GET "/$kind")"
    if printf '%s' "$existing" | jq -e --arg n "$name" '.entries[] | select(.name == $n)' >/dev/null; then
        fr_say "${kind%s} $name: already there"
        return
    fi
    body="$(jq -n --arg n "$name" --arg t "$note" --argjson p "$production" '{name:$n, note:$t, production:$p}')"
    if [ "$DRY_RUN" = 1 ]; then fr_say "would add ${kind%s} $name"; return; fi
    fr_api POST "/$kind" "$body" >/dev/null
    fr_say "${kind%s} $name: added"
}

label_id() {
    fr_api GET "/$1" | jq -r --arg n "$2" '.entries[] | select(.name == $n) | .id'
}

# rule ECOSYSTEM allow|deny PATTERN RANGE PRIORITY NOTE [APP-ID] [ENV-ID]
rule() {
    local eco="$1" kind="$2" pattern="$3" range="$4" priority="$5" note="$6" app="${7:-0}" env="${8:-0}" body
    body="$(jq -n --arg e "$eco" --arg k "$kind" --arg p "$pattern" --arg r "$range" \
        --argjson pr "$priority" --arg n "$note" --argjson a "$app" --argjson v "$env" \
        '{ecosystem:$e, kind:$k, pattern:$p, version_range:$r, priority:$pr, note:$n,
          enabled:true, application_id:$a, environment_id:$v}')"
    if [ "$DRY_RUN" = 1 ]; then printf '  would save %s %s %s %s\n' "$eco" "$kind" "$pattern" "$range"; return; fi
    fr_api POST /rules "$body" >/dev/null
    RULES_WRITTEN=$((RULES_WRITTEN + 1))
}

# ---------------------------------------------------------------- go

printf '\nSeeding the lab package registry at %s\n\n' "$FR_URL"
fr_login
load_settings

printf 'Package types\n'
# npm is always on.  The rest are switched on one setting each.
want_settings pypi_enabled=1 oci_enabled=1 maven_enabled=1 apt_enabled=1 rpm_enabled=1
# Whitelist mode is the whole point: no rule means no package.  Cache what an
# any-version allow currently resolves to, so a class of students does not each
# wait on the same download.
want_settings policy_mode=whitelist cache_tarballs=1 cache_latest_on_allow=1 auto_request=1
# Every refusal ends with "ask for it at <public_url>/_admin", so this has to be
# the address a student's browser can actually open, port and all.
want_settings "public_url=$FR_URL" 'registry_name=Hackrange Lab Registry'
load_settings

printf '\nUpstream registries\n'
UPSTREAMS="$(fr_api GET /upstreams)"
# npm's default (registry.npmjs.org) is created by the installer and is left alone.
want_upstream 'pypi.org'          pypi  'https://pypi.org'
want_upstream 'Docker Hub'        oci   'https://registry-1.docker.io'
want_upstream 'Google Distroless' oci   'https://gcr.io'   'distroless/*'   50
want_upstream 'GitHub Packages'   oci   'https://ghcr.io'  'aquasecurity/*' 50
want_upstream 'Maven Central'     maven 'https://repo1.maven.org/maven2'
want_upstream 'Debian'            apt   'https://deb.debian.org/debian' '' 100 \
    '{"filtered":false,"advisories":"Debian:13"}'
want_upstream 'Debian Security'   apt   'https://deb.debian.org/debian-security' '' 100 \
    '{"filtered":false,"advisories":"Debian:13"}'
want_upstream 'AlmaLinux 9 BaseOS' rpm  'https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os' '' 100 \
    '{"filtered":false,"advisories":"AlmaLinux:9"}'

printf '\nApplications and environments\n'
want_label applications 'secure-build-lab' 'The worked example app the course builds and ships'
want_label environments 'dev'        'Student workstations and their own pipelines'
want_label environments 'production' 'The tighter rules a release has to meet' true
APP_SECURE_BUILD="$(label_id applications 'secure-build-lab')"
ENV_PRODUCTION="$(label_id environments 'production')"
: "${APP_SECURE_BUILD:=0}" "${ENV_PRODUCTION:=0}"

printf '\nRules\n'
RULES_WRITTEN=0

# ---- npm ------------------------------------------------------------------
# The one package the lab installs to prove an allow works, pinned to the
# version the lesson names so the version rule is visible in the answer.
rule npm allow 'is-number'  '7.0.0' 0 'Day 6: the allowed package the lab installs'
rule npm allow '@types/*'   ''      0 'Type definitions, no runtime code'

# The deliberate refusals.  These are teaching artifacts: a student who installs
# one gets a 403 that names the rule and its reason, not a silent failure.
rule npm deny 'event-stream'   '' 100 'Denied: the 2018 supply chain incident. Day 6 installs this on purpose to read the refusal'
rule npm deny 'flatmap-stream' '' 100 'Denied: the payload event-stream pulled in'
rule npm deny 'node-ipc'       '' 100 'Denied: the 2022 protestware release wiped files by geography'
rule npm deny 'colors'         '' 100 'Denied: the 2022 sabotage release looped forever'

# Per application scoping.  lodash is blocked for everyone, and allowed for one
# application only.  A rule for an application beats a rule for everyone at the
# same priority, so the same npm install succeeds or fails purely on which
# token made the request.  That is the demonstration.
rule npm deny  'lodash' ''       0 'Blocked everywhere except the one application that still needs it'
if [ "$APP_SECURE_BUILD" != 0 ]; then
    rule npm allow 'lodash' '4.17.21' 0 \
        'Allowed for secure-build-lab only, and only on the patched version' "$APP_SECURE_BUILD"
fi

# ---- PyPI -----------------------------------------------------------------
# requests and its four runtime dependencies.  pip resolves them itself, so
# every one of them needs a rule of its own.
for p in requests certifi charset-normalizer idna urllib3; do
    rule pypi allow "$p" '' 0 'requests and its runtime dependencies'
done
# pip-tools, and the closure pip pulls in with it.
for p in pip-tools build click packaging pyproject-hooks setuptools wheel tomli pip importlib-metadata zipp; do
    rule pypi allow "$p" '' 0 'pip-compile (pip-tools) and what it needs to run'
done
# check-jsonschema, which Days 9, 10 and 11 use to validate a workflow file
# against GitHub's published schema before anything is pushed.  pip resolves the
# whole tree itself, so every name in it needs a rule.  ruamel.yaml is listed
# both ways because a name is normalised before it reaches the index.
for p in check-jsonschema jsonschema jsonschema-specifications referencing \
         regress attrs rpds-py ruamel.yaml ruamel-yaml ruamel.yaml.clib ruamel-yaml-clib; do
    rule pypi allow "$p" '' 0 'check-jsonschema and what it needs to run'
done
# The dependency confusion demo builds acme-utils locally and serves it from
# its own index, so this rule is only for the runs that go through the box.
rule pypi allow 'acme-utils' '' 0 'The local demo package the dependency confusion lab builds'

# ---- Maven ----------------------------------------------------------------
# The two libraries the fixture poms declare, at the versions they declare.
# These sit above the group rule below on priority, so they are the rules that
# answer for those versions and they are what an audit of the class shows.
# commons-lang3 is the awkward one: the lab pom declares 3.17.0, and the Maven
# plugins pull in versions of their own.  Naming both in one range keeps the pin
# real, so a student who edits the pom to 3.18.0 gets a refusal, and still lets
# the toolchain resolve itself.  The versions after 3.17.0 came from the audit
# mode run described below, not from guesswork.
rule maven allow 'org.apache.commons:commons-lang3' \
    '3.17.0 || 3.1 || 3.10 || 3.11 || 3.12.0 || 3.14.0 || 3.20.0' 10 \
    '3.17.0 is what the lab pom declares. The rest are what the Maven plugins pull in as their own'
rule maven allow 'org.apache.commons:commons-text'  '1.12.0' 10 'Day 7: the transitive dependency in the mediation example'
# The rest of Apache Commons that the plugins need, named one at a time rather
# than as org.apache.commons:*, because a wildcard there would quietly undo the
# version pin above.
rule maven allow 'org.apache.commons:commons-parent'     '' 0 'Parent pom every Apache Commons artifact inherits from'
rule maven allow 'org.apache.commons:commons-compress'   '' 0 'Pulled in by the Maven plugins'
rule maven allow 'org.apache.commons:commons-digester3'  '' 0 'Pulled in by the Maven plugins'

# mvn downloads its own plugins, their parent poms and their dependencies
# through the same mirror, so the build itself needs allow rules or it never
# gets as far as the project.  This list came from running the course builds
# with audit mode on and reading the traffic page, which is the way to redo it
# when Maven or a plugin moves:
#
#   1. Settings, Policy: turn Audit mode on (nothing is refused, everything logged)
#   2. run the lesson build with an empty local repository (-Dmaven.repo.local)
#   3. Traffic, filter on Maven, and read the groupIds out of the rows
#   4. turn Audit mode back off
for g in 'org.apache:*' 'org.apache.maven:*' 'org.apache.maven.plugins:*' \
         'org.apache.maven.plugin-tools:*' 'org.apache.maven.shared:*' 'org.apache.maven.resolver:*' \
         'org.apache.maven.wagon:*' 'org.apache.maven.enforcer:*' 'org.apache.maven.surefire:*' \
         'org.apache.maven.doxia:*' 'org.apache.maven.reporting:*' 'org.apache.maven.release:*' \
         'org.apache.velocity:*' 'org.apache.velocity.tools:*' 'org.apache-extras.beanshell:*' \
         'org.codehaus:*' 'org.codehaus.plexus:*' 'org.codehaus.mojo:*' 'classworlds:*' \
         'org.sonatype.plexus:*' 'org.sonatype.sisu:*' 'org.sonatype.sisu.inject:*' \
         'org.sonatype.forge:*' 'org.sonatype.oss:*' 'org.sonatype.spice:*' 'org.sonatype.aether:*' \
         'org.eclipse.sisu:*' 'org.eclipse.aether:*' 'org.slf4j:*' 'org.ow2:*' 'org.ow2.asm:*' \
         'org.iq80.snappy:*' 'org.tukaani:*' 'org.junit:*' 'junit:*' \
         'commons-io:*' 'commons-codec:*' 'commons-cli:*' 'commons-lang:*' \
         'commons-logging:*' 'commons-beanutils:*' 'commons-collections:*' \
         'javax.inject:*' 'io.airlift:*' 'com.github.cliftonlabs:*' 'com.github.luben:*' \
         'com.google.code.findbugs:*' 'com.google.guava:*' 'com.google.inject:*' \
         'com.thoughtworks.qdox:*' 'org.apache.httpcomponents:*'; do
    rule maven allow "$g" '' 0 'Maven build and enforcer plugins, their parent poms and what they load'
done

# ---- container images -----------------------------------------------------
# Repository plus reference.  Through this box the pull is
# labrepo.lab:8443/library/node:24-bookworm-slim, so the rule names library/node.
#
# These carry no version range on purpose.  Every one of these images is a
# multi architecture index, and docker, crane, trivy and the rest resolve the
# index and then ask for the architecture's own manifest BY DIGEST.  A rule
# whose range lists tags does not cover that digest, so the tag resolves and
# the pull then fails.  Refuse a version here with a deny rule instead.
rule oci allow 'library/node'   '' 0 'Day 9: the build stage base image'
rule oci allow 'library/debian' '' 0 'Day 9: the Debian base the labs compare against'
rule oci allow 'library/alpine' '' 0 'Day 9: the small base image in the size comparison'
rule oci allow 'library/nginx'  '' 0 'Day 9: the serving image in the multi stage example'
rule oci allow 'distroless/nodejs24-debian13' '' 0 'Day 9: the distroless runtime stage (gcr.io)'
# Trivy keeps its databases on GHCR as OCI artifacts, so they come through the
# box when TRIVY_DB_REPOSITORY points at it.  Grype is not here on purpose: its
# database is a plain https download from Anchore, not an OCI artifact, so
# there is nothing for an image rule to match.
for i in aquasecurity/trivy-db aquasecurity/trivy-java-db aquasecurity/trivy-checks; do
    rule oci allow "$i" '' 0 'Trivy vulnerability databases, pulled as OCI artifacts from GHCR'
done

# ---- APT and RPM ----------------------------------------------------------
# A distro archive is thousands of packages that pull each other in, so the
# documented shape for a mirror in whitelist mode is one allow of everything,
# then deny or kill what you do not want.
rule apt allow '*' '' 0 'Debian bookworm and trixie base packages, through the Debian mirror'
rule apt deny  'telnet'   '' 100 'Denied: the course teaches ssh, and this is here to be found by a student who looks'
rule rpm allow '*' '' 0 'AlmaLinux 9 BaseOS, for the labs that compare package managers'

printf '  %s rules saved\n' "$RULES_WRITTEN"

if [ "$DRY_RUN" = 0 ]; then
    printf '\nWhere it stands now\n'
    fr_api GET '/rules?limit=1' | jq -r '"  rules: \(.total)"'
    fr_api GET /upstreams | jq -r '"  registries: \(.upstreams | length)"'
    printf '  %s\n' "portal: $FR_URL/_admin/"
    printf '\nNext: lab-student-registry.sh create <student-id> for each student token.\n\n'
fi
