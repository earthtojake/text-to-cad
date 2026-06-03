#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

function usage() {
  cat <<'EOF'
Usage:
  VIEWER_VERCEL_BLOB_PREFIX=<prefix> \
  BLOB_READ_WRITE_TOKEN=<token> \
  scripts/viewer/upload-viewer-models-catalog.sh [directory] [upload options]

Uploads the models catalog and CAD Viewer-supported assets to Vercel Blob.
The uploader excludes mechbench/, mechbench2/, 7dof_arm/, and Python source
files by default.

Environment:
  VIEWER_VERCEL_BLOB_PREFIX                 Required. Blob path prefix, for example: models2
  BLOB_READ_WRITE_TOKEN                     Vercel Blob read/write token.
  VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN       Alternate Vercel Blob read/write token.
  VIEWER_ASSET_BACKEND                      Optional. Defaults to vercel-blob.

Options are passed through to npm --prefix viewer run upload:blob.
If no directory is passed, models/ is uploaded.
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

: "${VIEWER_VERCEL_BLOB_PREFIX:?Set VIEWER_VERCEL_BLOB_PREFIX before uploading to Vercel Blob.}"
if [ -z "${BLOB_READ_WRITE_TOKEN:-}" ] && [ -z "${VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN:-}" ]; then
  echo "Set BLOB_READ_WRITE_TOKEN or VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN before uploading to Vercel Blob." >&2
  exit 1
fi

export VIEWER_ASSET_BACKEND="${VIEWER_ASSET_BACKEND:-vercel-blob}"

UPLOAD_DIR="$REPO_ROOT/models"
if [ "$#" -gt 0 ] && [[ "${1:-}" != --* ]]; then
  UPLOAD_DIR="$1"
  shift
fi

npm --prefix "$REPO_ROOT/viewer" run upload:blob -- \
  "$UPLOAD_DIR" \
  "$@"
