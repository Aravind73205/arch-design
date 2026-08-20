# Architecture Saturday Builds

Toy implementations from my 26-week system design plan. Each week's folder has its
own README with setup instructions, what the build demonstrates, and the measured
findings.

## Builds

- **[week01-setup](week01-setup/)** — FastAPI environment + hello-world API. Verifies
  the full request loop (env → server → network → response) before real builds depend on it.

- **[week02-rest-api](week02-rest-api/)** — Patient-case REST API: GET/POST/PUT with correct
  status codes and deliberate 404s. Demonstrates PUT-vs-POST idempotency (3 PUTs → 1 case,
  3 POSTs → 3 duplicates) and sync-vs-async processing (5s block vs instant response with
  background work).

- **[week03-postgres](week03-postgres/)** — Normalized clinical schema in PostgreSQL (Docker).
  **Index timing: 16.772ms → 0.823ms on 505k rows (~20×, ~10× less data touched).** Also found
  the planner *deliberately ignoring* the index on a JOIN fetching ~10% of the table — indexes
  help on small slices, not large fractions.

- **[week04-rag](week04-rag/)** — Semantic retrieval with pgvector. Query "trouble breathing"
  matches "shortness of breath" despite sharing no words; retrieval in 1–4ms.
  **Chunk-size tradeoff measured: distance 0.42 (small chunks, precise) vs 0.62 (large chunks,
  context-rich but diluted).**

- **[week05-cache](week05-cache/)** — Redis cache-aside with TTL.
  **2003ms → 1.5ms (~1300×)** — because caching *skips* the work rather than making it faster.
  TTL expiry demonstrated: a cached entry vanishes on schedule and the next call is a MISS again.

- **[week06-queue](week06-queue/)** — Producer → queue → consumer on Redis lists, with an
  **idempotent consumer** (duplicate delivery → work happens once) and a **dead-letter queue**
  (poison message fails 3× → moved aside, pipeline stays clear). The flagship build: the
  reliability pattern behind robust agent handoff.

- **[week07-loadbalancer](week07-loadbalancer/)** — Round-robin load balancer across 3 API
  copies. Both experiments *failed instructively*: **stateful workers made the same GET return
  different answers** (1 of 3 requests found the case), and **killing one worker broke ~33% of
  traffic** because there's no health checking.

## Running any of them

Every build needs the venv:

```powershell
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Weeks 3–6 also need **Docker Desktop running** (whale icon → "Engine running"), then start
the relevant container:

```powershell
docker start healix-pg       # week03 — Postgres
docker start healix-vec      # week04 — pgvector (port 5433)
docker start healix-redis    # week05, week06 — Redis
```

See each week's README for the specific run commands.