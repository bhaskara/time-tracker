#!/usr/bin/env bash
# Install and start the Time Tracker server as a systemd user service that
# runs tt-server from this checkout's virtual environment.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
server="$repo/.venv/bin/tt-server"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit="$unit_dir/timetracker.service"

if [[ ! -x "$server" ]]; then
    echo "not found: $server (run 'uv sync' in $repo first)" >&2
    exit 1
fi

mkdir -p "$unit_dir"
cat > "$unit" <<UNIT
[Unit]
Description=Time Tracker server (http://127.0.0.1:8765)
After=graphical-session.target

[Service]
ExecStart=$server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now timetracker.service
systemctl --user --no-pager status timetracker.service | head -n 5
