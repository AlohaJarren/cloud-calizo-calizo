from __future__ import annotations

from typing import Final
from flask import Flask, url_for, Response

from model.base import Song  # used in later commits
from model.sqlite3_model import SQLite3Model


def create_app() -> Flask:
    """
    CS 530 HW2 - Songs MVP (Commit 3)
    Flask app with a landing page and basic list view.
    Uses a sqlite3-backed model; table is created at startup.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"

    # Data model for this stage. Later commits will add create/update/delete.
    model = SQLite3Model(db_path="songs.db")
    model.init_storage()

    @app.get("/")
    def index() -> Response:
        """
        Default landing page with links.
        HTML is inline for now; templates arrive in a later push.
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
        <p>This is the starting point for HW2. Current focus: read paths and data model.</p>
        <ul>
          <li>sqlite3 model initialized at startup</li>
          <li>/songs reads from the database</li>
          <li>Form and create flow coming next</li>
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
        List songs using the sqlite3 model.
        Still plain HTML to keep the surface small before templates.
        """
        songs = model.list_songs()
        rows = []
        for s in songs:
            yymm = ""
            if s.release_year and s.release_month:
                yymm = f"{s.release_year:04d}-{s.release_month:02d}"
            url_cell = f'<a href="{s.url}" target="_blank" rel="noopener">link</a>' if s.url else ""
            rows.append(
                f"<tr>"
                f"<td>{s.title}</td>"
                f"<td>{s.genre or ''}</td>"
                f"<td>{s.performer or ''}</td>"
                f"<td>{s.writer or ''}</td>"
                f"<td>{yymm}</td>"
                f"<td>{'' if s.rating is None else s.rating}</td>"
                f"<td>{url_cell}</td>"
                f"</tr>"
            )
        table_body = "\n".join(rows) if rows else '<tr><td colspan="7">No songs yet.</td></tr>'

        html = f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8"><title>Songs</title>
    <style>
      body {{ font-family: Trebuchet MS, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ border-bottom: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    </style>
  </head>
  <body>
    <p><a href="{url_for('index')}">Home</a></p>
    <h2>All Songs</h2>
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Genre</th>
          <th>Performer</th>
          <th>Writer</th>
          <th>Release (YYYY-MM)</th>
          <th>Rating</th>
          <th>URL</th>
        </tr>
      </thead>
      <tbody>
        {table_body}
      </tbody>
    </table>
  </body>
</html>
        """.strip()
        return Response(html, mimetype="text/html")

    @app.get("/songs/new")
    def songs_new() -> Response:
        """
        Creation form placeholder. The full form and POST handler
        will be introduced in the next commits.
        """
        html = f"""
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Add Song</title></head>
  <body style="font-family: Trebuchet MS, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;">
    <p><a href="{url_for('index')}">Home</a></p>
    <h2>Add Song</h2>
    <p>Form arrives in the next push.</p>
  </body>
</html>
        """.strip()
        return Response(html, mimetype="text/html")

    return app


if __name__ == "__main__":
    APP: Final[Flask] = create_app()
    APP.run(host="127.0.0.1", port=5000, debug=True)
