"""Desk Operate chrome: quieter tokens, no purple brand on the product shell."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "web" / "static" / "index.html"


def _style(html: str) -> str:
    start = html.find("<style>")
    end = html.find("</style>")
    assert start >= 0 and end > start
    return html[start:end]


def test_purple_token_stays_unused_on_chrome():
    style = _style(INDEX.read_text(encoding="utf-8"))
    assert style.count("#7c6cff") == 1
    assert "--purple:#7c6cff" in style.replace(" ", "")
    assert "var(--purple)" not in style
    assert "radial-gradient" not in style
    assert "linear-gradient" not in style
    assert "box-shadow" not in style
    assert "backdrop-filter" not in style
    assert "background:var(--bg)" in style.replace(" ", "")
    assert ".mark{width:28px;height:28px;border-radius:9px;background:var(--cyan);}" in style.replace(" ", "").replace("\n", "")
    assert ".purple{background:var(--cyan);color:#052226;}" in style.replace(" ", "").replace("\n", "")
    assert ".help-fab" in style
    fab = style[style.find(".help-fab") : style.find(".help-fab .fab-ico")]
    assert "var(--cyan)" in fab
    assert "box-shadow" not in fab


def test_zone_tint_lock_unchanged():
    html = INDEX.read_text(encoding="utf-8")
    assert 'neutral: {fill:"rgba(120, 150, 165, 0.22)", stroke:"rgba(160, 185, 195, 0.55)"}' in html
    assert 'support: {fill:"rgba(62, 224, 160, 0.22)", stroke:"rgba(62, 224, 160, 0.70)"}' in html
    assert 'resist: {fill:"rgba(255, 107, 129, 0.22)", stroke:"rgba(255, 107, 129, 0.70)"}' in html
    assert "人手價區。角色標籤只是標籤，不是訊號。" in html
