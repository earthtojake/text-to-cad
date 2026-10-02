#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"

LABEL=""
PROJECT_ID=""
PUBLIC_URLS=""

usage() {
  cat <<'EOF'
Usage:
  scripts/github-workflows/deploy-vercel-app.sh \
    --label "Docs app" \
    --project-id PROJECT_ID \
    --public-urls "https://example.com https://www.example.com"

Deploys one Vercel project to production from the current checkout:

1. configures Vercel Authentication to protect preview deployments only
2. runs vercel pull/build/deploy --prod with the project root taken from the
   Vercel project settings
3. verifies each public production URL responds with HTTP 2xx/3xx
4. appends a deployment summary to GITHUB_STEP_SUMMARY when set

Requires VERCEL_TOKEN and VERCEL_ORG_ID in the environment and the vercel CLI
on PATH. Run from a checkout of main (or a release tag).
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --label)
      [ "$#" -ge 2 ] || die "--label requires a value"
      LABEL="$2"
      shift
      ;;
    --project-id)
      [ "$#" -ge 2 ] || die "--project-id requires a value"
      PROJECT_ID="$2"
      shift
      ;;
    --public-urls)
      [ "$#" -ge 2 ] || die "--public-urls requires a value"
      PUBLIC_URLS="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
  shift
done

[ -n "$LABEL" ] || die "--label is required"
[ -n "$PROJECT_ID" ] || die "--project-id is required"
[ -n "$PUBLIC_URLS" ] || die "--public-urls is required"
[ -n "${VERCEL_TOKEN:-}" ] || die "VERCEL_TOKEN must be set"
[ -n "${VERCEL_ORG_ID:-}" ] || die "VERCEL_ORG_ID must be set"
command -v vercel >/dev/null 2>&1 || die "vercel CLI is required"
command -v curl >/dev/null 2>&1 || die "curl is required"

cd "$REPO_ROOT"

configure_project_protection() {
  local response_file
  local status

  response_file="$(mktemp)"
  if ! status="$(
    curl --silent --show-error --location --max-time 30 \
      --request PATCH \
      --header "Authorization: Bearer $VERCEL_TOKEN" \
      --header "Content-Type: application/json" \
      --output "$response_file" \
      --write-out "%{http_code}" \
      --data '{"ssoProtection":{"deploymentType":"preview"}}' \
      "https://api.vercel.com/v9/projects/$PROJECT_ID?teamId=$VERCEL_ORG_ID"
  )"; then
    status="000"
  fi

  if [ "$status" -lt 200 ] || [ "$status" -ge 300 ]; then
    echo "$LABEL Vercel Authentication update failed with HTTP $status" >&2
    cat "$response_file" >&2
    rm -f "$response_file"
    exit 1
  fi

  rm -f "$response_file"
  echo "$LABEL Vercel Authentication set to preview deployments only."
}

check_public_url() {
  local public_url="$1"
  local public_status="000"
  local attempt

  for attempt in 1 2 3 4 5; do
    if ! public_status="$(curl --silent --show-error --location --max-time 30 --output /dev/null --write-out "%{http_code}" "$public_url")"; then
      public_status="000"
    fi
    if [ "$public_status" -ge 200 ] && [ "$public_status" -lt 400 ]; then
      echo "$LABEL public URL check passed: $public_url returned HTTP $public_status"
      return 0
    fi
    if [ "$attempt" -lt 5 ]; then
      echo "$LABEL public URL check waiting for $public_url; attempt $attempt returned HTTP $public_status"
      sleep 5
    fi
  done

  echo "$LABEL public URL check failed: $public_url returned HTTP $public_status" >&2
  return 1
}

configure_project_protection

rm -rf .vercel
export VERCEL_ORG_ID
export VERCEL_PROJECT_ID="$PROJECT_ID"

echo "Using Vercel project root from project settings for $LABEL."
vercel pull --yes --environment=production --token="$VERCEL_TOKEN"
vercel build --prod --token="$VERCEL_TOKEN"
deployment_output="$(vercel deploy --prebuilt --prod --token="$VERCEL_TOKEN")"
echo "$deployment_output"
deployment_url="$(printf '%s\n' "$deployment_output" | tail -n 1)"

for public_url in $PUBLIC_URLS; do
  check_public_url "$public_url"
done

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### $LABEL"
    echo
    echo "Public production URLs:"
    for public_url in $PUBLIC_URLS; do
      echo "- $public_url"
    done
    echo
    echo "Raw Vercel deployment URL: $deployment_url"
    echo
    echo "> Raw Vercel deployment URLs may require Vercel Authentication. Use the public production URLs above for release testing and sharing."
    echo
  } >> "$GITHUB_STEP_SUMMARY"
fi

echo "$LABEL deployed to Vercel production."
