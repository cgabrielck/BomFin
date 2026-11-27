# S03/03c one-equity quote/bar smoke

Single-agent inline TDD; extends [03b runner](2026-11-25-gabfin-s03-03b-runner.md), Task 4. One fixed US.AAPL with QUOTE/K_DAY, no trading/history API/options or broad subscriptions.

- [x] Snapshot source/lock; test fake quote contexts before code.
- [x] Verify basicinfo code/stock_type=STOCK. Subscribe QUOTE/K_DAY once, push disabled. Read quote and at most two current D1 bars, AuType.NONE, normal session, no extended-time claim.
- [x] Return only symbol_verified, last_price/date/time and OHLC/provider_time strings plus capture UTC, latency unverified, fixed errors and cleanup status. SDK floats converted explicitly via Decimal(str), missing/nonfinite values stay null. No original precision/realtime/final-bar/native Instrument claim.
- [x] Wait at least 61 monotonic seconds after subscription success (sleep injected in tests), unsubscribe only this context's fixed symbol/types, verify own_used=0, close always. Failed subscription still attempts cleanup; timeout closes process and must be followed by metadata quota recheck after server minimum expiry.
- [x] Parent validates every output field, date/time/price shape and bounded record count. Preserve old metadata operation. Parent timeout 110s includes startup/hold/close; no blocking assistant tool waits over 60s.
- [x] Run bounded real localhost smoke, save only sanitized result, verify worker exit/quota separately, run app regression/build/preservation and update checkpoint. No real-time/session eligibility inferred from market-data API success.
