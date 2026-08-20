# Week 5 — Redis Cache with Cache-Aside & TTL

A cache-aside implementation over Redis, demonstrating why caching is the
highest-leverage performance tool — and how TTL bounds the staleness it creates.

## What's here

- `redis_cache.py` — cache-aside pattern + TTL expiry demo, with timings

## Prerequisites

**Docker Desktop must be running** (whale icon → "Engine running"; closing Docker
Desktop stops all containers).

```powershell
# start the Redis container
docker start healix-redis

# if it doesn't exist yet, create it:
# docker run --name healix-redis -p 6379:6379 -d redis:7-alpine

docker ps      # confirm it's up
```

```powershell
# from the repo root, with the venv active
venv\Scripts\Activate.ps1
pip install -r requirements.txt        # needs redis
```

## How to run

```powershell
python week05-cache/redis_cache.py
```

## What it demonstrates

### The cache-aside pattern

```
check cache → HIT?  → return it
            → MISS? → do the expensive work → store in cache → return it
```

Nine lines of code. `slow_guideline_lookup()` stands in for the expensive
guideline-RAG pipeline (embed query → vector search → LLM call), simulated with a
2-second sleep.

### Result — the headline number

```
--- First call (cache empty) ---
[MISS]  2003.88 ms  |  Guideline answer for: '...'
--- Second call (should be cached) ---
[HIT]      2.15 ms  |  Guideline answer for: '...'
--- Third call ---
[HIT]      1.52 ms  |  Guideline answer for: '...'
```

**2003ms → 1.5ms. Roughly 1300× faster.**

Compare to the Week 3 index result (16.7ms → 0.8ms, ~20×). The difference:
**an index makes the work faster; a cache skips the work entirely.** The second
call never ran the pipeline at all — it handed back a stored string.

### TTL expiry — the staleness safety net

```
Call 1 (empty cache):              [MISS]  2005.00 ms
Call 2 (immediately after):        [HIT]      1.50 ms
Waiting 6 seconds for TTL...
Call 3 (after TTL expired):        [MISS]  2004.99 ms
```

The third call is a **MISS again** — the 5-second TTL expired and the entry
vanished on its own, forcing a fresh computation.

**Why this matters:** in a clinical system, a cached guideline answer that goes
stale after the guideline updates is *outdated medical advice*. TTL guarantees
staleness can't last longer than the expiry window, even if event-based
invalidation is missed.

## Key API notes

- `r.get(key)` / `r.set(key, value, ex=SECONDS)` — the `ex` parameter sets the TTL
- `r.setex(key, seconds, value)` also works but is **deprecated** — prefer
  `r.set(..., ex=...)`
- Cache keys use the hierarchical convention: `guideline:{question}`

## Inspect Redis directly

```powershell
docker exec -it healix-redis redis-cli

KEYS *                      # all keys currently cached
GET guideline:<question>    # fetch one
TTL guideline:<question>    # seconds remaining before expiry (-1 = no TTL)
FLUSHALL                    # clear everything
exit
```

## The design reasoning behind this (Week 5 Fri capstone)

**Slow path chosen:** the guideline-RAG agent (embed → vector search → LLM).
Expensive, and the same questions repeat across doctors.

**Pattern: cache-aside** — read-heavy, writes are rare (guidelines change
occasionally and manually), fills lazily on misses. Write-through would be
needless overhead; write-back offers nothing here.

**TTL: long but bounded** (e.g. a day) — guidelines change rarely, but never
cache indefinitely, so an update can't stay hidden forever.

**Invalidation:** on guideline upload/change, invalidate the affected cached
answers. TTL is the safety net for when invalidation is missed. **Never rely on
invalidation alone in a clinical system** — it can fail silently.

**Monitoring:** hit rate is the key *performance* metric (proves the cache is
earning its place). **Staleness / version-mismatch alerts are the key *safety*
metric** — invalidation and TTL can both fail silently, and in a clinical context
you must *know* if a stale answer was served. Monitoring watches your safeguards;
it doesn't duplicate them.

## TTL tiering for a clinical LLM cache (Week 5 Wed)

| Content | TTL | Why |
|---|---|---|
| Guideline agent (NCCN/ICMR) | Long, bounded | Stable, expensive to fetch, rarely changes |
| Similar-case agent | Medium | Case pool is stable + expensive search; invalidate if patient diagnosis changes |
| Core agents (pathology/genomics/radiology), integrated & treatment summaries | Short / session-only | Patient-specific — go stale the moment files change |
| Patient identity (name, age) | **Don't cache** | Cheap indexed fetch; caching saves nothing and adds staleness/privacy risk |

**Two principles:** cache *expensive computations*, not cheap lookups. And
anything keyed to a specific patient's changeable data gets a short TTL — because
the cost of a stale clinical answer is a patient-harm event, not a performance
nuisance.

## Limitations (deliberate)

- Uses a simulated slow function (`time.sleep(2)`), not a real RAG pipeline
- No cache-hit-rate metrics collected — production would track hit rate,
  cached-vs-uncached latency, and staleness incidents
- No invalidation implemented — only TTL expiry is demonstrated
- Single-process; no distributed cache-invalidation concerns