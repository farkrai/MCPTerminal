from __future__ import annotations

from mcp_assistant import config
from mcp_assistant.llm import cache as llm_cache
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.model_router import ModelRouter, NL_CALL_TYPES
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPCall_SCHEMA, ParseError

_CHAIN_TRIGGER_WORDS = ("then", "after that", "first", "followed by", "and also")


def prepare_inference_request(
    nl_input: str,
    builder: PromptBuilder,
    model_router: ModelRouter | None = None,
    context: list[dict] | None = None,
) -> dict:
    system = builder.system_prompt()
    user = builder.user_prompt(nl_input, context)
    use_format = bool(
        model_router
        and model_router.supports_structured_output()
        and not _looks_like_chain_request(nl_input)
    )
    return {
        "system": system,
        "user": user,
        "model": model_router.router_model() if model_router else None,
        "format_schema": MCPCall_SCHEMA if use_format else None,
    }


def infer_call(
    nl_input: str,
    client: OllamaClient,
    builder: PromptBuilder,
    model_router: ModelRouter | None = None,
    context: list[dict] | None = None,
    max_parse_retries: int = config.MAX_PARSE_RETRIES,
    use_cache: bool = True,
) -> MCPCall | MCPChain:
    """Run the full NL-to-tool inference pipeline."""
    request = prepare_inference_request(nl_input, builder, model_router, context)
    system = request["system"]
    user = request["user"]
    reminder = ""

    if use_cache:
        cached = llm_cache.get(system, user)
        if cached:
            result = parse_response(cached)
            setattr(result, "_model_used", request["model"] or client.model)
            return result

    for attempt in range(max_parse_retries + 1):
        raw = client.generate(
            prompt=user + reminder,
            system=system,
            temperature=config.OLLAMA_TEMP_STRUCTURED,
            model=request["model"],
            format_schema=request["format_schema"],
        )
        try:
            result = parse_response(raw)
            if (
                model_router
                and isinstance(result, MCPCall)
                and getattr(result, "_complexity", "routing") != "routing"
                and result.action in NL_CALL_TYPES
            ):
                exec_model = model_router.executor_model(getattr(result, "_complexity", "low"))
                raw = client.generate(
                    prompt=user,
                    system=system,
                    temperature=config.OLLAMA_TEMP_NL,
                    model=exec_model,
                )
                result = parse_response(raw)
                setattr(result, "_model_used", exec_model)
            else:
                setattr(result, "_model_used", request["model"] or client.model)

            if use_cache:
                llm_cache.put(system, user, raw)
            return result
        except ParseError:
            if attempt == max_parse_retries:
                raise
            reminder = "\n\nREMINDER: Respond ONLY with a single valid JSON object. No prose."

    raise ParseError("Exhausted parse retries")


def _looks_like_chain_request(nl_input: str) -> bool:
    text = nl_input.lower()
    return any(trigger in text for trigger in _CHAIN_TRIGGER_WORDS)
