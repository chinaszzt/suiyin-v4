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


# v0.6.0 (M3 件 8 误报校准, desk 真 diff 73 FP 三层解剖):
#   旧 (?<!\d)27017(?!\d) 裸数字匹配把"提到禁令"当"违反禁令"——desk 守卫代码/文档
#   (testmongo_uri_ok 注释、policy 文档) 全数误中。收紧为连接/指向形态:
#   host:27017 / port[=: ]27017 / --port 27017——verify_cmd 真指向 27017 仍必中
#   (desk 旧机制"测试命令指向"级精度), 纯提及不中。
_MONGO_PROD_PORT = re.compile(
    r"[\w.\-]:27017(?!\d)"          # host:27017 (mongodb://h:27017, localhost:27017)
    r"|(?:--?port|port)[=:\s]\s*['\"]?27017(?!\d)",  # --port 27017 / MONGO_PORT=27017 / port: 27017
    re.IGNORECASE,
)
_BZDS = re.compile(r"bzds", re.IGNORECASE)
_WRITE_OPERATION = re.compile(
    r"insert|update|delete|drop|remove|save|write|set|create|replace",
    re.IGNORECASE,
)
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)
# v0.6.0: AWS access key 实际格式全大写; 旧 IGNORECASE 把随机混合大小写串
# (aKIah9..., 见 dogfood/P0-attribution) 误判为密钥。
_AWS_ACCESS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
# v0.6.0: 密钥体只含字母数字 (sk-proj- 前缀除外); 旧 pattern 允许 -/_ 把路径片段
# "sk-v4lab-worktrees-T-002" (suiyin-desk-v4lab/worktrees/...) 误判为密钥。
_OPENAI_STYLE_KEY = re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}(?![\w\-])")
# v0.6.0: 行内豁免标注——守卫代码自身必须包含违禁字面量时 (如断言 uri 不含 :27017)
# 加 `safety-ok: <说明>` 注释跳过内容规则。标注本身留在 diff 里, C5 审得到 (可审计);
# 威胁模型见 memory: 不存在 AI 主动破坏, 豁免不做密码学防伪。
_SAFETY_WAIVER = re.compile(r"safety-ok:", re.IGNORECASE)
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

    if _SAFETY_WAIVER.search(line) is not None:
        return violations

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
    """扫描 git diff：新增行应用规则 1-3；文件头应用规则 4（运行时工件入库）。

    v0.6.0 file-aware：规则 4 命中的文件（.suiyin/ 运行时工件）整体已被拦截，
    其**内容行**不再重复过规则 1-3——desk 真 diff 73 处误报里 50 处
    (bzds 22 全部 + 27017/凭证的大头) 是 session log 内容被逐行重复报。
    """
    violations: list[SafetyViolation] = []
    in_runtime_artifact = False
    for line in diff_text.splitlines():
        if line.startswith("+++"):
            # 规则 4 (v0.5.1, E4 floor blocker 承接): .suiyin/ 运行时工件
            # (session log / report / state) 绝不入库
            in_runtime_artifact = _RUNTIME_ARTIFACT_HEADER.match(line) is not None
            if in_runtime_artifact:
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
        if not line.startswith("+") or in_runtime_artifact:
            continue
        violations.extend(_check_line(line[1:], include_credentials=True))
    return violations
