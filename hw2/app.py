from __future__ import annotations

from typing import Final, Optional, Dict, Any
from flask import Flask, render_template, request, redirect, url_for, flash

from model.base import Song
from model.sqlite3_model import SQLite3Model


def create_app() -> Flask:
    """
    CS 530 HW2 - Songs MVP (Commit 5)
    Flask app with create and read paths using sqlite3.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"

    model = SQLite3Model(db_path="songs.db")
    model.init_storage()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/songs")
    def songs_list():
        songs = model.list_songs()
        return render_template("songs_list.html", songs=songs)

    @app.get("/songs/new")
    def songs_new():
        # prev allows us to repopulate the form after a validation error
        return render_template("songs_new.html", prev={})

    @app.post("/songs")
    def songs_create():
        """
        Handle the creation of a song entry.
        Validates title as required, clamps numeric fields to sane ranges.
        """
        def val(name: str) -> Optional[str]:
            v = request.form.get(name, "").strip()
            return v if v else None

        def to_int(name: str) -> Optional[int]:
            raw = val(name)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        prev: Dict[str, Any] = dict(request.form)

        title = val("title")
        if not title:
            flash("Title is required.", "error")
            return render_template("songs_new.html", prev=prev), 400

        release_year = to_int("release_year")
        release_month = to_int("release_month")
        rating = to_int("rating")

        # Basic range checks
        if release_month is not None and not (1 <= release_month <= 12):
            flash("Release month must be between 1 and 12.", "error")
            return render_template("songs_new.html", prev=prev), 400

        if rating is not None and not (0 <= rating <= 10):
            flash("Rating must be between 0 and 10.", "error")
            return render_template("songs_new.html", prev=prev), 400

        song = Song(
            title=title,
            genre=val("genre"),
            performer=val("performer"),
            writer=val("writer"),
            release_year=release_year,
            release_month=release_month,
            lyrics=val("lyrics"),
            rating=rating,
            url=val("url"),
        )

        model.insert_song(song)
        flash("Song added.", "success")
        return redirect(url_for("songs_list"))

    return app


if __name__ == "__main__":
    APP: Final[Flask] = create_app()
    APP.run(host="127.0.0.1", port=5000, debug=True)
