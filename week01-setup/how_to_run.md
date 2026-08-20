# Week 1 — Environment Setup & Hello World API

The first Saturday build. Deliberately trivial: the point isn't the code, it's
proving the whole toolchain works end to end **before** any real build day depends
on it.

## What's here

- `main.py` — a single-endpoint FastAPI app (`GET /hello`)

## Prerequisites

```powershell
# from the repo root
venv\Scripts\Activate.ps1
pip install -r requirements.txt        # needs fastapi, uvicorn
```

## How to run

```powershell
cd week01-setup
uvicorn main:app --reload
```

Server starts on `http://127.0.0.1:8000`. In a **second terminal**:

```powershell
curl.exe http://127.0.0.1:8000/hello
```

Expected:
```json
{"message":"loop works"}
```

You can also open `http://127.0.0.1:8000/hello` in a browser — same result.

**Note:** `http://127.0.0.1:8000` (the root) returns **404**, and that's correct —
only `/hello` is defined. A 404 means the server is alive and telling you that
address doesn't exist.

## What this actually verifies

The endpoint is pointless; the **loop** is the point. One successful request
confirms four links at once:

1. **Environment** — the venv activates and FastAPI is installed
2. **Server** — uvicorn starts and listens on port 8000
3. **Network** — a request from outside reaches the server
4. **Response** — the handler runs and the answer comes back

If any link were broken, you'd find out *here*, on a throwaway task, rather than
mid-build three weeks later when you can't tell whether it's your new code or your
setup.

## The pieces

- **FastAPI is the chef** — defines what each endpoint returns. It can't run
  alone; it doesn't know how to listen on a network port.
- **uvicorn is the waiter** — the actual server. It stands at the port, takes
  incoming HTTP requests, hands them to FastAPI, and carries the response back.

```
uvicorn main:app --reload
        │    │    └── auto-restart on file save
        │    └── the `app = FastAPI()` variable inside the file
        └── the file (main.py, minus the .py)
```

**Ports:** `127.0.0.1` means "this computer"; `:8000` is the door number. Each
program listening for network traffic needs its own port — which is why Postgres
uses 5432, pgvector 5433, Redis 6379, and the Week 7 workers 8001/8002/8003.

## Environment setup (one-time, if starting from a fresh clone)

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
(type `Y`, then retry the activate line)

**In Cursor/VS Code:** `Ctrl+Shift+P` → "Python: Select Interpreter" → pick the
one ending in `venv\Scripts\python.exe`. That makes new terminals auto-activate
the venv and stops the editor flagging imports as missing.

`venv/` is gitignored (machine-specific, large, regenerable). `requirements.txt`
**is** committed — it's the recipe for rebuilding the environment anywhere. Same
principle as a Dockerfile: ship the instructions, not the environment.

## Docker (installed this week, used from Week 3 onward)

Docker Desktop was set up in this week too, though nothing here uses it.
Verification:

```powershell
docker run hello-world
```

That single command demonstrates the whole model: Docker **pulls an image** from
Docker Hub (the registry), **creates a container** from it, runs it, and it exits.
Image = the frozen blueprint on disk; container = a running instance of it.

**On Windows, Docker requires WSL 2** — containers are built on Linux kernel
features (namespaces, cgroups) that Windows doesn't have, so WSL 2 provides a real
Linux kernel for Docker to run them on. If Docker complains WSL isn't installed,
run `wsl --install` in an **administrator** PowerShell and restart.

## Limitations

It's a hello-world. That's the entire point — a throwaway task whose only job is
to prove the pipeline is clean before real work depends on it.