#!/bin/bash
set -euo pipefail

install -d -m 0755 /run/sshd
exec /usr/sbin/sshd -D -e
