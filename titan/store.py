"""Normalized, tenant-scoped metrics store (in-memory).

All reads and writes go through WorkspaceManager.get_project, so a
workspace can never see another workspace's observations, even by
guessing a project id.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from .schema import MetricObservation


class MetricStore:
    def __init__(self, manager):
        self._manager = manager
        self._data = {}  # workspace_id -> project_id -> [MetricObservation]

    def add(self, obs: MetricObservation) -> None:
        # Enforces tenant match; raises TenantError on cross-tenant writes.
        self._manager.get_project(obs.workspace_id, obs.project_id)
        self._data.setdefault(obs.workspace_id, {}).setdefault(obs.project_id, []).append(obs)

    def query(
        self,
        workspace_id: str,
        project_id: str,
        metric: Optional[str] = None,
        source: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> List[MetricObservation]:
        # Enforces tenant match; raises TenantError on cross-tenant reads.
        self._manager.get_project(workspace_id, project_id)
        rows = self._data.get(workspace_id, {}).get(project_id, [])
        out = []
        for o in rows:
            if metric is not None and o.metric != metric:
                continue
            if source is not None and o.source != source:
                continue
            if start is not None and o.timestamp < start:
                continue
            if end is not None and o.timestamp > end:
                continue
            if dimensions and not all(o.dimensions.get(k) == v for k, v in dimensions.items()):
                continue
            out.append(o)
        return out

    def count(self, workspace_id: str, project_id: str) -> int:
        self._manager.get_project(workspace_id, project_id)
        return len(self._data.get(workspace_id, {}).get(project_id, []))

    def latest_date(self, workspace_id: str, project_id: str):
        rows = self._data.get(workspace_id, {}).get(project_id, [])
        if not rows:
            return None
        return max(o.timestamp for o in rows).date()
