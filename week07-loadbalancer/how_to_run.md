_# Week 7 — Round-Robin Load Balancer

A tiny load balancer that distributes requests across 3 identical copies of the
Week 2 patient-case API. Built to demonstrate horizontal scaling — and, more
usefully, the two ways it breaks.

## What's here

- `balancer.py` — the load balancer (FastAPI proxy, round-robin via `itertools.cycle`)
- Backends are 3 copies of `../week02-rest-api/cases_api.py`

## Prerequisites

```powershell
# from the repo root, with the venv active
venv\Scripts\Activate.ps1
pip install -r requirements.txt        # needs fastapi, uvicorn, httpx
```

## How to run

You need **5 terminals**. All of them need the venv active.

### Terminals 1-3: the three API workers

```powershell
cd week02-rest-api
uvicorn cases_api:app --port 8001      # terminal 1
uvicorn cases_api:app --port 8002      # terminal 2
uvicorn cases_api:app --port 8003      # terminal 3
```

Each is an independent copy of the same API on its own port.

### Terminal 4: the load balancer

```powershell
cd week07-loadbalancer
uvicorn balancer:app --port 9000
```

### Terminal 5: for sending requests

Send everything to **port 9000** (the balancer), never to the workers directly.

## Demo 1 — watch round-robin distribute

```powershell
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
```

**Watch the balancer terminal** — it prints its routing decisions:
```
  → routed GET /cases  ->  http://127.0.0.1:8001
  → routed GET /cases  ->  http://127.0.0.1:8002
  → routed GET /cases  ->  http://127.0.0.1:8003
  → routed GET /cases  ->  http://127.0.0.1:8001
```
**Also check the 3 worker terminals** — each should log roughly 1/3 of the requests.

## Demo 2 — the statelessness problem

```powershell
# create a case (lands on ONE worker only)
curl.exe -X POST http://127.0.0.1:9000/cases -H "Content-Type: application/json" -d '{\"patient\": \"Ravi\", \"diagnosis\": \"pending\"}'

# now read it back several times
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
```

**Expected result — the case flickers in and out:**
```
{"cases":[]}                                     ← hit a worker that never saw it
{"cases":[]}                                     ← same
{"cases":[{"id":1,"patient":"Ravi",...}]}        ← hit the worker that has it
{"cases":[]}                                     ← gone again
```

**Why:** `cases_api.py` stores cases in a Python dict — in each worker's own memory.
The POST wrote to one worker only; the other two have separate, empty dicts.

**FINDING 1: statelessness isn't optional for horizontal scaling.** With state in
worker memory, adding workers actively *breaks correctness*. The fix is to move
state out of the compute layer — into Postgres/Redis — so all workers read the
same source of truth.

## Demo 3 — no health checks

```powershell
# kill one worker: press Ctrl+C in the terminal running port 8003
# then hit the balancer repeatedly
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
curl.exe http://127.0.0.1:9000/cases
```

**Expected result — roughly 1 in 3 requests fails:**
```
{"cases":[]}
{"cases":[]}
Internal Server Error          ← rotation hit the dead worker
```

**FINDING 2: round-robin without health checks doesn't give you availability.**
The balancer has no idea 8003 is dead, so it keeps sending it every third request.
Killing 1 of 3 workers degrades **33% of traffic**, not 0%.

**What real load balancers do:** poll a `/health` endpoint on each backend every
few seconds; after N failures, remove that backend from the rotation until it
recovers. Users then see zero errors when one worker dies.

## Shutdown

`Ctrl+C` in each of the 5 terminals.

## Possible improvements (not implemented)

- Health checking (`GET /health` polling + remove unhealthy backends)
- Least-connections instead of round-robin (better when request durations vary)
- Make `cases_api.py` stateless by writing to Postgres — then Demo 2 would pass