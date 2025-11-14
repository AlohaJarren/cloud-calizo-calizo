from __future__ import annotations

"""
Commit 6

Flask app using Cloud Datastore for storage.
Reuses HW2 templates and static files for the UI.
Adds /readyz and lightweight request logging.

Adds stricter validation and field length caps.
"""

import os
import sys
import re
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Final
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, flash, g

REPO_ROOT = Path(__file__).resolve().parents[1]
HW2_PATH = REPO_ROOT / "hw2"
if HW2_PATH.exists():
    sys.path.insert(0, str(HW2_PATH))

from model_datastore import DatastoreModel, Song  # local module

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

        def sval(name: str, max_len: int) -> Optional[str]:
            v = (form.get(name) or "").strip()
            if not v:
                return None
            # collapse whitespace and trim to max length
            v = re.sub(r"\s+", " ", v)
            if len(v) > max_len:
                return v[:max_len]
            return v

        def ival(name: str) -> Optional[int]:
            v = (form.get(name) or "").strip()
            if not v:
                return None
            try:
                return int(v)
            except ValueError:
                return None

        def clamp_month(name: str) -> Optional[int]:
            m = ival(name)
            if m is None:
                return None
            return 1 if m < 1 else (12 if m > 12 else m)

        def url_ok(raw: Optional[str]) -> Optional[str]:
            if raw is None:
                return None
            if len(raw) > 2048:
                return None
            try:
                u = urlparse(raw)
            except Exception:
                return None
            if u.scheme not in {"http", "https"}:
                return None
            if not u.netloc:
                return None
            return raw

        # Required
        title = sval("title", 100)
        if not title:
            flash("Title is required.", "error")
            return render_template("songs_new.html", prev=form)

        # Optional with bounds
        release_year = ival("release_year")
        if release_year is not None and not (1800 <= release_year <= 2100):
            flash("Release year must be between 1800 and 2100.", "error")
            return render_template("songs_new.html", prev=form)

        release_month = clamp_month("release_month")

        rating = ival("rating")
        if rating is not None and not (0 <= rating <= 10):
            flash("Rating must be between 0 and 10.", "error")
            return render_template("songs_new.html", prev=form)

        url_val = url_ok((form.get("url") or "").strip() or None)
        if (form.get("url") or "").strip() and url_val is None:
            flash("URL must be http(s) and include a host.", "error")
            return render_template("songs_new.html", prev=form)

        song = Song(
            title=title,
            genre=sval("genre", 50),
            performer=sval("performer", 100),
            writer=sval("writer", 100),
            release_year=release_year,
            release_month=release_month,
            lyrics=sval("lyrics", 2000),
            rating=rating,
            url=url_val,
        )

        model.insert_song(song)
        flash("Song added.", "success")
        return redirect(url_for("songs_list"))

    return app


if __name__ == "__main__":
    PORT: Final[int] = int(os.environ.get("PORT", "5000"))
    APP: Final[Flask] = create_app()
    APP.run(host="0.0.0.0", port=PORT, debug=True)
