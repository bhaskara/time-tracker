# timetracker.web

The browser client: static pages served by the API server (`/`, `/review.html`
and `/signoff.html`).
Plain JavaScript, no build step.

- `index.html`, `app.js` — the day view: polls `/api/status`, renders the
  timer, progress, session list and working-memory panel, and handles the
  keyboard shortcuts.
- `review.html`, `review.js` — the review page: a bar per day for a month,
  the selected day's sessions (editable as on the day view) with that day's
  working memory beside them, and weekly and monthly totals.
- `signoff.html`, `signoff.js` — the shutdown view: the day's summary,
  today's working memory and the starting notes for the next day.
- `markdown.js` — small Markdown renderer for the working memory.
- `common.js` — helpers shared by the pages, including `SessionTable`, the
  selectable, editable session list used by the day view and the review page.
- `style.css` — matte dark theme for all pages.
