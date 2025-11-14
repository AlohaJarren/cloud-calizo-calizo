import os
import types

def test_healthz_and_form_flow(monkeypatch):
    # Patch DatastoreModel with an in-memory fake so tests do not hit GCP.
    import hw4.app as appmod

    class FakeModel:
        def __init__(self, *args, **kwargs):
            self._rows = []
        def init_storage(self):
            return None
        def insert_song(self, song):
            self._rows.append(song)
            return 1
        def list_songs(self):
            # Return dict-like objects that Jinja can use with dot access.
            # The template only reads attributes, so pass through dataclass or dict.
            return [types.SimpleNamespace(**vars(s)) if hasattr(s, "__dict__") else s for s in self._rows]

    monkeypatch.setattr(appmod, "DatastoreModel", FakeModel)

    app = appmod.create_app()
    client = app.test_client()

    # Health and readiness
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.is_json and r.get_json().get("ok") is True

    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.is_json and r.get_json().get("ready") is True

    # Index should render
    assert client.get("/").status_code == 200

    # Post a song
    resp = client.post(
        "/songs",
        data={
            "title": "Unit Song",
            "genre": "Test",
            "performer": "Tester",
            "writer": "Writer",
            "release_year": "2021",
            "release_month": "5",
            "rating": "7",
            "lyrics": "la la",
        },
        follow_redirects=False,
    )
    # Expect a redirect to /songs on success
    assert resp.status_code in (301, 302)

    # List page should include title
    page = client.get("/songs")
    assert page.status_code == 200
    assert b"Unit Song" in page.data
