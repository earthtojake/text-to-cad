#!/bin/sh
set -eu

default_base_url=https://github.com/amywork777/hardcore/releases/download/workspace-server
base_url=$default_base_url
version=
sha256=

fail() {
  code=$1
  shift
  printf 'workspace-server install: %s\n' "$*" >&2
  exit "$code"
}

require_value() {
  option=$1
  value=${2-}
  [ -n "$value" ] || fail 42 "$option requires a value"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base-url)
      require_value "$1" "${2-}"
      base_url=$2
      shift 2
      ;;
    --base-url=*)
      base_url=${1#*=}
      require_value --base-url "$base_url"
      shift
      ;;
    --version)
      require_value "$1" "${2-}"
      version=$2
      shift 2
      ;;
    --version=*)
      version=${1#*=}
      require_value --version "$version"
      shift
      ;;
    --sha256)
      require_value "$1" "${2-}"
      sha256=$2
      shift 2
      ;;
    --sha256=*)
      sha256=${1#*=}
      require_value --sha256 "$sha256"
      shift
      ;;
    *)
      fail 42 "unknown option '$1'"
      ;;
  esac
done

base_url=${base_url%/}
case "$base_url" in
  https://* | http://* | file://*) ;;
  *) fail 41 "base URL must use https, http, or file" ;;
esac
[ -n "$version" ] || fail 42 "--version is required"

case "$(uname -s 2>/dev/null || true)" in
  Linux) os=linux ;;
  *) fail 40 "workspace-server installation is only supported on Linux" ;;
esac

case "$(uname -m 2>/dev/null || true)" in
  x86_64 | amd64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) fail 40 "unsupported Linux architecture" ;;
esac

libc=$(getconf GNU_LIBC_VERSION 2>/dev/null || true)
case "$libc" in
  glibc\ *) ;;
  *) fail 40 "workspace-server Linux artifacts require glibc" ;;
esac

download() {
  source_url=$1
  destination=$2
  if command -v curl >/dev/null 2>&1; then
    curl -fL --output "$destination" -- "$source_url"
    return
  fi
  case "$source_url" in
    https://* | http://*)
      if command -v wget >/dev/null 2>&1; then
        wget -O "$destination" -- "$source_url"
        return
      fi
      ;;
  esac
  fail 41 "curl or wget is required to download workspace-server files"
}

temporary_metadata=${TMPDIR:-/tmp}/emdash-workspace-server-metadata-$$
cleanup_metadata() {
  rm -f -- "$temporary_metadata"
}
trap cleanup_metadata EXIT HUP INT TERM

if ! printf '%s\n' "$version" |
  grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?(\+[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$'; then
  fail 41 "invalid workspace-server version '$version'"
fi

artifact=emdash-workspace-server-$version-$os-$arch.tar.gz
artifact_url=$base_url/$version/$artifact
if [ -z "$sha256" ]; then
  if ! download "$artifact_url.sha256" "$temporary_metadata"; then
    fail 41 "could not download the checksum for $artifact"
  fi
  sha256=$(awk -v expected="$artifact" '
    NF == 2 {
      name = $2
      sub(/^\*/, "", name)
      if (name == expected) {
        print $1
        exit
      }
    }
  ' "$temporary_metadata")
fi
sha256=$(printf '%s' "$sha256" | tr 'A-F' 'a-f')
if ! printf '%s\n' "$sha256" | grep -Eq '^[a-f0-9]{64}$'; then
  fail 41 "invalid checksum for $artifact"
fi

case "${HOME-}" in
  /*) ;;
  *) fail 42 "HOME must be an absolute path" ;;
esac

root=$HOME/.emdash/workspace-server
versions_dir=$root/versions
version_dir=$versions_dir/$version
launcher=$version_dir/bin/emdash-workspace-server
current_link=$root/current
staging_dir=$root/staging
staging=$staging_dir/.install-$version-$$
staging_launcher=$staging/bin/emdash-workspace-server
archive=$staging_dir/$artifact.$$
next_link=$root/.current-$version-$$
run_dir=$root/run
lock=$root/install.lock
lock_pid_file=$lock/pid

cleanup_metadata
trap - EXIT HUP INT TERM

mkdir -p -- "$root"
attempt=0
while ! mkdir "$lock" 2>/dev/null; do
  if [ -r "$lock_pid_file" ]; then
    lock_pid=$(cat "$lock_pid_file" 2>/dev/null || true)
  else
    lock_pid=
  fi
  if [ -n "$lock_pid" ] && ! kill -0 "$lock_pid" 2>/dev/null; then
    rm -rf -- "$lock"
    continue
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 120 ]; then
    fail 42 "timed out waiting for install lock"
  fi
  sleep 0.25
done

printf '%s\n' "$$" > "$lock_pid_file"
cleanup() {
  rm -rf -- "$staging" "$archive" "$next_link"
  rm -rf -- "$lock"
}
trap cleanup EXIT HUP INT TERM

mkdir -p -- "$versions_dir" "$staging_dir" "$run_dir"

current_target=$(readlink "$current_link" 2>/dev/null || true)
if { [ "$current_target" = "versions/$version" ] || [ "$current_target" = "$version_dir" ]; } &&
  [ -x "$launcher" ]; then
  exit 0
fi

rm -f -- "$next_link"
if [ -d "$version_dir" ]; then
  if [ ! -x "$launcher" ]; then
    fail 42 "existing workspace-server $version installation is incomplete"
  fi
  ln -s -- "versions/$version" "$next_link"
  mv -Tf -- "$next_link" "$current_link"
  exit 0
fi

rm -rf -- "$staging" "$archive"
mkdir -p -- "$staging"
if ! download "$artifact_url" "$archive"; then
  fail 41 "could not download $artifact"
fi
if ! printf '%s  %s\n' "$sha256" "$archive" | sha256sum -c - >/dev/null; then
  fail 41 "checksum verification failed for $artifact"
fi
if ! tar \
  --extract \
  --gzip \
  --file "$archive" \
  --strip-components=1 \
  --directory "$staging" \
  --warning=no-unknown-keyword; then
  fail 42 "could not extract $artifact"
fi
if [ ! -x "$staging_launcher" ]; then
  fail 42 "artifact launcher is missing"
fi

mv -- "$staging" "$version_dir"
ln -s -- "versions/$version" "$next_link"
mv -Tf -- "$next_link" "$current_link"
