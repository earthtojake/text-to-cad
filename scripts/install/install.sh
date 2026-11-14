#!/bin/sh
# text-to-cad's installer for macOS and Linux:
#
#   curl -fsSL https://texttocad.dev/install.sh | sh
#
# It makes sure uv is here (installing it with uv's own installer when it is not), downloads install.py
# from beside this script and runs it with uv's Python: that installs the newest release of text-to-cad
# and puts the plugin into every agent app on this computer (install.py says how). Run it again to update.
# It takes no options. Everything happens inside main, called on the last line, so a download cut short
# runs nothing.

set -eu

INSTALL_PY="https://texttocad.dev/install.py"

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

main() {
  if [ "$#" -gt 0 ]; then
    say "This installer takes no options: run it as it is to install or update text-to-cad in every agent app"
    say "on this computer:  curl -fsSL https://texttocad.dev/install.sh | sh"
    say "To remove text-to-cad, run \`cad uninstall\`, and each app's own remove command."
    exit 2
  fi
  if ! uv=$(find_uv); then
    say "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/)."
    if command -v curl >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://astral.sh/uv/install.sh | sh
    else
      die "neither curl nor wget is here to download uv with; install uv (https://docs.astral.sh/uv/), then run this again"
    fi
    uv=$(find_uv) || die "uv was installed, but not found: open a new terminal and run this again"
  fi
  # uv's folder on PATH, so install.py finds uvx beside it.
  PATH="$(dirname "$uv"):$PATH"
  export PATH

  scratch=$(mktemp -d 2>/dev/null || mktemp -d -t text-to-cad)
  trap 'rm -rf "$scratch"' EXIT
  # CAD_INSTALL_PY: a local install.py instead (the installer rehearsals run this checkout's).
  if [ -n "${CAD_INSTALL_PY:-}" ]; then
    cp "$CAD_INSTALL_PY" "$scratch/install.py"
  else
    download "$INSTALL_PY" "$scratch/install.py" || die "could not download $INSTALL_PY"
  fi
  # It asks nothing, so it reads no terminal.
  "$uv" run --no-config --managed-python --python 3.14 --no-project "$scratch/install.py" </dev/null
}

main "$@"
