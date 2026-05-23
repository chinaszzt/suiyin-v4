"""Stream-JSON parsing tests for session.py _maybe_parse_final_output (v0.1.2 hotfix).

P0 spike (阶段 2.C dogfood prep) 发现 Claude `--print --output-format stream-json`
输出**多种 event type**, AI 最终回答是 assistant.message.content[].text 或
result event 的 result 字段, 不是 top-level JSON. 修后支持这两种实际形态.
"""

from __future__ import annotations

import json

from suiyin_flow.c2_executor.session import (
    _extract_json_from_text,
    _is_implementer_final,
    _maybe_parse_final_output,
)

# -------------------------------------------------------------------
# _is_implementer_final unit tests
# -------------------------------------------------------------------


def test_is_implementer_final_detects_required_fields() -> None:
    assert _is_implementer_final(
        {"task_id": "T-001", "files_changed": [], "verify_cmd_exit_code": 0}
    )


def test_is_implementer_final_rejects_missing_fields() -> None:
    assert not _is_implementer_final({"task_id": "T-001"})  # 缺 verify_cmd_exit_code
    assert not _is_implementer_final({"verify_cmd_exit_code": 0})  # 缺 task_id
    assert not _is_implementer_final({})


def test_is_implementer_final_rejects_non_dict() -> None:
    assert not _is_implementer_final("a string")
    assert not _is_implementer_final([1, 2, 3])
    assert not _is_implementer_final(None)


# -------------------------------------------------------------------
# _extract_json_from_text unit tests
# -------------------------------------------------------------------


def test_extract_json_from_text_whole_text_is_json() -> None:
    text = '{"task_id":"T-001","files_changed":[],"verify_cmd_exit_code":0,"commit_sha":"abc"}'
    result = _extract_json_from_text(text)
    assert result is not None
    assert result["task_id"] == "T-001"
    assert result["verify_cmd_exit_code"] == 0


def test_extract_json_from_text_in_code_block() -> None:
    """AI 通常按 prompt 模板用 ```json``` 包 final output."""
    text = """\
任务完成。最终输出:

```json
{
  "task_id": "T-042",
  "files_changed": ["docs/adrs/0002-python.md"],
  "verify_cmd_exit_code": 0,
  "commit_sha": "def5678"
}
```
"""
    result = _extract_json_from_text(text)
    assert result is not None
    assert result["task_id"] == "T-042"
    assert result["files_changed"] == ["docs/adrs/0002-python.md"]


def test_extract_json_from_text_code_block_no_language_tag() -> None:
    """AI 偶尔忘了写 'json' tag, 仅用 ```."""
    text = """\
```
{"task_id":"T-001","files_changed":[],"verify_cmd_exit_code":0,"commit_sha":""}
```
"""
    result = _extract_json_from_text(text)
    assert result is not None
    assert result["task_id"] == "T-001"


def test_extract_json_from_text_inline_fallback() -> None:
    """无 code block 时的 inline JSON 兜底."""
    text = (
        '完成! 输出: '
        '{"task_id":"T-001","files_changed":[],'
        '"verify_cmd_exit_code":0,"commit_sha":"a"} 再见'
    )
    result = _extract_json_from_text(text)
    assert result is not None
    assert result["task_id"] == "T-001"


def test_extract_json_from_text_ignores_non_final_json() -> None:
    """text 含其他 JSON (e.g. tool args) 但不含 task_id+verify_cmd_exit_code → None."""
    text = """
我刚才调用了 Edit 工具: {"old_string": "foo", "new_string": "bar"}
然后调用了 Bash 工具: {"command": "ls"}
"""
    result = _extract_json_from_text(text)
    assert result is None


def test_extract_json_from_text_empty_returns_none() -> None:
    assert _extract_json_from_text("") is None
    assert _extract_json_from_text("   \n  ") is None


# -------------------------------------------------------------------
# _maybe_parse_final_output integration tests (parsing stream-json lines)
# -------------------------------------------------------------------


def test_parse_legacy_top_level_json() -> None:
    """旧 mock / legacy: 整 line 就是 final JSON. 仍支持."""
    line = json.dumps(
        {
            "task_id": "T-001",
            "files_changed": [],
            "verify_cmd_exit_code": 0,
            "commit_sha": "abc",
        }
    )
    result = _maybe_parse_final_output(line)
    assert result is not None
    assert result["task_id"] == "T-001"


def test_parse_result_event_with_json_in_result_string() -> None:
    """真实 Claude: 'result' event 的 result 字段含 JSON-in-code-block."""
    result_text = (
        "任务完成。\n\n```json\n"
        '{"task_id":"T-042","files_changed":["docs/adrs/0002-python.md"],'
        '"verify_cmd_exit_code":0,"commit_sha":"def5678"}\n'
        "```\n"
    )
    line = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result_text,
            "session_id": "abc-123",
            "duration_ms": 5000,
        }
    )
    result = _maybe_parse_final_output(line)
    assert result is not None
    assert result["task_id"] == "T-042"
    assert result["verify_cmd_exit_code"] == 0


def test_parse_assistant_message_text_with_json() -> None:
    """真实 Claude: 'assistant' event 的 message.content[].text 含 JSON."""
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-7",
                "id": "msg_001",
                "content": [
                    {
                        "type": "text",
                        "text": '完成. ```json\n{"task_id":"T-001",'
                                '"files_changed":[],"verify_cmd_exit_code":0,'
                                '"commit_sha":"abc"}\n```',
                    }
                ],
            },
            "session_id": "abc-123",
        }
    )
    result = _maybe_parse_final_output(line)
    assert result is not None
    assert result["task_id"] == "T-001"


def test_parse_ignores_system_and_rate_limit_events() -> None:
    """非 final 的 stream-json event 应该 return None (不阻塞 caller scan)."""
    system_init = json.dumps(
        {
            "type": "system",
            "subtype": "init",
            "cwd": "/tmp",
            "session_id": "abc",
        }
    )
    rate_limit = json.dumps(
        {
            "type": "rate_limit_event",
            "rate_limit_info": {"status": "allowed"},
            "session_id": "abc",
        }
    )
    assert _maybe_parse_final_output(system_init) is None
    assert _maybe_parse_final_output(rate_limit) is None


def test_parse_ignores_non_json_line() -> None:
    assert _maybe_parse_final_output("not json") is None
    assert _maybe_parse_final_output("") is None
    assert _maybe_parse_final_output("{ broken json") is None


def test_parse_assistant_without_target_json_returns_none() -> None:
    """assistant 文本仅是普通对话, 不含 final JSON → None."""
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "好的, 我开始执行任务..."}],
            },
            "session_id": "abc",
        }
    )
    assert _maybe_parse_final_output(line) is None
