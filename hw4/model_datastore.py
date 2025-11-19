from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, List
import os

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
    Cloud Datastore model for Songs.
    Kind/namespace are configurable via ctor to avoid colliding with Guestbook labs.
    """

    def __init__(
        self,
        project_id: Optional[str],
        namespace: str = "cs530-hw4",
        kind: str = "CS530_SongsHW4",
    ) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.namespace = namespace
        self.kind = kind
        self.client = datastore.Client(project=self.project_id, namespace=self.namespace)

    def init_storage(self) -> None:
        # Datastore is schemaless; nothing to create.
        return

    def insert_song(self, s: Song) -> int:
        key = self.client.key(self.kind)
        entity = datastore.Entity(key=key, exclude_from_indexes=("lyrics",))
        payload = {k: v for k, v in asdict(s).items() if v is not None}
        entity.update(payload)
        self.client.put(entity)
        return int(entity.key.id)

    def list_songs(self) -> List[Song]:
        query = self.client.query(kind=self.kind)
        # No specific order required; fetch all
        rows = list(query.fetch(limit=200))
        out: List[Song] = []
        for e in rows:
            out.append(
                Song(
                    title=e.get("title"),
                    genre=e.get("genre"),
                    performer=e.get("performer"),
                    writer=e.get("writer"),
                    release_year=e.get("release_year"),
                    release_month=e.get("release_month"),
                    lyrics=e.get("lyrics"),
                    rating=e.get("rating"),
                    url=e.get("url"),
                )
            )
        return out
