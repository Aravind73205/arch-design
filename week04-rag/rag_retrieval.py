import time
from sentence_transformers import SentenceTransformer
import psycopg2

# 1. we load the local embedding model (downloads once, then cached)
print("Loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded.")

# 2. it connect to the pgvector database (note port 5433 — the vector container)
conn = psycopg2.connect(
    host="localhost",
    port=5433,
    dbname="vectordb",
    user="postgres",
    password="mypassword"
)
cur = conn.cursor()
print("Connected to pgvector.")

# 3. some guideline-style text (stand-in for a real clinical document)
guideline_text = """
Lung cancer staging follows the TNM system, where T describes tumor size, N describes lymph node involvement, and M describes metastasis.
Early-stage non-small cell lung cancer is often treated with surgical resection when the patient is a suitable candidate.
Chemotherapy is commonly recommended for patients with locally advanced or metastatic disease to control tumor growth.
Radiation therapy may be used alone or combined with chemotherapy, particularly when surgery is not an option.
Patients presenting with shortness of breath and persistent cough should be evaluated for possible pulmonary complications.
Immunotherapy has emerged as an effective treatment for certain patients based on biomarker expression such as PD-L1.
Regular follow-up imaging is essential to monitor treatment response and detect recurrence early.
Palliative care focuses on symptom management and quality of life for patients with advanced disease.
Smoking cessation is strongly advised at every stage as it improves treatment outcomes and overall survival.
Genetic testing for mutations such as EGFR and ALK guides the selection of targeted therapies.
"""

# 4. Chunk it — split into individual sentences/lines (simple chunking)
chunks = [line.strip() for line in guideline_text.strip().split("\n") if line.strip()]
print(f"Created {len(chunks)} chunks.")

# 5. Embed each chunk and store it in pgvector
# Clear any existing rows first (so re-running the script doesn't duplicate)
cur.execute("DELETE FROM guideline_chunks;")

for chunk in chunks:
    embedding = model.encode(chunk)          # text -> 384-dim vector
    cur.execute(
        "INSERT INTO guideline_chunks (chunk_text, embedding) VALUES (%s, %s)",
        (chunk, embedding.tolist())          # store the chunk + its vector
    )

conn.commit()
print("All chunks embedded and stored in pgvector.")

# 6. RETRIEVAL FUNCTION: query in -> top-k nearest chunks out
def retrieve(query, k=3):
    query_embedding = model.encode(query)      # embed the user's query

    start = time.time()                          # start timing
    cur.execute(
        """
        SELECT chunk_text, embedding <=> %s::vector AS distance
        FROM guideline_chunks
        ORDER BY distance
        LIMIT %s
        """,
        (query_embedding.tolist(), k)
    )
    results = cur.fetchall()
    elapsed = (time.time() - start) * 1000       # ms

    print(f"\nQuery: '{query}'")
    print(f"Retrieval time: {elapsed:.2f} ms")
    print(f"Top {k} chunks:")
    for i, (text, distance) in enumerate(results, 1):
        print(f"  {i}. (distance {distance:.4f}) {text}")

# 7. Try some queries
retrieve("patient has trouble breathing")
retrieve("what treatment for early stage cancer")
retrieve("how to guide targeted therapy selection")

# 8. CHUNK SIZE COMPARISON — large chunks (group sentences together)
# Re-chunk: combine every ~3 sentences into one bigger chunk
big_chunks = []
for i in range(0, len(chunks), 3):
    big_chunks.append(" ".join(chunks[i:i+3]))

print(f"\n--- Re-indexing with {len(big_chunks)} LARGE chunks (was {len(chunks)} small) ---")

cur.execute("DELETE FROM guideline_chunks;")
for chunk in big_chunks:
    embedding = model.encode(chunk)
    cur.execute(
        "INSERT INTO guideline_chunks (chunk_text, embedding) VALUES (%s, %s)",
        (chunk, embedding.tolist())
    )
conn.commit()

# Run the SAME query against the large chunks
retrieve("patient has trouble breathing", k=2)