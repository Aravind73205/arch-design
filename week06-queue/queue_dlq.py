import json
import time
import uuid
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

MAIN_QUEUE = "agent:tasks"
DLQ = "agent:dlq"
PROCESSED_SET = "agent:processed"     # tracks message IDs already handled
MAX_RETRIES = 3


def produce(payload):
    """Producer: push a task onto the queue with a unique message ID."""
    message = {
        "id": str(uuid.uuid4()),      # unique message ID (for idempotency)
        "payload": payload,
        "attempts": 0                  # retry counter
    }
    r.lpush(MAIN_QUEUE, json.dumps(message))  #r.lpush means puts it on the left end of the queue — exactly the LPUSH we did by hand in redis.
    print(f"  [PRODUCED] {message['id'][:8]} | {payload}")
    return message["id"]


def process_task(payload):
    """
    The actual 'agent work'. 
    Deliberately fails on any payload containing 'POISON'.
    """
    if "POISON" in payload:           # if the payload contains the word "POISON", it raises an exception (fails). Otherwise it succeeds.
        raise ValueError("Cannot process this payload — malformed input")
    return f"Processed: {payload}"


def consume_one():
    """Consumer: pop one task, check idempotency, process, handle failure."""
    raw = r.rpop(MAIN_QUEUE)  # RPOP takes the oldest message off the right end (FIFO)
    if raw is None:
        return False                          # queue empty

    message = json.loads(raw)
    msg_id = message["id"]

    # --- IDEMPOTENCY CHECK ---
    if r.sismember(PROCESSED_SET, msg_id):   # sismember means (S + IS MEMBER = "Is this a member of the Set")
        print(f"  [DUPLICATE] {msg_id[:8]} already processed — skipping")
        return True

    # --- PROCESS ---
    try:
        result = process_task(message["payload"])
        r.sadd(PROCESSED_SET, msg_id)          # mark as done  # (SADD = Set ADD)
        print(f"  [SUCCESS]   {msg_id[:8]} | {result}")

    except Exception as e:
        message["attempts"] += 1
        if message["attempts"] >= MAX_RETRIES:
            r.lpush(DLQ, json.dumps({**message, "error": str(e)}))
            print(f"  [DLQ]       {msg_id[:8]} | failed {message['attempts']}x → moved to DLQ | error: {e}")
        else:
            r.lpush(MAIN_QUEUE, json.dumps(message))   # retry
            print(f"  [RETRY {message['attempts']}]   {msg_id[:8]} | {e}")

    return True


def drain_queue():
    """Process everything currently in the queue."""
    while consume_one():
        pass


def show_state():
    print(f"\n  Queue depth: {r.llen(MAIN_QUEUE)}  |  DLQ depth: {r.llen(DLQ)}")


# ---------- CLEAN SLATE ----------
r.delete(MAIN_QUEUE, DLQ, PROCESSED_SET)


# ---------- DEMO 1: normal processing ----------
print("\n=== DEMO 1: Normal tasks ===")
produce("analyze patient 500")
produce("summarize case 42")
drain_queue()
show_state()


# ---------- DEMO 2: idempotency (duplicate delivery) ----------
print("\n=== DEMO 2: Duplicate message (at-least-once simulation) ===")
msg_id = produce("record diagnosis for patient 700")
drain_queue()

# Simulate the queue redelivering the SAME message (ack was lost)
duplicate = {"id": msg_id, "payload": "record diagnosis for patient 700", "attempts": 0}
r.lpush(MAIN_QUEUE, json.dumps(duplicate))
print("  (queue redelivered the same message — ack was lost)")
drain_queue()
show_state()


# ---------- DEMO 3: poison message → DLQ ----------
print("\n=== DEMO 3: Poison message ===")
produce("POISON corrupt patient record")
drain_queue()
show_state()

print("\n=== DLQ CONTENTS ===")
for item in r.lrange(DLQ, 0, -1):
    entry = json.loads(item)
    print(f"  id={entry['id'][:8]} | attempts={entry['attempts']} | error={entry['error']}")
    print(f"  payload: {entry['payload']}")