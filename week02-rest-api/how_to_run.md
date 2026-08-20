# Week 2 — Patient Case REST API (sync vs async)

A small REST API implementing the patient-case resource designed on paper, plus
two endpoints that make the difference between synchronous and asynchronous
processing physically visible.

This is also the API used as the backend in the Week 7 load balancer build.

## What's here

- `cases_api.py` — GET/POST/PUT endpoints with correct status codes, plus
  sync and async processing endpoints

## Prerequisites

```powershell
# from the repo root, with the venv active
venv\Scripts\Activate.ps1
pip install -r requirements.txt        # needs fastapi, uvicorn
```

No Docker needed — this one runs standalone.

## How to run

```powershell
cd week02-rest-api
uvicorn cases_api:app --reload
```

Server starts on `http://127.0.0.1:8000`. Leave it running and use a **second
terminal** for the curl commands below.

**Note:** `--reload` restarts the server whenever you save the file — and since
cases are stored in a Python dictionary in memory, **every restart wipes the
data**. If a case "disappears," that's why. Re-create it and test again without
saving in between.

## The endpoints

| Method | URL | Returns |
|---|---|---|
| GET | `/cases` | All cases. 200 |
| POST | `/cases` | Creates a case, returns it. **201 Created** |
| GET | `/cases/{id}` | One case. 200, or **404** if it doesn't exist |
| PUT | `/cases/{id}` | Replaces a case, returns it. 200, or 404 |
| POST | `/cases/{id}/process-sync` | Runs 5s of work, **then** responds |
| POST | `/cases/{id}/process-async` | Responds **immediately**, works in background |

Note `/cases` serves both GET and POST — **same URL, different method**. That's
REST working as designed: the address names the *thing*, the method says what to
*do* to it.

## Testing

```powershell
# list (empty at first)
curl.exe http://127.0.0.1:8000/cases

# create — returns 201 with an auto-assigned id
curl.exe -X POST http://127.0.0.1:8000/cases -H "Content-Type: application/json" -d '{\"patient\": \"Ravi\", \"diagnosis\": \"pending\"}'

# fetch one
curl.exe http://127.0.0.1:8000/cases/1

# a real 404 — use -i to see the status line in the headers
curl.exe -i http://127.0.0.1:8000/cases/999

# update
curl.exe -X PUT http://127.0.0.1:8000/cases/1 -H "Content-Type: application/json" -d '{\"patient\": \"Ravi\", \"diagnosis\": \"confirmed\"}'
```

The `\"` escaping is a Windows PowerShell quirk. Use `curl.exe` (not bare `curl`)
— PowerShell aliases `curl` to its own command, which formats output differently.

## Demo 1 — idempotency: PUT vs POST

**Run the PUT command three times**, then `GET /cases`:
→ **still exactly one case.** Repeated PUTs overwrite the same record; same end
state every time.

**Run the POST command three times**, then `GET /cases`:
→ **three cases**, ids 1, 2, 3 — identical data, all duplicates.

**That's the elevator button vs the vending machine.** PUT is idempotent
(`cases[id] = value` replaces); POST is not (`next_id += 1` appends).

**Why it matters:** this is the exact production bug behind retries. A client
POSTs, the network drops the *response*, the client doesn't know if it worked and
retries → **two identical patient cases**. In a tumor board, which one is real?
This is why POST-style operations need an idempotency key.

## Demo 2 — sync vs async

**Synchronous — the caller waits:**
```powershell
curl.exe -X POST http://127.0.0.1:8000/cases/1/process-sync
```
The terminal **freezes for 5 seconds**, then responds `{"status":"done"}`.
That's blocking — like a payment page that won't let you navigate away.

**Asynchronous — fire and move on:**
```powershell
curl.exe -X POST http://127.0.0.1:8000/cases/1/process-async
```
Returns `{"status":"accepted"}` **instantly** (milliseconds). Then **watch the
server terminal** — about 5 seconds later `[BACKGROUND] Finished processing case 1`
appears. The work was still running *after* curl already had its answer.

That gap — instant response, work continuing behind it — is asynchronous
processing made visible. Implemented with FastAPI's `BackgroundTasks`.

## Key REST concepts this implements

- **Resources over actions** — `/cases` (a noun), with GET/POST/PUT/DELETE doing
  the verbs. Not `/createCase`, `/getCase`.
- **Collections vs resources** — `/cases` (all) vs `/cases/123` (one).
- **Status codes as a language** — 2xx success (201 specifically for a successful
  POST), 4xx caller error (404 raised deliberately via `HTTPException`), 5xx
  server error.
- **Path parameters** — `{case_id}` in the route; FastAPI pulls it from the URL
  and converts it to `int` from the type hint. Send `/cases/abc` and it rejects
  the request automatically.
- **Type hints drive behaviour** — `case: dict` tells FastAPI "this comes from the
  JSON body"; `case_id: int` tells it "this comes from the URL path."

## Limitations (deliberate)

- **Data is stored in a Python dictionary** — wiped on every restart. This is
  fixed conceptually in Week 3 (Postgres) and it's the *exact* failure
  demonstrated in the Week 7 load balancer build, where 3 copies of this API each
  hold their own separate dict and the same GET returns different answers.
- **No idempotency key on POST** — duplicates are demonstrated, not prevented
- **No auth, no validation schema** (plain `dict` rather than a Pydantic model)
- **No `/health` endpoint** — which is why the Week 7 load balancer couldn't do
  health checking