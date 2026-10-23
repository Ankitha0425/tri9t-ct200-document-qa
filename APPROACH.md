# Approach Document — CT-200 Document QA API

## 1. Goal
Build a backend that turns a technical manual into a structured hierarchy, preserves document versions, stores version-pinned selections, creates QA test ideas, and reports whether source text has changed.

## 2. Parsing approach
The starter uses PyMuPDF to extract embedded PDF text and a conservative line-based parser to recognize explicitly numbered headings (for example, `2 Safety` and `2.1 Cuff safety`). Unclassified lines are kept as body text rather than silently discarded. This is intentionally narrow and must be checked against the real CT-200 PDFs. Scanned PDFs return an explicit error; OCR has not yet been implemented.

## 3. Data model
Each tree node stores an ID, heading, level, body text, parent ID, child nodes, and SHA-256 content hash. The JSON store keeps version snapshots, named selections, and generated cases. Each selection copies the source version, node IDs, source text, and hashes, so later ingestion does not erase the original evidence.

## 4. Version matching and staleness
Ingestion produces a hash of the full source and hashes per node. The ingest summary compares heading paths, which can flag changed text at a stable path. Retrieval-time staleness currently compares pinned node IDs and hashes to the latest version. This is a known weakness because parser-order IDs can shift when headings are inserted. A stronger implementation would assign stable logical IDs using normalized heading paths plus fuzzy matching and then compare section content; threshold/number changes should receive higher impact than punctuation changes.

## 5. QA generation and validation
The current `/generate` endpoint creates deterministic draft cases from selected nodes. It is a working fallback, not a real LLM integration. A production version should send selected source text to a configured LLM, request a strict JSON schema, validate every field with Pydantic, retry once for malformed output, and return a clear error or deterministic fallback after repeated failure. Each case should retain the exact source node ID and content hash.

## 6. Edge cases and validation
Regression tests currently cover duplicate headings, browse/search, version-pinned selections, generation retrieval, and changed text. The actual manual was not supplied with the assignment PDF in this work session, so the real document's irregularities have not been inspected or verified. Before claiming completion, test duplicate headings with distinct parents, missing/unnumbered headings, tables/captions, and any numbering anomalies found in both manuals.

## 7. Initial failures and improvements
No earlier implementation was available to compare. The initial version here deliberately avoids aggressive guessing: only numbered lines are headings, while other lines remain body text. This reduces silent content loss but may miss real headings. The API rejects missing versions/nodes and PDFs without extractable text rather than pretending the content was parsed successfully.

## 8. Required decision log
1. **Most likely silent wrong result:** assigning a numbered paragraph the wrong parent or treating a table row as ordinary prose. Catch it with page-by-page visual comparison, hierarchy assertions, and test cases for each irregular pattern.
2. **Where simplicity was chosen:** JSON storage and parser-order IDs were chosen for a fast local demonstration. Concurrent writes and inserted sections can break production traceability first.
3. **Unsupported input:** scanned/image-only PDF pages are not OCR'd by this starter. The API returns a clear error when no extractable text is found; OCR and visual validation remain required.

## 9. What I would do next
Obtain the exact v1/v2 PDFs, inspect every listed irregularity, add OCR (for scanned pages), stable logical-node matching, SQLAlchemy/SQLite persistence, real LLM integration with schema validation/retry, and an end-to-end v1-to-v2 test using the actual source manual.
