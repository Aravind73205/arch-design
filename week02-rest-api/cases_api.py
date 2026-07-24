from fastapi import FastAPI, HTTPException, BackgroundTasks
import time

#HTTPException we send error status codes like 404. 

app = FastAPI()

cases = {}   #cases = {} is our fake database — a plain Python dictionary holding all cases in memory.
next_id = 1  #next_id tracks what ID to give the next new case (1, then 2, then 3...)

@app.get("/cases")
def list_cases():
    return {"cases": list(cases.values())}


@app.post("/cases", status_code=201)
def create_case(case: dict):
    global next_id
    case_id = next_id
    next_id += 1

    new_case = {"id": case_id, **case}
    cases[case_id] = new_case

    return new_case

@app.get("/cases/{case_id}")
def get_case(case_id: int):
    if case_id not in cases:
        raise HTTPException(status_code=404, detail="Case not found")
    return cases[case_id]

@app.put("/cases/{case_id}")
def update_case(case_id: int, case: dict):
    if case_id not in cases:
        raise HTTPException(status_code=404, detail="Case not found")
    
    updated = {"id": case_id, **case}
    cases[case_id] = updated
    return updated

def slow_processing(case_id: int):
    """Pretend this is heavy work — de-identification, inference, etc."""
    time.sleep(5)
    print(f"[BACKGROUND] Finished processing case {case_id}")


@app.post("/cases/{case_id}/process-sync")
def process_sync(case_id: int):
    slow_processing(case_id)          # caller WAITS for this
    return {"status": "done", "case_id": case_id}


@app.post("/cases/{case_id}/process-async")
def process_async(case_id: int, background_tasks: BackgroundTasks):
    background_tasks.add_task(slow_processing, case_id)   # queued, not awaited
    return {"status": "accepted", "case_id": case_id}