# src/pipeline/fetch.py
"""
Everything that reads bars from MT5: historical (Fetcher) and live (LiveFeed).

    fetcher = Fetcher(months=3)
    raw     = fetcher.fetch(symbol="XAUUSDm", tfs=("1h","4h"))

    feed    = LiveFeed(fetcher)
    feed.seed(w4h, "XAUUSDm", "4h", raw=raw)
    feed.subscribe("XAUUSDm", "4h", w4h.push)
    feed.attach(conn)

Fetcher never imports Connection or MarketWatch. LiveFeed takes a Connection
as an argument to attach(); it does not own one.

Logging: src/logs/pipeline.log + stderr, configured by src/pipeline/__init__.py.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from src.data_structures.structures import Candle
from src.pipeline.settings import MT5_TIMEFRAME, TF_MINUTES
from src.pipeline.time import TimeConverter

log = logging.getLogger(__name__)

MONTH_S = 30 * 24 * 60 * 60


class FetchError(RuntimeError):
    """Raised when MT5 returns no data or errors during a fetch."""


class Fetcher:
    """Fetch native bars from MT5. Symbol-agnostic: caller passes the symbol."""

    def __init__(self, months: int = 3, workers: int = 1):
        if months <= 0:
            raise ValueError(f"months must be > 0, got {months}")
        if workers < 1:
            raise ValueError(f"workers must be >= 1, got {workers}")
        self.months, self.workers = months, workers
        self._conv = TimeConverter()

    def fetch(
        self,
        symbol: str | None = None,
        tfs: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "D"),
        symbols: list[str] | None = None,
    ) -> dict[str, list[Candle]]:
        if symbol is not None:
            targets = [symbol]
        elif symbols:
            targets = list(symbols)
        else:
            raise ValueError("Fetcher.fetch: pass symbol= or symbols=")

        if self.workers == 1 or len(targets) == 1:
            return {s: self.fetch_symbol(s, tfs=tfs) for s in targets}

        out: dict[str, list[Candle]] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futs = {pool.submit(self.fetch_symbol, s, tfs): s for s in targets}
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    out[sym] = fut.result()
                except Exception as e:
                    log.error("fetch failed  symbol=%s  err=%s", sym, e)
                    raise FetchError(f"fetch failed for {sym}: {e}") from e
        return out

    def fetch_symbol(
        self,
        symbol: str,
        tfs: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "D"),
    ) -> list[Candle]:
        candles: list[Candle] = []
        for tf in tfs:
            candles.extend(self._df_to_candles(self._fetch_df(symbol, tf), symbol, tf))
        return candles

    def _fetch_df(self, symbol: str, tf: str) -> pd.DataFrame:
        import MetaTrader5 as mt5
        if tf not in MT5_TIMEFRAME:
            raise ValueError(f"unsupported tf {tf!r}, known: {sorted(MT5_TIMEFRAME)}")

        self._ensure_symbol(mt5, symbol)
        self._prime_history(mt5, symbol, tf)
        start, end = self._window()

        log.info("fetch start  symbol=%s  tf=%-3s  months=%d", symbol, tf, self.months)

        rates = mt5.copy_rates_range(
            symbol, getattr(mt5, MT5_TIMEFRAME[tf]),
            self._to_dt(start), self._to_dt(end),
        )
        if rates is None:
            log.error("fetch FAIL   symbol=%s  tf=%s  last_error=%s",
                      symbol, tf, mt5.last_error())
            raise FetchError(f"copy_rates_range None for {symbol} {tf}: "
                             f"last_error={mt5.last_error()}")
        if len(rates) == 0:
            log.error("fetch EMPTY  symbol=%s  tf=%s  months=%d",
                      symbol, tf, self.months)
            raise FetchError(f"0 bars for {symbol} {tf}. Open chart, scroll back "
                             f"{self.months} months, retry.")

        log.info("fetch done   symbol=%s  tf=%-3s  bars=%d",
                 symbol, tf, len(rates))

        df = pd.DataFrame(rates)
        df["unix_time"] = df["time"].astype("int64")
        df = (df[["unix_time","open","high","low","close","tick_volume"]]
                .sort_values("unix_time").reset_index(drop=True))
        df.insert(0, "index", df.index)
        return df

    def _df_to_candles(self, df, symbol, tf):
        unixes = df["unix_time"].astype("int64").to_numpy()
        utc_idx = pd.to_datetime(unixes, unit="s", utc=True)
        utc_dt  = utc_idx.to_pydatetime()
        ny_dt   = utc_idx.tz_convert(self._conv.NY).to_pydatetime()
        return [
            Candle(index=int(i), open_time=u, symbol=symbol, timeframe=tf,
                   unix_time=int(x), utc_time=u, ny_time=n,
                   open=float(o), high=float(h), low=float(l), close=float(c),
                   tick_volume=int(v), source_indices=())
            for i, x, u, n, o, h, l, c, v in zip(
                df["index"].to_numpy(), unixes, utc_dt, ny_dt,
                df["open"].to_numpy(), df["high"].to_numpy(),
                df["low"].to_numpy(), df["close"].to_numpy(),
                df["tick_volume"].to_numpy())
        ]

    def _ensure_symbol(self, mt5, symbol: str) -> None:
        info = mt5.symbol_info(symbol)
        if info is None:
            log.error("symbol not found  symbol=%s", symbol)
            raise FetchError(f"Symbol {symbol!r} not found — case-sensitive.")
        if not info.visible and not mt5.symbol_select(symbol, True):
            log.error("symbol_select failed  symbol=%s  last_error=%s",
                      symbol, mt5.last_error())
            raise FetchError(f"MT5 could not add {symbol}: {mt5.last_error()}")

    def _prime_history(self, mt5, symbol: str, tf: str) -> None:
        n = (self.months * 30 * 24 * 60) // TF_MINUTES[tf] + 5_000
        _ = mt5.copy_rates_from_pos(symbol, getattr(mt5, MT5_TIMEFRAME[tf]), 0, n)

    def _window(self) -> tuple[int, int]:
        end = int(time.time())
        return end - self.months * MONTH_S, end

    @staticmethod
    def _to_dt(epoch: int) -> datetime:
        return datetime.fromtimestamp(epoch, tz=timezone.utc)


class LiveFeed:
    """
    Polls MT5 for the last *closed* bar of each subscription and pushes it
    to the subscriber callback. Dedupes by unix_time per (symbol, tf).
    """

    def __init__(self, fetcher: Fetcher, poll_interval_s: float = 1.0):
        self.fetcher = fetcher
        self.poll_interval_s = poll_interval_s
        self._conv = fetcher._conv
        self._last_unix: dict[tuple[str, str], int] = {}
        self._subs: list[tuple[str, str, Callable[[Candle], None]]] = []
        self._last_poll_ts = 0.0
        self._attached = False

    def seed(self, window, symbol: str, tf: str,
             raw: dict[str, list[Candle]] | None = None) -> None:
        if raw is None:
            raw = self.fetcher.fetch(symbol=symbol, tfs=(tf,))
        bars = raw.get(symbol) or []
        window.seed([c for c in bars if c.timeframe == tf])
        if bars:
            self._last_unix[(symbol, tf)] = bars[-1].unix_time
            log.info("seed         symbol=%s  tf=%-3s  bars=%d  last_unix=%d",
                     symbol, tf, len(bars), bars[-1].unix_time)

    def seed_all(self, windows: dict[tuple[str, str], object],
                 raw: dict[str, list[Candle]]) -> None:
        for (sym, tf), window in windows.items():
            self.seed(window, sym, tf, raw=raw)

    def subscribe(self, symbol: str, tf: str,
                  on_bar: Callable[[Candle], None]) -> None:
        self._subs.append((symbol, tf, on_bar))
        log.info("subscribe    symbol=%s  tf=%-3s  total_subs=%d",
                 symbol, tf, len(self._subs))

    def attach(self, conn) -> None:
        if self._attached:
            return
        conn.on_tick(self.poll_once)
        self._attached = True
        log.info("attach       conn.on_tick(poll_once)  subscriptions=%d",
                 len(self._subs))

    def poll_once(self, force: bool = False) -> None:
        import MetaTrader5 as mt5
        now = time.time()
        if not force and (now - self._last_poll_ts) < self.poll_interval_s:
            return
        self._last_poll_ts = now
        for symbol, tf, on_bar in self._subs:
            rates = mt5.copy_rates_from_pos(
                symbol, getattr(mt5, MT5_TIMEFRAME[tf]), 0, 2)
            if rates is None or len(rates) < 2:
                log.debug("poll skip    symbol=%s  tf=%-3s  (no closed bar yet)",
                          symbol, tf)
                continue
            r = rates[-2]
            unix = int(r["time"])
            key = (symbol, tf)
            if self._last_unix.get(key, 0) >= unix:
                continue
            self._last_unix[key] = unix
            candle = self._bar_from(r, symbol, tf)
            log.info("live bar     symbol=%s  tf=%-3s  close=%.5f  unix=%d",
                     symbol, tf, candle.close, unix)
            on_bar(candle)

    def _bar_from(self, r, symbol: str, tf: str) -> Candle:
        unix = int(r["time"])
        utc = self._conv.to_utc(unix)
        return Candle(
            index=-1, open_time=utc, symbol=symbol, timeframe=tf,
            unix_time=unix, utc_time=utc, ny_time=self._conv.to_ny(unix),
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]),  close=float(r["close"]),
            tick_volume=int(r["tick_volume"]), source_indices=())