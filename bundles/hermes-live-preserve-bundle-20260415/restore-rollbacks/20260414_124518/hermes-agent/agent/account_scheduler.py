"""Preflight account admission and scheduling helpers for Hermes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class SchedulingSuitability:
    eligible: bool
    risk_score: float
    suitable_for_long_task: bool
    suitable_for_streaming_task: bool
    suitable_for_background_task: bool
    reasons: List[str] = field(default_factory=list)


@dataclass(slots=True)
class AdmissionDecision:
    task_class: str
    selected_entry_id: str | None
    selection_reason: str
    candidate_count: int
    retry_policy: str
    rejected_entries: List[Dict[str, Any]] = field(default_factory=list)
    selected_snapshot: Dict[str, Any] = field(default_factory=dict)


class AccountScheduler:
    """Thin admission layer over ``CredentialPool`` for preflight logging/gating."""

    def __init__(self, pool: Any):
        self.pool = pool

    def _suitability_for_snapshot(self, snapshot: Dict[str, Any], *, task_class: str) -> SchedulingSuitability:
        reasons: List[str] = []
        runnable = bool(snapshot.get("runnable"))
        risk_score = float(snapshot.get("risk_score") or 0.0)
        suitable_for_long_task = bool(snapshot.get("suitable_for_long_task"))
        cooldown = int(snapshot.get("cooldown_remaining_sec") or 0)
        busy = bool(snapshot.get("busy"))
        auth_state = str(snapshot.get("auth_state") or "")
        last_status = str(snapshot.get("last_status") or "")

        if not runnable:
            reasons.append("not_runnable")
        if cooldown > 0:
            reasons.append(f"cooldown:{cooldown}")
        if busy:
            reasons.append("busy")
        if auth_state == "error":
            reasons.append("auth_error")
        if last_status in {"degraded", "exhausted"}:
            reasons.append(f"recent_status:{last_status}")
        if task_class in {"long_running", "fragile_stream"} and not suitable_for_long_task:
            reasons.append("not_suitable_for_long_task")

        return SchedulingSuitability(
            eligible=not reasons,
            risk_score=risk_score,
            suitable_for_long_task=suitable_for_long_task,
            suitable_for_streaming_task=suitable_for_long_task or task_class != "fragile_stream",
            suitable_for_background_task=runnable and not busy,
            reasons=reasons,
        )

    def decide(self, *, task_class: str = "interactive") -> AdmissionDecision:
        if self.pool is None:
            return AdmissionDecision(
                task_class=task_class,
                selected_entry_id=None,
                selection_reason="pool_unavailable",
                candidate_count=0,
                retry_policy="standard",
            )

        snapshots = []
        if hasattr(self.pool, "status_snapshot"):
            try:
                snapshots = list(self.pool.status_snapshot(force_refresh=False))
            except Exception:
                snapshots = []

        rejected_entries: List[Dict[str, Any]] = []
        for snapshot in snapshots:
            suitability = self._suitability_for_snapshot(snapshot, task_class=task_class)
            if not suitability.eligible:
                rejected_entries.append(
                    {
                        "id": snapshot.get("id"),
                        "label": snapshot.get("label"),
                        "reasons": suitability.reasons,
                        "risk_score": suitability.risk_score,
                    }
                )

        selected = None
        if hasattr(self.pool, "select_for_task"):
            try:
                selected = self.pool.select_for_task(task_class=task_class)
            except Exception:
                selected = self.pool.current() if hasattr(self.pool, "current") else None
        elif hasattr(self.pool, "select"):
            selected = self.pool.select()

        selected_snapshot = next((snap for snap in snapshots if snap.get("id") == getattr(selected, "id", None)), {})
        if task_class in {"long_running", "fragile_stream"}:
            retry_policy = "no_hidden_cross_account_retry_after_output"
        else:
            retry_policy = "bounded_same_account_retry"

        if selected is None:
            return AdmissionDecision(
                task_class=task_class,
                selected_entry_id=None,
                selection_reason="no_eligible_account",
                candidate_count=len(snapshots),
                retry_policy=retry_policy,
                rejected_entries=rejected_entries,
            )

        selection_reason = "selected_low_risk_candidate" if task_class in {"long_running", "fragile_stream"} else "selected_available_candidate"
        return AdmissionDecision(
            task_class=task_class,
            selected_entry_id=getattr(selected, "id", None),
            selection_reason=selection_reason,
            candidate_count=len(snapshots),
            retry_policy=retry_policy,
            rejected_entries=rejected_entries,
            selected_snapshot=selected_snapshot,
        )
