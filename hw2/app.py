from __future__ import annotations

from typing import Final
from flask import Flask, url_for, Response


def create_app() -> Flask:
    """
    CS 530 HW2 - Songs MVP (Commit 1)
    Minimal Flask app with a landing page and stubs for /songs and /songs/new.
    Binds to port 5000 when run directly.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"  # will be used in later commits for flash messages

    @app.get("/")
    def index() -> Response:
        """
        Default landing page with links to the next routes.
        HTML is inline for now so the app runs without templates.
        """
        html = f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Songs MVP - Home</title>
    <style>
      body {{ font-family: Trebuchet MS, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; }}
      header, main, footer {{ max-width: 960px; margin: 0 auto; padding: 1rem; }}
      nav a {{ margin-right: 1rem; }}
      .card {{ padding: 1rem; border: 1px solid #ddd; border-radius: 8px; }}
    </style>
  </head>
  <body>
    <header>
      <h1>Songs MVP</h1>
      <nav>
        <a href="{url_for('index')}">Home</a>
        <a href="{url_for('songs_list')}">View Songs</a>
        <a href="{url_for('songs_new')}">Add Song</a>
      </nav>
    </header>
    <main>
      <div class="card">
        <h2>Welcome</h2>
        <p>
          This is the starting point for HW2. Next up:
        </p>
        <ul>
          <li>Templates and a shared layout</li>
          <li>An abstract data model and a sqlite3 implementation</li>
          <li>Create and Read flows for song entries</li>
        </ul>
      </div>
    </main>
    <footer>
      <p>CS 530 - Internet, Web & Cloud Systems - HW2</p>
    </footer>
  </body>
</html>
        """.strip()
        return Response(html, mimetype="text/html")

    @app.get("/songs")
    def songs_list() -> Response:
        """
        Lists songs (stub). Will render a template and read from sqlite3 soon.
        """
        html = f"""
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Songs - Coming Soon</title></head>
  <body style="font-family: Trebuchet MS, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;">
    <p><a href="{url_for('index')}">Home</a></p>
    <h2>All Songs</h2>
    <p>Coming soon: this page will list songs from the database.</p>
  </body>
</html>
        """.strip()
        return Response(html, mimetype="text/html")

    @app.get("/songs/new")
    def songs_new() -> Response:
        """
        Creation form (stub). Will show fields and POST to /songs next.
        """
        html = f"""
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Add Song - Coming Soon</title></head>
  <body style="font-family: Trebuchet MS, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;">
    <p><a href="{url_for('index')}">Home</a></p>
    <h2>Add Song</h2>
    <p>Coming soon: this page will present a form to create a new song entry.</p>
  </body>
</html>
        """.strip()
        return Response(html, mimetype="text/html")

    return app


if __name__ == "__main__":
    # Listen on port 5000 while we build out the rest.
    APP: Final[Flask] = create_app()
    APP.run(host="127.0.0.1", port=5000, debug=True)
