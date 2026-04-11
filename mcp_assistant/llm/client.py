from __future__ import annotations
import json
import random
import time
from typing import Iterator
import asyncio
import requests
from mcp_assistant import config


class OllamaClient:
    def __init__(
        self,
        base_url: str = config.OLLAMA_BASE_URL,
        model: str = config.OLLAMA_MODEL,
        timeout: int = config.OLLAMA_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session = requests.Session()

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = config.OLLAMA_TEMP_STRUCTURED,
        model: str | None = None,
        format_schema: dict | None = None,
        max_retries: int = config.OLLAMA_MAX_RETRIES,
    ) -> str:
        delay = 1.0
        last_exc: requests.RequestException | None = None
        for attempt in range(max_retries):
            try:
                return self._do_generate(prompt, system, temperature, model, format_schema)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(delay + random.uniform(0.0, 0.5))
                    delay = min(delay * 2.0, 30.0)

        if last_exc is not None:
            raise last_exc

        raise RuntimeError("Ollama generate failed without an exception")

    def _do_generate(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        model: str | None,
        format_schema: dict | None,
    ) -> str:
        payload = self._build_payload(
            prompt,
            system,
            temperature,
            stream=False,
            model=model,
            format_schema=format_schema,
        )
        resp = self._session.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = config.OLLAMA_TEMP_NL,
        model: str | None = None,
        format_schema: dict | None = None,
    ) -> Iterator[str]:
        payload = self._build_payload(
            prompt,
            system,
            temperature,
            stream=True,
            model=model,
            format_schema=format_schema,
        )
        with self._session.post(
            f"{self.base_url}/api/generate",
            json=payload,
            stream=True,
            timeout=self.timeout,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    yield chunk.get("response", "")
                    if chunk.get("done"):
                        break

    async def generate_stream_async(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = config.OLLAMA_TEMP_NL,
        model: str | None = None,
        format_schema: dict | None = None,
    ):
        for token in self.generate_stream(
            prompt=prompt,
            system=system,
            temperature=temperature,
            model=model,
            format_schema=format_schema,
        ):
            yield token
            await asyncio.sleep(0)

    def is_available(self) -> bool:
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        resp = self._session.get(f"{self.base_url}/api/tags", timeout=10)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    def ollama_version(self) -> tuple[int, int, int]:
        resp = self._session.get(f"{self.base_url}/api/version", timeout=5)
        resp.raise_for_status()
        raw = str(resp.json().get("version", "0.0.0")).lstrip("v")
        parts = raw.split(".")
        nums = [int(part) for part in parts[:3]]
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums[:3])

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_payload(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        stream: bool,
        model: str | None = None,
        format_schema: dict | None = None,
    ) -> dict:
        payload: dict = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": temperature},
            "keep_alive": _normalize_keep_alive(config.OLLAMA_KEEP_ALIVE),
        }
        if system:
            payload["system"] = system
        if format_schema is not None:
            payload["format"] = format_schema
        return payload


def _normalize_keep_alive(value: str) -> int | str:
    raw = str(value).strip()
    if not raw:
        return "5m"
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


# ── CLI smoke test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    client = OllamaClient()
    if not client.is_available():
        print("Ollama is not running. Start it with: ollama serve")
    else:
        print(f"Ollama available. Models: {client.list_models()}")
        resp = client.generate("Say hello in one sentence.")
        print(f"Response: {resp}")
