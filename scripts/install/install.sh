#!/bin/sh
# text-to-cad's installer for macOS and Linux:
#
#   curl -fsSL https://texttocad.dev/install.sh | sh
#
# It makes sure uv is here and new enough (installing it with uv's own installer when it is not), downloads
# install.py from beside this script and runs it with uv's Python: that installs the cad command as a uv tool
# where there is none, brings a cad that is here up to date, and has cad put the plugin into every agent app on
# this computer (`cad plugin install`; install.py says how). Run it again to update both. It takes no options, and
# names no release. Everything happens inside main, called on the last line, so a download cut short runs nothing.
#
# Where it fails before install.py runs, it sends one anonymous report of where (`report`): uv could not be installed
# or is too old (uv), install.py could not be downloaded (fetch), or uv could not run it (python). install.py reports
# what fails after that, and says what a report holds and when none is sent. A run cad started says and sends nothing
# from here (`may_report`).

set -eu

INSTALL_PY="https://texttocad.dev/install.py"
UV_INSTALLER="https://astral.sh/uv/install.sh"
# The oldest uv that runs it: `--managed-python` came in uv 0.6.8, and a stable CPython 3.14 (`--python 3.14`)
# in uv 0.9.0 (uv's changelog, changelogs/0.6.x.md and 0.9.x.md). An older uv's downloads know no 3.14.0.
UV_MINIMUM="0.9.0"
# Where a failure's one report goes: cad's own service (CAD_API_URL, cad's own hook, names a stand-in's base).
REPORT_URL="https://api.texttocad.dev/v1/install"
# Said once, near the start, by a person's run that could send a report: install.py's NOTICE, word for word.
NOTICE="If the install fails before cad can run, one anonymous report of where it failed is sent to texttocad.dev (DO_NOT_TRACK=1 turns it off)."

say() {
  printf '%s\n' "$*" >&2
}

# The run ends here, failed at $stage, which main keeps.
die() {
  say "error: $*"
  report "$stage" 1
  exit 1
}

# A word of the environment as cad reads one: lower case, nothing around it.
word() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d ' \t\r\n'
}

# Whether cad's settings in the state folder $1 say no to telemetry: "choice": "off" in the "telemetry" section of
# its settings.json, which cad writes as JSON with no object inside that section. One that cannot be read is no yes.
kept_no() {
  [ -f "$1/settings.json" ] || return 1
  [ -r "$1/settings.json" ] || return 0
  tr -d ' \t\r\n' < "$1/settings.json" 2>/dev/null | grep -q '"telemetry":{[^{}]*"choice":"off"'
}

# Whether a failure of this run may be reported: not where the environment says no (DO_NOT_TRACK on, CAD_TELEMETRY
# off: cad's own spellings), in CI, on a checkout's run (CAD_INSTALL_PY), with nothing here to send by, or where
# cad's kept settings say no (its state folder: CAD_STATE_DIR, macOS's, XDG's). And never on a run cad started
# (CAD_INSTALL_BY_CAD, CAD_INSTALL_ATTEMPT or CAD_INSTALL_REPORT set: its output is a log's, or nobody's): the line
# said first would be read by no one, and nothing is sent before a person was told. Whether cad told them already
# is in its settings, which install.py reads: it reports such a run's later failures where they were.
may_report() {
  case "$(word "${DO_NOT_TRACK:-}")" in 1|on|true|yes) return 1 ;; esac
  case "$(word "${CAD_TELEMETRY:-}")" in 0|off|false|no) return 1 ;; esac
  case "$(word "${CI:-}")" in ''|0|off|false|no) ;; *) return 1 ;; esac
  [ -z "${CAD_INSTALL_PY:-}" ] || return 1
  [ -z "${CAD_INSTALL_BY_CAD:-}${CAD_INSTALL_ATTEMPT:-}${CAD_INSTALL_REPORT:-}" ] || return 1
  command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || return 1
  for dir in "${CAD_STATE_DIR:-}" "$HOME/Library/Application Support/cad" "${XDG_STATE_HOME:-$HOME/.local/state}/cad"; do
    if [ -n "$dir" ] && kept_no "$dir"; then
      return 1
    fi
  done
  return 0
}

# One anonymous report that this run failed at stage $1 (uv, fetch, python) with exit status $2, where one may be
# sent ($reports) and none was: the body install.py documents, its run id random and kept nowhere, a person's run
# always (`may_report`). curl gives it 2 seconds in all, wget 2 for each step of one try. It says nothing, and never
# changes how the run ends.
report() {
  [ -n "$reports" ] || return 0
  reports=""
  id=$(od -An -N16 -tx1 /dev/urandom 2>/dev/null | tr -d ' \t\n' |
    sed 's/^\(.\{8\}\)\(.\{4\}\)\(.\{4\}\)\(.\{4\}\)\(.\{12\}\)$/\1-\2-\3-\4-\5/') || return 0
  case "$id" in ????????-????-????-????-????????????) ;; *) return 0 ;; esac
  at=$(date +%s 2>/dev/null) || return 0
  case "$at" in ''|*[!0-9]*) return 0 ;; esac
  case "$(uname -s 2>/dev/null)" in Darwin) platform=darwin ;; Linux) platform=linux ;; *) platform=other ;; esac
  arch=$(uname -m 2>/dev/null | tr -d '\n' | tr '[:upper:]' '[:lower:]' |
    tr -cs 'abcdefghijklmnopqrstuvwxyz0123456789_.+:-' '-' | cut -c1-16) || arch=""
  with=none
  if printf '%s\n' "${version:-$had}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    with=${version:-$had}
  fi
  body=$(printf '{"schema":1,"run":"%s","at":%s,"stage":"%s","outcome":"failed","code":%s,"platform":"%s","arch":"%s","by":"person","uv":"%s"}' \
    "$id" "$at" "$1" "$2" "$platform" "$arch" "$with")
  url=$REPORT_URL
  case "${CAD_API_URL:-}" in http://*|https://*) url="${CAD_API_URL%/}/install" ;; esac
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -m 2 -o /dev/null -H 'Content-Type: application/json' -d "$body" "$url" >/dev/null 2>&1 || true
  elif command -v wget >/dev/null 2>&1; then
    wget -q -T 2 -t 1 -O /dev/null --header='Content-Type: application/json' --post-data="$body" "$url" >/dev/null 2>&1 || true
  fi
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
  # What a report of this run would say: the stage it is at, uv's version once known (the one found too old, where
  # no newer one took its place), and whether one may be sent.
  stage=uv
  version=""
  had=""
  reports=""
  if may_report; then
    reports=1
    say "$NOTICE"
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
    had=$version
    if uv_standalone; then
      say "$old is older than $UV_MINIMUM, the first that installs Python 3.14: updating it (uv self update)."
      "$uv" self update || true
      version=$(uv_version "$uv")
      had=${version:-$had}
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
  stage=fetch
  if [ -n "${CAD_INSTALL_PY:-}" ]; then
    cp "$CAD_INSTALL_PY" "$scratch/install.py"
  else
    download "$INSTALL_PY" "$scratch/install.py" || die "could not download $INSTALL_PY"
  fi
  # It asks nothing, so it reads no terminal. It finds uv by the UV variable `uv run` sets, and sees the PATH
  # this shell had, to say whether a new terminal is needed to find cad. It leaves the file CAD_INSTALL_MARK names
  # as it starts, and reports what fails from then on itself: without the file, uv could not run it (its Python
  # could not be set up, say), which is this script's to report.
  code=0
  CAD_INSTALL_MARK="$scratch/started" "$uv" run --no-config --managed-python --python 3.14 --no-project "$scratch/install.py" </dev/null || code=$?
  if [ "$code" -ne 0 ] && [ ! -e "$scratch/started" ]; then
    report python "$code"
  fi
  return "$code"
}

main "$@"
