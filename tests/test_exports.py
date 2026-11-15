import csv
from io import BytesIO, StringIO

from openpyxl import load_workbook


def test_excel_report(client):
    response = client.get("/api/exports/excel")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["content-disposition"] == 'attachment; filename="competitor_offer_intelligence_b2b_agency.xlsx"'
    with BytesIO(response.content) as stream:
        book = load_workbook(stream)
    assert book.sheetnames == ["Executive Summary", "CRO & Offer Matrix", "Change Alerts Log", "Sales Battlecards"]
    summary = book["Executive Summary"]
    assert summary["B2"].value == "b2b_agency"
    assert summary["B4"].value == 86
    assert summary["B6"].value == 35000
    assert summary["B8"].number_format == "0.00%"
    assert summary["A1"].font.bold
    assert summary["A1"].fill.fgColor.rgb == "FF1E40AF"
    assert summary["A12"].alignment.wrap_text
    assert any("AutoFunnel Pro" in row and 24900 in row for row in summary.values)
    matrix = book["CRO & Offer Matrix"]
    assert matrix["B1"].value == "uvp_clarity"
    assert matrix.max_row == 6
    log = book["Change Alerts Log"]
    assert any("price_drop" in row and "AutoFunnel Pro" in row for row in log.values)
    assert book["Sales Battlecards"].max_row == 5


def test_csv_report(client):
    response = client.get("/api/exports/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.content.startswith(bytes.fromhex("efbbbf"))
    rows = list(csv.DictReader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 5
    funnel = next(row for row in rows if row["Игрок"] == "AutoFunnel Pro")
    assert funnel["Мин. цена"] == "24900"
    assert funnel["H1"]
    assert funnel["CTA"]


def test_markdown_tracks_case_and_changes(client):
    assert client.post("/api/demo/reset", json={"case_id": "edtech"}).status_code == 200
    response = client.get("/api/exports/battlecards.md")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert 'filename="competitor_offer_intelligence_edtech.md"' in response.headers["content-disposition"]
    assert "## Executive Overview" in response.text
    assert "## Sales Battlecards" in response.text
    assert "### SkillMatrix Pro" in response.text
    assert "## Критичные алерты" in response.text
    assert "ZeroCode Camp" in response.text.split("## Критичные алерты")[1]


def test_exported_user_text_is_not_a_spreadsheet_formula(client):
    response = client.post("/api/competitors", json={
        "name": "=1+1", "domain": "example.org", "segment": "direct",
        "positioning_note": "Текст; с разделителем",
    })
    assert response.status_code == 201
    with BytesIO(client.get("/api/exports/excel").content) as stream:
        book = load_workbook(stream)
    sheet = book["Executive Summary"]
    assert sheet[f"A{sheet.max_row}"].data_type == "s"
    assert sheet[f"A{sheet.max_row}"].value == "=1+1"
    content = client.get("/api/exports/csv").content.decode("utf-8-sig")
    last = list(csv.DictReader(StringIO(content), delimiter=";"))[-1]
    assert last["Игрок"] == "'=1+1"
    assert last["Позиционирование"] == "Текст; с разделителем"


def test_spa_entrypoint_and_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="tab-market"' in response.text
    assert 'id="tab-alerts"' in response.text
    assert 'id="tab-capture"' in response.text
    assert 'id="tab-battlecards"' in response.text
    assert 'href="/api/exports/excel"' in response.text
    assert client.get("/styles.css").status_code == 200
    assert client.get("/app.js").status_code == 200
