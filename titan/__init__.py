"""TITAN — AI Growth Intelligence Engine (core Python package).

Read-only by design: this package imports metrics, analyses them, answers
questions with evidence, and generates experiment cards. It never takes
external actions (no ad edits, budget changes or publishing).
"""
from .workspace import WorkspaceManager, Workspace, Project, TenantError
from .store import MetricStore
from .schema import MetricObservation, APPROVED_METRICS, ValidationError
from .importer import import_csv, ImportResult
from .analytics import daily_series, wow_comparison, funnel, detect_anomalies
from .analyst import ask, Answer, Evidence
from .experiments import ExperimentCard, ExperimentBacklog, generate_from_anomaly, generate_from_decline
from .audit import AuditLog, AuditEvent

__all__ = [
    "WorkspaceManager", "Workspace", "Project", "TenantError",
    "MetricStore", "MetricObservation", "APPROVED_METRICS", "ValidationError",
    "import_csv", "ImportResult",
    "daily_series", "wow_comparison", "funnel", "detect_anomalies",
    "ask", "Answer", "Evidence",
    "ExperimentCard", "ExperimentBacklog", "generate_from_anomaly", "generate_from_decline",
    "AuditLog", "AuditEvent",
]
