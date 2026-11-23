

from dataclasses import dataclass
from datetime import datetime

@dataclass
class Candle:
    index: int  # continuous sequence number — proves the stream has no gaps
    open_time: datetime
    symbol: str
    timeframe: str
    unix_time: int
    utc_time: datetime
    ny_time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    source_indices: tuple[int, ...] = ()