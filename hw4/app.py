from __future__ import annotations

"""
Commit 5

Flask app using Cloud Datastore for storage.
Reuses HW2 templates and static files for the UI.
Adds /readyz and lightweight request logging.
"""

import os
import sys
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Final
from flask import Flask, render_template, request, redirect, url_for, flash, g

REPO_ROOT = Path(__file__).resolve().parents[1]
HW2_PATH = REPO_ROOT / "hw2"
if HW2_PATH.exists():
    sys.path.insert(0, str(HW2_PATH))

from model_datastore import DatastoreModel, Song  # local module

# Simple stdout logging for Cloud Run
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("hw4")


def create_app() -> Flask:
    """
    Application factory for HW4 using Datastore.
    """
    template_folder = str(HW2_PATH / "templates") if HW2_PATH.exists() else "templates"
    static_folder = str(HW2_PATH / "static") if HW2_PATH.exists() else "static"

    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")

    project_id = os.environ.get("PROJECT_ID")
    namespace = os.environ.get("DATASTORE_NAMESPACE", "cs530-hw4")
    kind = os.environ.get("DATASTORE_KIND", "CS530_SongsHW4")

    model = DatastoreModel(project_id=project_id, namespace=namespace, kind=kind)
    model.init_storage()

    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()
        g.req_id = str(uuid.uuid4())

    @app.after_request
    def _log_response(resp):
        try:
            dt_ms = round((time.perf_counter() - g._t0) * 1000, 2)
        except Exception:
            dt_ms = None
        log.info(
            {
                "req_id": getattr(g, "req_id", None),
                "method": request.method,
                "path": request.path,
                "status": resp.status_code,
                "latency_ms": dt_ms,
            }
        )
        return resp

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/readyz")
    def readyz():
        # Datastore is schemaless; this is a light-readiness check.
        return {"ready": True}

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/songs")
    def songs_list():
        songs = model.list_songs()
        return render_template("songs_list.html", songs=songs)

    @app.get("/songs/new")
    def songs_new():
        return render_template("songs_new.html", prev={})

    @app.post("/songs")
    def songs_create():
        """
        Create a song with light server-side checks.
        """
        form = request.form

        def val(name: str):
            v = (form.get(name) or "").strip()
            return v or None

        def to_int(name: str):
            v = val(name)
            if v is None:
                return None
            try:
                return int(v)
            except ValueError:
                return None

        def clamp_month(name: str):
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

        song = Song(
            title=title,
            genre=val("genre"),
            performer=val("performer"),
            writer=val("writer"),
            release_year=release_year,
            release_month=release_month,
            lyrics=val("lyrics"),
            rating=rating,
            url=url,
        )
        
        model.insert_song(song)
        flash("Song added.", "success")
        return redirect(url_for("songs_list"))

    return app


if __name__ == "__main__":
    PORT: Final[int] = int(os.environ.get("PORT", "5000"))
    APP: Final[Flask] = create_app()
    APP.run(host="0.0.0.0", port=PORT, debug=True)
