"""
scripts/test_groq_inference.py

Test script to verify Groq LLM inference locally using the GROQ_API_KEY
environment variable from the local .env file.

Usage:
    python scripts/test_groq_inference.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from dotenv import load_dotenv

# 1. Load .env file
load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
llm_model = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")

print("=" * 60)
print("Groq LLM Inference Verification")
print("=" * 60)

if not groq_api_key:
    print("ERROR: GROQ_API_KEY is not set in environment or .env file.")
    print("Please set GROQ_API_KEY in your .env file or export it.")
    sys.exit(1)

masked_key = f"{groq_api_key[:6]}...{groq_api_key[-4:]}" if len(groq_api_key) > 10 else "***"
print(f"GROQ_API_KEY detected : {masked_key}")
print(f"Target LLM Model       : {llm_model}")
print("-" * 60)

# 2. Test direct Groq SDK call (Streaming & Non-Streaming)
from groq import Groq

client = Groq()

print("\n[Step 1/3] Testing Groq streaming completion...")
try:
    completion = client.chat.completions.create(
        model=llm_model,
        messages=[
            {
                "role": "user",
                "content": "Respond with: 'Hello from Groq! Qwen inference is working.'",
            }
        ],
        temperature=0.6,
        max_completion_tokens=2048,
        top_p=0.95,
        reasoning_effort="default",
        stream=True,
        stop=None,
    )

    print("Streamed output: ", end="")
    for chunk in completion:
        print(chunk.choices[0].delta.content or "", end="")
    print("\n--> Step 1 PASSED!")
except Exception as exc:
    print(f"\n--> Step 1 FAILED: {exc}")
    sys.exit(1)


# 3. Test app's synchronous call_llm wrapper
from app.llm.llm_client import call_llm
from app.prompts.quiz_prompt import SYSTEM_PROMPT

sample_text = (
    "Photosynthesis is the process used by plants and other organisms to convert light energy "
    "into chemical energy that can later be released to fuel the organisms' metabolic activities."
)
user_prompt = f"Generate 1 multiple-choice question from this text:\n\n{sample_text}"

print("\n[Step 2/3] Testing app.llm.llm_client.call_llm (synchronous)...")
sync_record = call_llm(
    system_prompt=SYSTEM_PROMPT,
    user_prompt=user_prompt,
    model=llm_model,
)

if sync_record.success and sync_record.parsed_questions:
    print(f"--> Step 2 PASSED! Latency: {sync_record.latency_seconds:.3f}s | Tokens: {sync_record.tokens_used}")
    print(f"Parsed Question: {sync_record.parsed_questions[0].get('question')}")
else:
    print(f"--> Step 2 FAILED: {sync_record.error}")
    sys.exit(1)


# 4. Test app's asynchronous acall_llm wrapper (used in quiz generation pipeline)
from app.llm.llm_client import acall_llm

async def run_async_test():
    print("\n[Step 3/3] Testing app.llm.llm_client.acall_llm (asynchronous pipeline call)...")
    async_record = await acall_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=llm_model,
    )
    if async_record.success and async_record.parsed_questions:
        print(f"--> Step 3 PASSED! Latency: {async_record.latency_seconds:.3f}s | Tokens: {async_record.tokens_used}")
        print(f"Parsed Question: {async_record.parsed_questions[0].get('question')}")
    else:
        print(f"--> Step 3 FAILED: {async_record.error}")
        sys.exit(1)

asyncio.run(run_async_test())

print("\n" + "=" * 60)
print("ALL GROQ INFERENCE TESTS PASSED SUCCESSFULLY!")
print("=" * 60)
