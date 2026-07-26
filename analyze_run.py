import json

with open("runs/20260710T173958Z_upload.json", encoding="utf-8") as f:
    run = json.load(f)

meta   = run["run_metadata"]
stats  = run["parse_stats"]
chunks = run["chunks"]
summary = run["summary"]

print("=" * 60)
print("  MODEL")
print("=" * 60)
print(f"  {meta['model']}")

print()
print("=" * 60)
print("  DOCUMENT STATS")
print("=" * 60)
print(f"  Pages            : {stats['total_pages']}")
print(f"  Chars            : {stats['total_chars']:,}")
print(f"  Total doc tokens : {stats['total_tokens_in_document']:,}")
print(f"  Parse time       : {stats['parse_time_seconds']}s")

print()
print("=" * 60)
print(f"  LLM CALLS  (1 call per chunk = {len(chunks)} total calls)")
print("=" * 60)
print(f"  {'Chunk':<6} {'Tokens In':<12} {'Tokens Used':<14} {'Latency':<10} {'Questions'}")
print(f"  {'-'*5:<6} {'-'*10:<12} {'-'*11:<14} {'-'*8:<10} {'-'*9}")
for c in chunks:
    llm = c["llm"]
    print(
        f"  {c['chunk_index']:<6} "
        f"{c['token_count']:<12,} "
        f"{llm['tokens_used']:<14,} "
        f"{llm['latency_seconds']:.2f}s     "
        f"{len(c['questions'])}"
    )

total_in  = sum(c["token_count"] for c in chunks)
total_out = sum(c["llm"]["tokens_used"] for c in chunks)
avg_in    = total_in / len(chunks)
avg_out   = total_out / len(chunks)
avg_lat   = sum(c["llm"]["latency_seconds"] for c in chunks) / len(chunks)

print()
print(f"  {'TOTAL':<6} {total_in:<12,} {total_out:<14,}")
print(f"  {'AVG':<6} {avg_in:<12,.0f} {avg_out:<14,.0f} {avg_lat:.2f}s")

print()
print("=" * 60)
print("  SUMMARY")
print("=" * 60)
print(f"  Total LLM calls        : {len(chunks)}")
print(f"  Total questions        : {summary['total_questions_generated']}")
print(f"  Total tokens in (doc)  : {total_in:,}")
print(f"  Total tokens used (LLM): {total_out:,}")
print(f"  Total pipeline time    : {summary['total_pipeline_seconds']}s")
print(f"  Avg latency / call     : {avg_lat:.2f}s")
