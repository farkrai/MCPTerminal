from unittest.mock import MagicMock

from mcp_assistant import config
from mcp_assistant.llm.model_router import ModelRouter


def _mock_client(available_models):
    client = MagicMock()
    client.list_models.return_value = [{"name": model} for model in available_models]
    client.ollama_version.return_value = (0, 1, 34)
    return client


def test_resolves_router_model_when_available():
    router = ModelRouter(_mock_client([config.ROUTER_MODEL, config.OLLAMA_MODEL]))
    router.warm_up()
    assert router.router_model() == config.ROUTER_MODEL


def test_resolves_classifier_and_planner_models_when_available():
    router = ModelRouter(
        _mock_client(
            [
                config.CLASSIFIER_MODEL,
                config.PLANNER_MODEL,
                config.ROUTER_MODEL,
                config.AGGREGATOR_MODEL,
            ]
        )
    )
    router.warm_up()
    assert router.classifier_model() == config.CLASSIFIER_MODEL
    assert router.planner_model() == config.PLANNER_MODEL


def test_falls_back_when_preferred_unavailable():
    router = ModelRouter(_mock_client([config.OLLAMA_MODEL]))
    router.warm_up()
    assert router.router_model() == config.OLLAMA_MODEL


def test_falls_back_to_any_available_model_when_no_configured_tiers_exist():
    router = ModelRouter(_mock_client(["dolphin-mistral:latest"]))
    router.warm_up()
    assert router.router_model() == "dolphin-mistral:latest"


def test_executor_high_falls_back_to_low():
    router = ModelRouter(_mock_client([config.ROUTER_MODEL, config.EXECUTOR_MODEL_LOW]))
    router.warm_up()
    assert router.executor_model("high") == config.EXECUTOR_MODEL_LOW


def test_supports_structured_output_version_check():
    router = ModelRouter(_mock_client([]))
    assert router.supports_structured_output() is True


def test_no_structured_output_old_version():
    client = _mock_client([])
    client.ollama_version.return_value = (0, 1, 30)
    router = ModelRouter(client)
    assert router.supports_structured_output() is False
