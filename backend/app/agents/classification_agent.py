"""Agent 3: Department & Urgency Classifier.

Maps civic intents deterministically to Recommended Departments
and calculates objective risk severity (LOW to CRITICAL).
"""

from typing import List
from app.models.enums import CivicIntent, ControlledDepartment, UrgencyLevel
from app.models.reasoning import ClassificationResult
from app.agents.strands_adapter import calculate_urgency_tool, map_department_tool


class DepartmentUrgencyAgent:
    """Agent 3: Department & Urgency Classifier."""

    def classify(self, intent: CivicIntent, hazard_flags: List[str]) -> ClassificationResult:
        """Deterministically map department and score urgency."""
        # Map department
        dept_str = map_department_tool(intent.value)
        department = ControlledDepartment(dept_str)

        # Compute urgency
        urgency_data = calculate_urgency_tool(intent.value, hazard_flags)
        urgency = UrgencyLevel(urgency_data["urgency"])
        rationale = urgency_data["rationale"]

        return ClassificationResult(
            department=department,
            urgency=urgency,
            urgency_rationale=rationale,
        )

    async def run(self, intent: CivicIntent, hazard_flags: List[str]) -> ClassificationResult:
        """Run classification pipeline (deterministic by design to prevent hallucination)."""
        return self.classify(intent, hazard_flags)
