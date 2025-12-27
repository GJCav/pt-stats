import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import attrs
import time

def localize2utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC, assuming the input datetime is in local timezone if naive.
    """
    if dt.tzinfo is None:
        local_dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return local_dt.astimezone(ZoneInfo("UTC"))


@attrs.define
class Throttle:
    rate: float  # actions per second
    last_time: float = attrs.field(default=0.0)
    
    async def __call__(self):
        now = time.monotonic()
        elapsed = now - self.last_time
        wait_time = 1.0 / self.rate - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self.last_time = time.monotonic()