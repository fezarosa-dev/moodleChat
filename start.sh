#!/usr/bin/env bash
# Sobe o backend dentro da distrobox fedora-dev (onde estão gcc e claude).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/bot_moodle"
exec distrobox enter fedora-dev -- "$PWD/.venv/bin/bot-moodle" "$@"
