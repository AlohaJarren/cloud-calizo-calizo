from __future__ import annotations

from typing import Final
from flask import Flask, render_template

from model.sqlite3_model import SQLite3Model


def create_app() -> Flask:
    """
    CS 530 HW2 - Songs MVP (Commit 4)
    Flask app using templates for the landing page and list view.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"

    # Data model for this stage.
    model = SQLite3Model(db_path="songs.db")
    model.init_storage()

    @app.get("/")
    def index():
        # Default landing page with links to the other routes.
        return render_template("index.html")

    @app.get("/songs")
    def songs_list():
        # Read all songs from the db and render a table.
        songs = model.list_songs()
        return render_template("songs_list.html", songs=songs)

    @app.get("/songs/new")
    def songs_new():
        # Placeholder page. The full POST flow arrives next commit.
        return render_template("songs_new.html")

    return app


if __name__ == "__main__":
    APP: Final[Flask] = create_app()
    APP.run(host="127.0.0.1", port=5000, debug=True)
