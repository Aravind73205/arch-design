from fastapi import FastAPI, Request
import httpx
import itertools

app = FastAPI()

# The three backend workers
BACKENDS = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
]

# itertools.cycle gives an endless rotation: 8001, 8002, 8003, 8001, 8002...
backend_pool = itertools.cycle(BACKENDS)                    # this is the round-robin engine, it will cycle through the backends in a round-robin manner


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    backend = next(backend_pool)          # ← round-robin: pick the next worker
    url = f"{backend}/{path}"

    body = await request.body()

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers={"content-type": request.headers.get("content-type", "application/json")},
        )

    print(f"  → routed {request.method} /{path}  ->  {backend}")
    return response.json()