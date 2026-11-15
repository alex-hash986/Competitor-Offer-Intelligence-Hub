from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.database import DB, as_dict
from app.models import PageSnapshot, TrackedPage
from app.schemas import CaptureInput, SnapshotInput
from app.services.capture import analyze, save_snapshot
from app.services.diff_engine import compare_snapshots
from app.services.extractor import MAX_BYTES

router = APIRouter(prefix="/snapshots")


def capture(db, page_id, mode, content):
    page = db.get(TrackedPage, page_id)
    if page is None:
        raise HTTPException(404, "Страница не найдена")
    # Capture uses the saved URL. The preview route accepts standalone URLs.
    source = page.url if mode == "live_url" else content
    db.rollback()
    result = save_snapshot(db, page_id, mode, analyze(source, mode))
    if result is None:
        raise HTTPException(404, "Страница не найдена")
    snapshot, alerts = result
    response = dict(snapshot=as_dict(snapshot), alerts=[as_dict(alert) for alert in alerts])
    db.commit()
    return response


@router.post("/capture", status_code=201)
def capture_snapshot(data: CaptureInput, db: DB):
    return capture(db, data.page_id, data.mode, data.content)


@router.post("/upload", status_code=201)
def upload_snapshot(db: DB, page_id: Annotated[int, Form(gt=0)], file: Annotated[UploadFile, File()]):
    mode = {".html": "raw_html", ".json": "json_snapshot"}.get(Path(file.filename or "").suffix.lower())
    if mode is None:
        raise HTTPException(422, "Поддерживаются файлы .html и .json")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Файл превышает 2 МБ")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Используйте кодировку UTF-8") from exc
    return capture(db, page_id, mode, content)


@router.post("/preview")
def preview(data: SnapshotInput):
    if data.mode == "live_url" and not data.content:
        raise HTTPException(422, "Укажите URL в поле content")
    return analyze(data.content, data.mode)


@router.get("/diff")
def diff(old_id: int, new_id: int, db: DB):
    old, new = db.get(PageSnapshot, old_id), db.get(PageSnapshot, new_id)
    if old is None or new is None:
        raise HTTPException(404, "Снимок не найден")
    if old.page_id != new.page_id:
        raise HTTPException(422, "Снимки должны относиться к одной странице")
    return {"old_snapshot_id": old.id, "new_snapshot_id": new.id,
            "changes": compare_snapshots(old, new)}
