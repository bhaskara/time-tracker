"""Presence adapter using the screen-lock state.

On Wayland, KDE does not expose input idle time, so this adapter is coarse:
a locked screen means away, an unlocked one means present.
"""

import shutil
import subprocess
import time
from datetime import timedelta

AWAY = timedelta(days=1)
PRESENT = timedelta(0)
CACHE_SECONDS = 10.0

_QUERY = [
    "qdbus",
    "org.freedesktop.ScreenSaver",
    "/ScreenSaver",
    "org.freedesktop.ScreenSaver.GetActive",
]


class ScreenLockPresence:
    """Treats the user as present exactly when the screen is unlocked.

    The answer is cached for a few seconds to avoid spawning a process on
    every check.

    Raises
    ------
    FileNotFoundError
        If ``qdbus`` is not installed.
    """

    def __init__(self) -> None:
        if shutil.which("qdbus") is None:
            raise FileNotFoundError("required program not found: qdbus")
        self._checked_at = float("-inf")
        self._locked = False

    def input_idle(self) -> timedelta:
        """Return zero if the screen is unlocked, a long time if it is locked.

        Raises
        ------
        subprocess.CalledProcessError
            If the screen saver service cannot be queried.
        """
        if time.monotonic() - self._checked_at > CACHE_SECONDS:
            result = subprocess.run(_QUERY, capture_output=True, text=True, check=True)
            self._locked = result.stdout.strip() == "true"
            self._checked_at = time.monotonic()
        return AWAY if self._locked else PRESENT
