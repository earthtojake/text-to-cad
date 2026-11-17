#!/bin/sh
# text-to-cad's installer for macOS and Linux:
#
#   curl -fsSL https://texttocad.dev/install.sh | sh
#
# It makes sure uv is here and new enough (installing it with uv's own installer when it is not), downloads
# install.py from beside this script and runs it with uv's Python: that installs the cad command as a uv tool
# where there is none (a cad that is here updates itself), and puts the plugin into every agent app on this
# computer (install.py says how). Run it again to update the plugin. It takes no options, and names no release. Everything happens inside main, called on the last line, so a
# download cut short runs nothing.

set -eu

INSTALL_PY="https://texttocad.dev/install.py"
UV_INSTALLER="https://astral.sh/uv/install.sh"
# The oldest uv that runs it: `--managed-python` came in uv 0.6.8, and a stable CPython 3.14 (`--python 3.14`)
# in uv 0.9.0 (uv's changelog, changelogs/0.6.x.md and 0.9.x.md). An older uv's downloads know no 3.14.0.
UV_MINIMUM="0.9.0"

say() {
  printf '%s\n' "$*" >&2
}

die() {
  say "error: $*"
  exit 1
}

# uv: on PATH, else where uv's installer puts it before a new shell has it on PATH.
find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  for dir in "${UV_INSTALL_DIR:-}" "${UV_INSTALL_DIR:+$UV_INSTALL_DIR/bin}" "${XDG_BIN_HOME:-}" \
             "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
      printf '%s\n' "$dir/uv"
      return 0
    fi
  done
  return 1
}

download() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$2" "$1"
  else
    die "neither curl nor wget is here to download with"
  fi
}

# The uv uv's own installer put in place, never PATH's: the first in its folders, in the order it picks one
# (UV_INSTALL_DIR, and its bin for a Cargo-style folder; XDG_BIN_HOME; XDG_DATA_HOME/../bin; ~/.local/bin).
installed_uv() {
  for dir in "${UV_INSTALL_DIR:-}" "${UV_INSTALL_DIR:+$UV_INSTALL_DIR/bin}" "${XDG_BIN_HOME:-}" \
             "${XDG_DATA_HOME:+$XDG_DATA_HOME/../bin}" "$HOME/.local/bin"; do
    if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
      printf '%s\n' "$dir/uv"
      return 0
    fi
  done
  return 1
}

# uv's version, "0.9.5" from "uv 0.9.5 (Homebrew 2025-10-21)"; empty where it does not say.
uv_version() {
  "$1" --version 2>/dev/null | awk 'NR == 1 { print $2 }'
}

# Whether version $1 is older than $2 (each major.minor.patch; a missing part is 0).
older_than() {
  awk -v a="$1" -v b="$2" 'BEGIN {
    n = split(a, x, "."); m = split(b, y, ".")
    for (i = 1; i <= 3; i++) {
      p = (i <= n) ? x[i] + 0 : 0; q = (i <= m) ? y[i] + 0 : 0
      if (p < q) exit 0
      if (p > q) exit 1
    }
    exit 1
  }'
}

# uv installed by its own installer: that installer leaves a receipt, which `uv self update` needs.
uv_standalone() {
  [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/uv/uv-receipt.json" ]
}

main() {
  if [ "$#" -gt 0 ]; then
    say "This installer takes no options: run it as it is to install or update text-to-cad in every agent app"
    say "on this computer:  curl -fsSL https://texttocad.dev/install.sh | sh"
    say "To remove text-to-cad, run \`uv tool uninstall cad\`, and each app's own remove command."
    exit 2
  fi
  scratch=$(mktemp -d 2>/dev/null || mktemp -d -t text-to-cad)
  trap 'rm -rf "$scratch"' EXIT

  if ! uv=$(find_uv); then
    say "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/)."
    download "$UV_INSTALLER" "$scratch/uv-install.sh" ||
      die "could not download uv's installer from $UV_INSTALLER: check the network connection, or install uv (https://docs.astral.sh/uv/), then run this again"
    sh "$scratch/uv-install.sh" ||
      die "uv's installer failed (what it said is above): install uv (https://docs.astral.sh/uv/), then run this again"
    uv=$(find_uv) || die "uv was installed, but not found: open a new terminal and run this again"
  fi

  version=$(uv_version "$uv")
  if [ -z "$version" ] || older_than "$version" "$UV_MINIMUM"; then
    old="uv ${version:-of an unknown version}"
    if uv_standalone; then
      say "$old is older than $UV_MINIMUM, the first that installs Python 3.14: updating it (uv self update)."
      "$uv" self update || true
      version=$(uv_version "$uv")
    fi
    # One that cannot update itself (Homebrew's, pip's), or did not: uv's own installer puts a newer uv in its own
    # folder, as where uv is missing, and this run uses that one, whatever PATH finds first.
    if [ -z "$version" ] || older_than "$version" "$UV_MINIMUM"; then
      say "$old is older than $UV_MINIMUM, the first that installs Python 3.14: installing a newer uv with uv's own installer (https://docs.astral.sh/uv/)."
      if download "$UV_INSTALLER" "$scratch/uv-install.sh"; then
        sh "$scratch/uv-install.sh" || true
      fi
      version=""
      if uv=$(installed_uv); then
        version=$(uv_version "$uv")
      fi
      if [ -z "$version" ] || older_than "$version" "$UV_MINIMUM"; then
        die "$old is older than $UV_MINIMUM, and uv's installer did not install a newer uv (what it said is above)."
      fi
    fi
  fi
  # CAD_INSTALL_PY: a local install.py instead (the installer rehearsals run this checkout's).
  if [ -n "${CAD_INSTALL_PY:-}" ]; then
    cp "$CAD_INSTALL_PY" "$scratch/install.py"
  else
    download "$INSTALL_PY" "$scratch/install.py" || die "could not download $INSTALL_PY"
  fi
  # It asks nothing, so it reads no terminal. It finds uv by the UV variable `uv run` sets, and sees the PATH
  # this shell had, to say whether a new terminal is needed to find cad.
  "$uv" run --no-config --managed-python --python 3.14 --no-project "$scratch/install.py" </dev/null
}

main "$@"
