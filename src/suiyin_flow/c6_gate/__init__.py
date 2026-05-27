"""C6 Gate Contract — declarative merge gate (Layer 5).

按 docs/sdd/components/c6-gate-contract.md v0.1.1 实现.
"""

from suiyin_flow.c6_gate.contract import (
    CONTRACT_VERSION,
    Code,
    GateError,
    GateInput,
    GateOutput,
    GateResult,
    Reason,
    RecoveryAction,
    RecoveryKind,
    RulesBreakdown,
)

__all__ = [
    "CONTRACT_VERSION",
    "Code",
    "GateError",
    "GateInput",
    "GateOutput",
    "GateResult",
    "Reason",
    "RecoveryAction",
    "RecoveryKind",
    "RulesBreakdown",
]
