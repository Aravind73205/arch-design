# Week 4 — RAG Retrieval with pgvector

Semantic search over a real, persistent vector store. Chunks of guideline text
are embedded and stored in PostgreSQL (via the pgvector extension), then
retrieved by meaning rather than keyword.

This closes a real gap: my earlier RAG work stored vectors in **session memory**,
so they vanished on restart. This version persists them properly.

## What's here

- `rag_retrieval.py` — full pipeline: chunk → embed → store → retrieve, plus a
  chunk-size comparison

## Prerequisites

**Docker Desktop must be running** (whale icon → "Engine running").

### The pgvector container

```powershell
docker start healix-vec

# if it doesn't exist yet:
# docker run --name healix-vec -e POSTGRES_PASSWORD=mypassword -e POSTGRES_DB=vectordb `
#   -p 5433:5432 -d pgvector/pgvector:pg16

docker ps      # confirm it's up
```

**Note the port: 5433**, not 5432 — the plain Postgres container (`healix-pg`)
already uses 5432, and two containers can't claim the same host port.

### One-time database setup

```powershell
docker exec -it healix-vec psql -U postgres -d vectordb
```
```sql
CREATE EXTENSION vector;

CREATE TABLE guideline_chunks (
    id SERIAL PRIMARY KEY,
    chunk_text TEXT,
    embedding vector(384)
);
```
`vector(384)` — 384 dimensions, matching the output of the `all-MiniLM-L6-v2`
embedding model. **The dimension must match the model.**

### Python deps

```powershell
venv\Scripts\Activate.ps1
pip install -r requirements.txt    # needs sentence-transformers, psycopg2-binary, numpy
```

First run downloads the embedding model (~a few hundred MB), then it's cached.
The `HF_TOKEN` warning on load is harmless — it just means an anonymous download.

## How to run

```powershell
python week04-rag/rag_retrieval.py
```

## What it demonstrates

### Semantic retrieval — matching by meaning, not words

```
Query: 'patient has trouble breathing'
Retrieval time: 4.00 ms
Top 3 chunks:
  1. (distance 0.4208) Patients presenting with shortness of breath and
     persistent cough should be evaluated for possible pulmonary complications.
```

The query and the matched chunk share **almost no words** — "trouble breathing"
vs "shortness of breath" — but they *mean* the same thing, so their vectors sit
close together in embedding space.

**This is what a SQL `WHERE` clause fundamentally cannot do.** `WHERE` matches
values character by character; semantic search requires nearest-point distance
calculation across hundreds of dimensions. Two different operations.

Retrieval ran in **1–4 ms**.

### Chunk size: the precision-vs-context tradeoff, measured

Same query, two chunking strategies:

| Chunking | Distance | What came back |
|---|---|---|
| **Small** (1 sentence) | **0.4208** | Just the precise relevant sentence |
| **Large** (3 sentences) | **0.6175** | The relevant sentence *plus* 2 irrelevant ones |

**Precision measurably degraded: 0.42 → 0.62.** The large chunk contains the
right sentence but *diluted* by unrelated content (radiation therapy,
immunotherapy), which drags the chunk's overall meaning away from the query.

**The tradeoff:** small chunks = precise but context-poor; large chunks =
context-rich but fuzzier matching. For clinical text the practical answer is
**medium chunks with overlap** — enough precision without losing meaning at chunk
boundaries (a dosage cut off from its condition could be misread, so overlap is a
*safety* property, not just a nicety).

## How it works

**The `<=>` operator** is pgvector's distance operator (cosine distance):

```sql
SELECT chunk_text, embedding <=> %s::vector AS distance
FROM guideline_chunks
ORDER BY distance
LIMIT %s
```

That's **similarity search expressed as a SQL query** — "find nearest points in
space," executed by Postgres. Lower distance = more similar.

**Both sides get embedded with the same model:** chunks at ingestion time, the
query at search time — so they land in the same vector space and are comparable.

## Inspect the data directly

```powershell
docker exec -it healix-vec psql -U postgres -d vectordb
```
```sql
SELECT COUNT(*) FROM guideline_chunks;
SELECT id, LEFT(chunk_text, 60) FROM guideline_chunks;
\d guideline_chunks
```

## The production design this points at (Week 4 Fri capstone)

**Store metadata WITH each vector** — not bare vectors. This build stores only
`chunk_text` + `embedding`; a real version needs:

```
chunks: chunk_id | vector | document_id | version | page_number | section | text | active
```

Why: metadata is what makes **surgical updates** possible. When one guideline
changes:

```sql
UPDATE chunks SET active = false
WHERE document_id = 'lung-cancer-protocol' AND page_number IN (44,45);
```
→ re-chunk and re-embed only those pages → insert with a new version. **Touches
~5 vectors instead of re-embedding a 1000-page document.** Index `document_id` so
that filter is a fast lookup rather than a full scan.

**Versioning/audit:** prefer **soft-delete** (`active = false`) over hard delete —
retrieval filters to `active = true`, but superseded versions stay for the audit
trail (which guideline version was live when a decision was made). Don't erase
medical-guidance history; deactivate it.

**Why pgvector over FAISS / Pinecone / Weaviate** (Week 4 Thu):
- **pgvector** — self-hosted, data-residency safe (DPDP), and reuses the Postgres
  already running. Millions of vectors is well within range.
- **FAISS** — a library, no persistence (that's exactly the session-memory
  failure this build fixes).
- **Pinecone** — managed, but data lives on their servers → rules it out for
  hospital deployment.
- **Weaviate** — capable, but adds a whole system to operate for no gain here.

## Limitations (deliberate)

- **No metadata columns** — no `document_id`, `version`, `page_number`, or
  `active` flag, so surgical updates and audit versioning aren't possible yet
- **No PDF extraction** — uses a hardcoded text string instead of a real document
- **No ANN index** — with only ~10 chunks it does an exact scan; at scale you'd
  add an `ivfflat` or `hnsw` index for approximate nearest neighbour
- **Re-embeds everything on each run** (deletes and re-inserts) rather than
  updating incrementally