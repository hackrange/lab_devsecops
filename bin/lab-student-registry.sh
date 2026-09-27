#!/usr/bin/env bash
# Give one student their own identity on the lab package registry (ForgeRepo),
# or take it away again.
#
# Every token carries an application and an environment, and a rule can be
# limited to either.  That is how one student gets their own allow and deny
# rules without changing what the rest of the class can install: the scope comes
# from the token and from nothing else, so no header a student sends can borrow
# somebody else's rules.
#
# Applications are per student and this script makes them.  Environments are
# the shared list the seed script writes (dev, production), because "where is
# this running" is the same question for everyone; a student token is stamped
# dev unless another one is named.
#
# Usage:
#   lab-student-registry.sh create <student-id> [environment] [application]
#   lab-student-registry.sh delete <student-id>
#   lab-student-registry.sh list
#
# The application defaults to student-<student-id>, which is what a student
# wants.  Naming an existing one instead (secure-build-lab, say) issues a token
# that picks up that application's rules, which is how the class sees an
# application scoped rule allow something their own token is refused.
#
# create prints one line on stdout that another script can read:
#   TOKEN=nrt_xxxxxxxx
# Everything else it says goes to stderr, so `TOKEN=$(... create s01)` works.
#
# Re-running create is safe: it reuses the student's application, revokes the
# token it issued last time and mints a fresh one.  A token is shown once and
# only its hash is kept, so there is no way to reprint an old one.
# Author: Tim Rice
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=forgerepo-lib.sh
. "$HERE/forgerepo-lib.sh"

TOKEN_DAYS="${TOKEN_DAYS:-30}"

usage() {
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}" >&2
    exit 2
}

note() { printf '%s\n' "$*" >&2; }

# A student id becomes part of an application name, which the box accepts as
# letters, numbers, and dots, dashes, underscores or spaces in the middle.
check_id() {
    case "$1" in
        ''|*[!A-Za-z0-9._-]*) fr_die "a student id is letters, numbers, dots, dashes and underscores: \"$1\" is not" ;;
    esac
    [ "${#1}" -le 100 ] || fr_die 'that student id is too long'
}

app_name()   { printf 'student-%s' "$1"; }
token_name() { printf 'student-%s' "$1"; }

find_app() {
    fr_api GET /applications | jq -r --arg n "$1" '.entries[] | select(.name == $n) | "\(.id) \(.retired)"'
}

find_env() {
    fr_api GET /environments | jq -r --arg n "$1" '.entries[] | select(.name == $n) | .id'
}

# Every token with this name, whether it is live or already revoked.
find_tokens() {
    fr_api GET '/tokens?all=1' | jq -r --arg n "$1" '.tokens[] | select(.name == $n) | "\(.id) \(.revoked)"'
}

# ---------------------------------------------------------------- create

do_create() {
    local id="$1" env_name="${2:-dev}" app_name token_name app_id app_retired env_id answer token
    check_id "$id"
    app_name="${3:-$(app_name "$id")}"
    token_name="$(token_name "$id")"

    env_id="$(find_env "$env_name")"
    [ -n "$env_id" ] || fr_die "there is no environment called $env_name. Run seed-lab-registry.sh first"

    read -r app_id app_retired < <(find_app "$app_name"; printf '\n')
    if [ -z "${app_id:-}" ]; then
        app_id="$(fr_api POST /applications \
            "$(jq -n --arg n "$app_name" --arg t "Lab account for student $id" '{name:$n, note:$t}')" |
            jq -r '.id')"
        note "application $app_name created (id $app_id)"
    else
        if [ "$app_retired" = true ]; then
            fr_api PATCH "/applications/$app_id" '{"retired":false}' >/dev/null
            note "application $app_name was retired, put back in use (id $app_id)"
        else
            note "application $app_name already there (id $app_id)"
        fi
    fi

    # One live token per student.  An old one is revoked rather than left
    # lying around, so a student who lost theirs cannot be impersonated by it.
    local tid trevoked revoked=0
    while read -r tid trevoked; do
        [ -n "$tid" ] || continue
        [ "$trevoked" = 0 ] || continue
        fr_api DELETE "/tokens/$tid" >/dev/null
        revoked=$((revoked + 1))
    done < <(find_tokens "$token_name")
    [ "$revoked" = 0 ] || note "revoked $revoked older token(s) named $token_name"

    answer="$(fr_api_soft POST /tokens "$(jq -n --arg n "$token_name" --argjson d "$TOKEN_DAYS" \
        --argjson a "$app_id" --argjson e "$env_id" \
        '{name:$n, expires_days:$d, application_id:$a, environment_id:$e}')")"
    case "$answer" in
        2*) ;;
        *"live tokens"*)
            fr_die "the registry admin account has hit its limit of live tokens. Revoke some with
       lab-student-registry.sh delete <student-id>, or give the class a second
       portal account to mint from (FR_USER and FR_PASSWORD pick the account)." ;;
        *) fr_die "minting a token failed: ${answer#* }" ;;
    esac
    token="$(printf '%s' "${answer#* }" | jq -r '.token')"

    note "token $token_name issued for $app_name in $env_name, good for $TOKEN_DAYS days"
    note "rules for this student alone: give the rule application_id $app_id"
    printf 'TOKEN=%s\n' "$token"
}

# ---------------------------------------------------------------- delete

do_delete() {
    local id="$1" app_name token_name app_id app_retired answer revoked=0 removed=0
    check_id "$id"
    app_name="$(app_name "$id")"
    token_name="$(token_name "$id")"

    local tid trevoked
    while read -r tid trevoked; do
        [ -n "$tid" ] || continue
        if [ "$trevoked" = 0 ]; then
            fr_api DELETE "/tokens/$tid" >/dev/null
            revoked=$((revoked + 1))
        fi
    done < <(find_tokens "$token_name")
    note "revoked $revoked live token(s) named $token_name"

    read -r app_id app_retired < <(find_app "$app_name"; printf '\n')
    if [ -z "${app_id:-}" ]; then
        note "no application called $app_name, nothing else to do"
        return
    fi

    # An application cannot be deleted while a rule is scoped to it, so the
    # student's own rules go first.  Everyone else's rules are untouched.
    local rid
    while read -r rid; do
        [ -n "$rid" ] || continue
        fr_api DELETE "/rules/$rid" >/dev/null
        removed=$((removed + 1))
    done < <(fr_api GET '/rules?limit=500' | jq -r --argjson a "$app_id" '.rules[] | select(.application_id == $a) | .id')
    [ "$removed" = 0 ] || note "deleted $removed rule(s) scoped to $app_name"

    # The box refuses to delete an application any token ever pointed at, even
    # a revoked one, so that old traffic rows keep their name.  Retiring is the
    # product's answer to that, and it takes the application out of the lists.
    answer="$(fr_api_soft DELETE "/applications/$app_id")"
    case "$answer" in
        2*) note "application $app_name deleted" ;;
        *)  fr_api PATCH "/applications/$app_id" '{"retired":true}' >/dev/null
            note "application $app_name kept but retired, because its old tokens still name it in the traffic log" ;;
    esac
}

# ---------------------------------------------------------------- list

do_list() {
    fr_api GET '/tokens?all=1' | jq -r '
        .tokens[] | select(.name | startswith("student-")) |
        "\(.name)\t\(if .revoked == 1 then "revoked" else "live" end)\t\(.application // "-")\t\(.environment // "-")\t\(.expires_at // "no expiry")"' |
        { printf 'TOKEN\tSTATE\tAPPLICATION\tENVIRONMENT\tEXPIRES\n'; cat; } | column -t -s $'\t'
}

# ---------------------------------------------------------------- go

[ $# -ge 1 ] || usage
action="$1"; shift

fr_login
case "$action" in
    create) [ $# -ge 1 ] || usage; do_create "$@" ;;
    delete) [ $# -eq 1 ] || usage; do_delete "$1" ;;
    list)   do_list ;;
    *)      usage ;;
esac
