# Week 8 — Retries + Circuit Breaker

Two reliability patterns layered over a deliberately unreliable dependency: retries
with exponential backoff and jitter, wrapped in a circuit breaker that trips on
sustained failure and self-heals.

Small build, high insight — the state transitions are the whole point.

## What's here

- `circuit_breaker.py` — flaky function, retry layer, circuit breaker, and a demo
  that walks through every state transition

## Prerequisites

None beyond the venv. No Docker, no external services — pure Python.

```powershell
venv\Scripts\Activate.ps1
```

## How to run

```powershell
python week08-reliability/circuit_breaker.py
```

Takes ~10 seconds (there are deliberate cooldown sleeps).

## The three layers

```
CircuitBreaker.call()          ← trips after N consecutive failures, fails fast
    └── call_with_retries()    ← 3 attempts, exponential backoff + jitter
            └── flaky_call()   ← fails ~40% of the time (the "provider")
```

**Retries handle transient failures within one request. The breaker handles
sustained failure across many requests.** Different jobs, composed.

## Knobs

```python
FAILURE_RATE = 0.4        # how often flaky_call fails
force_down = False        # True = total outage (every call fails)
MAX_RETRIES = 3           # attempts per request
FAILURE_THRESHOLD = 3     # consecutive failures before the breaker trips
COOLDOWN = 3              # seconds OPEN before probing
```

Backoff is scaled down for the demo (`0.1 * 2**attempt` instead of `1 * 2**attempt`)
so it runs fast. The *shape* is identical to a real policy.

## What the demo shows

### 1. Normal operation — retries absorb the failures

```
Request 1: attempt 1 FAILED — retrying in 0.134s
           attempt 2 FAILED — retrying in 0.077s
           attempt 3 SUCCESS
```

**A 40% failure rate produced zero user-visible failures across 5 requests.**
Mathematically: all 3 attempts must fail, so 0.4³ ≈ **6%** effective failure rate.

Note the retry delays are *random* (0.134s, 0.077s) — that's **jitter**. The ceiling
doubles each attempt (exponential), but the actual wait is random within it, so 100
simultaneously-failing clients don't retry in synchronized waves (the thundering herd).

### 2. Provider goes down — the breaker trips

```
Request 1: 3 attempts, all failed
Request 2: 3 attempts, all failed
Request 3: 3 attempts, all failed
  [BREAKER] 3 consecutive failures -> OPEN
Request 4: [OPEN] -> circuit OPEN — failing fast (3.0s left)
Request 5: [OPEN] -> circuit OPEN — failing fast
Request 6: [OPEN] -> circuit OPEN — failing fast
```

**This contrast is the whole point.** Requests 1–3 each burned 3 attempts plus
backoff waits. Requests 4–6 failed **instantly** — no attempts, no waiting, no cost.

Scaled to production numbers (90s timeout × 3 retries), each of those first requests
would take **~4.5 minutes** to fail. Requests 4–6 fail in microseconds. That's the
difference between workers being tied up on a dead provider and staying free.

### 3. Half-open probe while still down

```
[BREAKER] cooldown over -> HALF_OPEN (sending one probe)
      attempt 1-3 FAILED
[BREAKER] probe FAILED -> back to OPEN
```

**One** probe — not a flood at a fragile recovering service. Fails → straight back
to OPEN, cooldown restarts.

### 4. Provider recovers — the breaker closes

```
[BREAKER] cooldown over -> HALF_OPEN (sending one probe)
      attempt 1: SUCCESS
[BREAKER] probe SUCCEEDED -> CLOSED
Request 2: [CLOSED] -> OK
```

**Self-healing** — no human reset needed. The probe is what makes half-open work.

## The state machine

```
CLOSED  --(N consecutive failures)-->  OPEN
  ^                                      |
  |                                (cooldown expires)
  |                                      v
  +--(probe succeeds)--  HALF-OPEN  --(probe fails)--> OPEN
```

"CLOSED" = working (like a closed electrical circuit — current flows).
Note failures must be **consecutive** — one success resets the counter to zero.

## Experiments to try

```python
FAILURE_RATE = 0.8        # breaker trips even without force_down
FAILURE_THRESHOLD = 10    # much more tolerant — trips rarely
COOLDOWN = 10             # long lockout; watch how long recovery takes to detect
MAX_RETRIES = 1           # no retry cushion — failures reach the breaker immediately
```

## What a production version adds (deliberately omitted here)

- **Error classification** — only *provider-health* errors should count toward
  tripping (timeouts, connection errors, 5xx). **Not** 400/401/403/404 — those are
  client-side, and counting them means one buggy caller's malformed requests trip
  the breaker for everyone.
- **429 handling** — retryable but should **not** trip the breaker (throttling ≠
  outage). Honor the `Retry-After` header instead of your own backoff curve.
- **Fallback on open** — failing fast is only useful if something sensible happens
  instead: a labelled cached result, a backup provider, a queued retry, or a clear
  "temporarily unavailable" message.
- **Per-dependency breakers** — one breaker per downstream service, not one global.
- **Metrics** — trip count, time spent open, probe success rate.
- **Thread safety** — this implementation isn't safe under concurrent access.

## The clinical design decision behind this (Week 8 reliability map)

For a clinical tool, **degradation means removing the AI, not weakening it.**

When the breaker opens, the temptation is to serve a cached answer or fall back to
a different model. Both are wrong for patient-specific clinical analysis:

- A **cached** analysis may not reflect the patient's current data
- A **backup model** may not be the validated clinical model
- An **ungrounded** generation (if retrieval failed) looks identical to a grounded one

A weakened AI output looks the same as a strong one, so the doctor can't calibrate
their trust. **Better absent and honest than present and unreliable.** So the fallback
is: state plainly that analysis is unavailable, keep all stored records fully
accessible, and never render a blank section that could be mistaken for "nothing found."