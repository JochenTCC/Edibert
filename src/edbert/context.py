"""Pricing context: time zone, location and holiday calendars of one house profile."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import holidays as holidays_lib

from edbert._fields import invalid
from edbert.errors import EdbertError, ErrorCode


class HolidayCalendar:
    """Public holidays of one country/region (``holidays`` package, offline) plus extra dates."""

    def __init__(self, land: str, region: str, extra_dates: frozenset[date] = frozenset()) -> None:
        try:
            self._lib = holidays_lib.country_holidays(land, subdiv=region)
        except NotImplementedError as exc:
            raise EdbertError(
                ErrorCode.HOLIDAY_REGION_UNKNOWN,
                f"Unknown holiday country/region: {land}/{region}.",
                land=land,
                region=region,
            ) from exc
        self._extra = extra_dates

    def is_holiday(self, day: date) -> bool:
        return day in self._extra or day in self._lib


class PricingContext:
    """Where and when prices are evaluated. Create one per house profile and session."""

    def __init__(self, timezone: str, land: str | None = None, region: str | None = None) -> None:
        try:
            self.tz = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise invalid("timezone", timezone) from exc
        self.timezone = timezone
        self.land = land.strip().upper() if land else None
        self.region = region.strip() if region else None
        self._calendars: dict[frozenset[date], HolidayCalendar] = {}

    def to_local(self, moment: datetime) -> datetime:
        """Local time of the house. A naive datetime is taken as local time."""
        if moment.tzinfo is None:
            return moment.replace(tzinfo=self.tz)
        return moment.astimezone(self.tz)

    def calendar_for(self, extra_dates: frozenset[date]) -> HolidayCalendar:
        """Holiday calendar for this location; a missing region is an error."""
        if not self.land or not self.region:
            raise EdbertError(
                ErrorCode.HOLIDAY_REGION_MISSING,
                "Holiday logic needs 'land' and 'region' in the pricing context.",
            )
        if extra_dates not in self._calendars:
            self._calendars[extra_dates] = HolidayCalendar(self.land, self.region, extra_dates)
        return self._calendars[extra_dates]
