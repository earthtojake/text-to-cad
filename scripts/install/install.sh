#!/bin/sh
# text-to-cad's installer for macOS and Linux:
#
#   curl -fsSL https://texttocad.dev/install.sh | sh
#
# It finds uv, or installs it with uv's own installer, then runs `cadgen setup` from the newest
# cadgen release through uvx: text-to-cad set up or updated in every agent app on this machine,
# with nothing asked. Run it again to update; with --uninstall it runs `cadgen uninstall` instead.
# Run with --help for its options; they go after `sh -s --` when piped.
# Everything happens inside main, called on the last line, so a download cut short runs nothing.

set -eu

# The release this script was published with, installed when the version feed cannot be read.
CADGEN_VERSION="0.8.4"
VERSION_FEED="https://api.texttocad.dev/v1/versions"
RELEASES="https://github.com/earthtojake/text-to-cad/releases/download"

say() {
  printf '%s\n' "$*" >&2
}

die() {
  say "error: $*"
  exit 1
}

usage() {
  cat <<EOF
text-to-cad's installer: installs or updates text-to-cad in every agent app on this machine. It
prints its plan and carries it out, asking nothing; --dry-run prints the plan alone.

  curl -fsSL https://texttocad.dev/install.sh | sh
  curl -fsSL https://texttocad.dev/install.sh | sh -s -- --dry-run

Options (all but --version, --from and --uninstall go to \`cadgen setup\`, or to \`cadgen uninstall\`):
  --dry-run          print the plan and stop: nothing is changed
  --only APP[,APP]   only these apps: claude, claude-desktop, codex, cursor, grok, gemini, or
                     the agents the skills go to through the Skills CLI (cadgen setup --help)
  --uninstall        take text-to-cad out again: runs cadgen uninstall (with --purge, cadgen's state and caches too)
  --no-telemetry     turn telemetry off
  --version X.Y.Z    install that cadgen release (default: the newest, from $VERSION_FEED,
                     never older than this script's own, $CADGEN_VERSION)
  --from SPEC        run cadgen from SPEC instead: a wheel, a folder or a requirement
                     (also the CADGEN_INSTALL_FROM variable); for testing a build before its release

uv comes from its own installer when it is missing; UV_NO_MODIFY_PATH=1 keeps it from editing
your shell profile. To read this script before running it, or to keep to one release, take the
copy attached to that release and check it against the release's SHA256SUMS:

  curl -fsSLO $RELEASES/v$CADGEN_VERSION/install.sh
  curl -fsSLO $RELEASES/v$CADGEN_VERSION/SHA256SUMS
  grep ' install.sh\$' SHA256SUMS | shasum -a 256 -c && sh install.sh

On Windows: irm https://www.texttocad.dev/install.ps1 | iex
EOF
}

# uvx: on PATH, else where uv's installer puts it before a new shell has it on PATH.
find_uvx() {
  if command -v uvx >/dev/null 2>&1; then
    command -v uvx
    return 0
  fi
  for dir in "${UV_INSTALL_DIR:-}" "${UV_INSTALL_DIR:+$UV_INSTALL_DIR/bin}" "${XDG_BIN_HOME:-}" \
             "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -n "$dir" ] && [ -x "$dir/uvx" ]; then
      printf '%s\n' "$dir/uvx"
      return 0
    fi
  done
  return 1
}

install_uv() {
  say "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/):"
  if command -v curl >/dev/null 2>&1; then
    say "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    say "  wget -qO- https://astral.sh/uv/install.sh | sh"
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    die "neither curl nor wget is here to download uv with; install uv (https://docs.astral.sh/uv/), then run this again"
  fi
}

# The newest release, from the version feed: {"latest": "X.Y.Z"}. Nothing when it cannot be read in 3 s.
latest() {
  if command -v curl >/dev/null 2>&1; then
    body=$(curl -fsS --max-time 3 "$VERSION_FEED" 2>/dev/null) || return 0
  elif command -v wget >/dev/null 2>&1; then
    body=$(wget -qO- --timeout=3 "$VERSION_FEED" 2>/dev/null) || return 0
  else
    return 0
  fi
  printf '%s\n' "$body" | sed -n 's/.*"latest"[[:space:]]*:[[:space:]]*"\([0-9][0-9A-Za-z.+-]*\)".*/\1/p' | head -n 1
}

# Whether release $1 is older than release $2: the first three dotted numbers compared, a
# suffix (-dev, rc1) ignored. The feed lags a release by up to an hour, and this script never
# installs a release older than the one it was published with: that one has no `cadgen setup`.
older() {
  i=1
  while [ "$i" -le 3 ]; do
    x=$(printf '%s\n' "$1" | awk -F. -v i="$i" '{ v = $i; sub(/[^0-9].*/, "", v); print (v == "" ? 0 : v) }')
    y=$(printf '%s\n' "$2" | awk -F. -v i="$i" '{ v = $i; sub(/[^0-9].*/, "", v); print (v == "" ? 0 : v) }')
    [ "$x" -lt "$y" ] && return 0
    [ "$x" -gt "$y" ] && return 1
    i=$((i + 1))
  done
  return 1
}

# A release's version: a digit first, then digits, letters, dots, + and - alone.
release() {
  case $1 in
    [0-9]*) ;;
    *) return 1 ;;
  esac
  case $1 in
    *[!0-9A-Za-z.+-]*) return 1 ;;
  esac
  return 0
}

main() {
  version=""
  from=""
  verb=setup
  # --version picks the release and --uninstall the verb; every other argument goes to it, in order.
  count=$#
  while [ "$count" -gt 0 ]; do
    argument=$1
    shift
    count=$((count - 1))
    case $argument in
      -h | --help)
        usage
        exit 0
        ;;
      --version)
        [ "$count" -gt 0 ] || die "--version needs a release, as in --version $CADGEN_VERSION"
        version=$1
        shift
        count=$((count - 1))
        ;;
      --version=*)
        version=${argument#--version=}
        ;;
      --from)
        [ "$count" -gt 0 ] || die "--from needs a wheel, a folder or a requirement, as in --from ./cadgen-$CADGEN_VERSION-py3-none-any.whl"
        from=$1
        shift
        count=$((count - 1))
        ;;
      --from=*)
        from=${argument#--from=}
        ;;
      --uninstall)
        verb=uninstall
        ;;
      *)
        set -- "$@" "$argument"
        ;;
    esac
  done

  [ -n "$from" ] || from=${CADGEN_INSTALL_FROM:-}
  if [ -n "$from" ]; then
    # A build named outright (a wheel, a folder, a requirement): uvx takes it as it is, nothing refreshed.
    requirement=$from
    refresh=""
    version=$from
    origin="as --from asked"
  else
    if [ -n "$version" ]; then
      origin="as --version asked"
    else
      version=$(latest)
      if [ -z "$version" ]; then
        version=$CADGEN_VERSION
        origin="this script's own: the version feed could not be read"
      elif older "$version" "$CADGEN_VERSION"; then
        origin="this script's own: the version feed still names $version"
        version=$CADGEN_VERSION
      else
        origin="the newest release"
      fi
    fi
    release "$version" || die "not a cadgen release: $version"
    requirement="cadgen==$version"
    refresh="--refresh-package cadgen"
  fi

  if ! uvx=$(find_uvx); then
    install_uv
    uvx=$(find_uvx) || die "uv was installed, but uvx was not found: open a new terminal and run this again"
  fi
  # uvx's folder on PATH: `cadgen setup` writes uvx's absolute path into the apps' configs.
  PATH="$(dirname "$uvx"):$PATH"
  export PATH

  say "text-to-cad: cadgen $version ($origin). The first run downloads it, which takes a minute."
  # cadgen asks nothing, so it reads no terminal. $refresh is two words or none.
  say "Running: $uvx --no-config --managed-python --python 3.14 ${refresh:+$refresh }--from $requirement cadgen $verb${*:+ $*}"
  exec "$uvx" --no-config --managed-python --python 3.14 $refresh --from "$requirement" cadgen "$verb" "$@"
}

main "$@"
