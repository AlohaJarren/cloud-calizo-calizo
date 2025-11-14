# Contributing - HW4

Short and clear commits. Prefer imperative mood and group related changes together.

## Commit style

- Good: "hw4: add Datastore model and wire routes"
- Good: "hw4: Dockerfile for Cloud Run (gunicorn, non-root)"
- Good: "hw4: tighten validation and add smoke test"
- Avoid vague: "fix stuff" or "update code"

## Branching

- Work on branch `hw4` and push often.
- Tag a clean point for grading, e.g., `hw4-v1`.

## Dev setup

```bash
gcloud auth application-default login
python -m venv .venv && source .venv/bin/activate
pip install -r hw4/requirements.txt -r hw4/requirements-dev.txt
PYTHONPATH=. pytest -q
```
