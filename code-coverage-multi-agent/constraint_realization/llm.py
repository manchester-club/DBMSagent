"""LLM client for plan instantiation. Analysis never goes through here."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

# Same defaults as langgraph/coverage_multi_agent.py (金箍 DeepSeek).
_DEFAULT_KEY = (
    os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or "sk-c15a9ceabf774ecf9b2aac355ef5f8bc"
)
_DEFAULT_BASE = (
    os.environ.get("DEEPSEEK_BASE_URL")
    or os.environ.get("OPENAI_BASE_URL")
    or "https://api.deepseek.com"
)
_DEFAULT_MODEL = os.environ.get("LLM_MODEL") or "deepseek-chat"


class LLMError(RuntimeError):
    pass


def _messages(prompt: Optional[str], system: str, messages: Optional[List[dict]]) -> List[dict]:
    out = [{"role": "system", "content": system}]
    if messages:
        out.extend(messages)
    elif prompt:
        out.append({"role": "user", "content": prompt})
    else:
        raise LLMError("no prompt or messages")
    return out


def _complete_openai_compat(
    prompt: Optional[str],
    *,
    system: str,
    temperature: float,
    messages: Optional[List[dict]] = None,
) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or _DEFAULT_KEY
    if not key:
        raise LLMError("no DEEPSEEK_API_KEY / OPENAI_API_KEY")
    base = (
        os.environ.get("DEEPSEEK_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or _DEFAULT_BASE
    ).rstrip("/")
    model = os.environ.get("LLM_MODEL") or _DEFAULT_MODEL
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": _messages(prompt, system, messages),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _complete_ollama(
    prompt: Optional[str],
    *,
    system: str,
    temperature: float,
    messages: Optional[List[dict]] = None,
) -> str:
    host = (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL") or os.environ.get("LLM_MODEL") or "qwen3:32b"
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": _messages(prompt, system, messages),
    }
    req = urllib.request.Request(
        host + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["message"]["content"]


def complete_chat(
    prompt: Optional[str] = None,
    *,
    system: str,
    temperature: float = 0.2,
    messages: Optional[List[dict]] = None,
) -> str:
    errors = []
    for fn, name in (
        (_complete_openai_compat, "deepseek/openai"),
        (_complete_ollama, "ollama"),
    ):
        try:
            return fn(prompt, system=system, temperature=temperature, messages=messages)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise LLMError("; ".join(errors))


def extract_json_object(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("LLM output has no JSON object")
    return json.loads(text[start : end + 1])
