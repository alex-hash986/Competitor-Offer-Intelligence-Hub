from sqlalchemy import select, update

from app.models import ChangeAlert, PageSnapshot, TrackedPage
from app.services.diff_engine import compare_snapshots
from app.services.extractor import extract_offer_elements
from app.services.scoring import calculate_cro_score


def analyze(content, mode):
    extracted = extract_offer_elements(content, mode)
    score, breakdown = calculate_cro_score(extracted)
    return dict(**extracted, cro_score=score, score_breakdown=breakdown)


def save_snapshot(db, page_id, mode, extracted, *, captured_at=None):
    # Serialize writes for this page before reading its previous snapshot.
    locked = db.execute(
        update(TrackedPage).where(TrackedPage.id == page_id)
        .values(is_active=TrackedPage.is_active).returning(TrackedPage.id)
    ).scalar_one_or_none()
    if locked is None:
        return None

    old = db.scalar(select(PageSnapshot).where(PageSnapshot.page_id == page_id)
                    .order_by(PageSnapshot.captured_at.desc(), PageSnapshot.id.desc()).limit(1))
    snapshot = PageSnapshot(page_id=page_id, source_mode=mode, **extracted)
    if captured_at is not None:
        snapshot.captured_at = captured_at
    db.add(snapshot)
    db.flush()
    alerts = []
    if old is not None:
        alerts = [ChangeAlert(page_id=page_id, old_snapshot_id=old.id, new_snapshot_id=snapshot.id,
                              created_at=snapshot.captured_at, **change)
                  for change in compare_snapshots(old, snapshot)]
        db.add_all(alerts)
        db.flush()
    return snapshot, alerts
