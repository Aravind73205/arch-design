# Week 3 — PostgreSQL Schema & Indexing

A normalized clinical schema in PostgreSQL (running in Docker), with a measured
demonstration of what an index actually buys you — and, more interestingly, when
the query planner decides *not* to use one.

## What's here

- `schema.sql` — the four-table schema, the index, and the measured results

## Prerequisites

**Docker Desktop must be running** (whale icon → "Engine running").

```powershell
docker start healix-pg

# if it doesn't exist yet:
# docker run --name healix-pg -e POSTGRES_PASSWORD=mypassword -e POSTGRES_DB=healix `
#   -p 5432:5432 -d postgres

docker ps      # confirm it's up
```

## How to run

Connect to the database:

```powershell
docker exec -it healix-pg psql -U postgres -d healix
```

Turn off the pager so long output doesn't trap you in a `(END)` screen:
```sql
\pset pager off
```

Then paste the contents of `schema.sql` to create the tables.

**Note:** data lives inside the container. `docker rm` deletes it; `docker stop`
does not. Nothing here is stored on the Windows filesystem.

## Generating test data

```sql
-- 1,000 patients
INSERT INTO patients (name, dob, phone)
SELECT 'Patient_' || i,
       '1960-01-01'::date + (i % 20000),
       '9' || LPAD((i % 1000000000)::text, 9, '0')
FROM generate_series(1, 1000) AS i;

-- 20 doctors
INSERT INTO doctors (name, specialty)
SELECT 'Doctor_' || i,
       (ARRAY['Oncology','Radiology','Pathology','Surgery'])[1 + (i % 4)]
FROM generate_series(1, 20) AS i;

-- 5,000 cases
INSERT INTO cases (patient_id, doctor_id, diagnosis, status)
SELECT 1 + (i % 1000), 1 + (i % 20),
       (ARRAY['Lung CA','Breast CA','Colon CA','Lymphoma'])[1 + (i % 4)],
       (ARRAY['pending','under_review','closed'])[1 + (i % 3)]
FROM generate_series(1, 5000) AS i;

-- 15,000 recommendations
INSERT INTO recommendations (case_id, doctor_id, text)
SELECT 1 + (i % 5000), 1 + (i % 20), 'Recommendation text number ' || i
FROM generate_series(1, 15000) AS i;

-- 500,000 more cases (needed for the index difference to be visible)
INSERT INTO cases (patient_id, doctor_id, diagnosis, status)
SELECT 1 + (i % 1000), 1 + (i % 20), 'Diagnosis ' || i, 'pending'
FROM generate_series(1, 500000) AS i;
```

`generate_series(1, N)` produces the numbers 1..N; `||` concatenates text; `%` is
modulo, used to spread values around.

## The main experiment — index vs no index

**Without the index** (force Postgres to ignore it):
```sql
SET enable_indexscan = off;
SET enable_bitmapscan = off;
EXPLAIN ANALYZE SELECT * FROM cases WHERE patient_id = 500;
```

**With the index:**
```sql
SET enable_indexscan = on;
SET enable_bitmapscan = on;
EXPLAIN ANALYZE SELECT * FROM cases WHERE patient_id = 500;
```

### Result on 505,000 rows

| | Plan | Rows examined | Buffers | Time |
|---|---|---|---|---|
| **No index** | Parallel Seq Scan | 168,165 discarded × 3 workers | 4,717 | **16.772 ms** |
| **With index** | Bitmap Index Scan | 505 fetched directly | 508 | **0.823 ms** |

**~20× faster, ~10× less data touched.**

Without the index Postgres was so desperate it launched **2 extra parallel
workers** to split the scanning — and still took 20× longer than a single process
using the index.

**Why `cases.patient_id` needed an index at all:** it's a **foreign key**, and
PostgreSQL does **not** auto-index foreign keys (it only auto-indexes primary
keys, because it needs an index to enforce uniqueness). Foreign-key indexes are
your decision — which is the point, since indexes cost write speed and storage.

## The more interesting finding — when an index is deliberately ignored

```sql
EXPLAIN ANALYZE
SELECT p.name, c.diagnosis, c.status
FROM patients p
JOIN cases c ON c.patient_id = p.patient_id
WHERE p.patient_id BETWEEN 1 AND 100;
```

Result: **Postgres chose `Seq Scan on cases`, not the index** — 50,500 rows in
42ms.

**Why that's correct, not a failure:** the query needs ~50,500 of 505,000 rows —
about **10% of the table**. When you're touching that large a fraction, doing
50,000 separate index lookups is *slower* than reading the table sequentially. The
planner worked that out on its own.

**The lesson: an index existing doesn't mean it gets used.** Indexes help when
fetching a **small slice** (the single-patient query = 0.1% of the table → 20×
win); they stop helping on **large fractions**. The planner decides based on how
much of the table you're touching.

## Reading a query plan

```sql
EXPLAIN ANALYZE <query>;
```
Runs the query and shows both the plan and the real timing. What to look for:

- **`Seq Scan`** — reading the whole table row by row. Slow on big tables; usually
  means no index on the filtered column (or the planner chose not to use one).
- **`Index Scan` / `Bitmap Index Scan`** — using an index to jump to matching rows.
- **`Rows Removed by Filter`** — rows examined and thrown away. High numbers here
  are the waste an index eliminates.
- **`Buffers: shared hit`** — blocks found in memory (the DB's own cache).
  Fewer buffers = less data touched = faster.

## The schema

Four tables, normalized to 3NF: `patients`, `doctors`, `cases`,
`recommendations`. Foreign keys are **enforced** — you cannot insert a case
pointing at a non-existent patient.

**Design test used:** *"is this column a fact about the thing this table is named
after?"* If not, it belongs in another table with a foreign-key pointer. That one
question replaces memorizing 2NF vs 3NF.

**Useful commands:**
```sql
\dt                  -- list tables
\d cases             -- describe one table
SELECT COUNT(*) FROM cases;
```

## Limitations (deliberate)

- Data lives only inside the container — no volume mounted, so `docker rm` wipes it
- Only `cases.patient_id` is indexed; `cases.doctor_id` and
  `recommendations.case_id` should be too for the real query patterns
- No audit-log table (designed on paper in the Week 3 Friday capstone, not built)
- Synthetic data with unrealistic distribution — every patient has exactly ~505
  cases, so no data-size skew to observe