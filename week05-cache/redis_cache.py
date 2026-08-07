import time
import redis

# Connect to Redis (port 6379, the container we just started)
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
print("Connected to Redis:", r.ping())   # r.ping() tests the connection(returns True if Redis is alive)


def slow_guideline_lookup(question):
    """
    Stands in for the expensive guideline-RAG pipeline:
    embed the query -> vector search -> LLM call.
    Simulated here with a 2-second delay.
    """
    time.sleep(2)
    return f"Guideline answer for: '{question}'"


def get_guideline(question):
    """Cache-aside: check cache -> miss -> compute -> store -> return."""
    cache_key = f"guideline:{question}"

    # 1. Check the cache first
    cached = r.get(cache_key)
    if cached:
        return cached, "HIT"

    # 2. Cache miss -> do the expensive work
    answer = slow_guideline_lookup(question)

    # 3. Store it in the cache with a TTL, then return
    r.setex(cache_key, 60, answer)      # 60-second TTL
    return answer, "MISS"


def timed_call(question):
    start = time.time()
    answer, status = get_guideline(question)
    elapsed = (time.time() - start) * 1000
    print(f"[{status}] {elapsed:8.2f} ms  |  {answer}")


q = "what is the treatment protocol for early stage lung cancer"

print("\n--- First call (cache empty) ---")
timed_call(q)

print("\n--- Second call (should be cached) ---")
timed_call(q)

print("\n--- Third call ---")
timed_call(q)

print("\n--- TTL DEMO: short 5-second cache ---")

def get_with_short_ttl(question):
    cache_key = f"short:{question}"
    cached = r.get(cache_key)
    if cached:
        return cached, "HIT"
    answer = slow_guideline_lookup(question)
    r.set(cache_key, answer, ex=5)      # 5-second TTL
    return answer, "MISS"

def timed_short(question):
    start = time.time()
    answer, status = get_with_short_ttl(question)
    elapsed = (time.time() - start) * 1000
    print(f"[{status}] {elapsed:8.2f} ms")

q2 = "what is TNM staging"

print("Call 1 (empty cache):")
timed_short(q2)

print("Call 2 (immediately after — cached):")
timed_short(q2)

print("Waiting 6 seconds for TTL to expire...")
time.sleep(6)

print("Call 3 (after TTL expired):")
timed_short(q2)