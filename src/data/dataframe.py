"""
Simple MT5 → DataFrame pull for a single symbol / timeframe / date window.

Output schema (index = time_ny):
    candle_id   : C(n)   -- 1-based, chronological, stable
    time_ny     : tz-aware DatetimeIndex in America/New_York
    open, high, low, close, tick_volume, spread, real_volume
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd
import MetaTrader5 as mt5

# --- config import -------------------------------------------------
from src.config.mt5_config import (
    MT5_CONFIG,
    SYMBOL,
    TIMEFRAME,
    START_DATE,
    END_DATE,
    CHUNK_DAYS,
    SERVER_TZ,
    TARGET_TZ,
)

# ------------------------------------------------------------------
# MT5 timeframe map
# ------------------------------------------------------------------
_TF_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}


# ------------------------------------------------------------------
# Connection helpers
# ------------------------------------------------------------------
def init_mt5() -> None:
    """Initialise (or attach to) the MT5 terminal."""
    kwargs = {k: v for k, v in MT5_CONFIG.items() if v is not None}
    if not mt5.initialize(**kwargs):
        code, msg = mt5.last_error()
        raise RuntimeError(f"MT5 initialize() failed [{code}] {msg}")

    info = mt5.account_info()
    if info is None:
        mt5.shutdown()
        raise RuntimeError("MT5 initialised but no account info available.")


def shutdown_mt5() -> None:
    mt5.shutdown()


# ------------------------------------------------------------------
# Core pull
# ------------------------------------------------------------------
def _pull_chunk(symbol: str, tf, dt_from: datetime, dt_to: datetime) -> pd.DataFrame:
    """Pull one chunk of bars and return a raw DataFrame (server tz, naive)."""
    rates = mt5.copy_rates_range(symbol, tf, dt_from, dt_to)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    # MT5 'time' is seconds since epoch in *server* time → to datetime
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def pull_rates(
    symbol: str = SYMBOL,
    timeframe: str = TIMEFRAME,
    start: str = START_DATE,
    end: str = END_DATE,
    chunk_days: int = CHUNK_DAYS,
) -> pd.DataFrame:
    """
    Pull bars for [start, end] inclusive, chunked, deduped, and
    normalised into the canonical DataFrame schema.
    """
    if timeframe not in _TF_MAP:
        raise ValueError(f"Unsupported timeframe {timeframe!r}")

    tf = _TF_MAP[timeframe]

    # Inclusive date window → datetime bounds
    dt_start = datetime.fromisoformat(start)
    dt_end   = datetime.fromisoformat(end) + timedelta(days=1) - timedelta(seconds=1)

    frames: list[pd.DataFrame] = []
    cursor = dt_start
    while cursor <= dt_end:
        chunk_end = min(cursor + timedelta(days=chunk_days), dt_end)
        chunk_df = _pull_chunk(symbol, tf, cursor, chunk_end)
        if not chunk_df.empty:
            frames.append(chunk_df)
        cursor = chunk_end + timedelta(seconds=1)
        time.sleep(0.05)  # be polite to the server

    if not frames:
        raise RuntimeError(
            f"No bars returned for {symbol} {timeframe} "
            f"{start} → {end}. Check symbol name / history availability."
        )

    df = pd.concat(frames, ignore_index=True)

    # Dedup (chunk boundaries can overlap)
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)

    # --- timezone chain: server → UTC → New York -------------------
    # NOTE: mt5 returns bar time as broker-server time. Tag as SERVER_TZ,
    # then convert. If your broker is not Etc/UTC, change SERVER_TZ in
    # mt5_config.py (Europe/Athens is a common one).
    df["time"] = (
        df["time"]
        .dt.tz_localize(SERVER_TZ, ambiguous="NaT", nonexistent="shift_forward")
        .dt.tz_convert(TARGET_TZ)
    )

    # --- candle id C(n) -------------------------------------------
    # 1-based, chronological, stable across re-pulls of same range.
    df.insert(0, "candle_id", range(1, len(df) + 1))

    # --- rename / select canonical schema -------------------------
    out = (
        df.rename(columns={"time": "time_ny"})
          [["candle_id", "time_ny",
            "open", "high", "low", "close",
            "tick_volume", "spread", "real_volume"]]
    )

    # Set index and coerce to DatetimeIndex so Pylance sees a typed
    # index with a .tz attribute (set_index returns Index[Any]).
    out = out.set_index("time_ny", drop=True)
    out.index = pd.DatetimeIndex(out.index)
    out.index.name = "time_ny"

    return out


# ------------------------------------------------------------------
# Convenience: single call that manages the MT5 lifecycle
# ------------------------------------------------------------------
def load_m1_august_2026() -> pd.DataFrame:
    """One-shot helper for the 2026-08-02 → 2026-08-29 window."""
    init_mt5()
    try:
        return pull_rates()
    finally:
        shutdown_mt5()


# ------------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------------
if __name__ == "__main__":
    df = load_m1_august_2026()
    print(df.head())
    print(df.tail())
    print(f"rows={len(df):,}  cols={list(df.columns)}")
    print(f"index tz: {df.index.tz}")