"use strict";

const $ = id => document.getElementById(id);
const html = value => String(value ?? "—").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);
const numeric = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
const dateTime = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" });
const number = value => value == null ? "—" : numeric.format(value);
const price = (value, currency) => value == null ? "—" :
  new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 2,
    minimumFractionDigits: 0 }).format(value);
const stamp = value => dateTime.format(new Date(value));
const items = values => values?.length ? values.join(" · ") : "—";
const cases = { b2b_agency: "B2B-агентство и автоматизация", edtech: "Онлайн-школа EdTech" };
const criteria = {
  uvp_clarity: "Ясность оффера", price_transparency: "Прозрачность цены",
  cta_strength: "Сила CTA", trust_proof: "Доверие", friction_reducers: "Снятие барьеров",
};
const changes = {
  price_drop: "Снижение цены", price_hike: "Повышение цены", h1_change: "Изменение H1",
  cta_change: "Изменение CTA", trust_update: "Сигналы доверия", offer_pivot: "Лид-магниты и условия входа",
};
const views = {
  market: ["Обзор рынка и CRO", "Позиция нашего оффера по цене и конверсии"],
  alerts: ["Лента изменений", "Алерты и сравнение двух слепков страницы"],
  capture: ["Песочница и слепки", "Анализ оффера и сохранение истории страницы"],
  battlecards: ["Боевые карточки продаж", "Позиционирование, контр-офферы и работа с возражениями"],
};
const state = { players: [], alerts: [], overview: null, details: new Map(), charts: {}, revision: 0 };
const cardFields = {
  competitor_strength: "Сильная сторона конкурента",
  our_counter_offer: "Наш контр-оффер",
  sales_objection_script: "Скрипт отработки возражения",
};

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map(item => item.msg).join(" · ") : body.detail;
    throw new Error(detail || `Ошибка HTTP ${response.status}`);
  }
  return response.json();
}

const send = (path, method, data) => api(path, {
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

function message(id, text, error = false) {
  const target = $(id);
  target.textContent = text || "";
  target.hidden = !text;
  target.classList.toggle("error", error);
}

let toastTimer;
function notify(text) {
  message("toast", text);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => message("toast", ""), 3800);
}

async function busy(button, callback, errorId = "app-error") {
  if (button?.disabled) return;
  if (button) button.disabled = true;
  message(errorId, "");
  try {
    await callback();
  } catch (error) {
    message(errorId, error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function table(headers, rows) {
  if (!rows.length) return '<p class="empty">Данных пока нет.</p>';
  return `<table><thead><tr>${headers.map(title => `<th scope="col">${html(title)}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("")}</tbody></table>`;
}

function selectOptions(select, options, placeholder, preferred) {
  const wanted = preferred ?? select.value;
  select.replaceChildren(new Option(placeholder, ""), ...options.map(([value, label]) => new Option(label, value)));
  select.value = options.some(([value]) => String(value) === String(wanted)) ? wanted : "";
  select.disabled = options.length === 0;
}

function activate(view, focus = false) {
  for (const key of Object.keys(views)) {
    const active = key === view;
    $(key).hidden = !active;
    const button = $(`tab-${key}`);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    if (active && focus) button.focus();
  }
  $("view-title").textContent = views[view][0];
  $("view-caption").textContent = views[view][1];
  if (view === "market") renderCharts();
}

const badge = player => {
  const segment = player.is_own_brand ? "own-brand" : player.segment;
  const label = { "own-brand": "Own Brand", leader: "Leader", direct: "Direct", indirect: "Indirect" };
  return `<span class="badge ${html(segment)}">${html(label[segment])}</span>`;
};

const severityBadge = severity => `<span class="badge ${html(severity)}">${html(severity.toUpperCase())}</span>`;

function renderMarket() {
  const data = state.overview;
  const active = state.alerts.filter(alert => !alert.is_acknowledged);
  const cards = [
    ["Наш CRO Score vs рынок", number(data.own_cro_score), `Средний по рынку · ${number(data.market_avg_cro_score)}`],
    ["Наша мин. цена vs медиана", price(data.own_min_price, data.price_currency),
      `Медиана рынка · ${price(data.market_median_min_price, data.price_currency)}`],
    ["Ценовой индекс", data.price_index == null ? "—" : `${number(data.price_index)}%`, "Медиана рынка = 100%"],
    ["Активные алерты", `${active.filter(alert => alert.severity === "high").length} / ${active.length}`, "HIGH / Всего непрочитанных"],
  ];
  $("kpis").innerHTML = cards.map(([label, value, note]) => `<article class="kpi"><p class="kpi-label">${html(label)}</p>
    <p class="kpi-value">${html(value)}</p><p class="kpi-note">${html(note)}</p></article>`).join("");
  const prices = new Map(data.price_matrix.map(row => [row.competitor_id, row]));
  $("matrix").innerHTML = table(["Игрок", "Сегмент", "Позиционирование", "Мин. цена", "Макс. цена", "CRO", "Новые алерты"],
    state.players.map(player => `<tr class="${player.is_own_brand ? "own" : ""}">
      <td><button class="text-button" data-player="${player.id}">${html(player.name)}</button></td>
      <td>${badge(player)}</td><td>${html(player.positioning_note || "—")}</td>
      <td class="number">${html(price(player.min_price, player.currency))}</td>
      <td class="number">${html(price(prices.get(player.id)?.max_price, player.currency))}</td>
      <td>${number(player.cro_score)}</td><td>${number(player.unread_alert_count)}</td></tr>`));
  const currencies = [...new Set(data.price_matrix.map(row => row.currency))];
  const current = $("price-currency").value;
  $("price-currency").replaceChildren(...currencies.map(currency => new Option(currency, currency)));
  if (currencies.includes(current)) $("price-currency").value = current;
  else if (currencies.includes(data.price_currency)) $("price-currency").value = data.price_currency;
  $("currency-control").hidden = currencies.length < 2;
  renderCharts();
}

const chartColors = ["#0f766e", "#7c3aed", "#d97706", "#64748b", "#db2777"];
function chartOrTable(key, label, config, fallbackHTML, hasData) {
  const frame = $(`${key}-frame`);
  const fallback = $(`${key}-fallback`);
  state.charts[key]?.destroy();
  delete state.charts[key];
  frame.replaceChildren();
  fallback.innerHTML = fallbackHTML;
  fallback.hidden = false;
  if (!window.Chart || !hasData) return;
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", label);
  frame.append(canvas);
  try {
    state.charts[key] = new window.Chart(canvas, config);
    fallback.hidden = true;
  } catch {
    frame.replaceChildren();
  }
}

function renderCharts() {
  if (!state.overview || $("market").hidden) return;
  const { radar_axes: axes, radar, price_matrix: matrix } = state.overview;
  const labels = axes.map(axis => criteria[axis]);
  const peers = radar.filter(row => row.scores).sort((a, b) => Number(b.is_own_brand) - Number(a.is_own_brand));
  const selected = matrix.filter(row => row.currency === $("price-currency").value);
  const colors = new Map(peers.map((row, index) => [row.competitor_id ?? row.id,
    row.is_own_brand ? "#1e40af" : chartColors[index % chartColors.length]]));
  const options = { responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 13 } } } };
  chartOrTable("radar", "Сравнение пяти критериев CRO", {
    type: "radar",
    data: { labels, datasets: peers.map(row => {
      const color = colors.get(row.competitor_id);
      return { label: row.name, data: axes.map(axis => row.scores[axis]), borderColor: color,
        backgroundColor: row.is_own_brand ? "#1e40af22" : "transparent", pointBackgroundColor: color,
        borderWidth: row.is_own_brand ? 3 : 1.5, pointRadius: 3 };
    }) },
    options: { ...options, scales: { r: { min: 0, max: 20, ticks: { stepSize: 5 },
      pointLabels: { font: { size: 11 } } } } },
  }, table(["Игрок", ...labels], peers.map(row => `<tr><td>${html(row.name)}</td>
    ${axes.map(axis => `<td>${number(row.scores[axis])}</td>`).join("")}</tr>`)), peers.length);
  chartOrTable("price", "Минимальная цена относительно CRO Score", {
    type: "scatter",
    data: { datasets: selected.map(row => ({
      label: row.name, data: [{ x: row.min_price, y: row.cro_score }],
      backgroundColor: colors.get(row.competitor_id), pointRadius: row.is_own_brand ? 9 : 7, pointHoverRadius: 11,
    })) },
    options: { ...options, scales: {
      x: { title: { display: true, text: `Минимальная цена · ${$("price-currency").value}` },
        ticks: { callback: value => number(value) } },
      y: { min: 0, max: 100, title: { display: true, text: "CRO Score" } },
    }, plugins: { ...options.plugins, tooltip: { callbacks: { label: context =>
      `${context.dataset.label} · ${price(context.parsed.x, $("price-currency").value)} · CRO ${context.parsed.y}` } } } },
  }, table(["Игрок", "Мин. цена", "CRO"], selected.map(row => `<tr><td>${html(row.name)}</td>
    <td class="number">${html(price(row.min_price, row.currency))}</td><td>${number(row.cro_score)}</td></tr>`)), selected.length);
}

function renderAlerts() {
  const severity = $("severity").value;
  const unread = $("ack-status").value === "false";
  const filtered = state.alerts.filter(alert => (!severity || alert.severity === severity) &&
    (!unread || !alert.is_acknowledged));
  $("alert-list").innerHTML = filtered.length ? filtered.map(alert => {
    const page = state.pages?.get(alert.page_id);
    const player = page ? `${page.player} · ${page.title || page.url}` : `Страница №${alert.page_id}`;
    return `<article class="alert-item"><div class="spread"><div>${severityBadge(alert.severity)}
      <strong>${html(changes[alert.change_type])}</strong></div><small>${html(stamp(alert.created_at))}</small></div>
      <p class="muted">${html(player)}</p><p>${html(alert.summary)}</p><div class="controls">
      <button type="button" data-diff="${alert.id}">Открыть diff</button>
      ${alert.is_acknowledged ? "<small>Прочитано</small>" :
        `<button type="button" data-ack="${alert.id}">Подтвердить / Прочитано</button>`}</div></article>`;
  }).join("") : '<p class="empty">По выбранным фильтрам алертов нет.</p>';
}

function fillPages(prefix, preferred) {
  const brand = state.details.get(Number($(`${prefix}-player`).value));
  const pages = brand?.pages || [];
  selectOptions($(`${prefix}-page`), pages.map(page => [page.id, page.title || page.url]), "Выберите страницу", preferred);
  if (!$(`${prefix}-page`).value && pages.length) $(`${prefix}-page`).value = pages[0].id;
  if (prefix === "diff") fillSnapshots();
  else updateCaptureMode();
}

function fillSnapshots(oldId, newId) {
  const page = state.pages.get(Number($("diff-page").value));
  const snapshots = page?.snapshots || [];
  const options = snapshots.map(snap => [snap.id, `${stamp(snap.captured_at)} · #${snap.id}`]);
  selectOptions($("old-snapshot"), options, "Выберите слепок", oldId ?? snapshots[1]?.id ?? "");
  selectOptions($("new-snapshot"), options, "Выберите слепок", newId ?? snapshots[0]?.id ?? "");
  $("diff-form").querySelector("button").disabled = snapshots.length < 2;
  $("diff-result").innerHTML = snapshots.length < 2 ? '<p class="empty">Для сравнения нужны два слепка страницы.</p>' : "";
}

function diffText(change) {
  const detail = change.diff_details;
  if (change.change_type === "price_drop" || change.change_type === "price_hike") {
    return `${price(detail.old, detail.currency)} → ${price(detail.new, detail.currency)}
      ${detail.percent_delta == null ? "" : `(${detail.percent_delta > 0 ? "+" : ""}${number(detail.percent_delta)}%)`}`;
  }
  if (change.change_type === "h1_change") return `${detail.old || "—"} → ${detail.new || "—"}`;
  return [detail.added?.length ? `Добавлено · ${items(detail.added)}` : "",
    detail.removed?.length ? `Удалено · ${items(detail.removed)}` : ""].filter(Boolean).join("\n");
}

async function compare() {
  const oldId = $("old-snapshot").value;
  const newId = $("new-snapshot").value;
  if (!oldId || !newId || oldId === newId) throw new Error("Выберите два разных слепка.");
  const diff = await api(`/snapshots/diff?old_id=${oldId}&new_id=${newId}`);
  if ($("old-snapshot").value !== oldId || $("new-snapshot").value !== newId) return;
  $("diff-result").innerHTML = diff.changes.length ? diff.changes.map(change =>
    `<article class="change">${severityBadge(change.severity)} <strong>${html(changes[change.change_type])}</strong>
      <dl><dd>${html(diffText(change))}</dd></dl></article>`).join("") :
    '<p class="empty">Между слепками нет зафиксированных изменений.</p>';
}

function detailList(values) {
  return `<dl>${values.map(([label, value]) => `<dt>${html(label)}</dt><dd>${html(value || "—")}</dd>`).join("")}</dl>`;
}

function showPlayer(id) {
  const player = state.details.get(id);
  if (!player) return;
  const detail = $("player-detail");
  detail.innerHTML = `<div class="spread"><div><h3>${html(player.name)}</h3>${badge(player)}</div>
    <button id="close-player" type="button">Закрыть</button></div>
    ${detailList([["Домен", player.domain], ["Позиционирование", player.positioning_note],
      ["Аудитория", player.target_audience]])}
    ${player.pages.map(page => `<h4>${html(page.title || page.url)}</h4><p class="muted">${html(page.url)}</p>
      ${table(["Слепок", "H1", "Мин. цена", "CRO"], page.snapshots.map(snap => `<tr>
        <td>${html(stamp(snap.captured_at))}</td><td>${html(snap.h1_text)}</td>
        <td class="number">${html(price(snap.min_price, snap.currency))}</td><td>${number(snap.cro_score)}</td></tr>`))}`).join("")}`;
  detail.hidden = false;
  $("close-player").onclick = () => { detail.hidden = true; $("matrix").querySelector(`[data-player="${id}"]`)?.focus(); };
  detail.focus();
}

function renderCards() {
  const rivals = state.players.filter(player => !player.is_own_brand);
  $("card-grid").innerHTML = rivals.length ? rivals.map(player => {
    const fields = Object.entries(cardFields);
    const card = player.battlecard || {};
    return `<article class="panel" data-card="${player.id}"><div class="spread"><h3>${html(player.name)}</h3>${badge(player)}</div>
      <div class="metrics"><strong>${html(price(player.min_price, player.currency))}</strong><span>CRO · ${number(player.cro_score)}</span></div>
      <div data-card-values>${detailList(fields.map(([key, label]) => [label, card[key]]))}</div>
      <button type="button" data-edit>Редактировать</button>
      <form class="stack" hidden>${fields.map(([key, label]) => `<label>${html(label)}<textarea name="${key}" rows="3">${html(card[key] || "")}</textarea></label>`).join("")}
      <div class="controls"><button class="primary" type="submit">Сохранить</button><button data-cancel type="button">Отмена</button></div>
      <p class="notice error" role="alert" hidden></p></form></article>`;
  }).join("") : '<p class="empty">Конкурентов пока нет.</p>';
}

const exampleHTML = `<h1>Автоматизация продаж для B2B-команд</h1>
<h2>Запуск за 14 дней с персональным менеджером</h2>
<p>Стартовый тариф — 24 900 ₽. Командный тариф — 45 000 ₽.</p>
<button>Оставить заявку</button><a href="/demo">Demo</a>
<p>Кейсы, отзывы, гарантия возврата и 200 клиентов.</p>
<p>Бесплатный аудит, триал 14 дней, чек-лист и рассрочка 0%.</p>`;

function updateCaptureMode() {
  const mode = $("capture-mode").value;
  $("content-field").hidden = !["raw_html", "manual_text"].includes(mode);
  $("file-field").hidden = mode !== "upload";
  $("url-field").hidden = mode !== "live_url";
  $("content-label").textContent = mode === "manual_text" ? "Текст оффера" : "HTML страницы";
  $("capture-content").placeholder = mode === "manual_text" ? "Вставьте текст оффера" : "Вставьте HTML страницы";
  const page = state.pages?.get(Number($("capture-page").value));
  $("capture-url-hint").textContent = page ? `URL для сохранения · ${page.url}` :
    "Выберите отслеживаемую страницу для сохранения.";
}

function renderCapture(result) {
  $("capture-result").innerHTML = `<div class="metrics"><strong>${number(result.cro_score)} / 100</strong><span>CRO Score</span></div>
    ${Object.entries(criteria).map(([key, label]) => {
      const value = result.score_breakdown[key] ?? 0;
      return `<div class="score-row"><span>${html(label)}</span><span>${number(value)} / 20</span>
      <progress max="20" value="${value}" aria-label="${html(label)}"></progress></div>`;
    }).join("")}
    ${detailList([
      ["Найденные цены", items(result.extracted_prices.map(value => price(value, result.currency)))],
      ["H1", result.h1_text], ["Подзаголовок", result.subheadline], ["CTA", items(result.cta_buttons)],
      ["Триггеры доверия", items(result.trust_signals)], ["Лид-магниты", items(result.lead_magnets)],
    ])}`;
}

async function capture(save) {
  const mode = $("capture-mode").value;
  const pageId = Number($("capture-page").value);
  if (save && !pageId) throw new Error("Выберите отслеживаемую страницу.");
  let result;
  if (mode === "upload") {
    const file = $("capture-file").files[0];
    if (!file) throw new Error("Выберите файл .html или .json.");
    const extension = file.name.split(".").pop().toLowerCase();
    if (!["html", "json"].includes(extension)) throw new Error("Поддерживаются файлы .html и .json.");
    if (file.size > 2_000_000) throw new Error("Файл превышает 2 МБ.");
    if (save) {
      const form = new FormData();
      form.append("page_id", String(pageId));
      form.append("file", file);
      result = await api("/snapshots/upload", { method: "POST", body: form });
    } else {
      result = await send("/snapshots/preview", "POST", {
        mode: extension === "json" ? "json_snapshot" : "raw_html", content: await file.text(),
      });
    }
  } else {
    const content = mode === "live_url" ? $("capture-url").value.trim() : $("capture-content").value;
    if (!content.trim() && !(save && mode === "live_url")) throw new Error("Укажите источник оффера.");
    result = save ? await send("/snapshots/capture", "POST", {
      page_id: pageId, mode, content: mode === "live_url" ? null : content,
    }) : await send("/snapshots/preview", "POST", { mode, content });
  }
  renderCapture(save ? result.snapshot : result);
  message("capture-status", save ? `Слепок сохранён · новые алерты: ${result.alerts.length}` : "Анализ завершён.");
  if (save) {
    try {
      await refresh({ preserveCards: true });
    } catch (error) {
      message("app-error", `Слепок сохранён. Ошибка обновления данных: ${error.message}`, true);
    }
  }
}

async function refresh({ preserveCards = false, reset = false } = {}) {
  const revision = ++state.revision;
  const [health, players, overview, alerts] = await Promise.all([
    api("/health"), api("/competitors"), api("/analytics/overview"), api("/alerts"),
  ]);
  const details = await Promise.all(players.map(player => api(`/competitors/${player.id}`)));
  if (revision !== state.revision) return;
  Object.assign(state, {
    players, overview, alerts, activeCase: health.active_demo_case,
    details: new Map(details.map(brand => [brand.id, brand])),
    pages: new Map(details.flatMap(brand => brand.pages.map(page => [page.id, { ...page, player: brand.name }]))),
  });
  $("demo-case").value = health.active_demo_case || "b2b_agency";
  const options = players.map(player => [player.id, player.name]);
  for (const prefix of ["diff", "capture"]) {
    selectOptions($(`${prefix}-player`), options, "Выберите игрока", reset ? "" : undefined);
    if (options.length && !$(`${prefix}-player`).value) $(`${prefix}-player`).value = options[0][0];
    fillPages(prefix);
  }
  renderMarket();
  renderAlerts();
  if (!preserveCards || reset) renderCards();
  else {
    for (const player of players) {
      const metrics = $("card-grid").querySelector(`[data-card="${player.id}"] .metrics`);
      if (metrics) metrics.innerHTML = `<strong>${html(price(player.min_price, player.currency))}</strong><span>CRO · ${number(player.cro_score)}</span>`;
    }
  }
  $("player-detail").hidden = true;
}

const tabs = [...document.querySelectorAll('[role="tab"]')];
tabs.forEach((button, index) => {
  button.addEventListener("click", () => activate(button.getAttribute("aria-controls")));
  button.addEventListener("keydown", event => {
    const next = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length,
      Home: 0, End: tabs.length - 1 }[event.key];
    if (next == null) return;
    event.preventDefault();
    activate(tabs[next].getAttribute("aria-controls"), true);
  });
});
$("chart-library").addEventListener("load", renderCharts);
$("price-currency").addEventListener("change", renderCharts);
$("matrix").addEventListener("click", event => {
  const button = event.target.closest("[data-player]");
  if (button) showPlayer(Number(button.dataset.player));
});

$("demo-form").addEventListener("submit", event => {
  event.preventDefault();
  const selected = $("demo-case").value;
  if (!selected || selected === state.activeCase) return;
  if (!window.confirm(`Загрузить «${cases[selected]}»? Текущие игроки, слепки, алерты и карточки будут заменены.`)) return;
  busy(event.submitter, async () => {
    const main = document.querySelector("main");
    main.inert = true;
    try {
      await send("/demo/reset", "POST", { case_id: selected });
      $("capture-result").innerHTML = '<p class="empty">Добавьте источник и запустите анализ.</p>';
      message("capture-status", "");
      $("severity").value = "";
      $("ack-status").value = "";
      await refresh({ reset: true });
      notify(`Загружен кейс «${cases[selected]}».`);
    } finally {
      main.inert = false;
    }
  });
});

for (const id of ["severity", "ack-status"]) $(id).addEventListener("change", renderAlerts);
$("alert-list").addEventListener("click", event => {
  const ack = event.target.closest("[data-ack]");
  const open = event.target.closest("[data-diff]");
  if (ack) busy(ack, async () => {
    const updated = await api(`/alerts/${ack.dataset.ack}/ack`, { method: "PATCH" });
    state.alerts = state.alerts.map(alert => alert.id === updated.id ? updated : alert);
    const player = state.players.find(brand => state.details.get(brand.id)?.pages.some(page => page.id === updated.page_id));
    if (player) player.unread_alert_count = state.alerts.filter(alert => !alert.is_acknowledged &&
      state.details.get(player.id).pages.some(page => page.id === alert.page_id)).length;
    renderAlerts();
    renderMarket();
    notify("Алерт отмечен как прочитанный.");
  });
  if (open) busy(open, async () => {
    const alert = state.alerts.find(item => item.id === Number(open.dataset.diff));
    const player = state.players.find(brand => state.details.get(brand.id)?.pages.some(page => page.id === alert.page_id));
    if (!player) throw new Error("Отслеживаемая страница не найдена.");
    $("diff-player").value = player.id;
    fillPages("diff", alert.page_id);
    fillSnapshots(alert.old_snapshot_id, alert.new_snapshot_id);
    await compare();
    $("diff-player").focus();
  });
});

$("diff-player").addEventListener("change", () => fillPages("diff"));
$("diff-page").addEventListener("change", () => fillSnapshots());
for (const id of ["old-snapshot", "new-snapshot"]) $(id).addEventListener("change", () => {
  $("diff-result").replaceChildren();
});
$("diff-form").addEventListener("submit", event => {
  event.preventDefault();
  busy(event.submitter, compare);
});

$("capture-player").addEventListener("change", () => fillPages("capture"));
$("capture-page").addEventListener("change", updateCaptureMode);
$("capture-mode").addEventListener("change", updateCaptureMode);
$("capture-form").addEventListener("submit", event => {
  event.preventDefault();
  runCapture(event.submitter?.value === "save");
});
$("example").addEventListener("click", () => {
  $("capture-mode").value = "raw_html";
  $("capture-content").value = exampleHTML;
  updateCaptureMode();
  runCapture(false);
});

let capturing = false;
async function runCapture(save) {
  if (capturing) return;
  capturing = true;
  const buttons = $("capture-form").querySelectorAll("button");
  buttons.forEach(button => { button.disabled = true; });
  try {
    await busy(null, () => capture(save), "capture-status");
  } finally {
    buttons.forEach(button => { button.disabled = false; });
    capturing = false;
  }
}

function toggleEditor(card, open) {
  card.querySelector("form").hidden = !open;
  card.querySelector("[data-card-values]").hidden = open;
  card.querySelector("[data-edit]").hidden = open;
  card.querySelector(open ? "textarea" : "[data-edit]").focus();
}

$("card-grid").addEventListener("click", event => {
  const edit = event.target.closest("[data-edit]");
  const cancel = event.target.closest("[data-cancel]");
  if (!edit && !cancel) return;
  const card = event.target.closest("[data-card]");
  if (cancel) {
    const form = card.querySelector("form");
    form.reset();
    form.querySelector('[role="alert"]').hidden = true;
  }
  toggleEditor(card, Boolean(edit));
});

$("card-grid").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.target;
  const card = form.closest("[data-card]");
  const error = form.querySelector('[role="alert"]');
  const cancel = form.querySelector("[data-cancel]");
  error.hidden = true;
  event.submitter.disabled = cancel.disabled = true;
  try {
    const saved = await send(`/competitors/${card.dataset.card}/battlecard`, "PUT",
      Object.fromEntries(new FormData(form)));
    state.players.find(player => player.id === Number(card.dataset.card)).battlecard = saved;
    for (const key of Object.keys(cardFields)) {
      form.elements[key].defaultValue = saved[key];
      form.elements[key].value = saved[key];
    }
    card.querySelector("[data-card-values]").innerHTML = detailList(
      Object.entries(cardFields).map(([key, label]) => [label, saved[key]]));
    toggleEditor(card, false);
    notify("Боевая карточка сохранена.");
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    event.submitter.disabled = cancel.disabled = false;
  }
});

updateCaptureMode();
busy(null, refresh);
