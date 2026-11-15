import csv
import re
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from app.models import BattlecardNote, ChangeAlert, Competitor, DemoState, TrackedPage, utc_now
from app.services.battlecards import market_rows, overview
from app.services.scoring import CRITERIA

PRICE = "#,##0.00"
PLAYERS = ("Игрок", "Сегмент", "Свой бренд", "Позиционирование", "Мин. цена", "Макс. цена", "Валюта", "CRO Score")
OFFER = ("H1", "Подзаголовок", "CTA", "Доверие", "Лид-магниты")
CARDS = ("Конкурент", "Сильная сторона", "Наш контр-оффер", "Скрипт отработки возражения")


def case_id(db):
    state = db.get(DemoState, 1)
    return state.case_id if state else "custom"


def player_row(brand, snap):
    values = (snap.min_price, snap.max_price, snap.currency, snap.cro_score) if snap else (None,) * 4
    return (brand.name, brand.segment, "Да" if brand.is_own_brand else "Нет", brand.positioning_note, *values)


def offer_row(snap):
    if snap is None:
        return ("",) * len(OFFER)
    return (snap.h1_text, snap.subheadline, " · ".join(snap.cta_buttons),
            " · ".join(snap.trust_signals), " · ".join(snap.lead_magnets))


def alert_rows(db):
    return db.execute(
        select(ChangeAlert, Competitor.name, TrackedPage.title, TrackedPage.url)
        .join(TrackedPage, ChangeAlert.page_id == TrackedPage.id)
        .join(Competitor, TrackedPage.competitor_id == Competitor.id)
        .order_by(ChangeAlert.created_at, ChangeAlert.id)
    ).all()


def card_rows(db):
    return db.execute(
        select(Competitor.name, BattlecardNote.competitor_strength, BattlecardNote.our_counter_offer,
               BattlecardNote.sales_objection_script)
        .join(BattlecardNote, BattlecardNote.competitor_id == Competitor.id)
        .where(Competitor.is_own_brand.is_(False)).order_by(Competitor.id)
    ).all()


def kpis(db, case, alerts):
    metrics = overview(db)
    currency = metrics["price_currency"] or "—"
    return [
        ("Активный демо-кейс", case),
        ("Дата генерации (UTC)", utc_now().isoformat(timespec="seconds")),
        ("Наш CRO Score", metrics["own_cro_score"]),
        ("Средний CRO Score рынка", metrics["market_avg_cro_score"]),
        (f"Наша минимальная цена ({currency})", metrics["own_min_price"]),
        (f"Медиана минимальных цен рынка ({currency})", metrics["market_median_min_price"]),
        ("Ценовой индекс", metrics["price_index"]),
        ("Непрочитанные алерты", sum(not alert.is_acknowledged for alert, *_ in alerts)),
    ]


def append_row(sheet, values):
    sheet.append([ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value for value in values])
    for cell in sheet[sheet.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def style_sheet(sheet, headers, price_columns=()):
    table_header = max(headers)
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = f"A{table_header + 1}"
    sheet.auto_filter.ref = f"A{table_header}:{get_column_letter(sheet.max_column)}{sheet.max_row}"
    for column in sheet.columns:
        longest = 0
        for cell in column:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row in headers and cell.value is not None:
                cell.fill = PatternFill("solid", fgColor="FF1E40AF")
                cell.font = Font(color="FFFFFFFF", bold=True)
                sheet.row_dimensions[cell.row].height = 28
            elif cell.row > table_header:
                if cell.row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="FFF1F5F9")
                if cell.column in price_columns:
                    cell.number_format = PRICE
            value = str(cell.value) if cell.value is not None else ""
            longest = max(longest, max(map(len, value.splitlines()), default=0))
        sheet.column_dimensions[column[0].column_letter].width = min(52, max(13, longest + 4))


def write_table(sheet, columns, rows):
    append_row(sheet, columns)
    header = sheet.max_row
    for row in rows:
        append_row(sheet, row)
    return header


def export_excel(db, case):
    players = market_rows(db)
    alerts = alert_rows(db)
    wb = Workbook()
    summary = wb.active
    summary.title = "Executive Summary"
    write_table(summary, ("Показатель", "Значение"), kpis(db, case, alerts))
    summary["B6"].number_format = summary["B7"].number_format = PRICE
    if summary["B8"].value is not None:
        summary["B8"].value /= 100
    summary["B8"].number_format = "0.00%"
    summary.append([None])
    header = write_table(summary, PLAYERS, (player_row(brand, snap) for brand, snap in players))
    style_sheet(summary, {1, header}, (5, 6))

    matrix = wb.create_sheet("CRO & Offer Matrix")
    write_table(matrix, ("Игрок", *CRITERIA, "CRO Score", *OFFER), (
        (brand.name, *((snap.score_breakdown if snap else {}).get(key) for key in CRITERIA),
         snap.cro_score if snap else None, *offer_row(snap))
        for brand, snap in players
    ))
    style_sheet(matrix, {1})

    log = wb.create_sheet("Change Alerts Log")
    write_table(log, ("Severity", "Тип изменения", "Игрок", "Страница", "URL", "Изменение", "Статус", "Дата (UTC)"), (
        (alert.severity.upper(), alert.change_type, name, title or url, url, alert.summary,
         "Прочитано" if alert.is_acknowledged else "Новое", alert.created_at.isoformat(timespec="seconds"))
        for alert, name, title, url in alerts
    ))
    style_sheet(log, {1})
    cards = wb.create_sheet("Sales Battlecards")
    write_table(cards, CARDS, card_rows(db))
    style_sheet(cards, {1})
    with BytesIO() as output:
        wb.save(output)
        return output.getvalue()


def csv_cell(value):
    if isinstance(value, str) and (value.startswith(("\t", "\r", "\n")) or
                                   value.lstrip().startswith(("=", "+", "-", "@"))):
        return "'" + value
    if isinstance(value, float):
        return format(value, ".15g").replace(".", ",")
    return value


def export_csv(db):
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow((*PLAYERS, *OFFER))
    for brand, snap in market_rows(db):
        writer.writerow(map(csv_cell, (*player_row(brand, snap), *offer_row(snap))))
    return output.getvalue().encode("utf-8-sig")


def md(value):
    text = " ".join(str(value).split()) if value is not None else "—"
    return re.sub(r"([\\\[\]()!<>#*_~&|\x60])", r"\\\1", text)


def export_markdown(db, case):
    alerts = alert_rows(db)
    rows = kpis(db, case, alerts)
    index = rows[6][1]
    rows[6] = (rows[6][0], f"{index:.2f}%" if index is not None else None)
    lines = ["# Competitor & Offer Intelligence Hub", "", "## Executive Overview", ""]
    lines.extend(f"- **{label}** — {md(value)}" for label, value in rows)
    lines.extend(("", "## Sales Battlecards", ""))
    cards = card_rows(db)
    for name, *details in cards:
        lines.extend((f"### {md(name)}", ""))
        lines.extend(f"- **{label}** — {md(value)}" for label, value in zip(CARDS[1:], details))
        lines.append("")
    if not cards:
        lines.extend(("Боевые карточки пока не заполнены.", ""))
    lines.extend(("## Критичные алерты", ""))
    critical = [(alert, name, title or url) for alert, name, title, url in reversed(alerts)
                if alert.severity == "high"]
    for alert, name, page in critical:
        status = "прочитано" if alert.is_acknowledged else "новое"
        lines.append(f"- **{md(name)}** · {md(page)} · {alert.created_at.date()} · {status} · {md(alert.summary)}")
    if not critical:
        lines.append("Критичных алертов нет.")
    return ("\n".join(lines) + "\n").encode("utf-8")
