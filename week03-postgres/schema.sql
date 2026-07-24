-- Week 3 Saturday: HEALiX schema in PostgreSQL (Docker)
-- Run with: docker run --name healix-pg -e POSTGRES_PASSWORD=mypassword 
--           -e POSTGRES_DB=healix -p 5432:5432 -d postgres

CREATE TABLE patients (
    patient_id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    dob DATE,
    phone VARCHAR(15)
);

CREATE TABLE doctors (
    doctor_id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    specialty VARCHAR(100)
);

CREATE TABLE cases (
    case_id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES patients(patient_id),
    doctor_id INT REFERENCES doctors(doctor_id),
    diagnosis VARCHAR(200),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE recommendations (
    rec_id SERIAL PRIMARY KEY,
    case_id INT REFERENCES cases(case_id),
    doctor_id INT REFERENCES doctors(doctor_id),
    text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- The index that made the difference (foreign keys are NOT auto-indexed in Postgres)
CREATE INDEX idx_cases_patient_id ON cases(patient_id);

-- RESULT on 505,000 rows, query: SELECT * FROM cases WHERE patient_id = 500;
--   WITHOUT index: Seq Scan, 168,165 rows discarded per worker, 4717 buffers -> 16.772 ms
--   WITH index:    Bitmap Index Scan, 505 rows fetched directly, 508 buffers -> 0.823 ms
--   ~20x faster, ~10x less data touched
--
-- Also learned: an index existing doesn't mean it gets used. On a JOIN fetching
-- ~10% of the table, Postgres chose Seq Scan over the index -- because at that
-- fraction, reading sequentially beats 50,000 index lookups. The planner decides
-- based on how much of the table you're touching.