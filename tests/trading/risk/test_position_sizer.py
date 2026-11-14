from backend.trading.risk.position_sizer import (
    auto_kelly_sizer_enabled,
    cap_shares_to_notional,
    kelly_fraction,
    position_size_dollars,
    quantity_after_kelly_gate,
    shares_to_buy,
)


def test_cap_shares_floors_to_notional_limit():
    # 33 * 349.4 = 11,530.2 > 10_000 → 28 shares * 349.4 = 9,783.2
    assert cap_shares_to_notional(33, 349.4, 10_000) == 28


def test_cap_shares_leaves_small_orders():
    assert cap_shares_to_notional(10, 200.0, 10_000) == 10


def test_cap_shares_zero_when_one_share_too_expensive():
    assert cap_shares_to_notional(5, 12_000.0, 10_000) == 0


def test_kelly_helpers_remain_but_default_qty_ignores_them(monkeypatch):
    monkeypatch.delenv("CGAB_AUTO_KELLY_SIZER", raising=False)
    assert auto_kelly_sizer_enabled() is False
    fraction = kelly_fraction(0.55, 0.08, 0.04, kelly_fraction_scale=0.5, max_fraction=0.25)
    assert fraction > 0
    assert position_size_dollars(100_000, 0.55, 0.08, 0.04) == 100_000 * fraction
    kelly_qty = shares_to_buy(
        100_000, 100, 0.55, 0.08, 0.04, kelly_fraction_scale=0.5, max_fraction=0.25
    )
    assert kelly_qty > 0
    assert quantity_after_kelly_gate(500, kelly_qty, use_kelly=False) == 500
    assert quantity_after_kelly_gate(500, kelly_qty, use_kelly=True) == min(500, kelly_qty)


def test_kelly_flag_opt_in(monkeypatch):
    monkeypatch.setenv("CGAB_AUTO_KELLY_SIZER", "1")
    assert auto_kelly_sizer_enabled() is True
