import httpx
import json
import time

print("Sending test.pdf to /generate-quiz ...")
start = time.time()

with open("test.pdf", "rb") as f:
    resp = httpx.post(
        "http://localhost:8000/generate-quiz",
        files={"file": ("test.pdf", f, "application/pdf")},
        timeout=300,
    )

elapsed = time.time() - start
print(f"Status : {resp.status_code}  ({elapsed:.1f}s)")

if resp.status_code == 200:
    data = resp.json()
    print(f"Total questions : {data['total_questions']}")
    print(f"Total chunks    : {data['total_chunks']}")
    print(f"Total pages     : {data['total_pages']}")
    print()
    print("--- First 2 questions ---")
    for q in data["questions"][:2]:
        print(json.dumps(q, indent=2))
else:
    print("ERROR:", resp.text[:2000])
