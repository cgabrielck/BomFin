"""
Trading Dashboard UI — v2

New in v2:
  - Strategy selector (Stable / Aggressive / Hybrid)
  - Worker start/stop toggle with live status indicator
  - Auto-trade panel showing last signal summary
  - Position table with trailing stop and P&L
  - All existing manual signal injection and ledger preserved
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from backend.trading.broker import BrokerAdapter
from backend.trading.engine.order_manager import OrderStore
from backend.trading.models import OrderStatus
from backend.trading.performance.display import build_trust_status
from backend.trading.reconciliation.service import ReconciliationService
from backend.trading.strategies.registry import STRATEGY_REGISTRY
from backend.i18n import t
from backend.utils.constants import DATA_DIR


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------

def _status_pill(status: OrderStatus) -> str:
    label = status.value.replace("_", " ").upper()
    return f'<span class="status-pill st-{status.value}">{label}</span>'


def _empty_state(icon: str, title: str, desc: str = "") -> None:
    st.markdown(
        f"<div class='empty-state'><div class='empty-icon'>{icon}</div>"
        f"<div>{html.escape(title)}</div>"
        + (f"<div style='margin-top:.25rem;font-size:.74rem;'>{html.escape(desc)}</div>" if desc else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def _dot(color: str) -> str:
    return f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};box-shadow:0 0 6px {color};margin-right:.4rem;'></span>"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_paper_book_status() -> Dict[str, Any]:
    """Read the broker paper book under backend/data/, not the Kelly data/ book."""
    root = Path(DATA_DIR)
    paper = _read_json(root / "performance_paper.json")
    heartbeat = _read_json(root / "worker_heartbeat.json")
    return build_trust_status(paper, heartbeat)


def render_paper_book_status(lang: str = "zh_tw") -> None:
    """Seal, session card, and freshness for the backend/data paper ledger."""
    status = load_paper_book_status()
    fresh = status.get("freshness") or {}
    session = status.get("session_card") or {}
    st.markdown(f"### {t('trading.perf.title', lang)}")
    st.caption(t("trading.perf.books", lang))
    if fresh.get("stale"):
        age = fresh.get("age_days")
        age_txt = "—" if age is None else str(age)
        st.warning(t("trading.perf.outdated", lang, days=age_txt, threshold=fresh.get("stale_after_days", 7)))
    else:
        st.caption(t("trading.perf.fresh", lang, generated=status.get("generated_at") or "—"))

    c1, c2, c3, c4 = st.columns(4)
    if status.get("claims_allowed"):
        total = status.get("total_return_pct")
        spy = status.get("spy_return_pct")
        beats = status.get("beats_spy_net")
        c1.metric(t("trading.perf.total_return", lang), "n/a" if total is None else f"{total:+.2f}%")
        c2.metric(t("trading.perf.vs_spy", lang), "n/a" if spy is None else f"{spy:+.2f}%")
        c3.metric(
            t("trading.perf.beats_spy", lang),
            "YES" if beats is True else ("NO" if beats is False else "n/a"),
        )
        c4.metric(t("trading.perf.annualized", lang), status.get("annualized_label") or "n/a")
    else:
        c1.metric(t("trading.perf.total_return", lang), "n/a")
        c2.metric(t("trading.perf.vs_spy", lang), "n/a")
        c3.metric(t("trading.perf.beats_spy", lang), "n/a")
        c4.metric(t("trading.perf.annualized", lang), "n/a")
        st.info(t("trading.perf.withheld", lang, reason=status.get("reason") or "trades/days below min"))

    seal_txt = "pass" if status.get("seal_passed") else "fail"
    st.caption(t("trading.perf.seal", lang, state=seal_txt, trades=status.get("num_trades") if status.get("num_trades") is not None else "—"))
    if session.get("available"):
        st.caption(
            t(
                "trading.perf.session",
                lang,
                seal=str(bool(session.get("seal"))).lower(),
                not_a_seal=str(bool(session.get("not_a_seal"))).lower(),
                claims=str(bool(session.get("claims_beat_spy"))).lower(),
            )
        )
    else:
        st.caption(t("trading.perf.session_missing", lang))
    why = status.get("why_no_trade_summary") or ""
    st.caption(t("trading.perf.why", lang, summary=why or "—"))


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_trading_dashboard(
    broker: BrokerAdapter,
    store: OrderStore,
    reconciler: ReconciliationService,
    lang: str = "zh_tw",
) -> None:

    # ── Header ──────────────────────────────────────────────────────────────
    st.markdown(
        f"<div class='brand-kicker'>{t('nav.trading', lang)}</div>"
        f"<p class='app-title' style='font-size:1.55rem;margin-bottom:.2rem;'>{t('trading.title', lang)}</p>"
        f"<p class='app-subtitle' style='margin-bottom:1.1rem;'>{t('trading.subtitle', lang)}</p>",
        unsafe_allow_html=True,
    )

    banner_text = t("trading.mode.browse", lang)
    st.markdown(
        f"<div class='trading-banner paper'>"
        f"<span class='banner-dot'></span>{html.escape(banner_text)}</div>",
        unsafe_allow_html=True,
    )
    st.warning(t("trading.dual_book", lang))
    render_paper_book_status(lang)

    # ── Tab layout ───────────────────────────────────────────────────────────
    tab_auto, tab_manual, tab_ledger, tab_reconcile = st.tabs([
        "🤖 " + t("trading.tab.auto", lang),
        "✍️ " + t("trading.tab.manual", lang),
        "📋 " + t("trading.tab.ledger", lang),
        "🔍 " + t("trading.tab.reconcile", lang),
    ])

    # ── Fetch account once ───────────────────────────────────────────────────
    summary = None
    try:
        summary = broker.get_account_summary()
    except Exception as e:
        st.error(t("trading.account.error", lang, msg=str(e)))

    # ====================================================================
    # TAB 1: AUTO TRADING
    # ====================================================================
    with tab_auto:
        _render_auto_tab(broker, store, reconciler, summary, lang)

    # ====================================================================
    # TAB 2: MANUAL SIGNAL INJECTION
    # ====================================================================
    with tab_manual:
        _render_manual_tab(broker, store, summary, lang)

    # ====================================================================
    # TAB 3: ORDER LEDGER
    # ====================================================================
    with tab_ledger:
        _render_ledger_tab(store, lang)

    # ====================================================================
    # TAB 4: RECONCILIATION
    # ====================================================================
    with tab_reconcile:
        _render_reconcile_tab(reconciler, summary, lang)


# ---------------------------------------------------------------------------
# Auto-trading tab
# ---------------------------------------------------------------------------

def _render_auto_tab(broker, store, reconciler, summary, lang: str) -> None:
    del broker, store, reconciler
    st.markdown(f"### {t('trading.section.account', lang)}")

    # Account metrics
    if summary:
        col1, col2, col3 = st.columns(3)
        col1.metric(t("trading.metric.portfolio_value", lang), f"${summary.portfolio_value:,.2f}")
        col2.metric(t("trading.metric.cash", lang),            f"${summary.cash:,.2f}")
        col3.metric(t("trading.metric.buying_power", lang),    f"${summary.buying_power:,.2f}")

    st.divider()

    # ── Strategy selector ────────────────────────────────────────────────
    st.markdown(f"### 🎯 {t('trading.section.strategy', lang)}")

    strategy_options = {sid: strat.display_name for sid, strat in STRATEGY_REGISTRY.items()}
    selected_strategy = st.selectbox(
        t("trading.strategy.select", lang),
        options=list(strategy_options.keys()),
        format_func=lambda k: strategy_options[k],
        index=0,
        key="trading_strategy_select",
    )

    strat = STRATEGY_REGISTRY[selected_strategy]
    col_r, col_wl = st.columns(2)
    col_r.metric("预期胜率 Win Rate",   f"{strat.expected_win_rate*100:.0f}%")
    col_wl.metric("风险档位 Risk Profile", strat.risk_profile.upper())

    strategy_descriptions = {
        "stable": "均值回归 · 只买超跌优质股 (RSI<32 + BB下轨 + 基本面>65) · 目标胜率62%",
        "aggressive": "VCP突破 · Minervini形态 + 放量突破 + SMA50确认 · 目标胜率44%，盈亏比2.6",
        "hybrid": "混合型 · 稳健信号优先，无信号时触发激进策略扫描",
    }
    st.caption(strategy_descriptions.get(selected_strategy, ""))

    st.divider()

    # Worker start stays off in this shell. Orders below are a read-only mirror.
    st.markdown(f"### ⚙️ {t('trading.section.worker', lang)}")
    st.caption(t("trading.worker.start_disabled", lang))
    st.button(
        t("trading.worker.start", lang),
        type="primary",
        disabled=True,
        width="stretch",
        key="worker_start_btn",
    )
    st.button(
        t("trading.worker.stop", lang),
        type="secondary",
        disabled=True,
        width="stretch",
        key="worker_stop_btn",
    )

    st.divider()

    # ── Last signal summary ──────────────────────────────────────────────
    st.markdown(f"### 📊 {t('trading.section.last_signals', lang)}")
    _empty_state("🔍", t("trading.signals.empty", lang), t("trading.signals.empty_desc", lang))

    if summary and summary.positions:
        st.divider()
        st.markdown(f"### {t('trading.positions.title', lang)}")
        for p in summary.positions:
            st.markdown(
                "<div class='rec-card' style='padding:.65rem .85rem;min-height:0;margin-bottom:.4rem;"
                "display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;'>"
                f"<span style='font-family:var(--mono);font-weight:800;color:var(--text);font-size:.95rem;'>{html.escape(p.symbol)}</span>"
                f"<span style='font-family:var(--mono);font-size:.75rem;color:var(--muted);'>{p.quantity} @ ${p.average_entry_price:,.2f}</span>"
                "</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Manual signal tab  (preserved from v1)
# ---------------------------------------------------------------------------

def _render_manual_tab(broker, store, summary, lang: str) -> None:
    """Ticket fields stay visible. Submit cannot place an order from this shell."""
    del broker, store, summary
    st.markdown(f"### {t('trading.section.signal', lang)}")
    st.caption(t("trading.signal.disabled", lang))

    with st.form("signal_injection_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input(t("trading.signal.symbol", lang), value="AAPL", disabled=True)
            st.selectbox(
                t("trading.signal.side", lang),
                ["buy", "sell"],
                format_func=lambda v: t(f"trading.signal.side.{v}", lang),
                disabled=True,
            )
            st.number_input(t("trading.signal.quantity", lang), min_value=1, value=1, step=1, disabled=True)
        with col2:
            st.selectbox(
                t("trading.signal.order_type", lang),
                ["limit", "market"],
                format_func=lambda v: t(f"trading.signal.order_type.{v}", lang),
                disabled=True,
            )
            st.number_input(
                t("trading.signal.limit_price", lang),
                min_value=0.0,
                value=150.0,
                step=0.5,
                disabled=True,
            )
            st.checkbox(t("trading.signal.shadow_mode", lang), value=True, disabled=True)

        st.form_submit_button(
            t("trading.signal.submit", lang),
            type="primary",
            width="stretch",
            disabled=True,
        )


# ---------------------------------------------------------------------------
# Ledger tab
# ---------------------------------------------------------------------------

def _render_ledger_tab(store, lang: str) -> None:
    hdr_col, btn_col = st.columns([3, 1])
    with hdr_col:
        st.markdown(f"### {t('trading.section.ledger', lang)}")
    with btn_col:
        st.button(t("trading.ledger.refresh", lang), width="stretch", key="trading_refresh_ledger")

    try:
        recent = store.get_recent_orders(limit=30) if hasattr(store, "get_recent_orders") else []
        if recent:
            for o in recent:
                side_color = "var(--green)" if o.side.value == "buy" else "var(--red)"
                price_txt  = f"${o.limit_price:,.2f}" if o.limit_price else t("trading.signal.order_type.market", lang)
                note       = f" · {html.escape(str(o.error_message)[:80])}" if o.error_message else ""
                st.markdown(
                    "<div class='rec-card' style='padding:.65rem .85rem;min-height:0;margin-bottom:.45rem;"
                    "display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;'>"
                    "<div style='display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;'>"
                    f"<span style='font-family:var(--mono);font-weight:800;color:var(--text);font-size:.95rem;'>{html.escape(o.symbol)}</span>"
                    f"<span style='font-family:var(--mono);font-size:.68rem;font-weight:700;color:{side_color};'>{o.side.value.upper()}</span>"
                    f"<span style='font-family:var(--mono);font-size:.72rem;color:var(--muted);'>{o.quantity} @ {html.escape(price_txt)}</span>"
                    "</div>"
                    "<div style='display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;'>"
                    f"{_status_pill(o.status)}"
                    f"<span style='font-family:var(--mono);font-size:.64rem;color:var(--faint);'>{o.created_at.strftime('%m-%d %H:%M')} UTC</span>"
                    "</div></div>",
                    unsafe_allow_html=True,
                )
                if note:
                    st.caption(note.lstrip(" ·"))
        else:
            _empty_state("🗒️", t("trading.ledger.empty", lang), t("trading.ledger.empty_desc", lang))
    except Exception as e:
        st.error(t("trading.ledger.load_error", lang, msg=str(e)))


# ---------------------------------------------------------------------------
# Reconciliation tab
# ---------------------------------------------------------------------------

def _render_reconcile_tab(reconciler, summary, lang: str) -> None:
    st.markdown(f"### {t('trading.section.reconciliation', lang)}")
    st.caption(t("trading.reconciliation.desc", lang))
    if st.button(t("trading.reconciliation.run", lang), width="stretch", key="trading_run_reconciliation"):
        with st.spinner(t("trading.reconciliation.running", lang)):
            local_positions = summary.positions if summary else []
            report = reconciler.reconcile_positions(local_positions)
            if report.is_match:
                st.success(f"✅ {t('trading.reconciliation.match', lang)}")
            else:
                st.error(f"❌ {t('trading.reconciliation.mismatch', lang)}")
                for d in report.discrepancies:
                    st.warning(d)
