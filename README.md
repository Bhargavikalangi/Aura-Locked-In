# Aura: Locked In

Aura: Locked In is a Flask + SQLite full-stack starter app for self-improvement, productivity, career tracking, and comeback planning.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`.

The app creates `instance/aura.db` automatically. The demo account starts fresh at 0 XP and 0 streak so habits, Pomodoro sessions, and analytics track from the day you actually use it.

## Custom Planner Features

- Add your own habits, weekly goals, colors, and XP rewards.
- Create your own skill checklists by typing one topic per line.
- Track jobs with follow-up reminders, HR contacts, notes, and job links.
- Update job stage and status from spreadsheet-style dropdowns.
- Add schedule/calendar items for study blocks, interviews, deadlines, reminders, and follow-ups.
- Save sheets, course links, drive links, and motivation resources.
- Customize profile picture, bio, and one of ten themes: Barbie Pink, Cyber Blue, Lavender Soft, Dark Red Vampire, Green Forest Focus, Anime Dream, Marvel Hero, Waterfall Calm, Robotics Lab, and Sky Blue.
- Main tracker actions refresh visible stats immediately without a browser reload.
- Analytics starts empty and fills from real habits, Pomodoro sessions, and skill checklist progress.

Demo login:

```text
demo@aura.app
lockedin
```

## Structure

```text
app.py                  Flask routes, database schema, seed data, API endpoints
templates/             Jinja pages and shared layout
static/css/styles.css   Cyberpunk glassmorphism design system
static/js/app.js        Charts, timers, XP popups, dashboard interactions
instance/aura.db        Generated SQLite database
```
