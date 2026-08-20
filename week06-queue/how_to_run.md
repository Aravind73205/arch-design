# Week 6 — Message Queue with Idempotency & Dead-Letter Queue

A producer → queue → consumer pipeline built on Redis lists, demonstrating the
three reliability mechanisms that underpin any robust multi-agent system:
at-least-once delivery, idempotent consumers, and a dead-letter queue.

This is the flagship build of the plan — the architecture pattern behind
reliable agent handoff.

## What's here

- `queue_dlq.py` — the full pipeline: producer, idempotent consumer, retry logic, DLQ

## Prerequisites

**Docker Desktop must be running** (the whale icon in the system tray must say
"Engine running" — closing Docker Desktop stops all containers).

```powershell
# start the Redis container
docker start healix-redis

# if it doesn't exist yet, create it:
# docker run --name healix-redis -p 6379:6379 -d redis:7-alpine

# confirm it's up
docker ps
```

```powershell
# from the repo root, with the venv active
venv\Scripts\Activate.ps1
pip install -r requirements.txt        # needs redis
```

## How to run

```powershell
python week06-queue/queue_dlq.py
```

The script clears Redis state and runs three demos in sequence.

## What each demo proves

### Demo 1 — normal processing
Two tasks go in, both succeed, the queue empties. Baseline check that
producer → queue → consumer works.

```
[PRODUCED] 8190ea0e | analyze patient 500
[SUCCESS]  8190ea0e | Processed: analyze patient 500
Queue depth: 0  |  DLQ depth: 0
```

### Demo 2 — idempotency (the duplicate problem)
A message is produced and processed. Then the **same message ID is deliberately
pushed back onto the queue**, simulating what at-least-once delivery does when an
acknowledgment is lost.

```
[SUCCESS]   3bdc4891 | Processed: record diagnosis for patient 700
(queue redelivered the same message — ack was lost)
[DUPLICATE] 3bdc4891 already processed — skipping
```

**The message was delivered twice; the diagnosis was recorded once.**

Without this, that patient's record would contain two identical diagnosis entries
— and a reviewing doctor couldn't tell whether the tumor board decided twice,
whether it's a data error, or which entry is authoritative.

### Demo 3 — poison message → DLQ
A message containing `POISON` fails every time (the work function raises on it).
Watch it exhaust its retries and get moved aside.

```
[RETRY 1] 50553a9c | Cannot process this payload — malformed input
[RETRY 2] 50553a9c | Cannot process this payload — malformed input
[DLQ]     50553a9c | failed 3x → moved to DLQ
Queue depth: 0  |  DLQ depth: 1
```

**Three attempts, then it stops — not four, not forever.** And `Queue depth: 0`
means the pipeline is clear: a message that can never succeed did **not** block
anything behind it (no head-of-line blocking).

The DLQ entry preserves the id, attempt count, the actual error, and the payload
— everything a human needs to debug it.

## How the mechanisms work

**Redis keys used:**
- `agent:tasks` — the main queue (a Redis list; `LPUSH` to add, `RPOP` to take → FIFO)
- `agent:dlq` — the dead-letter queue (another list)
- `agent:processed` — a Redis **Set** of message IDs already completed

**Idempotency:** every message carries a unique `uuid`. Before doing the work,
the consumer runs `SISMEMBER` against `agent:processed`. If the ID is there →
skip and acknowledge. If not → do the work, then `SADD` the ID. Duplicates still
*arrive*, but they're detected and ignored, so the work happens exactly once.
This gives "effectively exactly-once" behaviour on top of at-least-once delivery.

**Retry + DLQ:** each message carries an `attempts` counter that travels with it.
On failure the counter increments; if it's below `MAX_RETRIES` (3) the message is
pushed back onto the main queue, otherwise it's pushed to the DLQ **with the error
attached**. The **counter is what stops the infinite loop**; the **DLQ is where the
message lands** so it isn't lost.

## Trigger a failure yourself

The work function fails on any payload containing the string `POISON`:

```python
produce("POISON whatever you like")     # will fail 3x then hit the DLQ
produce("anything else")                # succeeds
```

## Inspect Redis directly

```powershell
docker exec -it healix-redis redis-cli

LLEN agent:tasks           # how many tasks are waiting
LLEN agent:dlq             # how many failed permanently
LRANGE agent:dlq 0 -1      # see the dead-lettered messages
SMEMBERS agent:processed   # which message IDs have been completed
exit
```

## Limitations (deliberate — concepts over production-hardening)

- **Single-threaded** — one consumer, processed synchronously.
- **No true acknowledgment semantics.** Uses `RPOP`, which removes the message
  immediately. If the consumer *crashed* mid-work, the message would be lost.
  A production version uses `BRPOPLPUSH` to atomically move the message to a
  "processing" list, only deleting it after successful completion.
- **No exponential backoff on retries** — retries are immediate. Production would
  space them out (e.g. 10min → 15min → 30min).
- **No alerting** — a DLQ arrival should notify an on-call engineer with the agent
  name, message ID, error, attempt count and payload. In a clinical system it
  should *also* alert the operational side, since a DLQ'd task means a patient's
  case didn't get processed.

## The pattern this maps to

Everything here transfers directly to SQS / RabbitMQ — only the API calls change.
The design decision from Week 6 Tuesday was **SQS** for agent orchestration
(near-zero ops burden, AWS deployment, scale is thousands not millions), with
self-hosted RabbitMQ if on-premises hospital deployment demands it, and Kafka only
if event replay or millions of msgs/sec ever becomes a real requirement.