# timetracker.web

The browser client: static pages served by the API server (`/` and
`/review.html`).
Plain JavaScript, no build step.

- `index.html`, `app.js` — the day view: polls `/api/status`, renders the
  timer, progress and session list, and handles the keyboard shortcuts.
- `review.html`, `review.js` — the review page: a bar per day for a month,
  the selected day's sessions, and weekly and monthly totals.
- `common.js` — helpers shared by both pages.
- `style.css` — matte dark theme for both pages.
