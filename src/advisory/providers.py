"""LLM providers behind one interface. Order comes from LLM_PROVIDERS (default "ollama,playbook").

Every provider streams text chunks; the caller assembles and validates the JSON.
"""
from __future__ import annotations

import json
import os
from typing import Iterator

import httpx

from src.advisory.prompts import SYSTEM
from src.advisory.schema import LLM_SCHEMA


class ProviderError(RuntimeError):
    pass


class OllamaProvider:
    name = "ollama"

    def __init__(self):
        self.base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.timeout = float(os.getenv("LLM_TIMEOUT_S", "60"))

    @property
    def label(self) -> str:
        return f"Local · {self.model}"

    def status(self) -> dict:
        try:
            r = httpx.get(f"{self.base}/api/tags", timeout=2.0)
            names = [m["name"] for m in r.json().get("models", [])]
            ok = any(n == self.model or n.split(":")[0] == self.model for n in names)
            return {"available": ok, "detail": "ready" if ok else f"model {self.model} not pulled",
                    "installed": names}
        except Exception as e:  # server down / not installed
            return {"available": False, "detail": f"ollama unreachable ({type(e).__name__})"}

    # Same num_ctx for warm-up and generation: a different context size forces Ollama to reload the model.
    OPTIONS = {"temperature": 0.2, "num_ctx": 2048, "num_predict": 700}

    def warm(self) -> None:
        httpx.post(f"{self.base}/api/generate", json={"model": self.model, "prompt": "", "keep_alive": "30m",
                                                      "options": self.OPTIONS}, timeout=120.0)

    def stream(self, prompt: str) -> Iterator[str]:
        body = {
            "model": self.model, "stream": True, "format": LLM_SCHEMA, "keep_alive": "30m",
            "options": self.OPTIONS,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        }
        try:
            with httpx.stream("POST", f"{self.base}/api/chat", json=body, timeout=self.timeout) as r:
                if r.status_code != 200:
                    raise ProviderError(f"ollama HTTP {r.status_code}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("error"):
                        raise ProviderError(msg["error"])
                    chunk = msg.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if msg.get("done"):
                        break
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama: {type(e).__name__}") from e


class GeminiProvider:
    """Optional cloud tier. Enabled only when GEMINI_API_KEY is set and 'gemini' is in LLM_PROVIDERS."""
    name = "gemini"

    def __init__(self):
        self.key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout = float(os.getenv("LLM_TIMEOUT_S", "60"))

    @property
    def label(self) -> str:
        return f"Gemini · {self.model}"

    def status(self) -> dict:
        return {"available": bool(self.key), "detail": "key configured" if self.key else "GEMINI_API_KEY not set"}

    def warm(self) -> None:
        pass

    def stream(self, prompt: str) -> Iterator[str]:
        if not self.key:
            raise ProviderError("gemini: no API key")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
               f":streamGenerateContent?alt=sse")
        schema = _gemini_schema(LLM_SCHEMA)
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200,
                                 "responseMimeType": "application/json", "responseSchema": schema},
        }
        try:
            with httpx.stream("POST", url, json=body, timeout=self.timeout,
                              headers={"x-goog-api-key": self.key}) as r:
                if r.status_code != 200:
                    raise ProviderError(f"gemini HTTP {r.status_code}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:])
                    for cand in data.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            if part.get("text"):
                                yield part["text"]
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini: {type(e).__name__}") from e


def _gemini_schema(s: dict) -> dict:
    """Gemini's responseSchema is an OpenAPI subset: drop keywords it does not accept."""
    out = {k: v for k, v in s.items() if k not in ("minItems", "maxItems")}
    if "properties" in out:
        out["properties"] = {k: _gemini_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _gemini_schema(out["items"])
    return out


REGISTRY = {"ollama": OllamaProvider, "gemini": GeminiProvider}


def configured_chain() -> list:
    names = [n.strip() for n in os.getenv("LLM_PROVIDERS", "ollama,playbook").split(",") if n.strip()]
    return [REGISTRY[n]() for n in names if n in REGISTRY]
