"""UTC persistence and user-local review day boundaries."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Dialect
from sqlalchemy.types import TypeDecorator


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Require aware writes and return UTC-aware values, including on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        return None if value is None else as_utc(value)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        # SQLite drops timezone information; this type always writes UTC.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return as_utc(value)


def local_day_bounds(now: datetime, timezone: str) -> tuple[datetime, datetime]:
    """Return [local midnight, next local midnight) as UTC instants."""
    zone = ZoneInfo(timezone)
    today = as_utc(now).astimezone(zone).date()
    start = datetime.combine(today, time.min, tzinfo=zone)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
    return as_utc(start), as_utc(end)
