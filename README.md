# CT-200 Document QA API — Tri9T AI Internship Assignment

## Status and scope
This is a runnable starter implementation of the requested backend. It includes a conservative numbered-heading parser, persistent JSON storage, version snapshots, browse/search endpoints, version-pinned selections, deterministic QA-case generation, retrieval, and staleness checks.

**Important limitation:** The assignment's actual `ct200_manual.pdf` and `ct200_manual_v2.pdf` were not available while this implementation was prepared. `data/sample_v1.txt` and `data/sample_v2.txt` are clearly labelled illustrative fixtures, not extracted CT-200 source content. Do not claim the parser has been validated against the real manual until you obtain both PDFs. The current generator is a deterministic fallback, not an external LLM call. The code does not OCR scanned PDFs; it extracts embedded text with PyMuPDF and returns an explicit error if no text is available.

## Setup (macOS/Linux)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for interactive API documentation.

## Demonstrate v1 → v2
In another terminal, from the repository root:
```bash
curl -X POST http://127.0.0.1:8000/ingest -H 'Content-Type: application/json' -d '{"version":"v1","filename":"sample_v1.txt"}'
curl -X POST http://127.0.0.1:8000/ingest -H 'Content-Type: application/json' -d '{"version":"v2","filename":"sample_v2.txt"}'
curl 'http://127.0.0.1:8000/sections?version=v1'
curl 'http://127.0.0.1:8000/search?q=pressure&version=v2'
```
Note: `/ingest` supports `text` or a filename under `data/`. The example fixtures are `.txt` files; pass their content via `text`, or use the helper script below to load them. The filename route is intended for PDFs, so the simplest fixture demo is:
```bash
python - <<'PY'
import json, urllib.request
for version, filename in [('v1','data/sample_v1.txt'),('v2','data/sample_v2.txt')]:
    text=open(filename).read()
    req=urllib.request.Request('http://127.0.0.1:8000/ingest',
        data=json.dumps({'version':version,'text':text}).encode(),
        headers={'Content-Type':'application/json'})
    print(urllib.request.urlopen(req).read().decode()[:500])
PY
```
Create a selection using node IDs returned by `/sections?version=v1`:
```bash
curl -X POST http://127.0.0.1:8000/selections -H 'Content-Type: application/json' \
  -d '{"name":"Safety review","version":"v1","node_ids":["n1"]}'
```
Use the returned selection ID:
```bash
curl -X POST http://127.0.0.1:8000/generate -H 'Content-Type: application/json' \
  -d '{"selection_id":"sel_REPLACE_ME"}'
curl 'http://127.0.0.1:8000/generated?selection_id=sel_REPLACE_ME'
```
Node IDs are parser-order IDs, so they can shift between versions. This starter's comparison uses heading paths for ingest summaries, while retrieval-time staleness currently checks IDs and hashes. That mismatch is a known limitation and should be fixed before claiming robust production traceability.

## API endpoints
- `POST /ingest` — ingest text or an extractable-text PDF into a version snapshot.
- `GET /sections?version=v1` — list top-level sections.
- `GET /nodes/{node_id}?version=v1` — retrieve a node and its descendants.
- `GET /search?q=pressure&version=v1` — search headings/body.
- `GET /diff/{node_id}?from_version=v1&to_version=v2` — basic hash comparison.
- `POST /selections` — save version-pinned source node snapshots.
- `POST /generate` — generate deterministic draft QA ideas tied to source hashes.
- `GET /generated?selection_id=...` or `?node_id=...` — retrieve generated ideas and current staleness.

## Tests
```bash
pytest -q
```
Tests cover browsing/search, duplicate headings, pinned selections and retrieval, and changed-content staleness. These are initial regression tests, not full coverage of the supplied manual's irregularities.

## Architecture and known limitations
- FastAPI + Pydantic; JSON persistence chosen for speed and transparent inspectability instead of SQLAlchemy/SQLite + MongoDB.
- SHA-256 hashes identify exact heading/body text changes.
- Numbered lines become headings; other lines are preserved as body text. Tables, captions, unnumbered headings, multi-column order, and scanned pages need manual review/OCR.
- LLM output is not called in this starter. The deterministic fallback avoids malformed provider responses, but does not meet the full LLM-powered requirement.
- The JSON store is suitable only for a small local demo; no concurrency control or migration system.
- Never use generated QA ideas as approved medical-device tests without engineering review.
