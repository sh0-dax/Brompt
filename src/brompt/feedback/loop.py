"""Central feedback loop — records executions, computes stats, detects regressions.

Optionally pushes each record to an AuditLog for tamper-evident integrity,
bridging the analytics store and the cryptographically chained audit trail.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .models import PromptExecution, PromptOutcome, TemplateStats

if TYPE_CHECKING:
    from ..audit import AuditLog

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """Tracks prompt execution outcomes, computes template-level stats, detects
    performance regression, and recommends the best template.

    Parameters
    ----------
    storage_path:
        Path to the JSON file used for persistence across restarts.
    audit_log:
        Optional AuditLog instance. When provided every recorded execution is
        also appended to the audit chain for tamper-evident integrity.
    """

    def __init__(
        self,
        storage_path: str = "data/feedback_store.json",
        audit_log: Optional["AuditLog"] = None,
    ):
        self.storage_path = Path(storage_path)
        self._audit_log = audit_log
        self.executions: list[PromptExecution] = []
        self.template_stats: dict[str, TemplateStats] = {}

        self._load_history()
        logger.info("FeedbackLoop ready — %d templates loaded", len(self.template_stats))

    def record_execution(
        self,
        template_id: str,
        generated_prompt: str,
        model_response: str,
        outcome: PromptOutcome,
        latency_ms: float,
        tokens_used: int,
        user_feedback: Optional[int] = None,
        model_name: str = "unknown",
        metadata: Optional[dict] = None,
    ) -> PromptExecution:
        """Record one prompt execution and update template statistics."""
        if user_feedback is not None and not (1 <= user_feedback <= 5):
            raise ValueError(f"User feedback must be 1-5, got {user_feedback}")
        if latency_ms < 0:
            raise ValueError(f"Latency cannot be negative: {latency_ms}")

        execution = PromptExecution(
            template_id=template_id,
            generated_prompt=generated_prompt,
            model_response=model_response,
            outcome=outcome,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            user_feedback=user_feedback,
            model_name=model_name,
            metadata=metadata or {},
        )

        self.executions.append(execution)
        if len(self.executions) > 1000:
            self.executions = self.executions[-1000:]

        if template_id not in self.template_stats:
            self.template_stats[template_id] = TemplateStats(template_id=template_id)
        self.template_stats[template_id].update_from_execution(execution)

        # Optional integrity hook: push a tamper-evident record to the audit log.
        if self._audit_log is not None:
            self._audit_log.record(
                event="feedback_execution",
                state_id=template_id,
                is_secure=outcome == PromptOutcome.SUCCESS,
                detail=(
                    f"latency={latency_ms:.0f}ms tokens={tokens_used} "
                    f"outcome={outcome.value} feedback={user_feedback}"
                ),
            )

        self._save_history()
        return execution

    def get_best_template(self, exclude_ids: Optional[list[str]] = None) -> Optional[str]:
        """Score every template and return the best-performing one.

        Uses a weighted formula:
          score = success_rate * 0.5 + rating * 0.3 + speed * 0.2
        """
        exclude_ids = exclude_ids or []
        candidates = {}

        for tid, stats in self.template_stats.items():
            if tid in exclude_ids or stats.total_uses < 5:
                continue

            success_score = stats.success_rate
            rating_score = (stats.avg_rating / 5) * 100 if stats.avg_rating > 0 else 50
            speed_score = max(0, 100 - (stats.avg_latency / 100))

            candidates[tid] = (
                success_score * 0.5 + rating_score * 0.3 + speed_score * 0.2
            )

        if not candidates:
            return None
        best = max(candidates, key=candidates.get)
        logger.info("Best template: %s (score=%.1f)", best, candidates[best])
        return best

    def generate_improvement_suggestions(self) -> list[dict]:
        """Analyse low-performing templates and suggest concrete improvements."""
        suggestions = []

        for tid, stats in self.template_stats.items():
            if stats.total_uses < 5:
                continue

            issues = []
            actions = []

            if stats.success_rate < 70.0:
                issues.append(f"Low success rate ({stats.success_rate:.1f}%)")
                actions.append("Review template instructions — may be ambiguous or contradictory")
                actions.append("Add few-shot examples showing the desired output format")

            if stats.avg_latency > 5000.0:
                issues.append(f"High latency ({stats.avg_latency:.0f}ms)")
                actions.append("Shorten the prompt — fewer tokens reduce processing time")
                actions.append("Split the task into smaller, focused prompts")

            if stats.total_ratings >= 3 and stats.avg_rating < 3.5:
                issues.append(f"Low user rating ({stats.avg_rating:.1f}/5)")
                actions.append("Collect examples of unsatisfactory outputs and identify patterns")
                actions.append("Add explicit quality criteria in the prompt")

            if stats.total_uses >= 10:
                h_rate = stats.hallucination_count / stats.total_uses
                if h_rate > 0.1:
                    issues.append(f"High hallucination rate ({h_rate:.1%})")
                    actions.append("Add: 'Do not invent information — say you don't know if unsure'")
                    actions.append("Lower temperature for this prompt type")

            if issues:
                suggestions.append({
                    "template_id": tid,
                    "total_uses": stats.total_uses,
                    "success_rate": f"{stats.success_rate:.1f}%",
                    "issues": issues,
                    "recommended_actions": actions,
                    "priority": "HIGH" if stats.success_rate < 50 else "MEDIUM",
                })

        suggestions.sort(key=lambda s: (0 if s["priority"] == "HIGH" else 1, s["success_rate"]))
        return suggestions

    def get_performance_report(self) -> dict:
        """Full performance report across all templates."""
        if not self.executions:
            return {"status": "no_data", "message": "No executions recorded yet"}

        total = len(self.executions)
        successes = sum(1 for e in self.executions if e.outcome == PromptOutcome.SUCCESS)
        partials = sum(1 for e in self.executions if e.outcome == PromptOutcome.PARTIAL)
        hallucinations = sum(1 for e in self.executions if e.outcome == PromptOutcome.HALLUCINATION)
        errors = sum(1 for e in self.executions if e.outcome == PromptOutcome.ERROR)
        avg_latency = sum(e.latency_ms for e in self.executions) / total
        avg_tokens = sum(e.tokens_used for e in self.executions) / total

        model_stats = defaultdict(lambda: {"uses": 0, "successes": 0})
        for e in self.executions:
            model_stats[e.model_name]["uses"] += 1
            if e.outcome == PromptOutcome.SUCCESS:
                model_stats[e.model_name]["successes"] += 1

        return {
            "status": "ok",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_executions": total,
                "total_templates": len(self.template_stats),
                "overall_success_rate": f"{((successes + partials * 0.5) / total * 100):.1f}%",
                "hallucination_rate": f"{(hallucinations / total * 100):.1f}%",
                "error_rate": f"{(errors / total * 100):.1f}%",
                "average_latency_ms": f"{avg_latency:.0f}",
                "average_tokens": f"{avg_tokens:.0f}",
            },
            "templates_detail": {tid: s.to_summary() for tid, s in self.template_stats.items()},
            "model_performance": {
                m: {"uses": d["uses"], "success_rate": f"{(d['successes'] / d['uses'] * 100):.1f}%"}
                for m, d in model_stats.items()
            },
            "best_template": self.get_best_template(),
            "improvement_suggestions": self.generate_improvement_suggestions(),
        }

    def get_template_health(self, template_id: str) -> dict:
        if template_id not in self.template_stats:
            return {"status": "unknown", "message": "No data for this template"}

        stats = self.template_stats[template_id]

        if stats.success_rate >= 90:
            health = "excellent"
        elif stats.success_rate >= 70:
            health = "good"
        elif stats.success_rate >= 50:
            health = "needs_improvement"
        else:
            health = "poor"

        return {"template_id": template_id, "health": health, **stats.to_summary()}

    def _save_history(self):
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "executions": [e.to_dict() for e in self.executions],
                "updated_at": datetime.now().isoformat(),
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save feedback history: %s", e)

    def _load_history(self):
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ed in data.get("executions", []):
                try:
                    execution = PromptExecution.from_dict(ed)
                    self.executions.append(execution)
                    tid = execution.template_id
                    if tid not in self.template_stats:
                        self.template_stats[tid] = TemplateStats(template_id=tid)
                    self.template_stats[tid].update_from_execution(execution)
                except Exception:
                    continue
            logger.info("Loaded %d execution records", len(self.executions))
        except Exception as e:
            logger.error("Failed to load feedback history: %s", e)

    def reset(self):
        self.executions.clear()
        self.template_stats.clear()
