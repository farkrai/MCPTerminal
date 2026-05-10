from __future__ import annotations
import json
from typing import Iterator
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
        format: dict | str | None = None,
    ) -> str:
        """Generate a completion.

        Pass ``format`` as a JSON-schema dict to enforce structured output via
        Ollama's built-in GGML grammar enforcement (Ollama ≥ 0.5). This helps
        smaller models stay on-spec for tool-call JSON without extra retries.
        Pass ``format="json"`` for generic JSON mode.
        """
        payload = self._build_payload(prompt, system, temperature, stream=False)
        if format is not None:
            payload["format"] = format
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
    ) -> Iterator[str]:
        payload = self._build_payload(prompt, system, temperature, stream=True)
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

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_payload(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        stream: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        return payload


# ── CLI smoke test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    client = OllamaClient()
    if not client.is_available():
        print("Ollama is not running. Start it with: ollama serve")
    else:
        print(f"Ollama available. Models: {client.list_models()}")
        resp = client.generate("Say hello in one sentence.")
        print(f"Response: {resp}")
