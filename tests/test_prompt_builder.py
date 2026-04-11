from mcp_assistant.llm.prompt_builder import PromptBuilder


def test_system_prompt_includes_disambiguation_table():
    prompt = PromptBuilder().system_prompt()

    assert "ACTION DISAMBIGUATION - use this table to pick the correct action:" in prompt
    assert '"find", "search for", "look for", "grep", "locate"' in prompt
    assert '"run tests", "execute tests", "test suite"' in prompt
    assert '"RAM", "memory", "how much memory"' in prompt


def test_system_prompt_includes_few_shot_examples():
    prompt = PromptBuilder().system_prompt()

    assert 'User: "find all python files" -> {"tool": "FileHandler", "action": "search"' in prompt
    assert 'User: "show staged changes" -> {"tool": "GitTool", "action": "diff"' in prompt
    assert 'User: "how much memory is free" -> {"tool": "SystemTool", "action": "ram_stats"' in prompt


def test_direct_response_prompt_ignores_context_for_simple_greeting():
    builder = PromptBuilder()

    prompt = builder.direct_response_prompt(
        "hi",
        plan={"mode": "direct"},
        context=[
            {"role": "user", "content": "list files in ~/Desktop"},
            {"role": "assistant", "content": "Permission denied: Path not allowed by policy."},
        ],
    )

    assert "CONVERSATION HISTORY:" not in prompt
    assert "Permission denied" not in prompt
