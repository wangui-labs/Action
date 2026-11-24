import logging
import threading

from src.interface.connection import Connection
from src.interface.marketwatch import MarketWatch
from src.interface.account import Account
from src.interface.position import Position
from src.interface.order import Order

from src.pipeline.access import bootstrap
from src.analysis.analysis import Analysis
from src.worker.stop_loss import StopLossWorker


log = logging.getLogger(__name__)


def _safe_on_bar(analysis, symbol, tf, candle):
    """Never let a strategy exception kill conn.run_loop()."""
    try:
        analysis.on_bar(symbol, tf, candle)
    except Exception:
        log.exception("analysis.on_bar failed  symbol=%s  tf=%s", symbol, tf)


# ── Stage 1: connection (the ONLY file that touches mt5.initialize) ──
conn = Connection()
conn._startup()

# ── Stage 2: interface objects ─────────────────────────────────
mw    = MarketWatch()          # stateless — reads mt5 directly, no conn needed
acc   = Account()              # stateless cache
pos   = Position()             # stateless cache
order = Order()                # pure executor

# ── Stage 3: data ingest ───────────────────────────────────────
layer = bootstrap(conn, mw, symbols=["XAUUSDm"], months=3, depth=500)

# ── Stage 4: analysis ──────────────────────────────────────────
analysis = Analysis(layer.md, layer.windows)
analysis.order = order
for (sym, tf) in list(layer.windows.keys()):
    layer.feed.subscribe(
        sym, tf,
        lambda c, s=sym, t=tf: _safe_on_bar(analysis, s, t, c),
    )

# ── Stage 5: wire refreshes to the loop ────────────────────────
conn.on_tick(pos.refresh)
conn.on_tick(acc.refresh)
conn.on_tick(acc.print_status)

# ── Stage 6: workers ───────────────────────────────────────────
stop = threading.Event()
sl = StopLossWorker.start(mw, stop)

# ── Stage 7: run ───────────────────────────────────────────────
print(acc.status_line())
try:
    conn.run_loop()
except KeyboardInterrupt:
    pass
finally:
    conn.disconnect()