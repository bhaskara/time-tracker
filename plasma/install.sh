#!/usr/bin/env bash
# Install or upgrade the Time Tracker panel widget for the current user.
set -euo pipefail

package="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/org.timetracker.panel"

installed="${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/org.timetracker.panel"

# Checked via the install directory: "kpackagetool5 --show" crashes on some
# Plasma 5.27 builds.
if [[ -d "$installed" ]]; then
    kpackagetool5 --type Plasma/Applet --upgrade "$package"
else
    kpackagetool5 --type Plasma/Applet --install "$package"
fi
echo "Installed. Add it with: right-click the panel > Add Widgets > Time Tracker."
echo "After an upgrade, restart the shell to load the new version: systemctl --user restart plasma-plasmashell"
