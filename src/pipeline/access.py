# src/pipeline/access.py
"""
Single entry point for market data.

    from src.pipeline.access import MarketData, DataLayer, bootstrap

    layer = bootstrap(conn, mw, symbols=["XAUUSDm"], months=3, depth=500)
    layer.md        # MarketData
    layer.feed      # LiveFeed (already attached to conn)
    layer.windows   # dict[(symbol, tf), Window]

    md = MarketData(mw)
    md.get("XAUUSDm", "5m")
    md.get_multi("XAUUSDm", ["5m","1h","4h"])
    md.get_last("XAUUSDm", "4h")
    md.get_universe("4h")

Logging: src/logs/pipeline.log + stderr, configured by src/pipeline/__init__.py.
"""
from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from typing import Sequence

from src.data_structures.structures import Candle
from src.interface.connection import Connection
from src.interface.marketwatch import MarketWatch
from src.pipeline.fetch import Fetcher, LiveFeed
from src.pipeline.settings import FALLBACK_SYMBOL, FETCH_TFS, TF_MINUTES
from src.pipeline.window import Window

log = logging.getLogger(__name__)

_VALID_TFS = frozenset(TF_MINUTES)


class MarketData:
    """Cache over Fetcher. Owns MarketWatch (for universe), never a Connection."""

    def __init__(self, marketwatch: MarketWatch, default_months: int = 3,
                 workers: int = 1):
        if default_months <= 0:
            raise ValueError(f"default_months must be > 0, got {default_months}")
        self._mw = marketwatch
        self._default_months = default_months
        self._workers = workers
        self._cache: dict[tuple[str, str, int], list[Candle]] = {}

    def get(self, symbol: str, tf: str = "5m",
            months: int | None = None, refresh: bool = False) -> list[Candle]:
        self._validate(symbol, tf, months)
        months = months or self._default_months
        key = (symbol, tf, months)
        if not refresh and key in self._cache:
            log.debug("get HIT      symbol=%s  tf=%-3s  months=%d", symbol, tf, months)
            return self._cache[key]
        log.debug("get MISS     symbol=%s  tf=%-3s  months=%d", symbol, tf, months)
        fresh = self._fetch_symbol(symbol, months, tfs=(tf,))
        bars = [c for c in fresh if c.timeframe == tf]
        self._cache[key] = bars
        return bars

    def get_multi(self, symbol: str, timeframes: Sequence[str],
                  months: int | None = None, refresh: bool = False,
                  ) -> dict[str, list[Candle]]:
        self._validate(symbol, timeframes[0] if timeframes else "1m", months)
        months = months or self._default_months
        missing = [tf for tf in timeframes
                   if refresh or (symbol, tf, months) not in self._cache]
        if missing:
            log.info("get_multi MISS  symbol=%s  months=%d  tfs=%s",
                     symbol, months, missing)
            fresh = self._fetch_symbol(symbol, months, tfs=tuple(missing))
            for tf in missing:
                self._cache[(symbol, tf, months)] = [
                    c for c in fresh if c.timeframe == tf
                ]
        else:
            log.info("get_multi HIT   symbol=%s  months=%d  tfs=%s",
                     symbol, months, list(timeframes))
        return {tf: self._cache[(symbol, tf, months)] for tf in timeframes}

    def get_last(self, symbol: str, tf: str = "5m",
                 months: int | None = None) -> Candle | None:
        bars = self.get(symbol, tf, months)
        return bars[-1] if bars else None

    def get_universe(self, tf: str = "5m", months: int | None = None,
                     refresh: bool = False) -> dict[str, list[Candle]]:
        months = months or self._default_months
        symbols = self._mw.tradable_symbols() or [FALLBACK_SYMBOL]
        log.info("get_universe    tf=%s  months=%d  symbols=%d",
                 tf, months, len(symbols))
        return {s: self.get(s, tf, months, refresh=refresh) for s in symbols}

    def clear_cache(self) -> None:
        n = len(self._cache)
        self._cache.clear()
        log.info("cache cleared   dropped=%d", n)

    def cache_info(self) -> dict:
        return {
            "entries": len(self._cache),
            "total_candles": sum(len(c) for c in self._cache.values()),
            "keys": list(self._cache.keys()),
        }

    def _fetch_symbol(self, symbol: str, months: int,
                      tfs: tuple[str, ...]) -> list[Candle]:
        fetcher = Fetcher(months=months, workers=self._workers)
        return fetcher.fetch_symbol(symbol, tfs=tfs)

    @staticmethod
    def _validate(symbol: str, tf: str, months: int | None) -> None:
        if not symbol:
            raise ValueError("symbol cannot be empty")
        if tf not in _VALID_TFS:
            raise ValueError(f"unknown timeframe {tf!r}, known: {sorted(_VALID_TFS)}")
        if months is not None and months <= 0:
            raise ValueError(f"months must be > 0, got {months}")


@dataclass
class DataLayer:
    """Bag of resources main.py needs after bootstrap(). Not a lifecycle owner."""

    md:      MarketData
    fetcher: Fetcher
    feed:    LiveFeed
    windows: dict[tuple[str, str], Window] = field(default_factory=dict)

    def bars(self, symbol: str, tf: str) -> list[Candle]:
        return self.md.get(symbol, tf)

    def last(self, symbol: str, tf: str) -> Candle | None:
        return self.md.get_last(symbol, tf)

    def window(self, symbol: str, tf: str) -> Window | None:
        return self.windows.get((symbol, tf))


def bootstrap(
    conn: Connection,
    mw: MarketWatch,
    symbols: list[str] | None = None,
    tfs: tuple[str, ...] = FETCH_TFS,
    months: int = 3,
    depth: int = 500,
    workers: int = 4,
    poll_interval_s: float = 1.0,
) -> DataLayer:
    """
    Backfill history, build windows, attach live feed. Does NOT own conn.
    main.py passes it in and keeps ownership.
    """
    symbols = list(symbols) if symbols else [FALLBACK_SYMBOL]

    md      = MarketData(mw, default_months=months, workers=workers)
    fetcher = Fetcher(months=months, workers=workers)
    feed    = LiveFeed(fetcher, poll_interval_s=poll_interval_s)

    log.info("bootstrap start  symbols=%s  tfs=%s  months=%d  depth=%d  workers=%d",
             symbols, list(tfs), months, depth, workers)

    # 1. backfill
    for sym in symbols:
        t0 = _time.time()
        md.get_multi(sym, tfs, months=months)
        log.info("backfill done    symbol=%s  elapsed=%.2fs",
                 sym, _time.time() - t0)

    # 2. build + seed windows
    windows: dict[tuple[str, str], Window] = {}
    for sym in symbols:
        for tf in tfs:
            w = Window(depth)
            w.seed(md.get(sym, tf, months=months))
            windows[(sym, tf)] = w
            log.info("window seeded    symbol=%s  tf=%-3s  bars=%d",
                     sym, tf, len(w))

    # 3. attach live feed
    for (sym, tf), w in windows.items():
        feed.subscribe(sym, tf, w.push)
    feed.attach(conn)

    log.info("bootstrap done   windows=%d", len(windows))
    return DataLayer(md=md, fetcher=fetcher, feed=feed, windows=windows)


__all__ = ["MarketData", "DataLayer", "bootstrap"]