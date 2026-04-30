import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        self._migrate()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                location TEXT,
                remote BOOLEAN,
                salary TEXT,
                description TEXT,
                department TEXT,
                seniority TEXT,
                source TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS matches (
                job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                relevance_score REAL NOT NULL,
                match_reason TEXT NOT NULL,
                resume_path TEXT,
                suggestions TEXT,
                matched_at TEXT NOT NULL,
                notified_at TEXT,
                dismissed_at TEXT,
                interview_prep_path TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                jobs_scraped INTEGER DEFAULT 0,
                new_jobs INTEGER DEFAULT 0,
                matches_found INTEGER DEFAULT 0,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS applications (
                job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                status TEXT NOT NULL,
                applied_date TEXT,
                notes TEXT,
                status_updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                follow_up_after TEXT,
                followed_up_at TEXT
            );
            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id),
                old_status TEXT,
                new_status TEXT NOT NULL,
                changed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cost_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                estimated_cost REAL NOT NULL,
                run_id INTEGER REFERENCES runs(id),
                job_id TEXT REFERENCES jobs(id),
                recorded_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def _migrate(self):
        try:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE runs ADD COLUMN current_stage TEXT")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass
        # Close any runs that were left open by a crash
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE runs SET completed_at = ?, error = 'App crashed' WHERE completed_at IS NULL",
            (now,),
        )
        self._conn.commit()

    def upsert_job(
        self,
        *,
        id: str,
        company: str,
        title: str,
        url: str,
        scraped_at: datetime,
        location: str = None,
        remote: bool = None,
        salary: str = None,
        description: str = None,
        department: str = None,
        seniority: str = None,
        source: str = None,
    ):
        now = scraped_at.isoformat()
        self._conn.execute(
            """
            INSERT INTO jobs (id, company, title, url, location, remote, salary,
                            description, department, seniority, source,
                            first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                description = COALESCE(excluded.description, jobs.description),
                salary = COALESCE(excluded.salary, jobs.salary),
                location = COALESCE(excluded.location, jobs.location),
                source = COALESCE(jobs.source, excluded.source),
                closed_at = NULL
        """,
            (
                id,
                company,
                title,
                url,
                location,
                remote,
                salary,
                description,
                department,
                seniority,
                source,
                now,
                now,
            ),
        )

    def commit(self):
        self._conn.commit()

    def update_job_description(self, job_id: str, description: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET description = ? WHERE id = ?",
            (description, job_id),
        )
        self._conn.commit()

    def add_manual_job(
        self,
        job_id: str,
        url: str,
        title: str,
        company: str,
        location: str | None = None,
        salary: str | None = None,
        remote: bool = False,
        description: str | None = None,
    ) -> bool:
        """Insert a manually-added job and a synthetic match row. Returns True if new, False if already existed."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO jobs (id, company, title, url, location, remote, salary,
                              description, source, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                job_id,
                company,
                title,
                url,
                location,
                remote,
                salary,
                description,
                now,
                now,
            ),
        )
        is_new = cur.rowcount > 0
        self._conn.execute(
            """
            INSERT INTO matches (job_id, relevance_score, match_reason, matched_at)
            VALUES (?, 0, 'Manually added', ?)
            ON CONFLICT(job_id) DO NOTHING
            """,
            (job_id, now),
        )
        self._conn.commit()
        return is_new

    def get_job(self, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_new_job_ids(self, candidate_ids: list[str]) -> list[str]:
        existing = set()
        for i in range(0, len(candidate_ids), 500):
            batch = candidate_ids[i : i + 500]
            placeholders = ",".join("?" * len(batch))
            rows = self._conn.execute(
                f"SELECT id FROM jobs WHERE id IN ({placeholders})", batch
            ).fetchall()
            existing.update(r["id"] for r in rows)
        return [cid for cid in candidate_ids if cid not in existing]

    def close_missing_jobs(self, company: str, current_ids: list[str]):
        now = datetime.now(timezone.utc).isoformat()
        if not current_ids:
            self._conn.execute(
                "UPDATE jobs SET closed_at = ? WHERE company = ? AND closed_at IS NULL",
                (now, company),
            )
        else:
            placeholders = ",".join("?" * len(current_ids))
            self._conn.execute(
                f"""UPDATE jobs SET closed_at = ?
                    WHERE company = ? AND closed_at IS NULL
                    AND id NOT IN ({placeholders})""",
                [now, company] + current_ids,
            )
        self._conn.commit()

    def close_job(self, job_id: str):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE jobs SET closed_at = ? WHERE id = ? AND closed_at IS NULL",
            (now, job_id),
        )
        self._conn.commit()

    def insert_match(
        self,
        *,
        job_id: str,
        relevance_score: float,
        match_reason: str,
        suggestions: str = None,
        resume_path: str = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO matches
            (job_id, relevance_score, match_reason, suggestions, resume_path, matched_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (job_id, relevance_score, match_reason, suggestions, resume_path, now),
        )
        self._conn.commit()

    def update_match_paths(
        self,
        job_id: str,
        *,
        resume_path: str = None,
        interview_prep_path: str = None,
    ):
        updates = []
        params = []
        if resume_path:
            updates.append("resume_path = ?")
            params.append(resume_path)
        if interview_prep_path:
            updates.append("interview_prep_path = ?")
            params.append(interview_prep_path)
        if updates:
            params.append(job_id)
            self._conn.execute(
                f"UPDATE matches SET {', '.join(updates)} WHERE job_id = ?", params
            )
            self._conn.commit()

    def update_match_suggestions(self, job_id: str, suggestions: str):
        self._conn.execute(
            "UPDATE matches SET suggestions = ? WHERE job_id = ?", (suggestions, job_id)
        )
        self._conn.commit()

    def dismiss_match(self, job_id: str):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE matches SET dismissed_at = ? WHERE job_id = ?", (now, job_id)
        )
        self._conn.commit()

    def undismiss_match(self, job_id: str):
        self._conn.execute(
            "UPDATE matches SET dismissed_at = NULL WHERE job_id = ?", (job_id,)
        )
        self._conn.commit()

    def get_match(self, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM matches WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_unnotified_matches(self) -> list[dict]:
        rows = self._conn.execute("""
            SELECT m.*, j.company, j.title, j.url, j.location, j.salary, j.description
            FROM matches m JOIN jobs j ON m.job_id = j.id
            WHERE m.notified_at IS NULL
            ORDER BY m.relevance_score DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def mark_notified(self, job_ids: list[str]):
        now = datetime.now(timezone.utc).isoformat()
        for job_id in job_ids:
            self._conn.execute(
                "UPDATE matches SET notified_at = ? WHERE job_id = ?", (now, job_id)
            )
        self._conn.commit()

    def start_run(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now,))
        self._conn.commit()
        return cursor.lastrowid

    def complete_run(
        self,
        run_id: int,
        *,
        jobs_scraped: int,
        new_jobs: int,
        matches_found: int,
        error: str = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE runs SET completed_at = ?, jobs_scraped = ?, new_jobs = ?,
                           matches_found = ?, error = ?
            WHERE id = ?
        """,
            (now, jobs_scraped, new_jobs, matches_found, error, run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def set_application_status(self, job_id: str, status: str):
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_application(job_id)
        old_status = existing["status"] if existing else None

        if existing:
            updates = {"status": status, "status_updated_at": now}
            if status == "applied" and not existing.get("applied_date"):
                updates["applied_date"] = now
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            self._conn.execute(
                f"UPDATE applications SET {set_clause} WHERE job_id = ?",
                list(updates.values()) + [job_id],
            )
        else:
            applied_date = now if status == "applied" else None
            self._conn.execute(
                "INSERT INTO applications (job_id, status, applied_date, status_updated_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, status, applied_date, now, now),
            )

        self._conn.execute(
            "INSERT INTO status_history (job_id, old_status, new_status, changed_at) VALUES (?, ?, ?, ?)",
            (job_id, old_status, status, now),
        )
        self._conn.commit()

    def get_application(self, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_status_history(self, job_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM status_history WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_notes(self, job_id: str, notes: str):
        self._conn.execute(
            "UPDATE applications SET notes = ? WHERE job_id = ?", (notes, job_id)
        )
        self._conn.commit()

    def get_all_applications(self) -> list[dict]:
        rows = self._conn.execute("""
            SELECT m.job_id, j.company, j.title, j.url, j.location, m.relevance_score,
                   COALESCE(a.status, 'new') as status,
                   a.applied_date, a.status_updated_at, a.notes,
                   m.matched_at, m.resume_path, m.match_reason
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            LEFT JOIN applications a ON m.job_id = a.job_id
            WHERE m.dismissed_at IS NULL
              AND (j.closed_at IS NULL
                   OR COALESCE(a.status, 'new') IN ('applied', 'interviewing', 'offer'))
            ORDER BY
                CASE COALESCE(a.status, 'new')
                    WHEN 'interviewing' THEN 1
                    WHEN 'offer' THEN 2
                    WHEN 'applied' THEN 3
                    WHEN 'new' THEN 4
                    WHEN 'rejected' THEN 5
                    WHEN 'withdrawn' THEN 6
                END,
                m.relevance_score DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def set_follow_up_date(self, job_id: str, date_str: str):
        self._conn.execute(
            "UPDATE applications SET follow_up_after = ? WHERE job_id = ?",
            (date_str, job_id),
        )
        self._conn.commit()

    def mark_followed_up(self, job_id: str, reset_days: int = 7):
        now = datetime.now(timezone.utc)
        app = self.get_application(job_id)
        if not app:
            return
        new_follow_up = None
        if app.get("follow_up_after") is not None:
            new_follow_up = (now + timedelta(days=reset_days)).strftime("%Y-%m-%d")
        self._conn.execute(
            "UPDATE applications SET followed_up_at = ?, follow_up_after = ? WHERE job_id = ?",
            (now.isoformat(), new_follow_up, job_id),
        )
        self._conn.commit()

    def get_overdue_follow_ups(self) -> list[dict]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            """
            SELECT a.job_id, j.company, j.title, j.url, a.status,
                   a.applied_date, a.follow_up_after,
                   julianday(?) - julianday(a.follow_up_after) AS days_overdue
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            WHERE a.follow_up_after IS NOT NULL
              AND a.follow_up_after <= ?
              AND a.status IN ('new', 'applied', 'interviewing')
            ORDER BY a.follow_up_after ASC
            """,
            (today, today),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unfiltered_open_job_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT id FROM jobs WHERE id NOT IN (SELECT job_id FROM matches) AND closed_at IS NULL"
        ).fetchall()
        return [r["id"] for r in rows]

    def get_active_matches(self) -> list[dict]:
        rows = self._conn.execute("""
            SELECT m.job_id, j.company, j.title, j.location, m.relevance_score,
                   CASE WHEN m.resume_path IS NOT NULL THEN '✓' ELSE '—' END as has_pdf,
                   COALESCE(a.status, 'new') as status,
                   j.first_seen_at
            FROM matches m JOIN jobs j ON m.job_id = j.id
            LEFT JOIN applications a ON m.job_id = a.job_id
            WHERE j.closed_at IS NULL AND m.dismissed_at IS NULL
            ORDER BY m.relevance_score DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_top_matches(self, limit: int = 15) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT m.job_id, j.company, j.title, m.relevance_score,
                   COALESCE(a.status, 'new') as status
            FROM matches m JOIN jobs j ON m.job_id = j.id
            LEFT JOIN applications a ON m.job_id = a.job_id
            WHERE j.closed_at IS NULL AND m.dismissed_at IS NULL
            ORDER BY m.relevance_score DESC LIMIT ?
        """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_match_stats(self) -> dict:
        row = self._conn.execute("""
            SELECT COUNT(*) as total_matches,
                   AVG(m.relevance_score) as avg_score
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            WHERE j.closed_at IS NULL AND m.dismissed_at IS NULL
        """).fetchone()
        return {
            "total_matches": row["total_matches"] or 0,
            "avg_score": row["avg_score"] or 0.0,
        }

    def count_matches_since(self, since_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM matches WHERE matched_at > ? AND dismissed_at IS NULL",
            (since_iso,),
        ).fetchone()
        return row["cnt"] or 0

    def record_cost_event(
        self,
        *,
        action_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        run_id: int | None = None,
        job_id: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO cost_events
               (action_type, model, input_tokens, output_tokens, estimated_cost, run_id, job_id, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                action_type,
                model,
                input_tokens,
                output_tokens,
                estimated_cost,
                run_id,
                job_id,
                now,
            ),
        )
        self._conn.commit()

    def sum_costs_since(self, since_iso: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(estimated_cost), 0.0) AS total FROM cost_events WHERE recorded_at >= ?",
            (since_iso,),
        ).fetchone()
        return row["total"] or 0.0

    def update_run_stage(self, run_id: int, stage: str) -> None:
        self._conn.execute(
            "UPDATE runs SET current_stage = ? WHERE id = ?", (stage, run_id)
        )
        self._conn.commit()

    def sum_costs_this_month(self) -> float:
        now = datetime.now(timezone.utc)
        month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        return self.sum_costs_since(month_start)

    def sum_costs_total(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(estimated_cost), 0.0) AS total FROM cost_events"
        ).fetchone()
        return row["total"] or 0.0

    def count_runs_today(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM runs WHERE date(started_at) = date('now')"
        ).fetchone()
        return row["cnt"] or 0

    def get_value_summary(self) -> dict:
        jobs = (
            self._conn.execute("SELECT COUNT(*) AS cnt FROM jobs").fetchone()["cnt"]
            or 0
        )
        tailored = (
            self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM matches WHERE resume_path IS NOT NULL"
            ).fetchone()["cnt"]
            or 0
        )
        applied = (
            self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM applications WHERE status NOT IN ('new', 'interested')"
            ).fetchone()["cnt"]
            or 0
        )
        return {"jobs_reviewed": jobs, "tailored": tailored, "applications": applied}

    def close(self) -> None:
        self._conn.close()
