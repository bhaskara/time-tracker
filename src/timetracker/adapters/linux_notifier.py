"""Notifier adapter for a Linux desktop: notify-send for the message, pw-play for the chime."""

import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from timetracker.ports import Notification

APP_NAME = "Time Tracker"


class LinuxNotifier:
    """Shows desktop notifications and plays a chime.

    Each notification runs in its own daemon thread so ``send`` never blocks.

    Parameters
    ----------
    sound_file : Path
        Audio file played for notifications with ``sound=True``.

    Raises
    ------
    FileNotFoundError
        If ``notify-send`` or ``pw-play`` is not installed, or the sound file
        does not exist.
    """

    def __init__(self, sound_file: Path) -> None:
        for tool in ("notify-send", "pw-play"):
            if shutil.which(tool) is None:
                raise FileNotFoundError(f"required program not found: {tool}")
        if not sound_file.is_file():
            raise FileNotFoundError(f"sound file not found: {sound_file}")
        self._sound_file = sound_file

    def send(
        self, notification: Notification, on_action: Callable[[str], None] | None = None
    ) -> None:
        """Deliver ``notification`` without blocking.

        Plays the chime if ``sound`` is set and shows a pop-up if ``popup``
        is set. If the user picks one of the pop-up's actions, ``on_action``
        is called from a background thread with that action's name.
        """
        if notification.sound:
            threading.Thread(
                target=subprocess.run, args=(["pw-play", str(self._sound_file)],), daemon=True
            ).start()
        if notification.popup:
            threading.Thread(
                target=self._show, args=(notification, on_action), daemon=True
            ).start()

    def _show(self, notification: Notification, on_action: Callable[[str], None] | None) -> None:
        """Run notify-send; with actions it waits and reports the one chosen."""
        command = ["notify-send", "--app-name", APP_NAME]
        for name, text in notification.actions:
            command += ["--action", f"{name}={text}"]
        command += [notification.title, notification.body]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        chosen = result.stdout.strip()
        if chosen and on_action is not None:
            on_action(chosen)
