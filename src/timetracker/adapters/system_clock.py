"""Clock adapter backed by the system time."""

from datetime import UTC, datetime


class SystemClock:
    """Reads the real current time."""

    def now(self) -> datetime:
        """Return the current instant in UTC."""
        return datetime.now(UTC)
