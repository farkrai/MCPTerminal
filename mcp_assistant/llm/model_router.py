from __future__ import annotations

import logging

from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient

log = logging.getLogger(__name__)

COMPLEXITY_ROUTING = "routing"
COMPLEXITY_LOW = "low"
COMPLEXITY_MEDIUM = "medium"
COMPLEXITY_HIGH = "high"

NL_CALL_TYPES = {"explain_failures", "summarize_git_diff", "clarification"}


class ModelRouter:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._available: set[str] = set()
        self._resolved: dict[str, str] = {}

    def warm_up(self) -> None:
        """Resolve configured tiers against the models actually available."""
        try:
            models = self._client.list_models()
            self._available = {
                item["name"] if isinstance(item, dict) else str(item)
                for item in models
            }
        except Exception:
            log.warning("Could not list Ollama models — falling back to configured defaults.")
            self._available = set()

        self._resolved = {
            "classifier": self._resolve(config.CLASSIFIER_MODEL),
            "planner": self._resolve(config.PLANNER_MODEL),
            "router": self._resolve(config.ROUTER_MODEL),
            "low": self._resolve(config.EXECUTOR_MODEL_LOW),
            "medium": self._resolve(config.EXECUTOR_MODEL_MEDIUM),
            "high": self._resolve(config.EXECUTOR_MODEL_HIGH),
            "aggregator": self._resolve(config.AGGREGATOR_MODEL),
        }
        log.info("Model tiers resolved: %s", self._resolved)

    def classifier_model(self) -> str:
        return self._resolved.get("classifier", config.CLASSIFIER_MODEL)

    def planner_model(self) -> str:
        return self._resolved.get("planner", config.PLANNER_MODEL)

    def router_model(self) -> str:
        return self._resolved.get("router", config.ROUTER_MODEL)

    def executor_model(self, complexity: str) -> str:
        key = complexity if complexity in {"low", "medium", "high"} else "low"
        return self._resolved.get(key, config.OLLAMA_MODEL)

    def aggregator_model(self) -> str:
        return self._resolved.get("aggregator", config.OLLAMA_MODEL)

    def supports_structured_output(self) -> bool:
        try:
            return self._client.ollama_version() >= (0, 1, 34)
        except Exception:
            return False

    def _resolve(self, preferred: str) -> str:
        fallback_chain = [
            preferred,
            config.EXECUTOR_MODEL_HIGH,
            config.EXECUTOR_MODEL_MEDIUM,
            config.EXECUTOR_MODEL_LOW,
            config.ROUTER_MODEL,
        ]

        seen: set[str] = set()
        for model in fallback_chain:
            if not model or model in seen:
                continue
            seen.add(model)
            if not self._available:
                return model
            resolved = self._match_available(model)
            if resolved is not None:
                if resolved != preferred:
                    log.warning("Model '%s' not found — using '%s' instead.", preferred, resolved)
                return resolved
        if self._available:
            fallback = sorted(self._available)[0]
            log.warning("No configured model tiers are available — using installed model '%s'.", fallback)
            return fallback
        return preferred

    def _match_available(self, requested: str) -> str | None:
        if requested in self._available:
            return requested

        base = requested.split(":", 1)[0]
        candidates = sorted(
            candidate
            for candidate in self._available
            if candidate == base or candidate.startswith(f"{base}:")
        )
        return candidates[0] if candidates else None
