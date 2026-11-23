# src/pipeline/time.py
"""
Time conversion and trading-session calendar.

Single source of truth for:
    - UTC / NY conversion (TimeConverter, to_utc, to_ny)
    - the 18:00 NY trading-day roll (SessionCalendar, session)
    - session boundaries (SESSION_START, SESSION_END)
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")


def to_utc(unix: int) -> datetime:
    return datetime.fromtimestamp(unix, tz=timezone.utc)


def to_ny(unix: int) -> datetime:
    return to_utc(unix).astimezone(NY)


SESSION_START = time(18, 0)
SESSION_END   = time(17, 0)


class TimeConverter:
    NY = NY

    def to_utc(self, unix: int) -> datetime:
        return to_utc(unix)

    def to_ny(self, unix: int) -> datetime:
        return to_ny(unix)

    def to_both_text(self, unix: int) -> Tuple[str, str]:
        return self.to_utc(unix).isoformat(), self.to_ny(unix).isoformat()


class SessionCalendar:
    SESSION_START_HOUR = 18
    SESSION_END_HOUR   = 17

    TRADING_DAY_NAMES = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday",
    }

    @staticmethod
    def trading_day_date(t: datetime) -> date:
        if t.tzinfo is not None:
            t = t.astimezone(NY)
        if t.hour >= SessionCalendar.SESSION_START_HOUR:
            return (t + timedelta(days=1)).date()
        return t.date()

    @staticmethod
    def trading_day_id(t: datetime) -> Tuple[int, int, int]:
        d = SessionCalendar.trading_day_date(t)
        return (d.year, d.month, d.day)

    @staticmethod
    def trading_day_name(t: datetime) -> str:
        d = SessionCalendar.trading_day_date(t)
        return SessionCalendar.TRADING_DAY_NAMES.get(d.weekday(), "Unknown")

    @staticmethod
    def trading_week_start(t: datetime) -> datetime:
        day_date = SessionCalendar.trading_day_date(t)
        days_since_sunday = (day_date.weekday() + 1) % 7
        week_start_date = day_date - timedelta(days=days_since_sunday)
        return datetime.combine(
            week_start_date,
            datetime.min.time().replace(hour=SessionCalendar.SESSION_START_HOUR),
        )

    @staticmethod
    def trading_week_id(t: datetime) -> Tuple[int, int]:
        week_start = SessionCalendar.trading_week_start(t)
        return (week_start.year, week_start.toordinal() // 7)

    @staticmethod
    def trading_month_id(t: datetime) -> Tuple[int, int]:
        d = SessionCalendar.trading_day_date(t)
        return (d.year, d.month)

    @staticmethod
    def trading_year_id(t: datetime) -> int:
        return SessionCalendar.trading_day_date(t).year

    @staticmethod
    def is_new_trading_day(prev_t: Optional[datetime], curr_t: datetime) -> bool:
        if prev_t is None:
            return True
        return (SessionCalendar.trading_day_id(prev_t)
                != SessionCalendar.trading_day_id(curr_t))

    @staticmethod
    def is_new_trading_week(prev_t: Optional[datetime], curr_t: datetime) -> bool:
        if prev_t is None:
            return True
        return (SessionCalendar.trading_week_id(prev_t)
                != SessionCalendar.trading_week_id(curr_t))

    @staticmethod
    def is_new_trading_month(prev_t: Optional[datetime], curr_t: datetime) -> bool:
        if prev_t is None:
            return True
        return (SessionCalendar.trading_month_id(prev_t)
                != SessionCalendar.trading_month_id(curr_t))

    @staticmethod
    def is_new_trading_year(prev_t: Optional[datetime], curr_t: datetime) -> bool:
        if prev_t is None:
            return True
        return (SessionCalendar.trading_year_id(prev_t)
                != SessionCalendar.trading_year_id(curr_t))

    @staticmethod
    def trading_days_in_week(t: datetime) -> List[date]:
        week_start = SessionCalendar.trading_week_start(t)
        return [week_start.date() + timedelta(days=i) for i in range(5)]

    @staticmethod
    def shift_to_session_start(dt: datetime) -> datetime:
        if dt.hour >= SessionCalendar.SESSION_START_HOUR:
            return dt.replace(hour=SessionCalendar.SESSION_START_HOUR,
                              minute=0, second=0, microsecond=0)
        return (dt - timedelta(days=1)).replace(
            hour=SessionCalendar.SESSION_START_HOUR,
            minute=0, second=0, microsecond=0,
        )


session = SessionCalendar()


class Session:
    SESSION_START_HOUR = SessionCalendar.SESSION_START_HOUR
    SESSION_END        = SESSION_END
    TRADING_DAY_NAMES  = SessionCalendar.TRADING_DAY_NAMES