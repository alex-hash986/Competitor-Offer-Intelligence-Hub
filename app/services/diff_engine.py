from app.models import PageSnapshot


def compare_snapshots(old_snap: PageSnapshot, new_snap: PageSnapshot) -> list[dict]:
    changes = []

    def add(change_type, severity, summary, **details):
        changes.append(dict(change_type=change_type, severity=severity,
                            summary=summary, diff_details=details))

    old, new = old_snap.min_price, new_snap.min_price
    if old is not None and new is not None and old != new and old_snap.currency == new_snap.currency:
        delta = new - old
        currency = new_snap.currency
        add("price_drop" if delta < 0 else "price_hike", "high" if delta < 0 else "medium",
            f"Минимальная цена: {old:g} → {new:g} {currency}",
            old=old, new=new, delta=round(delta, 2), absolute_delta=round(abs(delta), 2),
            percent_delta=round(delta / old * 100, 2) if old else None, currency=currency)

    if old_snap.h1_text != new_snap.h1_text:
        add("h1_change", "high", "Изменился главный заголовок", old=old_snap.h1_text, new=new_snap.h1_text)

    for field, kind, severity, summary in (
        ("cta_buttons", "cta_change", "medium", "Изменились призывы к действию"),
        ("trust_signals", "trust_update", "medium", "Изменились сигналы доверия"),
        ("lead_magnets", "offer_pivot", "low", "Изменились лид-магниты и условия входа"),
    ):
        before = {item.casefold(): item for item in getattr(old_snap, field) or []}
        after = {item.casefold(): item for item in getattr(new_snap, field) or []}
        added = [after[key] for key in after.keys() - before.keys()]
        removed = [before[key] for key in before.keys() - after.keys()]
        if added or removed:
            add(kind, severity, summary, added=sorted(added), removed=sorted(removed))
    return changes
