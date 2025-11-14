from __future__ import annotations

"""
Datastore model
Dedicated Kind to keep it separate from Guestbook exercises.
"""

from dataclasses import dataclass
from typing import Optional, List
from google.cloud import datastore


@dataclass
class Song:
    title: str
    genre: Optional[str] = None
    performer: Optional[str] = None
    writer: Optional[str] = None
    release_year: Optional[int] = None
    release_month: Optional[int] = None
    lyrics: Optional[str] = None
    rating: Optional[int] = None
    url: Optional[str] = None


class DatastoreModel:
    """
    Thin wrapper over google-cloud-datastore.
    Surface mirrors the HW2 model so routes do not change.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        namespace: Optional[str] = None,
        kind: str = "CS530_SongsHW4",
    ) -> None:
        self.client = datastore.Client(project=project_id, namespace=namespace)
        self.kind = kind

    def init_storage(self) -> None:
        # Datastore is schemaless.
        return None

    def insert_song(self, song: Song) -> int:
        key = self.client.key(self.kind)
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "title": song.title,
                "genre": song.genre,
                "performer": song.performer,
                "writer": song.writer,
                "release_year": song.release_year,
                "release_month": song.release_month,
                "lyrics": song.lyrics,
                "rating": song.rating,
                "url": song.url,
            }
        )
        self.client.put(entity)
        return int(entity.key.id)

    def list_songs(self) -> List[Song]:
        q = self.client.query(kind=self.kind)
        q.order = ["__key__"]
        rows = list(q.fetch())
        out: List[Song] = []
        for r in rows:
            out.append(
                Song(
                    title=r.get("title"),
                    genre=r.get("genre"),
                    performer=r.get("performer"),
                    writer=r.get("writer"),
                    release_year=r.get("release_year"),
                    release_month=r.get("release_month"),
                    lyrics=r.get("lyrics"),
                    rating=r.get("rating"),
                    url=r.get("url"),
                )
            )
        return out
