"""C2 安全闸：在模型调用与 commit 采纳前机械扫描危险文本。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel


class SafetyViolation(BaseModel):
    """一条安全闸命中记录。"""

    rule_id: Literal[
        "SAFETY_MONGO_PROD_PORT",
        "SAFETY_BZDS_WRITE",
        "SAFETY_CREDENTIAL_IN_DIFF",
        "SAFETY_RUNTIME_ARTIFACT_IN_DIFF",
    ]
    detail: str
    matched_text: str


_MONGO_PROD_PORT = re.compile(r"(?<!\d)27017(?!\d)", re.IGNORECASE)
_BZDS = re.compile(r"bzds", re.IGNORECASE)
_WRITE_OPERATION = re.compile(
    r"insert|update|delete|drop|remove|save|write|set|create|replace",
    re.IGNORECASE,
)
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)
_AWS_ACCESS_KEY = re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE)
_OPENAI_STYLE_KEY = re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE)
_QUOTED_CREDENTIAL = re.compile(
    r"(?:password|passwd|secret|token|api_key|apikey)\s*[=:]\s*"
    r"[\"'](?P<value>[^\"']{8,})[\"']",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"xxx|\*\*\*|example|changeme|placeholder|your_|<",
    re.IGNORECASE,
)
_MATCHED_TEXT_LIMIT = 120


def _truncate(text: str) -> str:
    """把命中文本截断到 schema 约定的 120 字符以内。"""
    if len(text) <= _MATCHED_TEXT_LIMIT:
        return text
    return f"{text[: _MATCHED_TEXT_LIMIT - 3]}..."


def _check_line(line: str, *, include_credentials: bool) -> list[SafetyViolation]:
    """扫描单行；diff 与 command 共用规则 1、2。"""
    violations: list[SafetyViolation] = []

    mongo_match = _MONGO_PROD_PORT.search(line)
    if mongo_match is not None:
        violations.append(
            SafetyViolation(
                rule_id="SAFETY_MONGO_PROD_PORT",
                detail="命中生产 MongoDB 默认端口 27017。",
                matched_text=_truncate(mongo_match.group(0)),
            )
        )

    if _BZDS.search(line) is not None and _WRITE_OPERATION.search(line) is not None:
        violations.append(
            SafetyViolation(
                rule_id="SAFETY_BZDS_WRITE",
                detail="生产库账号 bzds 与写操作在同一行共现。",
                matched_text=_truncate(line),
            )
        )

    if not include_credentials:
        return violations

    hard_credential_match: tuple[re.Match[str], str] | None = None
    for pattern, detail in (
        (_PRIVATE_KEY, "新增行包含 private key 文件头。"),
        (_AWS_ACCESS_KEY, "新增行包含 AWS access key。"),
        (_OPENAI_STYLE_KEY, "新增行包含 sk- 格式密钥。"),
    ):
        credential_match = pattern.search(line)
        if credential_match is not None:
            hard_credential_match = (credential_match, detail)
            break

    if hard_credential_match is not None:
        credential_match, detail = hard_credential_match
        violations.append(
            SafetyViolation(
                rule_id="SAFETY_CREDENTIAL_IN_DIFF",
                detail=detail,
                matched_text=_truncate(credential_match.group(0)),
            )
        )
        return violations

    for credential_match in _QUOTED_CREDENTIAL.finditer(line):
        if _PLACEHOLDER.search(credential_match.group("value")) is not None:
            continue
        violations.append(
            SafetyViolation(
                rule_id="SAFETY_CREDENTIAL_IN_DIFF",
                detail="新增行包含疑似明文凭证赋值。",
                matched_text=_truncate(credential_match.group(0)),
            )
        )
        break

    return violations


def check_command(cmd: str) -> list[SafetyViolation]:
    """扫描验证命令中的生产 MongoDB 端口与 bzds 写操作。"""
    violations: list[SafetyViolation] = []
    for line in cmd.splitlines() or [cmd]:
        violations.extend(_check_line(line, include_credentials=False))
    return violations


_RUNTIME_ARTIFACT_HEADER = re.compile(r"^\+\+\+ (?:b/)?\.suiyin/")


def check_diff(diff_text: str) -> list[SafetyViolation]:
    """扫描 git diff：新增行应用规则 1-3；文件头应用规则 4（运行时工件入库）。"""
    violations: list[SafetyViolation] = []
    for line in diff_text.splitlines():
        if line.startswith("+++"):
            # 规则 4 (v0.5.1, E4 floor blocker 承接): .suiyin/ 运行时工件
            # (session log / report / state) 绝不入库
            if _RUNTIME_ARTIFACT_HEADER.match(line):
                violations.append(
                    SafetyViolation(
                        rule_id="SAFETY_RUNTIME_ARTIFACT_IN_DIFF",
                        detail=(
                            ".suiyin/ 运行时工件被提交入 git"
                            "（session log 等含敏感路径与会话内容）。"
                        ),
                        matched_text=_truncate(line),
                    )
                )
            continue
        if not line.startswith("+"):
            continue
        violations.extend(_check_line(line[1:], include_credentials=True))
    return violations
