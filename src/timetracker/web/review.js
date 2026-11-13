// Time Tracker review page: a bar per day for one month, the selected day's
// sessions, and weekly/monthly totals. Uses common.js.
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
// Chart geometry in SVG user units (the SVG scales to the page width).
const CHART = { width: 728, height: 230, left: 30, right: 4, top: 10, bottom: 22, barMax: 24, gap: 2, radius: 4 };

let month = null;        // response of /api/months/...
let selectedDay = null;  // "YYYY-MM-DD"

function parseDay(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function dayLabel(iso, options) {
  return parseDay(iso).toLocaleDateString([], options);
}

function shiftMonth(key, delta) {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function svg(name, attributes, parent) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  parent.append(node);
  return node;
}

// Path for a rectangle whose top corners are rounded and whose base is square.
function topRounded(x, y, w, h, radius) {
  const r = Math.min(radius, h, w / 2);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

function tipHtml(d) {
  const tip = $("tip");
  tip.replaceChildren();
  const title = document.createElement("b");
  title.textContent = dayLabel(d.day, { weekday: "short", month: "short", day: "numeric" });
  const lines = [
    `counted ${hoursMinutes(d.counted_s)} of ${hoursMinutes(d.target_s)}`,
    `work ${hoursMinutes(d.work_s)} · break ${hoursMinutes(d.break_s)}`,
    `distraction ${hoursMinutes(d.distraction_s)}`,
  ];
  tip.append(title);
  for (const line of lines) {
    tip.append(document.createElement("br"), line);
  }
}

function showTip(d, event) {
  tipHtml(d);
  const tip = $("tip");
  tip.hidden = false;
  const wrap = $("chart-wrap").getBoundingClientRect();
  const x = event.clientX - wrap.left;
  const left = x > wrap.width / 2 ? x - tip.offsetWidth - 12 : x + 12;
  tip.style.left = `${left}px`;
  tip.style.top = `${Math.max(0, event.clientY - wrap.top - tip.offsetHeight - 8)}px`;
}

function renderChart() {
  const chart = $("chart");
  chart.replaceChildren();
  chart.setAttribute("viewBox", `0 0 ${CHART.width} ${CHART.height}`);
  const days = month.days;
  const plotW = CHART.width - CHART.left - CHART.right;
  const plotH = CHART.height - CHART.top - CHART.bottom;
  const baseline = CHART.top + plotH;
  const slot = plotW / days.length;
  const barW = Math.min(CHART.barMax, slot - 6);

  // Y scale in hours, topped at an even number covering targets and data.
  const peak = Math.max(...days.map((d) => Math.max(d.counted_s, d.target_s)));
  const maxHours = Math.max(2, 2 * Math.ceil(peak / 7200));
  const y = (seconds) => baseline - (seconds / (maxHours * 3600)) * plotH;

  for (let h = 0; h <= maxHours; h += 2) {
    svg("line", { class: "grid", x1: CHART.left, x2: CHART.width - CHART.right, y1: y(h * 3600), y2: y(h * 3600) }, chart);
    svg("text", { x: CHART.left - 6, y: y(h * 3600) + 4, "text-anchor": "end" }, chart).textContent = `${h}h`;
  }

  days.forEach((d, i) => {
    const x0 = CHART.left + i * slot;
    const barX = x0 + (slot - barW) / 2;
    const column = svg("rect", { class: d.day === selectedDay ? "col selected" : "col", x: x0, y: CHART.top - 6, width: slot, height: plotH + 6 + CHART.bottom }, chart);
    column.addEventListener("click", () => selectDay(d.day));
    column.addEventListener("mousemove", (event) => showTip(d, event));
    column.addEventListener("mouseleave", () => { $("tip").hidden = true; });

    const workH = baseline - y(d.work_s);
    const breakH = baseline - y(d.break_s);
    const hasBreak = breakH >= CHART.gap + 1;
    if (workH > 0) {
      const attrs = { class: "bar-work", "pointer-events": "none" };
      if (hasBreak) svg("rect", { ...attrs, x: barX, y: baseline - workH, width: barW, height: workH }, chart);
      else svg("path", { ...attrs, d: topRounded(barX, baseline - workH, barW, workH, CHART.radius) }, chart);
    }
    if (hasBreak) {
      // The gap between the segments is left in the surface colour.
      const h = breakH - CHART.gap;
      svg("path", { class: "bar-break", "pointer-events": "none", d: topRounded(barX, baseline - workH - breakH, barW, h, CHART.radius) }, chart);
    }
    if (d.day <= month.today) {
      svg("line", { class: "target", "pointer-events": "none", x1: x0 + 2, x2: x0 + slot - 2, y1: y(d.target_s), y2: y(d.target_s) }, chart);
    }
    const date = parseDay(d.day);
    const classes = [d.day === month.today ? "today" : "", [0, 6].includes(date.getDay()) ? "weekend" : ""].join(" ").trim();
    const label = svg("text", { x: x0 + slot / 2, y: CHART.height - 6, "text-anchor": "middle", "pointer-events": "none" }, chart);
    if (classes) label.setAttribute("class", classes);
    label.textContent = String(date.getDate());
  });
}

// Background shade proportional to value / max, in the given RGB colour.
function shade(cell, value, max, rgb) {
  if (max > 0 && value > 0) cell.style.background = `rgba(${rgb}, ${(0.08 + 0.42 * (value / max)).toFixed(3)})`;
}

function statsRow(body, name, r, maxima, className) {
  const row = body.insertRow();
  row.className = className;
  const perDay = r.days_worked ? hoursMinutes(r.counted_s / r.days_worked) : "–";
  const values = [name, String(r.days_worked), hoursMinutes(r.work_s), hoursMinutes(r.break_s), hoursMinutes(r.counted_s), perDay, hoursMinutes(r.distraction_s)];
  const cells = values.map((text) => {
    const cell = row.insertCell();
    cell.textContent = text;
    return cell;
  });
  if (maxima) {
    shade(cells[4], r.counted_s, maxima.counted, "91, 147, 214");
    shade(cells[6], r.distraction_s, maxima.distraction, "185, 128, 108");
  }
}

function renderWeeks() {
  const body = $("weeks").tBodies[0];
  body.replaceChildren();
  const maxima = {
    counted: Math.max(...month.weeks.map((w) => w.counted_s)),
    distraction: Math.max(...month.weeks.map((w) => w.distraction_s)),
  };
  const short = { month: "short", day: "numeric" };
  for (const w of month.weeks) {
    const partial = !w.start.startsWith(month.month) || !w.end.startsWith(month.month);
    statsRow(body, `${dayLabel(w.start, short)} – ${dayLabel(w.end, short)}`, w, maxima, partial ? "partial" : "");
  }
  statsRow(body, dayLabel(`${month.month}-01`, { month: "long", year: "numeric" }), month.total, null, "total");
}

async function renderDay() {
  $("day-title").textContent = dayLabel(selectedDay, { weekday: "long", month: "long", day: "numeric" });
  let day;
  try {
    day = await api("GET", `/api/days/${selectedDay}`);
  } catch (e) {
    $("msg").textContent = e.message;
    return;
  }
  if (day.day !== selectedDay) return;  // selection moved on while loading
  const totals = $("day-totals");
  totals.replaceChildren();
  const parts = [
    ["counted", `${hoursMinutes(day.counted_s)} of ${hoursMinutes(day.target_s)} (${Math.round(100 * day.progress)}%)`],
    ["work", hoursMinutes(day.work_s)],
    ["credited break", hoursMinutes(day.break_s)],
    ["distraction", hoursMinutes(day.distraction_s)],
  ];
  parts.forEach(([name, value], i) => {
    const strong = document.createElement("b");
    strong.textContent = value;
    totals.append(`${i ? " · " : ""}${name} `, strong);
  });
  const body = $("day-sessions").tBodies[0];
  body.replaceChildren();
  $("empty").hidden = day.sessions.length > 0;
  $("day-sessions").hidden = day.sessions.length === 0;
  for (const s of day.sessions) appendSessionRow(body, s, s.end ? "" : "active", hoursMinutes);
}

function selectDay(day) {
  selectedDay = day;
  renderChart();
  renderDay();
}

// Day to select when a month is first shown: today if it is in the month,
// otherwise the last day with any counted time, otherwise the first day.
function defaultDay() {
  if (month.today.startsWith(month.month)) return month.today;
  const worked = month.days.filter((d) => d.counted_s > 0);
  return (worked.length ? worked[worked.length - 1] : month.days[0]).day;
}

async function loadMonth(key, keepSelection) {
  try {
    month = await api("GET", `/api/months/${key}`);
  } catch (e) {
    $("msg").textContent = `Cannot load the month: ${e.message}`;
    return;
  }
  $("msg").textContent = "";
  $("month-title").textContent = dayLabel(`${month.month}-01`, { month: "long", year: "numeric" });
  if (!keepSelection || !selectedDay || !selectedDay.startsWith(month.month)) selectedDay = defaultDay();
  renderChart();
  renderWeeks();
  renderDay();
}

function moveDay(delta) {
  const index = month.days.findIndex((d) => d.day === selectedDay);
  const next = Math.min(month.days.length - 1, Math.max(0, index + delta));
  if (next !== index) selectDay(month.days[next].day);
}

const ACTIONS = {
  prev: () => loadMonth(shiftMonth(month.month, -1), false),
  next: () => loadMonth(shiftMonth(month.month, 1), false),
  current: () => { selectedDay = null; loadMonth("current", false); },
  back: () => { window.location.href = "/"; },
};
const KEYS = {
  "[": "prev", "]": "next", t: "current", v: "back",
  ArrowLeft: () => moveDay(-1), h: () => moveDay(-1), ArrowRight: () => moveDay(1), l: () => moveDay(1),
};

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || !month) return;
  const action = KEYS[event.key];
  if (!action) return;
  event.preventDefault();
  if (typeof action === "function") action();
  else ACTIONS[action]();
});
for (const id of Object.keys(ACTIONS)) {
  $(id).addEventListener("click", (event) => { event.currentTarget.blur(); ACTIONS[id](); });
}

loadMonth("current", false);
// Keep the current numbers fresh while the page stays open.
setInterval(() => { if (month) loadMonth(month.month, true); }, 60000);
