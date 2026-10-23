"""
Entry point for the Action project.

Run from the project root:
    python main.py
    python main.py --start 2026-08-02 --end 2026-08-29
    python main.py --save parquet
    python main.py --save csv --out data\my_pull.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.data.dataframe import (
    init_mt5,
    shutdown_mt5,
    pull_rates,
)
from src.config.mt5_config import (
    SYMBOL,
    TIMEFRAME,
    START_DATE,
    END_DATE,
    DATA_DIR,
)


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="action",
        description="MT5 data pull for the Action project.",
    )
    p.add_argument("--symbol",    default=SYMBOL,    help=f"MT5 symbol (default: {SYMBOL})")
    p.add_argument("--timeframe", default=TIMEFRAME, help=f"MT5 timeframe (default: {TIMEFRAME})")
    p.add_argument("--start",     default=START_DATE, help=f"Start date YYYY-MM-DD (default: {START_DATE})")
    p.add_argument("--end",       default=END_DATE,   help=f"End date   YYYY-MM-DD (default: {END_DATE})")
    p.add_argument("--save",      choices=["none", "csv", "parquet"], default="none",
                   help="Persist the DataFrame (default: none — in-memory only)")
    p.add_argument("--out",       default=None,
                   help="Output path when --save is used (auto-generated if omitted)")
    return p.parse_args(argv)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _default_out_path(symbol: str, timeframe: str, start: str, end: str, ext: str) -> Path:
    fname = f"{symbol.lower()}_{timeframe.lower()}_{start}_{end}.{ext}"
    return DATA_DIR / fname


def _save(df: pd.DataFrame, fmt: str, out: str | None, symbol: str,
          timeframe: str, start: str, end: str) -> Path:
    if out is None:
        path = _default_out_path(symbol, timeframe, start, end, fmt)
    else:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        df.to_csv(path, index=True)
    elif fmt == "parquet":
        df.to_parquet(path, index=True)
    else:
        raise ValueError(fmt)
    return path


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print(f"[main] {args.symbol} {args.timeframe}  "
          f"{args.start} → {args.end}")

    init_mt5()
    try:
        df = pull_rates(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
        )
    finally:
        shutdown_mt5()

    # --- summary ---------------------------------------------------
    # Coerce once so .tz is typed; Pylance accepts this everywhere.
    idx = pd.DatetimeIndex(df.index)

    print(f"[main] rows = {len(df):,}")
    print(f"[main] index tz = {idx.tz}")
    print(f"[main] first bar = {idx[0]}  (C(1))")
    print(f"[main] last  bar = {idx[-1]}  (C({len(df)}))")
    print(df.head(3))
    print("...")
    print(df.tail(3))

    # --- optional persistence -------------------------------------
    if args.save != "none":
        path = _save(df, args.save, args.out,
                     args.symbol, args.timeframe, args.start, args.end)
        print(f"[main] saved -> {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())