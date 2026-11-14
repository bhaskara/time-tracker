#!/usr/bin/env bash
# Set up a daily database snapshot: records the backup folder in the config
# file and installs a systemd user timer that runs "tt backup".
#
# Usage: deploy/install-backup.sh BACKUP_DIR
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 BACKUP_DIR" >&2
    exit 1
fi
backup_dir="$(realpath -m "$1")"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tt="$repo/.venv/bin/tt"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}"
config="$config_dir/timetracker/config.toml"
unit_dir="$config_dir/systemd/user"

if [[ ! -x "$tt" ]]; then
    echo "not found: $tt (run 'uv sync' in $repo first)" >&2
    exit 1
fi

# Record the folder in the config file, replacing an earlier setting.
mkdir -p "$(dirname "$config")"
touch "$config"
if grep -q '^backup_dir[[:space:]]*=' "$config"; then
    sed -i "s|^backup_dir[[:space:]]*=.*|backup_dir = \"$backup_dir\"|" "$config"
else
    echo "backup_dir = \"$backup_dir\"" >> "$config"
fi

mkdir -p "$unit_dir"
cat > "$unit_dir/timetracker-backup.service" <<UNIT
[Unit]
Description=Time Tracker database snapshot

[Service]
Type=oneshot
ExecStart=$tt backup
UNIT

# 03:00 is after the 2 AM day boundary, so each snapshot holds the whole
# previous day. Persistent runs a missed backup at the next login or wake.
cat > "$unit_dir/timetracker-backup.timer" <<UNIT
[Unit]
Description=Daily Time Tracker database snapshot

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now timetracker-backup.timer
systemctl --user start timetracker-backup.service
systemctl --user --no-pager list-timers timetracker-backup.timer | head -n 3
