// Helpers shared by the day view (app.js) and the review page (review.js),
// including SessionTable, the selectable and editable list of a day's sessions.
"use strict";

const $ = (id) => document.getElementById(id);

// API paths are written as "/api/..." but fetched relative to the page, so the
// same pages serve the default workspace at "/" and any other under
// "/w/<name>/". Only "/api/workspaces" (the list of all of them) is absolute.
async function api(method, path, body) {
  const url = path === "/api/workspaces" ? path : path.replace(/^\//, "");
  const response = await fetch(url, {
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

// Local "HH:MM" of an ISO timestamp, as used by <input type="time">.
function hhmm(iso) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// ISO timestamp for a local "HH:MM" on tracking day `day` ("YYYY-MM-DD").
// Times before the day-start hour belong to the following calendar date.
function dayTimeIso(day, time, dayStartHour) {
  const [year, month, date] = day.split("-").map(Number);
  const [hours, minutes] = time.split(":").map(Number);
  const nextDate = hours < dayStartHour ? 1 : 0;
  return new Date(year, month - 1, date + nextDate, hours, minutes).toISOString();
}

// One day's sessions as a table whose rows can be selected (click, or
// moveSelection), edited inline (double-click, or startEdit), added, deleted
// (deleteSelected, which asks for a second press) and given a following break.
// The page feeds it data with setDay and binds keys to its methods; after any
// change it calls the page's reload, which is expected to fetch fresh data and
// call setDay again.
class SessionTable {
  // table: the <table> (one tbody); empty: element shown when there are no
  // sessions; showMessage(text): status line; reload(): async refetch;
  // newestFirst: list order.
  constructor({ table, empty, showMessage, reload, newestFirst = false }) {
    Object.assign(this, { table, empty, showMessage, reload, newestFirst });
    this.day = null;
    this.sessions = [];
    this.dayStartHour = 0;
    // The highlighted row, the row being edited ({id} for an existing
    // session, {id: null} for a new one), and the row for which a first
    // delete has been pressed.
    this.selectedId = null;
    this.editing = null;
    this.armedDelete = null;
  }

  // Show `sessions` (chronological) of tracking day `day`. Switching to
  // another day drops the selection and any open edit.
  setDay(day, sessions, dayStartHour) {
    if (day !== this.day) {
      this.selectedId = null;
      this.editing = null;
      this.armedDelete = null;
    }
    this.day = day;
    this.sessions = sessions;
    this.dayStartHour = dayStartHour;
    this.render();
  }

  listOrder() {
    return this.newestFirst ? [...this.sessions].reverse() : this.sessions;
  }

  form() {
    return this.table.querySelector("#edit-form");
  }

  // Run an API call, reload, then show the server's reason if it refused.
  async act(method, path, body) {
    this.showMessage("");
    let error = null;
    try {
      await api(method, path, body);
    } catch (e) {
      error = e;
    }
    await this.reload();
    if (error) this.showMessage(error.message);
  }

  render() {
    // Leave the table alone while a row is being edited, so polling does not
    // wipe what is being typed.
    if (this.editing && this.form()) return;
    const body = this.table.tBodies[0];
    body.replaceChildren();
    const sessions = this.listOrder();
    if (!sessions.some((s) => s.id === this.selectedId)) this.selectedId = null;
    const adding = this.editing && this.editing.id === null;
    this.empty.hidden = sessions.length > 0 || adding;
    this.table.hidden = sessions.length === 0 && !adding;
    if (adding) this.appendEditRow(body, null);
    for (const s of sessions) {
      if (this.editing && this.editing.id === s.id) {
        this.appendEditRow(body, s);
        continue;
      }
      const className = [s.end ? "" : "active", s.id === this.selectedId ? "selected" : ""].join(" ").trim();
      const row = appendSessionRow(body, s, className);
      // Click selects the row; double-click opens it for editing.
      row.addEventListener("click", () => {
        this.selectedId = s.id;
        this.armedDelete = null;
        this.showMessage("");
        this.render();
      });
      row.addEventListener("dblclick", () => this.startEdit(s.id));
    }
  }

  // Inline form for editing a session (or creating one when s is null).
  appendEditRow(body, s) {
    const row = body.insertRow();
    row.className = "edit";
    const cell = row.insertCell();
    cell.colSpan = 5;
    const form = document.createElement("form");
    form.id = "edit-form";
    form.autocomplete = "off";
    form.innerHTML = `
      <select name="type" aria-label="Type">
        <option value="work">work</option><option value="break">break</option><option value="distraction">distraction</option>
      </select>
      <input name="start" type="time" aria-label="Start" required>
      <span class="unit">to</span>
      <input name="end" type="time" aria-label="End">
      <input name="label" type="text" placeholder="Label" aria-label="Label">
      <input name="planned" type="number" min="0.05" step="any" aria-label="Planned minutes">
      <span class="unit">min planned</span>
      <button type="submit">Save</button>
      <button type="button" name="remove">Delete</button>`;
    const f = form.elements;
    if (s) {
      f.type.value = s.type;
      f.start.value = hhmm(s.start);
      f.end.value = s.end ? hhmm(s.end) : "";
      f.label.value = s.label;
      f.planned.value = s.planned_s ? s.planned_s / 60 : "";
      f.remove.addEventListener("click", () => {
        this.editing = null;
        this.act("DELETE", `/api/sessions/${s.id}`);
      });
    } else {
      f.end.required = true;
      f.remove.hidden = true;
    }
    form.addEventListener("submit", (event) => { event.preventDefault(); this.saveEdit(form, s); });
    cell.append(form);
  }

  moveSelection(delta) {
    const list = this.listOrder();
    if (!list.length || this.editing) return;
    const index = list.findIndex((s) => s.id === this.selectedId);
    const next = index < 0 ? (delta > 0 ? 0 : list.length - 1) : Math.min(list.length - 1, Math.max(0, index + delta));
    this.selectedId = list[next].id;
    this.armedDelete = null;
    this.showMessage("");
    this.render();
  }

  // Open the inline form for session `id`, or for a new session when null.
  startEdit(id) {
    this.editing = { id };
    this.render();
    this.form().elements[id === null ? "type" : "start"].focus();
  }

  editSelected() {
    if (this.selectedId) this.startEdit(this.selectedId);
  }

  // Close an open edit form; returns whether one was open.
  cancelEdit() {
    if (!this.editing) return false;
    this.editing = null;
    this.render();
    return true;
  }

  clearSelection() {
    this.selectedId = null;
    this.armedDelete = null;
    this.showMessage("");
    this.render();
  }

  // Send only what changed, so untouched times keep their seconds.
  async saveEdit(form, s) {
    const f = form.elements;
    const toIso = (time) => dayTimeIso(this.day, time, this.dayStartHour);
    const planned = f.type.value === "work" && f.planned.value ? Number(f.planned.value) : null;
    let method, path;
    const body = {};
    if (!s) {
      method = "POST";
      path = "/api/sessions";
      Object.assign(body, { type: f.type.value, label: f.label.value.trim(), start: toIso(f.start.value), end: toIso(f.end.value) });
      if (planned) body.planned_minutes = planned;
    } else {
      method = "PATCH";
      path = `/api/sessions/${s.id}`;
      if (f.type.value !== s.type) body.type = f.type.value;
      if (f.label.value.trim() !== s.label) body.label = f.label.value.trim();
      if (f.start.value !== hhmm(s.start)) body.start = toIso(f.start.value);
      const originalEnd = s.end ? hhmm(s.end) : "";
      if (f.end.value !== originalEnd) {
        if (f.end.value) body.end = toIso(f.end.value);
        else body.reopen = true;
      }
      if (planned && planned !== (s.planned_s || 0) / 60) body.planned_minutes = planned;
    }
    try {
      if (Object.keys(body).length) await api(method, path, body);
    } catch (e) {
      // Keep the form open so the entry can be corrected.
      this.showMessage(e.message);
      return;
    }
    this.showMessage("");
    this.editing = null;
    await this.reload();
  }

  deleteSelected() {
    if (!this.selectedId || this.editing) return;
    if (this.armedDelete !== this.selectedId) {
      this.armedDelete = this.selectedId;
      this.showMessage("Press x (or Delete) again to delete the selected session.");
      return;
    }
    this.armedDelete = null;
    this.act("DELETE", `/api/sessions/${this.selectedId}`);
  }

  // Record the break that followed the selected (finished work) session.
  breakAfterSelected() {
    if (!this.selectedId || this.editing) {
      this.showMessage("Select a finished work session first (j / k).");
      return;
    }
    this.act("POST", `/api/sessions/${this.selectedId}/break`);
  }
}

// Workspace switcher: a small tab strip in the top-left corner, shown when
// the server has more than one workspace. The current workspace is found
// from the page's path; a dot marks a workspace with a session running.
// The "o" key moves to the next workspace, staying on the same kind of page.
class WorkspaceBar {
  constructor() {
    this.workspaces = [];
    this.current = null;
    this.nav = document.createElement("nav");
    this.nav.id = "workspaces";
    this.nav.hidden = true;
    document.body.prepend(this.nav);
    document.addEventListener("keydown", (event) => {
      if (event.ctrlKey || event.metaKey || event.altKey || event.key !== "o") return;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
      const next = this.next();
      if (next) window.location.href = this.urlFor(next);
    });
    this.refresh();
    setInterval(() => this.refresh(), 15000);
  }

  // Same page (day view, review, sign-off) in another workspace.
  urlFor(workspace) {
    return workspace.path + window.location.pathname.split("/").pop();
  }

  next() {
    if (this.workspaces.length < 2) return null;
    const index = this.workspaces.findIndex((w) => w.name === this.current.name);
    return this.workspaces[(index + 1) % this.workspaces.length];
  }

  async refresh() {
    try {
      this.workspaces = await api("GET", "/api/workspaces");
    } catch (e) {
      return;  // The page itself reports an unreachable server.
    }
    // The longest matching path wins, so "/" only matches when nothing else does.
    const here = window.location.pathname;
    this.current = this.workspaces
      .filter((w) => here.startsWith(w.path))
      .sort((a, b) => b.path.length - a.path.length)[0];
    this.render();
  }

  render() {
    this.nav.hidden = this.workspaces.length < 2;
    this.nav.replaceChildren();
    for (const w of this.workspaces) {
      const link = document.createElement("a");
      link.href = this.urlFor(w);
      link.textContent = w.name;
      if (w.name === this.current.name) link.className = "current";
      if (w.active) {
        link.classList.add("running");
        link.title = `${w.active.type} running${w.active.label ? `: ${w.active.label}` : ""}`;
      }
      this.nav.append(link);
    }
    if (!this.current.default && !document.title.endsWith(` · ${this.current.name}`)) {
      document.title += ` · ${this.current.name}`;
    }
  }
}

const workspaceBar = new WorkspaceBar();
