from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Song:
    """
    A single song entry.

    Fields:
      title: Song title.
      genre: Optional genre string.
      performer: Optional performer name.
      writer: Optional writer name.
      release_year: Four-digit year or None.
      release_month: Month 1-12 or None.
      lyrics: Free-form lyrics text.
      rating: Integer rating such as 0-10, or None.
      url: Link to a streaming service or None.
    """
    title: str
    genre: Optional[str] = None
    performer: Optional[str] = None
    writer: Optional[str] = None
    release_year: Optional[int] = None
    release_month: Optional[int] = None
    lyrics: Optional[str] = None
    rating: Optional[int] = None
    url: Optional[str] = None


class BaseModel(ABC):
    """
    Base interface for data models.

    Implementations provide:
      - init_storage: create tables or indexes if missing
      - insert_song: persist a Song and return its id
      - list_songs: return all songs in insertion order

    Keeping this contract steady lets us swap backends later without
    touching routes or templates.
    """

    @abstractmethod
    def init_storage(self) -> None:
        """Create underlying storage artifacts if needed."""
        raise NotImplementedError

    @abstractmethod
    def insert_song(self, song: Song) -> int:
        """
        Insert a song and return its id.

        Args:
          song: The Song to store.

        Returns:
          The new integer id from the backend.
        """
        raise NotImplementedError

    @abstractmethod
    def list_songs(self) -> List[Song]:
        """Return all songs in insertion order."""
        raise NotImplementedError
