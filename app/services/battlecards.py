from collections import Counter
from statistics import mean, median

from sqlalchemy import func, select

from app.models import ChangeAlert, Competitor, PageSnapshot, TrackedPage
from app.services.scoring import CRITERIA


def market_rows(db):
    # Use the most recent active-page snapshot per player, with ID as tie-breaker.
    ranked = (select(
        TrackedPage.competitor_id.label("competitor_id"),
        PageSnapshot.id.label("snapshot_id"),
        func.row_number().over(
            partition_by=TrackedPage.competitor_id,
            order_by=(PageSnapshot.captured_at.desc(), PageSnapshot.id.desc()),
        ).label("rank"),
    ).join(TrackedPage, TrackedPage.id == PageSnapshot.page_id)
        .where(TrackedPage.is_active.is_(True)).subquery())
    return db.execute(
        select(Competitor, PageSnapshot)
        .outerjoin(ranked, (ranked.c.competitor_id == Competitor.id) & (ranked.c.rank == 1))
        .outerjoin(PageSnapshot, PageSnapshot.id == ranked.c.snapshot_id)
        .order_by(Competitor.id)
    ).all()


def overview(db):
    rows = market_rows(db)
    own_brand, own = next(((brand, snapshot) for brand, snapshot in rows if brand.is_own_brand),
                          (None, None))
    market = [snapshot for brand, snapshot in rows if not brand.is_own_brand and snapshot]
    price_rows = [(brand, snapshot) for brand, snapshot in rows if snapshot and snapshot.min_price is not None]
    currencies = Counter(snapshot.currency for brand, snapshot in price_rows if not brand.is_own_brand)
    currency = own.currency if own and own.min_price is not None else (
        currencies.most_common(1)[0][0] if currencies else None
    )
    prices = [snap.min_price for snap in market if snap.currency == currency and snap.min_price is not None]
    median_price = median(prices) if prices else None
    index = round(own.min_price / median_price * 100, 2) if own and own.min_price is not None and median_price else None
    counts = dict(db.execute(select(ChangeAlert.severity, func.count()).group_by(ChangeAlert.severity)).all())

    criteria = []
    if own and market:
        criteria = [
            dict(criterion=key, own=own.score_breakdown.get(key, 0),
                 market=round(mean(snap.score_breakdown.get(key, 0) for snap in market), 2))
            for key in CRITERIA
        ]

    return {
        "own_competitor_id": own_brand.id if own_brand else None,
        "own_cro_score": own.cro_score if own else None,
        "market_avg_cro_score": round(mean(snap.cro_score for snap in market), 2) if market else None,
        "own_min_price": own.min_price if own else None,
        "market_avg_min_price": round(mean(prices), 2) if prices else None,
        "market_median_min_price": median_price,
        "price_currency": currency,
        "price_index": index,
        "alerts_by_severity": {severity: counts.get(severity, 0) for severity in ("high", "medium", "low")},
        "radar_axes": list(CRITERIA),
        "radar": [dict(competitor_id=brand.id, name=brand.name, is_own_brand=brand.is_own_brand,
                       scores=snapshot.score_breakdown if snapshot else None)
                  for brand, snapshot in rows],
        "price_matrix": [
            dict(competitor_id=brand.id, name=brand.name, is_own_brand=brand.is_own_brand,
                 min_price=snap.min_price, max_price=snap.max_price, currency=snap.currency, cro_score=snap.cro_score)
            for brand, snap in price_rows
        ],
        "strengths": [result for result in criteria if result["own"] > result["market"]],
        "vulnerabilities": [result for result in criteria if result["own"] < result["market"]],
    }
