from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "instance", "aura.db")

app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = os.environ.get("AURA_SECRET_KEY", "aura-locked-in-dev-key")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        os.makedirs(app.instance_path, exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'Beginner',
            xp INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            profile_image TEXT,
            theme TEXT NOT NULL DEFAULT 'cyber-pink',
            bio TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            color TEXT NOT NULL,
            weekly_goal INTEGER NOT NULL DEFAULT 7,
            completed_today INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            xp_reward INTEGER NOT NULL DEFAULT 20,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            completed_on TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (habit_id, completed_on),
            FOREIGN KEY (habit_id) REFERENCES habits (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            xp_reward INTEGER NOT NULL DEFAULT 50,
            color TEXT NOT NULL,
            notes TEXT,
            resource_link TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS skill_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            locked INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (skill_id) REFERENCES skills (id)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_name TEXT NOT NULL,
            company TEXT NOT NULL,
            applied_date TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            hr_contact TEXT,
            follow_up TEXT,
            link TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            minutes INTEGER NOT NULL,
            completed_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            mood TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS schedule_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_time TEXT,
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Planned',
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )
    ensure_column("users", "profile_image", "TEXT")
    ensure_column("users", "theme", "TEXT NOT NULL DEFAULT 'cyber-pink'")
    ensure_column("users", "bio", "TEXT")
    ensure_column("skills", "notes", "TEXT")
    ensure_column("skills", "resource_link", "TEXT")
    ensure_column("jobs", "follow_up", "TEXT")
    ensure_column("jobs", "link", "TEXT")
    db.execute("UPDATE skill_topics SET locked = 0")
    db.commit()
    seed_demo_data()


def ensure_column(table: str, column: str, definition: str) -> None:
    columns = [row["name"] for row in get_db().execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        get_db().execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_demo_data() -> None:
    db = get_db()
    existing = query_one("SELECT id FROM users WHERE email = ?", ("demo@aura.app",))
    if existing:
        migrate_demo_to_fresh_start(existing["id"])
        return

    now = datetime.utcnow().isoformat()
    cursor = db.execute(
        """
        INSERT INTO users (name, email, password_hash, level, xp, streak, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Aura Starter",
            "demo@aura.app",
            generate_password_hash("lockedin"),
            "Beginner",
            0,
            0,
            now,
        ),
    )
    user_id = cursor.lastrowid
    create_starter_records(user_id)
    db.commit()


def migrate_demo_to_fresh_start(user_id: int) -> None:
    marker = query_one("SELECT value FROM app_meta WHERE key = ?", ("fresh_demo_v2",))
    if marker:
        return
    db = get_db()
    db.execute("DELETE FROM habit_logs WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM habits WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM skill_topics WHERE skill_id IN (SELECT id FROM skills WHERE user_id = ?)", (user_id,))
    db.execute("DELETE FROM skills WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM jobs WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM pomodoro_sessions WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
    db.execute("UPDATE users SET level = 'Beginner', xp = 0, streak = 0 WHERE id = ?", (user_id,))
    create_starter_records(user_id)
    db.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", ("fresh_demo_v2", datetime.utcnow().isoformat()))
    db.commit()


@app.before_request
def ensure_database() -> None:
    init_db()
    if session.get("user_id"):
        sync_user_stats(session["user_id"])


def current_user() -> sqlite3.Row | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


@app.context_processor
def inject_user() -> dict:
    return {"current_user": current_user()}


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if current_user() is None:
            flash("Enter Locked In Mode to continue.", "info")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def level_for_xp(xp: int) -> str:
    if xp >= 3000:
        return "Discipline Demon"
    if xp >= 1500:
        return "Locked In"
    if xp >= 600:
        return "Consistent"
    return "Beginner"


def calculate_habit_streak(habit_id: int) -> int:
    logs = query_all("SELECT completed_on FROM habit_logs WHERE habit_id = ? ORDER BY completed_on DESC", (habit_id,))
    completed_days = {row["completed_on"] for row in logs}
    cursor_day = date.today()
    streak = 0
    while cursor_day.isoformat() in completed_days:
        streak += 1
        cursor_day -= timedelta(days=1)
    return streak


def get_habits_with_tracking(user_id: int, limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM habits WHERE user_id = ? ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = []
    today = date.today().isoformat()
    for habit in query_all(sql, (user_id,)):
        item = dict(habit)
        item["completed_today"] = 1 if query_one(
            "SELECT id FROM habit_logs WHERE habit_id = ? AND completed_on = ?",
            (habit["id"], today),
        ) else 0
        item["streak"] = calculate_habit_streak(habit["id"])
        rows.append(item)
    return rows


def user_activity_streak(user_id: int) -> int:
    habit_days = {row["completed_on"] for row in query_all("SELECT DISTINCT completed_on FROM habit_logs WHERE user_id = ?", (user_id,))}
    focus_days = {
        row["completed_at"][:10]
        for row in query_all("SELECT completed_at FROM pomodoro_sessions WHERE user_id = ?", (user_id,))
    }
    active_days = habit_days | focus_days
    cursor_day = date.today()
    streak = 0
    while cursor_day.isoformat() in active_days:
        streak += 1
        cursor_day -= timedelta(days=1)
    return streak


def sync_user_stats(user_id: int) -> None:
    user = query_one("SELECT xp FROM users WHERE id = ?", (user_id,))
    if not user:
        return
    get_db().execute(
        "UPDATE users SET streak = ?, level = ? WHERE id = ?",
        (user_activity_streak(user_id), level_for_xp(user["xp"]), user_id),
    )
    get_db().commit()


def recalculate_skill_progress(skill_id: int) -> None:
    counts = query_one(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS done
        FROM skill_topics
        WHERE skill_id = ?
        """,
        (skill_id,),
    )
    total = counts["total"] or 0
    done = counts["done"] or 0
    progress = round((done / total) * 100) if total else 0
    get_db().execute("UPDATE skills SET progress = ? WHERE id = ?", (progress, skill_id))
    get_db().commit()


def weekly_counts(user_id: int) -> list[int]:
    values = []
    today = date.today()
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        habit_count = query_one("SELECT COUNT(*) AS count FROM habit_logs WHERE user_id = ? AND completed_on = ?", (user_id, day))["count"]
        focus_count = query_one(
            "SELECT COUNT(*) AS count FROM pomodoro_sessions WHERE user_id = ? AND substr(completed_at, 1, 10) = ?",
            (user_id, day),
        )["count"]
        values.append(habit_count + focus_count)
    return values


def weekly_study_hours(user_id: int) -> list[float]:
    values = []
    today = date.today()
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        row = query_one(
            "SELECT COALESCE(SUM(minutes), 0) AS minutes FROM pomodoro_sessions WHERE user_id = ? AND substr(completed_at, 1, 10) = ?",
            (user_id, day),
        )
        values.append(round(row["minutes"] / 60, 2))
    return values


def week_labels() -> list[str]:
    today = date.today()
    return [(today - timedelta(days=offset)).strftime("%a") for offset in range(6, -1, -1)]


def dashboard_metrics(user_id: int) -> dict:
    habits = get_habits_with_tracking(user_id)
    completed = sum(row["completed_today"] for row in habits)
    total = len(habits) or 1
    pomodoros = query_all("SELECT * FROM pomodoro_sessions WHERE user_id = ?", (user_id,))
    today_minutes = sum(row["minutes"] for row in pomodoros if row["completed_at"].startswith(date.today().isoformat()))
    jobs = query_all("SELECT * FROM jobs WHERE user_id = ?", (user_id,))
    skills = query_all("SELECT * FROM skills WHERE user_id = ?", (user_id,))
    return {
        "habit_completion": round((completed / total) * 100),
        "completed_habits": completed,
        "total_habits": total,
        "today_xp": sum(row["xp_reward"] for row in habits if row["completed_today"]) + today_minutes * 2,
        "focus_minutes": today_minutes,
        "applications": len(jobs),
        "interviews": len([job for job in jobs if job["status"] in ("Interview", "Selected")]),
        "skill_average": round(sum(skill["progress"] for skill in skills) / (len(skills) or 1)),
    }


@app.route("/")
def landing():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = query_one("SELECT * FROM users WHERE email = ?", (email,))
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back. Your comeback is online.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="login")


@app.route("/signup", methods=("GET", "POST"))
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if not name or not email or not password:
            flash("Fill all fields to start your aura system.", "error")
        else:
            try:
                cursor = get_db().execute(
                    """
                    INSERT INTO users (name, email, password_hash, level, xp, streak, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, email, generate_password_hash(password), "Beginner", 0, 0, datetime.utcnow().isoformat()),
                )
                get_db().commit()
                session.clear()
                session["user_id"] = cursor.lastrowid
                create_starter_records(cursor.lastrowid)
                flash("Aura created. First level unlocked.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That email already has an Aura account.", "error")
    return render_template("auth.html", mode="signup")


def create_starter_records(user_id: int) -> None:
    db = get_db()
    habits = [
        ("Sleep", "Recovery", "#a78bfa", 7, 20),
        ("Water Intake", "Health", "#38bdf8", 7, 15),
        ("Workout", "Body", "#22c55e", 5, 35),
        ("Skincare", "Care", "#f9a8d4", 7, 15),
        ("Studying", "Mind", "#f472b6", 6, 40),
        ("Coding", "Career", "#c084fc", 6, 45),
        ("Reading", "Growth", "#facc15", 5, 25),
    ]
    for habit, category, color, weekly_goal, xp_reward in habits:
        db.execute(
            "INSERT INTO habits (user_id, name, category, color, weekly_goal, xp_reward) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, habit, category, color, weekly_goal, xp_reward),
        )
    skills = {
        "Python": ["Variables", "Loops", "Functions", "Arrays", "OOP", "File Handling"],
        "SQL": ["SELECT", "JOINs", "Aggregations", "Subqueries", "Indexes", "Normalization"],
        "DBMS": ["ER Models", "Keys", "Transactions", "ACID", "Concurrency", "Recovery"],
        "Git/GitHub": ["Init", "Branching", "Pull Requests", "Merge Conflicts", "Actions", "Releases"],
        "HTML/CSS": ["Semantic HTML", "Flexbox", "Grid", "Responsive UI", "Animations", "Accessibility"],
        "Power BI": ["Data Import", "DAX", "Relationships", "Charts", "Dashboards", "Publishing"],
        "Aptitude": ["Percentages", "Ratios", "Time Work", "Puzzles", "Probability", "Mock Tests"],
        "AI/ML": ["NumPy", "Pandas", "Regression", "Classification", "Model Metrics", "Projects"],
    }
    colors = ["#f472b6", "#a78bfa", "#38bdf8", "#c084fc", "#fb7185", "#facc15", "#22c55e", "#818cf8"]
    for index, (skill, topics) in enumerate(skills.items()):
        skill_id = db.execute(
            "INSERT INTO skills (user_id, name, progress, xp_reward, color) VALUES (?, ?, ?, ?, ?)",
            (user_id, skill, 0, 50, colors[index]),
        ).lastrowid
        db.executemany(
            "INSERT INTO skill_topics (skill_id, title, completed, locked) VALUES (?, ?, ?, ?)",
            [(skill_id, topic, 0, 0) for topic in topics],
        )
    db.commit()


@app.route("/forgot-password")
def forgot_password():
    return render_template("auth.html", mode="forgot")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out. Your progress is waiting.", "info")
    return redirect(url_for("landing"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    metrics = dashboard_metrics(user["id"])
    habits = get_habits_with_tracking(user["id"], limit=5)
    skills = query_all("SELECT * FROM skills WHERE user_id = ? ORDER BY progress DESC LIMIT 5", (user["id"],))
    notes = query_all("SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC LIMIT 2", (user["id"],))
    upcoming = query_all(
        """
        SELECT * FROM schedule_events
        WHERE user_id = ? AND event_date >= ?
        ORDER BY event_date, event_time
        LIMIT 4
        """,
        (user["id"], date.today().isoformat()),
    )
    return render_template(
        "dashboard.html",
        metrics=metrics,
        habits=habits,
        skills=skills,
        notes=notes,
        weekly_labels=week_labels(),
        weekly_values=weekly_counts(user["id"]),
        upcoming=upcoming,
    )


@app.route("/habits", methods=("GET", "POST"))
@login_required
def habits():
    user = current_user()
    if request.method == "POST":
        get_db().execute(
            """
            INSERT INTO habits (user_id, name, category, color, weekly_goal, xp_reward)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                request.form["name"].strip(),
                request.form.get("category", "Custom").strip() or "Custom",
                request.form.get("color", "#f472b6"),
                int(request.form.get("weekly_goal", 7)),
                int(request.form.get("xp_reward", 20)),
            ),
        )
        get_db().commit()
        flash("Custom habit added. Track it from today.", "success")
        return redirect(url_for("habits"))
    rows = get_habits_with_tracking(user["id"])
    return render_template(
        "habits.html",
        habits=rows,
        metrics=dashboard_metrics(user["id"]),
        weekly_labels=week_labels(),
        weekly_values=weekly_counts(user["id"]),
    )


@app.route("/skills", methods=("GET", "POST"))
@login_required
def skills():
    user = current_user()
    if request.method == "POST":
        topics = [topic.strip() for topic in request.form.get("topics", "").splitlines() if topic.strip()]
        skill_id = get_db().execute(
            """
            INSERT INTO skills (user_id, name, progress, xp_reward, color, notes, resource_link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                request.form["name"].strip(),
                0,
                int(request.form.get("xp_reward", 50)),
                request.form.get("color", "#a78bfa"),
                request.form.get("notes", "").strip(),
                request.form.get("resource_link", "").strip(),
            ),
        ).lastrowid
        if topics:
            get_db().executemany(
                "INSERT INTO skill_topics (skill_id, title, completed, locked) VALUES (?, ?, ?, ?)",
                [(skill_id, topic, 0, 0) for topic in topics],
            )
        get_db().commit()
        flash("Custom skill checklist created.", "success")
        return redirect(url_for("skills"))
    rows = query_all("SELECT * FROM skills WHERE user_id = ?", (user["id"],))
    topics = query_all(
        """
        SELECT skill_topics.*, skills.name AS skill_name
        FROM skill_topics JOIN skills ON skill_topics.skill_id = skills.id
        WHERE skills.user_id = ?
        """,
        (user["id"],),
    )
    topic_map: dict[int, list[sqlite3.Row]] = {}
    for topic in topics:
        topic_map.setdefault(topic["skill_id"], []).append(topic)
    return render_template("skills.html", skills=rows, topic_map=topic_map)


@app.route("/pomodoro")
@login_required
def pomodoro():
    user = current_user()
    sessions = query_all("SELECT * FROM pomodoro_sessions WHERE user_id = ? ORDER BY completed_at DESC", (user["id"],))
    total_minutes = sum(row["minutes"] for row in sessions)
    return render_template("pomodoro.html", sessions=sessions, total_minutes=total_minutes)


@app.route("/jobs", methods=("GET", "POST"))
@login_required
def jobs():
    user = current_user()
    if request.method == "POST":
        get_db().execute(
            """
            INSERT INTO jobs (user_id, job_name, company, applied_date, stage, status, notes, hr_contact, follow_up, link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                request.form["job_name"].strip(),
                request.form["company"].strip(),
                request.form.get("applied_date") or date.today().isoformat(),
                request.form.get("stage", "Applied"),
                request.form.get("status", "Applied"),
                request.form.get("notes", "").strip(),
                request.form.get("hr_contact", "").strip(),
                request.form.get("follow_up", "").strip(),
                request.form.get("link", "").strip(),
            ),
        )
        get_db().commit()
        flash("Application added to your tracker.", "success")
        return redirect(url_for("jobs"))
    rows = query_all("SELECT * FROM jobs WHERE user_id = ? ORDER BY applied_date DESC", (user["id"],))
    return render_template("jobs.html", jobs=rows)


@app.route("/schedule", methods=("GET", "POST"))
@login_required
def schedule():
    user = current_user()
    if request.method == "POST":
        get_db().execute(
            """
            INSERT INTO schedule_events (user_id, title, event_date, event_time, category, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                request.form["title"].strip(),
                request.form["event_date"],
                request.form.get("event_time", ""),
                request.form.get("category", "Study"),
                request.form.get("status", "Planned"),
                request.form.get("notes", "").strip(),
                datetime.utcnow().isoformat(),
            ),
        )
        get_db().commit()
        flash("Schedule item added.", "success")
        return redirect(url_for("schedule"))
    events = query_all(
        "SELECT * FROM schedule_events WHERE user_id = ? ORDER BY event_date, event_time",
        (user["id"],),
    )
    return render_template("schedule.html", events=events)


@app.route("/analytics")
@login_required
def analytics():
    user = current_user()
    metrics = dashboard_metrics(user["id"])
    habits = get_habits_with_tracking(user["id"])
    skills = query_all("SELECT name, progress, color FROM skills WHERE user_id = ?", (user["id"],))
    return render_template("analytics.html", metrics=metrics, habits=habits, skills=skills)


@app.route("/notes", methods=("GET", "POST"))
@login_required
def notes():
    user = current_user()
    if request.method == "POST":
        if request.form.get("form_type") == "resource":
            get_db().execute(
                "INSERT INTO resources (user_id, title, url, category, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    user["id"],
                    request.form["title"].strip(),
                    request.form["url"].strip(),
                    request.form.get("category", "Sheet").strip() or "Sheet",
                    datetime.utcnow().isoformat(),
                ),
            )
            flash("Sheet or link saved.", "success")
        else:
            get_db().execute(
                "INSERT INTO notes (user_id, title, body, mood, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    user["id"],
                    request.form["title"].strip() or "Reflection",
                    request.form["body"].strip(),
                    request.form["mood"].strip() or "Focused",
                    datetime.utcnow().isoformat(),
                ),
            )
            flash("+30 XP for reflection saved.", "success")
        get_db().commit()
        return redirect(url_for("notes"))
    rows = query_all("SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
    resources = query_all("SELECT * FROM resources WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
    return render_template("notes.html", notes=rows, resources=resources)


@app.route("/profile", methods=("GET", "POST"))
@login_required
def profile():
    user = current_user()
    if request.method == "POST":
        get_db().execute(
            "UPDATE users SET name = ?, email = ?, profile_image = ?, theme = ?, bio = ? WHERE id = ?",
            (
                request.form["name"].strip(),
                request.form["email"].strip().lower(),
                request.form.get("profile_image", "").strip(),
                request.form.get("theme", "cyber-pink"),
                request.form.get("bio", "").strip(),
                user["id"],
            ),
        )
        get_db().commit()
        flash("Profile signal updated.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html")


@app.post("/api/habits/<int:habit_id>/toggle")
@login_required
def toggle_habit(habit_id: int):
    user = current_user()
    habit = query_one("SELECT * FROM habits WHERE id = ? AND user_id = ?", (habit_id, user["id"]))
    if not habit:
        return jsonify({"error": "Habit not found"}), 404
    today = date.today().isoformat()
    existing = query_one("SELECT id FROM habit_logs WHERE habit_id = ? AND completed_on = ?", (habit_id, today))
    completed = 0 if existing else 1
    if existing:
        get_db().execute("DELETE FROM habit_logs WHERE id = ?", (existing["id"],))
    else:
        get_db().execute(
            "INSERT INTO habit_logs (habit_id, user_id, completed_on, created_at) VALUES (?, ?, ?, ?)",
            (habit_id, user["id"], today, datetime.utcnow().isoformat()),
        )
        get_db().execute("UPDATE users SET xp = xp + ? WHERE id = ?", (habit["xp_reward"], user["id"]))
    streak = calculate_habit_streak(habit_id)
    get_db().execute("UPDATE habits SET completed_today = ?, streak = ? WHERE id = ?", (completed, streak, habit_id))
    get_db().commit()
    sync_user_stats(user["id"])
    return jsonify({"completed": completed, "streak": streak, "xp": habit["xp_reward"]})


@app.post("/api/skills/topics/<int:topic_id>/toggle")
@login_required
def toggle_skill_topic(topic_id: int):
    user = current_user()
    topic = query_one(
        """
        SELECT skill_topics.*, skills.user_id, skills.xp_reward
        FROM skill_topics JOIN skills ON skill_topics.skill_id = skills.id
        WHERE skill_topics.id = ? AND skills.user_id = ?
        """,
        (topic_id, user["id"]),
    )
    if not topic or topic["locked"]:
        return jsonify({"error": "Topic not found"}), 404
    completed = 0 if topic["completed"] else 1
    get_db().execute("UPDATE skill_topics SET completed = ? WHERE id = ?", (completed, topic_id))
    if completed:
        get_db().execute("UPDATE users SET xp = xp + ? WHERE id = ?", (topic["xp_reward"], user["id"]))
    get_db().commit()
    recalculate_skill_progress(topic["skill_id"])
    sync_user_stats(user["id"])
    return jsonify({"completed": completed, "xp": topic["xp_reward"]})


@app.post("/api/jobs/<int:job_id>/update")
@login_required
def update_job(job_id: int):
    user = current_user()
    data = request.get_json() or {}
    allowed = {"stage", "status", "follow_up", "notes", "hr_contact"}
    field = data.get("field")
    if field not in allowed:
        return jsonify({"error": "Invalid field"}), 400
    job = query_one("SELECT id FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"]))
    if not job:
        return jsonify({"error": "Job not found"}), 404
    get_db().execute(f"UPDATE jobs SET {field} = ? WHERE id = ?", (data.get("value", ""), job_id))
    get_db().commit()
    return jsonify({"ok": True})


@app.post("/api/pomodoro/complete")
@login_required
def complete_pomodoro():
    user = current_user()
    data = request.get_json() or {}
    minutes = int(data.get("minutes", 25))
    mode = data.get("mode", "25/5")
    get_db().execute(
        "INSERT INTO pomodoro_sessions (user_id, mode, minutes, completed_at) VALUES (?, ?, ?, ?)",
        (user["id"], mode, minutes, datetime.utcnow().isoformat()),
    )
    get_db().execute("UPDATE users SET xp = xp + ? WHERE id = ?", (minutes * 2, user["id"]))
    get_db().commit()
    sync_user_stats(user["id"])
    return jsonify({"xp": minutes * 2, "message": "Focus session complete"})


@app.get("/api/analytics")
@login_required
def analytics_data():
    user = current_user()
    skills = query_all("SELECT name, progress, color FROM skills WHERE user_id = ?", (user["id"],))
    habits = get_habits_with_tracking(user["id"])
    return jsonify(
        {
            "weeklyActivity": weekly_counts(user["id"]),
            "weekLabels": week_labels(),
            "studyHours": weekly_study_hours(user["id"]),
            "habitLabels": [row["name"] for row in habits],
            "habitValues": [row["streak"] for row in habits],
            "skillLabels": [row["name"] for row in skills],
            "skillValues": [row["progress"] for row in skills],
            "colors": [row["color"] for row in skills],
        }
    )


@app.get("/api/metrics")
@login_required
def live_metrics():
    user = current_user()
    metrics = dashboard_metrics(user["id"])
    return jsonify(
        {
            "xp": user["xp"],
            "level": user["level"],
            "streak": user_activity_streak(user["id"]),
            "habitCompletion": metrics["habit_completion"],
            "completedHabits": metrics["completed_habits"],
            "totalHabits": metrics["total_habits"],
            "todayXp": metrics["today_xp"],
            "focusMinutes": metrics["focus_minutes"],
            "weeklyActivity": weekly_counts(user["id"]),
            "weekLabels": week_labels(),
        }
    )


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, use_reloader=False)
