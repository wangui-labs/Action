# src/interface/order.py
"""
order.py — pure MT5 order sender. No checks, no strategy, no connection.

Two jobs:
    send(request)  → mt5.order_send(request)   — any of the 8 MT5 order types
    cancel(ticket) → mt5.order_send({REMOVE})  — remove a pending order

Caller (analysis.py / main.py) builds the full MT5 request dict.
This class forwards it and returns the raw OrderSendResult.
"""
from __future__ import annotations

import MetaTrader5 as mt5


class Order:
    """Thin MT5 order sender. send() and cancel(). Nothing else."""

    def send(self, request: dict):
        """Forward `request` to mt5.order_send(). Returns raw OrderSendResult."""
        return mt5.order_send(request)

    def cancel(self, ticket: int):
        """Remove a pending order by ticket. Returns raw OrderSendResult."""
        return mt5.order_send({
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(ticket),
        })


__all__ = ["Order"]