from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import BattlecardNote, Competitor, DemoState, TrackedPage, utc_now
from app.services.capture import analyze, save_snapshot

DEMO_CASES = {
    "b2b_agency": "B2B-агентство и платформа маркетинговой автоматизации",
    "edtech": "Онлайн-школа по AI и автоматизации",
}

# Each tuple contains the two price points, the two headlines, and the latest evidence.
PLAYERS = {
    "b2b_agency": [
        ("CyberNeuro Growth Stack", "direct", 35000, 35000,
         "Автоматизация маркетинга для B2B", "Автоматизация маркетинга для B2B",
         "Кейсы", "Отзывы", "Гарантия возврата", "Бесплатный аудит", "Демо-доступ", "Шаблон"),
        ("MetricPulse Enterprise", "leader", 69000, 69000,
         "Единая аналитика для крупных команд", "Единая аналитика для крупных команд",
         "Кейсы", "Партнёры", "Отзывы", "Демо-доступ"),
        ("AutoFunnel Pro", "direct", 39000, 24900,
         "Автоматизируйте B2B воронку продаж", "Автоматизируйте B2B воронку продаж",
         "Отзывы", "Триал"),
        ("LeadCraft Studio", "direct", 42000, 42000,
         "Агентство лидогенерации для B2B", "Квалифицированные лиды для вашей команды",
         "Кейсы", "Бесплатный аудит"),
        ("SmartBI Lite", "indirect", 12000, 12000,
         "Отчёты маркетинга своими руками", "Отчёты маркетинга своими руками", "Шаблон"),
    ],
    "edtech": [
        ("CyberNeuro Academy", "direct", 29900, 29900,
         "Освойте профессию AI-интегратора", "Освойте профессию AI-интегратора",
         "Гарантия трудоустройства", "Кейсы", "Отзывы", "Рассрочка 0%", "Пробный урок", "Шаблон"),
        ("SkillMatrix Pro", "leader", 65000, 79000,
         "Практика AI в большой школе", "Практика AI в большой школе", "Кейсы", "Рейтинг", "Партнёры"),
        ("ZeroCode Camp", "direct", 34900, 19900,
         "Автоматизация без программирования", "Автоматизация без программирования",
         "Отзывы", "Бесплатный 3-дневный интенсив"),
        ("AI Boost School", "direct", 39000, 39000,
         "Курсы по нейросетям", "Профессия AI-интегратор за 8 недель", "Кейсы", "Пробный урок"),
        ("PromptStart", "indirect", 7900, 7900,
         "Мини-курс по промптам без кураторов", "Мини-курс по промптам без кураторов", "Чек-лист"),
    ],
}

BATTLECARDS = {
    "b2b_agency": [
        ("Корпоративная отчётность и партнёрская сеть", "Запуск с 35 000 ₽ и аудит", "Какие отчёты нужны в первый месяц? Покажем их на демо."),
        ("Порог входа 24 900 ₽", "Внедрение с аудитом процессов", "Сравним цену подписки и стоимость настройки вашей воронки."),
        ("Бесплатный аудит", "Аудит вместе с демо платформы", "На демо покажем, как рекомендации аудита переходят в автоматизацию."),
        ("Конструктор отчётов от 12 000 ₽", "Автоматизация от сбора данных до передачи лидов", "Посчитаем время команды на подготовку отчёта и обработку лидов."),
    ],
    "edtech": [
        ("Партнёрская сеть и отзывы", "Практическая программа от 29 900 ₽", "Сравним программы по набору проектов для портфолио."),
        ("Тариф 19 900 ₽ и бесплатный интенсив", "Пробный урок и рассрочка 0%", "Попробуйте урок и оцените сложность итогового проекта."),
        ("Оффер профессии за 8 недель", "Разбор кейсов и гарантия трудоустройства", "Какие задачи вы хотите уметь решать после курса? Сверим их с программой."),
        ("Мини-курс за 7 900 ₽", "Полная программа с наставничеством", "Если цель — освоить профессию, сравним объём практики и обратной связи."),
    ],
}


def seed_demo_data(db: Session, case_id: str = "b2b_agency"):
    if case_id not in PLAYERS:
        raise ValueError(f"Unknown demo case {case_id}")
    if db.scalar(select(Competitor.id).limit(1)) is not None:
        return

    now = utc_now()
    for index, (name, segment, old_price, new_price, old_h1, new_h1, *evidence) in enumerate(PLAYERS[case_id]):
        own = index == 0
        academy = case_id == "edtech" and own
        domain = name.lower().replace(" ", "-") + ".example"
        brand = Competitor(name=name, domain=domain, segment=segment, is_own_brand=own,
                           positioning_note=new_h1, target_audience=(
                               "Маркетинговые команды B2B" if case_id == "b2b_agency"
                               else "Специалисты по AI и автоматизации"
                           ))
        db.add(brand)
        db.flush()
        page = TrackedPage(competitor_id=brand.id, page_type="main", url=f"https://{domain}/", title=name)
        db.add(page)
        db.flush()

        for latest, price, h1 in ((False, old_price, old_h1), (True, new_price, new_h1)):
            active_evidence = evidence if latest else [
                item for item in evidence if item != "Бесплатный 3-дневный интенсив"
                and not (name == "LeadCraft Studio" and item == "Бесплатный аудит")
            ]
            # A small set of concrete proof points makes the two demo cases comparable.
            snapshot = dict(
                h1_text=h1,
                subheadline=("5 проектов для портфолио с обратной связью наставника" if academy
                             else "Практическое внедрение по шагам с поддержкой команды"),
                prices=[price, 54900] if academy else [price],
                cta_buttons=(["Записаться"] if academy else ["Оставить заявку", "Demo"] if own
                             else ["Получить предложение"]),
                trust_signals=[item for item in active_evidence if item in {
                    "Кейсы", "Отзывы", "Рейтинг", "Партнёры", "Гарантия возврата", "Гарантия трудоустройства"
                }],
                lead_magnets=[item for item in active_evidence if item in {
                    "Бесплатный аудит", "Демо-доступ", "Шаблон", "Триал", "Рассрочка 0%",
                    "Пробный урок", "Бесплатный 3-дневный интенсив", "Чек-лист"
                }],
            )
            save_snapshot(db, page.id, "json_snapshot", analyze(snapshot, "json_snapshot"),
                          captured_at=now - timedelta(days=1 if latest else 14, minutes=index))

        if not own:
            strength, counter, script = BATTLECARDS[case_id][index - 1]
            db.add(BattlecardNote(competitor_id=brand.id, competitor_strength=strength,
                                  our_counter_offer=counter, sales_objection_script=script))
    db.merge(DemoState(id=1, case_id=case_id))


def reset_demo_data(db: Session, case_id: str):
    db.execute(delete(Competitor))
    seed_demo_data(db, case_id)
