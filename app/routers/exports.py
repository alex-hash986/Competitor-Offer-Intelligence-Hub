from fastapi import APIRouter, Response

from app.database import DB
from app.services.exporter import case_id, export_csv, export_excel, export_markdown

router = APIRouter(prefix="/exports", tags=["exports"])
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def download(content, case, extension, media_type):
    filename = f"competitor_offer_intelligence_{case}.{extension}"
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/excel", response_class=Response, responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}})
def excel(db: DB):
    case = case_id(db)
    return download(export_excel(db, case), case, "xlsx", XLSX_MEDIA_TYPE)


@router.get("/csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def csv_report(db: DB):
    return download(export_csv(db), case_id(db), "csv", "text/csv")


@router.get("/battlecards.md", response_class=Response, responses={200: {"content": {"text/markdown": {}}}})
def markdown(db: DB):
    case = case_id(db)
    return download(export_markdown(db, case), case, "md", "text/markdown")
