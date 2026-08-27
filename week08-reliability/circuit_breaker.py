import time
import random

# ---------- The flaky dependency (stands in for an LLM provider) ----------

FAILURE_RATE = 0.4          # fails ~40% of the time
force_down = False           # flip to True to simulate a total outage


def flaky_call(payload):
    """Simulates calling an external model provider."""
    if force_down:
        raise ConnectionError("provider unreachable")
    if random.random() < FAILURE_RATE:
        raise ConnectionError("provider timed out")
    return f"OK: {payload}"


# ---------- Layer 1: retries with exponential backoff + jitter ----------

MAX_RETRIES = 3


def call_with_retries(payload):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = flaky_call(payload)
            print(f"      attempt {attempt}: SUCCESS")
            return result
        except ConnectionError as e:
            if attempt == MAX_RETRIES:
                print(f"      attempt {attempt}: FAILED ({e}) — retries exhausted")
                raise
            # exponential backoff with jitter: random(0 .. 2^attempt) capped small for the demo
            ceiling = 0.1 * (2 ** attempt)
            wait = random.uniform(0, ceiling)
            print(f"      attempt {attempt}: FAILED ({e}) — retrying in {wait:.3f}s")
            time.sleep(wait)

# ---------- Layer 2: circuit breaker ----------

FAILURE_THRESHOLD = 3        # consecutive failures before tripping
COOLDOWN = 3                 # seconds to stay open before probing

class CircuitBreaker:
    def __init__(self):
        self.state = "CLOSED"
        self.consecutive_failures = 0
        self.opened_at = None

    def call(self, payload):
        # --- OPEN: fail fast, unless cooldown has expired ---
        if self.state == "OPEN":
            if time.time() - self.opened_at >= COOLDOWN:
                self.state = "HALF_OPEN"
                print("  [BREAKER] cooldown over -> HALF_OPEN (sending one probe)")
            else:
                remaining = COOLDOWN - (time.time() - self.opened_at)
                raise RuntimeError(f"circuit OPEN — failing fast ({remaining:.1f}s left)")

        # --- CLOSED or HALF_OPEN: actually attempt the call ---
        try:
            result = call_with_retries(payload)
        except ConnectionError:
            self.consecutive_failures += 1
            if self.state == "HALF_OPEN":
                self.state = "OPEN"
                self.opened_at = time.time()
                print("  [BREAKER] probe FAILED -> back to OPEN")
            elif self.consecutive_failures >= FAILURE_THRESHOLD:
                self.state = "OPEN"
                self.opened_at = time.time()
                print(f"  [BREAKER] {self.consecutive_failures} consecutive failures -> OPEN")
            raise

        # --- success ---
        if self.state == "HALF_OPEN":
            print("  [BREAKER] probe SUCCEEDED -> CLOSED")
        self.state = "CLOSED"
        self.consecutive_failures = 0
        return result

 #test code
 
breaker = CircuitBreaker()

print("\n=== Normal operation (40% failure, breaker CLOSED) ===")
for i in range(5):
    print(f"  Request {i+1}: [{breaker.state}]")
    try:
        print(f"    -> {breaker.call(f'task-{i+1}')}")
    except Exception as e:
        print(f"    -> {e}")

print("\n=== Provider goes DOWN — watch the breaker trip ===")
force_down = True
for i in range(6):
    print(f"  Request {i+1}: [{breaker.state}]")
    try:
        print(f"    -> {breaker.call(f'task-{i+1}')}")
    except Exception as e:
        print(f"    -> {e}")

print("\n=== Waiting for cooldown... ===")
time.sleep(COOLDOWN + 0.5)

print("\n=== Probe while still down ===")
try:
    breaker.call("probe-task")
except Exception as e:
    print(f"    -> {e}")

print("\n=== Provider RECOVERS — watch the breaker close ===")
force_down = False
time.sleep(COOLDOWN + 0.5)
for i in range(4):
    print(f"  Request {i+1}: [{breaker.state}]")
    try:
        print(f"    -> {breaker.call(f'task-{i+1}')}")
    except Exception as e:
        print(f"    -> {e}")