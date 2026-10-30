from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    latency_ms: float
    model: str
    total_duration_ns: int
    load_duration_ns: int
    prompt_eval_count: int
    eval_count: int


class OllamaProvider:
    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 240,
        temperature: float = 0.0,
        seed: int = 20261018,
        num_ctx: int = 8192,
        num_predict: int = 512,
        top_p: float = 1.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.options = {
            "temperature": temperature,
            "seed": seed,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "top_p": top_p,
        }

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="GET" if payload is None else "POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama request failed for {path}: {exc}") from exc

    def model_info(self) -> dict[str, Any]:
        tags = self._request("/api/tags")
        for item in tags.get("models", []):
            if item.get("name") == self.model or item.get("model") == self.model:
                return item
        raise RuntimeError(f"Ollama model is not installed: {self.model}")

    def generate(self, messages: list[dict[str, str]]) -> ProviderResponse:
        started = time.perf_counter()
        response = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": self.options,
            },
        )
        latency_ms = (time.perf_counter() - started) * 1000
        if not response.get("done"):
            raise RuntimeError(f"Ollama did not complete generation: {response}")
        return ProviderResponse(
            content=str(response.get("message", {}).get("content") or ""),
            latency_ms=latency_ms,
            model=str(response.get("model") or self.model),
            total_duration_ns=int(response.get("total_duration") or 0),
            load_duration_ns=int(response.get("load_duration") or 0),
            prompt_eval_count=int(response.get("prompt_eval_count") or 0),
            eval_count=int(response.get("eval_count") or 0),
        )

    def unload(self) -> None:
        self._request(
            "/api/generate",
            {"model": self.model, "prompt": "", "stream": False, "keep_alive": 0},
        )

