// Time Tracker shutdown view: shows the day's summary and lets the user tidy
// today's working memory and write the starting notes for the next day
// before signing off. Uses common.js.
"use strict";

let day = null;       // response of /api/days/today
let saveTimer = null;
let dirty = false;

function renderSummary() {
  $("title").textContent = `Sign off · ${new Date(`${day.day}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}`;
  const totals = $("day-totals");
  totals.replaceChildren();
  const parts = [
    ["counted", `${duration(day.counted_s)} of ${duration(day.target_s)} (${Math.round(100 * day.progress)}%)`],
    ["work", duration(day.work_s)],
    ["credited break", duration(day.break_s)],
    ["distraction", duration(day.distraction_s)],
  ];
  parts.forEach(([name, value], i) => {
    const strong = document.createElement("b");
    strong.textContent = value;
    totals.append(`${i ? " · " : ""}${name} `, strong);
  });
  if (day.signed_off_at) totals.append(` · already signed off at ${timeOfDay(day.signed_off_at)}`);
  const body = $("day-sessions").tBodies[0];
  body.replaceChildren();
  $("empty").hidden = day.sessions.length > 0;
  $("day-sessions").hidden = day.sessions.length === 0;
  for (const s of day.sessions) appendSessionRow(body, s, s.end ? "" : "active");
}

// What to send when saving. Before sign-off an empty right-hand box is not
// saved, so backing out does not make the next day start empty.
function payload(final) {
  const body = { body: $("today-notes").value };
  const seed = $("next-notes").value;
  if (final || seed !== "") body.seed_next = seed;
  return body;
}

async function save(final) {
  clearTimeout(saveTimer);
  const sent = payload(final);
  const notes = await api("PUT", `/api/days/${day.day}/notes`, sent);
  if ($("today-notes").value === sent.body) dirty = false;
  $("save-status").textContent = `saved ${timeOfDay(notes.updated_at)}`;
}

function scheduleSave() {
  dirty = true;
  $("save-status").textContent = "editing…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => save(false).catch((e) => { $("save-status").textContent = `not saved: ${e.message}`; }), 800);
}

async function signOff() {
  try {
    await save(true);
    await api("POST", `/api/days/${day.day}/signoff`);
  } catch (e) {
    $("msg").textContent = `Could not sign off: ${e.message}`;
    return;
  }
  window.location.href = "/";
}

async function goBack() {
  try {
    if (dirty) await save(false);
  } catch (e) {
    $("msg").textContent = `Not saved: ${e.message}`;
    return;
  }
  window.location.href = "/";
}

function copyAcross() {
  $("next-notes").value = $("today-notes").value;
  scheduleSave();
  $("next-notes").focus();
}

async function load() {
  try {
    day = await api("GET", "/api/days/today");
    const notes = await api("GET", "/api/days/today/notes");
    $("today-notes").value = notes.body;
    $("next-notes").value = notes.seed_next || "";
  } catch (e) {
    $("msg").textContent = `Cannot load: ${e.message}`;
    return;
  }
  renderSummary();
  $("today-notes").focus();
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    signOff();
  } else if (event.key === "c" && event.altKey) {
    event.preventDefault();
    copyAcross();
  } else if (event.key === "Escape") {
    if (event.target.tagName === "TEXTAREA") event.target.blur();
    else goBack();
  }
});
$("today-notes").addEventListener("input", scheduleSave);
$("next-notes").addEventListener("input", scheduleSave);
$("copy").addEventListener("click", copyAcross);
$("confirm").addEventListener("click", signOff);
$("cancel").addEventListener("click", goBack);

load();
