"""Tiny OpenAI-compatible chat server standing in for vLLM/llama.cpp in tests."""
import json

from fastapi import FastAPI, Request

app = FastAPI()
SEEN: list[dict] = []


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    user = body["messages"][-1]["content"]
    # a deliberately weak verdict for the injected-leak scenario so the policy path is exercised
    weak = "SYSTEM PROMPT" in user
    out = {"score": 0.1 if weak else 0.9, "justification": "stub verdict", "evidence": ["stub"], "confidence": 0.9}
    return {"choices": [{"message": {"content": json.dumps(out)}}]}
