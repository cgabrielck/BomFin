# Trading UI Module

Streamlit trading view. It browses the paper ledger and does not start the worker or place orders. Order actions stay on the Desk shell (FastAPI + `web/static`). This module provides interfaces for:
1. Viewing account summary (cash, buying power, positions).
2. Simulating orders via the Shadow Trading engine.
3. Reviewing the **L2** `OrderStore` ledger (`backend/trading/storage.py`). This is **not** ADR-003 IntentStore / Intent v0.
4. Running manual reconciliation against the broker.

It is currently integrated into the main `backend/app.py` via the sidebar.
