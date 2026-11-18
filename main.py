import threading

from src.interface.connection import Connection
from src.interface.marketwatch import MarketWatch
from src.interface.position import Position
from src.interface.account import Account
from src.interface.order import Order
from src.worker.stop_loss import StopLossWorker

conn = Connection()
conn._startup()
mw = MarketWatch(conn)
pos = Position(conn)
acc = Account(conn)
order = Order(conn, mw)

stop = threading.Event()

# Order's autonomous loop
threading.Thread(target=order.run_auto,
                 kwargs={"interval_s": 5.0, "stop_event": stop},
                 daemon=True).start()

# StopLossWorker — ONE line constructs + starts
sl = StopLossWorker.start(conn, pos, mw, order.c0, stop)

print(acc.status_line())
try:
    conn.run_loop()
finally:
    stop.set()