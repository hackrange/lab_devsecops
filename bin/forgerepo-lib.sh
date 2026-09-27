#!/usr/bin/env bash
# Shared helpers for talking to the lab package registry (ForgeRepo) from a
# script.  Source this, call fr_login once, then use fr_api.
#
# The portal API lives under /_api.  Signing in returns a session cookie and a
# CSRF token, and every write has to carry that token in an X-CSRF-Token header
# and send application/json, or the box refuses it.  Nothing here writes the
# admin password to disk; the cookie jar lives in a temporary directory that is
# removed when the calling script exits.
#
# Environment, all optional:
#   FR_URL       registry address            (default https://labrepo.lab:8443)
#   FR_IP        address behind that name    (default 10.10.10.70)
#   FR_CA        lab CA certificate          (default: the first copy found, see below)
#   FR_USER      portal admin user           (default admin)
#   FR_PASSWORD  portal admin password       (default: read from Kubernetes)
#   FR_SSH       host to read the secret on  (default student@10.10.10.70)
# Author: Tim Rice
set -euo pipefail

FR_URL="${FR_URL:-https://labrepo.lab:8443}"
FR_IP="${FR_IP:-10.10.10.70}"
# The lab CA: the Local Lab's own (the installer passes FR_CA), one next to
# this script, or the copy inside a lab container.  Take the first one that is
# actually there rather than insisting on one path.
if [ -z "${FR_CA:-}" ]; then
    for _ca in /etc/nginx/labtls/lab-ca.crt \
               "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lab-ca.crt" \
               /usr/local/share/lab-ca.crt \
               /usr/local/share/ca-certificates/lab-ca.crt; do
        [ -r "$_ca" ] && { FR_CA="$_ca"; break; }
    done
    unset _ca
fi
FR_CA="${FR_CA:-/etc/nginx/labtls/lab-ca.crt}"
FR_USER="${FR_USER:-admin}"
FR_SSH="${FR_SSH:-student@10.10.10.70}"
FR_NAMESPACE="${FR_NAMESPACE:-lab-services}"
FR_SECRET="${FR_SECRET:-forgerepo-admin}"

FR_HOSTPORT="${FR_URL#https://}"
FR_HOSTPORT="${FR_HOSTPORT#http://}"
FR_HOSTPORT="${FR_HOSTPORT%%/*}"
FR_HOST="${FR_HOSTPORT%%:*}"
FR_PORT="${FR_HOSTPORT#*:}"
[ "$FR_PORT" = "$FR_HOST" ] && FR_PORT=443

FR_TMP=""
FR_CSRF=""

fr_die() { printf 'error: %s\n' "$*" >&2; exit 1; }
fr_say() { printf '  %s\n' "$*"; }

fr_cleanup() { [ -n "$FR_TMP" ] && rm -rf "$FR_TMP"; }

# Raw curl against the registry, with the lab name pinned to the lab address so
# the certificate still matches when there is no DNS for it on this box.
fr_curl() {
    curl --silent --show-error --cacert "$FR_CA" \
         --resolve "${FR_HOST}:${FR_PORT}:${FR_IP}" \
         --cookie "$FR_TMP/cookies" --cookie-jar "$FR_TMP/cookies" "$@"
}

# The admin password: whatever was handed in, else the Kubernetes secret, read
# locally if kubectl is here and over ssh if it is not.
fr_password() {
    if [ -n "${FR_PASSWORD:-}" ]; then printf '%s' "$FR_PASSWORD"; return; fi
    local read_it='sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml /usr/local/bin/kubectl'
    read_it="$read_it -n ${FR_NAMESPACE} get secret ${FR_SECRET} -o jsonpath={.data.password}"
    if [ -x /usr/local/bin/kubectl ] && [ -r /etc/rancher/k3s/k3s.yaml ]; then
        eval "$read_it" | base64 -d
    else
        ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$FR_SSH" "$read_it" | base64 -d
    fi
}

fr_login() {
    for tool in curl jq; do
        command -v "$tool" >/dev/null || fr_die "$tool is needed and is not installed"
    done
    [ -r "$FR_CA" ] || fr_die "the lab CA certificate is not readable at $FR_CA"

    FR_TMP="$(mktemp -d)"
    trap fr_cleanup EXIT
    chmod 700 "$FR_TMP"

    local password answer
    password="$(fr_password)"
    [ -n "$password" ] || fr_die 'could not work out the registry admin password'

    answer="$(jq -n --arg u "$FR_USER" --arg p "$password" '{username:$u,password:$p}' |
        fr_curl -H 'content-type: application/json' --data @- "$FR_URL/_api/login")" ||
        fr_die "could not reach $FR_URL"
    FR_CSRF="$(printf '%s' "$answer" | jq -r '.csrf // empty')"
    [ -n "$FR_CSRF" ] || fr_die "sign in was refused: $(printf '%s' "$answer" | jq -r '.error // .')"
}

# fr_api METHOD PATH [JSON BODY].  Prints the reply body.  A 4xx or 5xx stops
# the calling script, with the message the box gave.
fr_api() {
    local method="$1" path="$2" body="${3:-}" out code
    if [ -n "$body" ]; then
        out="$(fr_curl -X "$method" -w '\n%{http_code}' \
            -H "x-csrf-token: $FR_CSRF" -H 'content-type: application/json' \
            --data "$body" "$FR_URL/_api$path")"
    else
        out="$(fr_curl -X "$method" -w '\n%{http_code}' \
            -H "x-csrf-token: $FR_CSRF" "$FR_URL/_api$path")"
    fi
    code="${out##*$'\n'}"
    out="${out%$'\n'*}"
    case "$code" in
        2*) printf '%s' "$out" ;;
        *)  fr_die "$method $path answered $code: $(printf '%s' "$out" | jq -r '.error // .' 2>/dev/null || printf '%s' "$out")" ;;
    esac
}

# fr_api_soft is the same call without the stop: it prints "<code> <body>" so a
# caller can decide for itself what a refusal means.
fr_api_soft() {
    local method="$1" path="$2" body="${3:-}" out code
    if [ -n "$body" ]; then
        out="$(fr_curl -X "$method" -w '\n%{http_code}' \
            -H "x-csrf-token: $FR_CSRF" -H 'content-type: application/json' \
            --data "$body" "$FR_URL/_api$path")"
    else
        out="$(fr_curl -X "$method" -w '\n%{http_code}' \
            -H "x-csrf-token: $FR_CSRF" "$FR_URL/_api$path")"
    fi
    code="${out##*$'\n'}"
    printf '%s %s' "$code" "${out%$'\n'*}"
}
