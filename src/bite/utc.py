from datetime import tzinfo, timedelta, datetime
import re

from dateutil.parser import parse as parsetime
from dateutil.relativedelta import relativedelta

ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# A UTC class.

class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return 'UTC'

    def dst(self, dt):
        return ZERO

utc = UTC()

# A class capturing the platform's idea of local time.

import time as _time

STDOFFSET = timedelta(seconds = -_time.timezone)
if _time.daylight:
    DSTOFFSET = timedelta(seconds = -_time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

class LocalTimezone(tzinfo):

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return ZERO

    def tzname(self, dt):
        return _time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        stamp = _time.mktime(tt)
        tt = _time.localtime(stamp)
        return tt.tm_isdst > 0

Local = LocalTimezone()


def utcnow():
    """Return current UTC date and time at second resolution level."""
    d = datetime.utcnow()
    return d.replace(microsecond=0)


def parse_date(s):
    if re.match(r'^(\d+([ymwdhs]|min))+$', s):
        date = utcnow()
        units = {
            'y': 'years',
            'm': 'months',
            'w': 'weeks',
            'd': 'days',
            'h': 'hours',
            'min': 'minutes',
            's': 'seconds',
        }
        for value, unit in re.findall(r'(\d+)([ymwdhs]|min)', s):
            kw = {units[unit]: -int(value)}
            date += relativedelta(**kw)
    elif re.match(r'^\d\d\d\d$', s):
        date = parsetime(s) + relativedelta(yearday=1)
    elif re.match(r'^\d\d\d\d[-/]\d\d$', s):
        date = parsetime(s) + relativedelta(day=1)
    elif re.match(r'^(\d\d)?\d\d[-/]\d\d[-/]\d\d$', s):
        date = parsetime(s)
    elif re.match(r'^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(\+\d\d:\d\d)?$', s):
        try:
            # try converting timezone if one is specified
            date = parsetime(s).astimezone(utc)
        except ValueError:
            # otherwise default to UTC if none is specified
            date = parsetime(s).replace(tzinfo=utc)
    elif s == 'now':
        return utcnow()
    else:
        raise ValueError(f'invalid time value: {s!r}')

    # drop microsecond resolution since we shouldn't need it
    return date.replace(microsecond=0)
