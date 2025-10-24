from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

from .base import BaseModel, Song


class SQLite3Model(BaseModel):
    """
    sqlite3-backed model using Python's standard library.

    Keeps the interface small:
      - init_storage: create table if missing
      - insert_song: add a row and return its id
      - list_songs: fetch all rows as Song objects
    """

    def __init__(self, db_path: str = "songs.db") -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def init_storage(self) -> None:
        """
        Create the songs table if it does not exist.
        """
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS songs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    genre TEXT,
                    performer TEXT,
                    writer TEXT,
                    release_year INTEGER,
                    release_month INTEGER,
                    lyrics TEXT,
                    rating INTEGER,
                    url TEXT
                );
                """
            )
            con.commit()

    def insert_song(self, song: Song) -> int:
        """
        Insert a song and return the row id.
        """
        with self._connect() as con:
            cur = con.execute(
                """
                INSERT INTO songs
                    (title, genre, performer, writer, release_year, release_month, lyrics, rating, url)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    song.title,
                    song.genre,
                    song.performer,
                    song.writer,
                    song.release_year,
                    song.release_month,
                    song.lyrics,
                    song.rating,
                    song.url,
                ),
            )
            con.commit()
            return int(cur.lastrowid)

    def list_songs(self) -> List[Song]:
        """
        Return all songs ordered by id asc.
        """
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT
                    title, genre, performer, writer,
                    release_year, release_month, lyrics, rating, url
                FROM songs
                ORDER BY id ASC;
                """
            ).fetchall()
            return [
                Song(
                    title=row["title"],
                    genre=row["genre"],
                    performer=row["performer"],
                    writer=row["writer"],
                    release_year=row["release_year"],
                    release_month=row["release_month"],
                    lyrics=row["lyrics"],
                    rating=row["rating"],
                    url=row["url"],
                )
                for row in rows
            ]
