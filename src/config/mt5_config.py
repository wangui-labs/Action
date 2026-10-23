"""
MT5 connection + data-pull configuration.
Keep all tunables here so the data module stays dumb.
"""
from pathlib import Path

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .../Action
DATA_DIR     = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# MT5 account / terminal
# ------------------------------------------------------------------
MT5_CONFIG = {
    # Leave login/password/server as None to attach to an already
    # logged-in terminal (recommended when using the GUI terminal).
    "login":    None,          # e.g. 12345678
    "password": None,          # e.g. "your_password"
    "server":   None,          # e.g. "MetaQuotes-Demo"
    "path":     None,          # optional path to terminal64.exe
    "timeout":  60_000,        # ms
    "portable": False,
}


# ------------------------------------------------------------------
# Symbol / timeframe / date window
# ------------------------------------------------------------------
SYMBOL     = "XAUUSDm"
TIMEFRAME  = "M1"            # MT5.TIMEFRAME_M1

# 1-month window you asked for
START_DATE = "2026-08-02"    # inclusive
END_DATE   = "2026-08-29"    # inclusive (end-of-day)

# Chunk the pull into blocks so we never hammer the server
CHUNK_DAYS = 7

# ------------------------------------------------------------------
# Timezones
# ------------------------------------------------------------------
# Server time is *usually* broker-specific (often GMT+2/+3).
# We do not assume — we read bar time as-is, tag it "server",
# convert to UTC, then to America/New_York.
SERVER_TZ  = "Etc/UTC"       # adjust if your broker feed differs
TARGET_TZ  = "America/New_York"