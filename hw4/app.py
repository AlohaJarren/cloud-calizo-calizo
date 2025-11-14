from __future__ import annotations

"""
CS 530 - HW4 (Commit 1 of 6)

Flask shell that reuses the HW2 UI. Uses a simple in-memory list so it
runs cleanly by itself. A Datastore-backed model drops in next.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Final
from flask import Flask, render_template, request, redirect, url_for, flash

# Point Flask at HW2 assets so the UI matches my earlier homework.
REPO_ROOT = Path(__file__).resolve().parents[1]
HW2_PATH = REPO_ROOT / "hw2"
if HW2_PATH.exists():
    sys.path.insert(0, str(HW2_PATH))


def create_app() -> Flask:
    """
    Application factory for HW4.

    This first commit keeps persistence in-memory. The route surfaces
    stay the same so we can swap to Datastore in the next commit
    without churn in templates or handlers.
    """
    template_folder = str(HW2_PATH / "templates") if HW2_PATH.exists() else "templates"
    static_folder = str(HW2_PATH / "static") if HW2_PATH.exists() else "static"

    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")

    # Temporary store. Jinja can access dict fields directly.
    store: list[Dict[str, Any]] = []

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/songs")
    def songs_list():
        return render_template("songs_list.html", songs=store)

    @app.get("/songs/new")
    def songs_new():
        # Used to repopulate fields after a validation error.
        return render_template("songs_new.html", prev={})

    @app.post("/songs")
    def songs_create():
        """
        Create a song with light server-side checks.
        Mirrors HW2 rules so the UX feels the same.
        """
        form = request.form

        def val(name: str) -> Optional[str]:
            v = (form.get(name) or "").strip()
            return v or None

        def to_int(name: str) -> Optional[int]:
            v = val(name)
            if v is None:
                return None
            try:
                return int(v)
            except ValueError:
                return None

        def clamp_month(name: str) -> Optional[int]:
            m = to_int(name)
            if m is None:
                return None
            if m < 1:
                return 1
            if m > 12:
                return 12
            return m

        # Required
        title = val("title")
        if not title:
            flash("Title is required.", "error")
            return render_template("songs_new.html", prev=form)

        # Optional with bounds
        release_year = to_int("release_year")
        if release_year is not None and not (1800 <= release_year <= 2100):
            flash("Release year must be between 1800 and 2100.", "error")
            return render_template("songs_new.html", prev=form)

        release_month = clamp_month("release_month")

        rating = to_int("rating")
        if rating is not None and not (0 <= rating <= 10):
            flash("Rating must be between 0 and 10.", "error")
            return render_template("songs_new.html", prev=form)

        url = val("url")
        if url is not None and not (url.startswith("http://") or url.startswith("https://")):
            flash("URL must start with http:// or https://", "error")
            return render_template("songs_new.html", prev=form)

        store.append(
            {
                "title": title,
                "genre": val("genre"),
                "performer": val("performer"),
                "writer": val("writer"),
                "release_year": release_year,
                "release_month": release_month,
                "lyrics": val("lyrics"),
                "rating": rating,
                "url": url,
            }
        )

        flash("Song added.", "success")
        return redirect(url_for("songs_list"))

    return app


if __name__ == "__main__":
    # Bind to 0.0.0.0 so it works in containers later.
    PORT: Final[int] = int(os.environ.get("PORT", "5000"))
    APP: Final[Flask] = create_app()
    APP.run(host="0.0.0.0", port=PORT, debug=True)
