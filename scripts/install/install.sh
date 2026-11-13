#!/bin/sh
# text-to-cad's installer for macOS and Linux:
#
#   curl -fsSL https://texttocad.dev/install.sh | sh
#
# It finds uv, or installs it with uv's own installer, then runs `cad setup` from the newest
# release of text-to-cad's server through uvx: text-to-cad set up or updated in every agent app on this machine,
# with nothing asked. Run it again to update; with --uninstall it runs `cad uninstall` instead; with
# --add X it installs release X alone (`cad setup --add`), which a skill's setup block asks for.
# Run with --help for its options; they go after `sh -s --` when piped.
# Everything happens inside main, called on the last line, so a download cut short runs nothing.

set -eu

# The release this script was published with, installed when the version feed cannot be read.
CAD_VERSION="0.11.10"
# The first release whose `cad uninstall` asks before it destroys, and takes --yes for an answer.
CONSENT_SINCE="0.11.0"
# The first release that installs itself alone, `cad setup --add`: the first whose skills pin their release.
ADD_SINCE="0.11.11"
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
  curl -fsSL https://texttocad.dev/install.sh | sh -s -- --add X.Y.Z

Options (all but --version, --from, --add and --uninstall go to \`cad setup\`, or to \`cad uninstall\`):
  --dry-run          print the plan and stop: nothing is changed
  --only APP[,APP]   only these apps: claude, claude-desktop, codex, cursor, grok, gemini, or
                     the agents the skills go to through the Skills CLI (cad setup --help)
  --uninstall        take text-to-cad out again: runs cad uninstall (with --purge, everything)
  --add X.Y.Z        install release X.Y.Z alone, and the cad command, and change nothing else: no app,
                     no other release, no setting (\`cad setup --add\`, which a skill's setup block asks
                     for). It reads no version feed and installs exactly X.Y.Z; it takes no other option
  --no-telemetry     turn telemetry off
  --version X.Y.Z    install that release (default: the newest, from $VERSION_FEED,
                     never older than this script's own, $CAD_VERSION)
  --from SPEC        run the server from SPEC instead: a wheel, a folder or a requirement
                     (also the CAD_INSTALL_FROM variable); for testing a build before its release,
                     with UV_FIND_LINKS naming the folder of the library's wheel beside it

uv comes from its own installer when it is missing; UV_NO_MODIFY_PATH=1 keeps it from editing
your shell profile. To read this script before running it, or to keep to one release, take the
copy attached to that release and check it against the release's SHA256SUMS:

  curl -fsSLO $RELEASES/v$CAD_VERSION/install.sh
  curl -fsSLO $RELEASES/v$CAD_VERSION/SHA256SUMS
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
# installs a release older than the one it was published with: that one has no `cad setup`.
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

# The device's state folder, as text-to-cad's own code says it (CAD_STATE_DIR overrides it).
state_dir() {
  if [ -n "${CAD_STATE_DIR:-}" ]; then
    printf '%s\n' "$CAD_STATE_DIR"
  elif [ "$(uname -s)" = Darwin ]; then
    printf '%s\n' "$HOME/Library/Application Support/cad"
  else
    printf '%s\n' "${XDG_STATE_HOME:-$HOME/.local/state}/cad"
  fi
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
  add=""
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
        [ "$count" -gt 0 ] || die "--version needs a release, as in --version $CAD_VERSION"
        version=$1
        shift
        count=$((count - 1))
        ;;
      --version=*)
        version=${argument#--version=}
        ;;
      --from)
        [ "$count" -gt 0 ] || die "--from needs a wheel, a folder or a requirement, as in --from ./cad_server-$CAD_VERSION-py3-none-any.whl"
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
      --add)
        [ "$count" -gt 0 ] || die "--add needs a release, as in --add $CAD_VERSION"
        add=$1
        shift
        count=$((count - 1))
        [ -n "$add" ] || die "--add needs a release, as in --add $CAD_VERSION"
        ;;
      --add=*)
        add=${argument#--add=}
        [ -n "$add" ] || die "--add needs a release, as in --add $CAD_VERSION"
        ;;
      *)
        set -- "$@" "$argument"
        ;;
    esac
  done

  if [ -n "$add" ]; then
    # Exactly that release, alone: no feed read, no newer one taken, nothing else asked of it.
    [ "$verb" = setup ] || die "--add installs a release; it does not go with --uninstall"
    [ -z "$version" ] || die "--add names its release; it does not go with --version"
    [ "$#" -eq 0 ] || die "--add takes no other option: $*"
    case $add in
      *-dev.*) die "$add is a development version: it is installed from its own checkout alone (scripts/install/dev_install.py)" ;;
    esac
    release "$add" || die "not a release: $add"
    # A build named outright (--from, CAD_INSTALL_FROM) is taken as this one.
    if [ -z "$from" ] && [ -z "${CAD_INSTALL_FROM:-}" ] && older "$add" "$ADD_SINCE"; then
      die "$add installs no release alone (the first that does is $ADD_SINCE): run this without --add"
    fi
    version=$add
    set -- --add
  fi

  [ -n "$from" ] || from=${CAD_INSTALL_FROM:-}
  if [ -n "$from" ]; then
    # A build named outright (a wheel, a folder, a requirement): uvx takes it as it is, nothing refreshed. With
    # --add, it must be that release's: a wheel's file name says its version.
    if [ -n "$add" ]; then
      case ${from##*/} in
        cad_server-"$add"-*.whl | cad-server=="$add") ;;
        cad_server-*.whl | cad-server==*) die "--from $from is not text-to-cad $add" ;;
      esac
    fi
    requirement=$from
    refresh=""
    version=${add:-$from}
    origin="as --from asked"
  else
    if [ -n "$add" ]; then
      origin="as --add asked"
    elif [ -n "$version" ]; then
      origin="as --version asked"
    else
      version=$(latest)
      if [ -z "$version" ]; then
        version=$CAD_VERSION
        origin="this script's own: the version feed could not be read"
      elif older "$version" "$CAD_VERSION"; then
        origin="this script's own: the version feed still names $version"
        version=$CAD_VERSION
      else
        origin="the newest release"
      fi
    fi
    release "$version" || die "not a release: $version"
    # Going back below the first pinned release on a device that runs one: that release knows no version folders,
    # and would point clients of it at another version than the default channel's. Not supported.
    if [ "$origin" = "as --version asked" ] && older "$version" "$ADD_SINCE" && [ -f "$(state_dir)/default" ]; then
      die "this computer runs text-to-cad $ADD_SINCE or newer: going back to $version, a release before $ADD_SINCE, is not supported"
    fi
    requirement="cad-server==$version"
    # The server, and the library it pins at its own release: uv reads both anew from the index.
    refresh="--refresh-package cad-server --refresh-package cad"
  fi

  if ! uvx=$(find_uvx); then
    install_uv
    uvx=$(find_uvx) || die "uv was installed, but uvx was not found: open a new terminal and run this again"
  fi
  # uvx's folder on PATH: `cad setup` writes uvx's absolute path into the apps' configs.
  PATH="$(dirname "$uvx"):$PATH"
  export PATH

  # --uninstall is the person's own word: `cad uninstall` is told yes for them (it would ask at a terminal),
  # but a release from before it asked, which takes no --yes. A build named outright is taken as this one.
  if [ "$verb" = uninstall ] && { [ -n "$from" ] || ! older "$version" "$CONSENT_SINCE"; }; then
    set -- "$@" --yes
  fi
  say "text-to-cad: $version ($origin). The first run downloads it, which takes a minute."
  # cad asks nothing here, so it reads no terminal. $refresh is four words or none.
  say "Running: $uvx --no-config --managed-python --python 3.14 ${refresh:+$refresh }--from $requirement cad $verb${*:+ $*}"
  exec "$uvx" --no-config --managed-python --python 3.14 $refresh --from "$requirement" cad "$verb" "$@"
}

main "$@"
