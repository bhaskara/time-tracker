# timetracker.web

The browser client: a single static page served by the API server at `/`.
Plain JavaScript, no build step.

- `index.html` — page structure.
- `style.css` — matte dark theme.
- `app.js` — polls `/api/status`, renders the timer, progress and session
  list, and handles the keyboard shortcuts.
