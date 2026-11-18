"""
Base Move Architecture for Kozmo Renewal Desk Moves.
Implements directed graph execution with Actions, Gates, Checks, and dynamic Skipping.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time


class ActionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass
class ActionTrace:
    id: str
    name: str
    status: ActionStatus
    duration_ms: float = 0.0
    output_summary: Optional[str] = None
    skip_reason: Optional[str] = None


@dataclass
class GateTrace:
    id: str
    name: str
    passed: bool
    decision: str
    details: Optional[str] = None


@dataclass
class MoveTrace:
    move_id: str
    name: str
    verb: str
    status: str
    actions: List[ActionTrace] = field(default_factory=list)
    gates: List[GateTrace] = field(default_factory=list)
    summary: str = ""


class BaseMove:
    move_id: str = "M00"
    name: str = "Base Move"
    verb: str = "FRAME"

    def __init__(self):
        self.action_traces: List[ActionTrace] = []
        self.gate_traces: List[GateTrace] = []

    def record_action(
        self,
        action_id: str,
        name: str,
        status: ActionStatus,
        duration_ms: float = 0.0,
        output_summary: Optional[str] = None,
        skip_reason: Optional[str] = None
    ) -> ActionTrace:
        trace = ActionTrace(
            id=action_id,
            name=name,
            status=status,
            duration_ms=round(duration_ms, 2),
            output_summary=output_summary,
            skip_reason=skip_reason
        )
        self.action_traces.append(trace)
        return trace

    def record_gate(
        self,
        gate_id: str,
        name: str,
        passed: bool,
        decision: str,
        details: Optional[str] = None
    ) -> GateTrace:
        trace = GateTrace(
            id=gate_id,
            name=name,
            passed=passed,
            decision=decision,
            details=details
        )
        self.gate_traces.append(trace)
        return trace

    def execute_action(
        self,
        action_id: str,
        name: str,
        fn: Callable[[], Any],
        format_output: Optional[Callable[[Any], str]] = None
    ) -> Any:
        start = time.perf_counter()
        try:
            result = fn()
            duration = (time.perf_counter() - start) * 1000
            summary = format_output(result) if format_output and result is not None else str(result)[:100]
            self.record_action(action_id, name, ActionStatus.EXECUTED, duration, summary)
            return result
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            self.record_action(action_id, name, ActionStatus.FAILED, duration, None, str(e))
            raise

    def skip_action(self, action_id: str, name: str, reason: str):
        self.record_action(action_id, name, ActionStatus.SKIPPED, 0.0, None, skip_reason=reason)

    def run(self, dossier: Any) -> MoveTrace:
        """Subclasses implement their graph traversal here"""
        raise NotImplementedError
