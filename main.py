import logging
import threading

from src.interface.connection import Connection
from src.interface.marketwatch import MarketWatch
from src.interface.account import Account
from src.interface.position import Position
from src.interface.order import Order

from src.pipeline.access import bootstrap
# from src.analysis.analysis import Analysis
from src.worker.stop_loss import StopLossWorker


log = logging.getLogger(__name__)


# ── Stage 1: connection (the ONLY file that touches mt5.initialize) ──
conn = Connection()
conn._startup()

# ── Stage 2: interface objects ─────────────────────────────────
mw    = MarketWatch(conn)      # read-only symbol metadata
acc   = Account()              # stateless cache
pos   = Position()             # stateless cache
order = Order()                # pure executor

# ── Stage 3: data ingest ───────────────────────────────────────
layer = bootstrap(conn, mw, symbols=["XAUUSDm"], months=3, depth=500)

# ── Stage 4: analysis (uncomment when ready) ───────────────────
# analysis = Analysis(layer.md, layer.windows)
# analysis.order = order
# for (sym, tf) in list(layer.windows.keys()):
#     layer.feed.subscribe(sym, tf,
#         lambda c, s=sym, t=tf: analysis.on_bar(s, t, c))

# ── Stage 5: wire refreshes to the loop ────────────────────────
conn.on_tick(pos.refresh)
conn.on_tick(acc.refresh)
conn.on_tick(acc.print_status)

# ── Stage 6: workers (uncomment when ready) ────────────────────
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