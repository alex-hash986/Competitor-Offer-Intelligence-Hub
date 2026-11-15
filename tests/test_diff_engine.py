import pytest

from app.models import PageSnapshot
from app.services.diff_engine import compare_snapshots


def snapshot(**overrides):
    defaults = dict(min_price=100, currency="RUB", h1_text="Old", cta_buttons=["Demo"],
                    trust_signals=["Кейсы"], lead_magnets=[])
    return PageSnapshot(**(defaults | overrides))


@pytest.mark.parametrize(("price", "kind", "severity", "delta"), [
    (80, "price_drop", "high", -20), (125, "price_hike", "medium", 25),
])
def test_price_change(price, kind, severity, delta):
    change, = compare_snapshots(snapshot(), snapshot(min_price=price))
    assert change["change_type"] == kind
    assert change["severity"] == severity
    assert change["diff_details"]["percent_delta"] == delta
    assert change["diff_details"]["absolute_delta"] == abs(delta)


def test_offer_changes():
    changes = {change["change_type"]: change for change in compare_snapshots(
        snapshot(), snapshot(h1_text="New", cta_buttons=["Купить"], trust_signals=["Кейсы", "Отзывы"],
                             lead_magnets=["Триал"])
    )}
    assert changes["h1_change"]["diff_details"] == {"old": "Old", "new": "New"}
    assert changes["cta_change"]["diff_details"] == {"added": ["Купить"], "removed": ["Demo"]}
    assert changes["trust_update"]["diff_details"] == {"added": ["Отзывы"], "removed": []}
    assert changes["offer_pivot"]["severity"] == "low"
    assert compare_snapshots(snapshot(), snapshot()) == []


def test_price_comparison_requires_shared_currency():
    assert compare_snapshots(snapshot(), snapshot(min_price=20, currency="USD")) == []
    alert, = compare_snapshots(snapshot(min_price=0), snapshot())
    assert alert["diff_details"]["percent_delta"] is None
