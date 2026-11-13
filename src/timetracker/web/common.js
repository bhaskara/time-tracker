// Helpers shared by the day view (app.js) and the review page (review.js).
"use strict";

const $ = (id) => document.getElementById(id);

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "content-type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail);
  }
  return data;
}

function duration(seconds) {
  if (seconds > 0 && seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
}

function timeOfDay(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// Hours and minutes as "8:25" (used on the review page).
function hoursMinutes(seconds) {
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}

// fmt formats a number of seconds; pages choose duration or hoursMinutes.
function accountingNote(s, fmt) {
  if (s.type === "work") {
    const over = s.duration_s - s.planned_s;
    return over > 60 ? `${fmt(over)} past planned ${fmt(s.planned_s)}` : `planned ${fmt(s.planned_s)}`;
  }
  if (s.type === "break") return `${fmt(s.counted_s)} credited`;
  return `charged ${fmt(s.distraction_s)} (includes switch cost)`;
}

// Cells of one row of a session table: [css class, text] pairs.
function sessionCells(s, fmt) {
  return [
    ["time", `${timeOfDay(s.start)} – ${s.end ? timeOfDay(s.end) : "now"}`],
    [`type type-${s.type}`, s.type],
    ["", s.label],
    ["num", fmt(s.duration_s)],
    ["note", accountingNote(s, fmt)],
  ];
}

function appendSessionRow(body, s, className, fmt = duration) {
  const row = body.insertRow();
  row.className = className || "";
  for (const [cls, text] of sessionCells(s, fmt)) {
    const cell = row.insertCell();
    cell.className = cls;
    cell.textContent = text;
  }
  return row;
}
