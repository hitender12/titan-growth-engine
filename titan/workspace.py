"""Workspace and project management with tenant isolation.

Every project belongs to exactly one workspace. Any access to a project
from a different workspace raises TenantError. This is the single choke
point that enforces isolation; the store, importer and analyst all go
through it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


class TenantError(PermissionError):
    """Raised when a workspace tries to touch another workspace's data."""


@dataclass
class Workspace:
    name: str
    owner: str
    plan: str = "free"
    id: str = field(default_factory=lambda: f"ws_{uuid.uuid4().hex[:8]}")


@dataclass
class Project:
    workspace_id: str
    domain: str
    timezone: str = "UTC"
    currency: str = "USD"
    id: str = field(default_factory=lambda: f"prj_{uuid.uuid4().hex[:8]}")


class WorkspaceManager:
    """In-memory registry of workspaces and projects."""

    def __init__(self):
        self.workspaces = {}
        self.projects = {}

    def create_workspace(self, name: str, owner: str, plan: str = "free") -> Workspace:
        ws = Workspace(name=name, owner=owner, plan=plan)
        self.workspaces[ws.id] = ws
        return ws

    def create_project(
        self, workspace_id: str, domain: str, timezone: str = "UTC", currency: str = "USD"
    ) -> Project:
        if workspace_id not in self.workspaces:
            raise KeyError(f"unknown workspace {workspace_id}")
        prj = Project(workspace_id=workspace_id, domain=domain, timezone=timezone, currency=currency)
        self.projects[prj.id] = prj
        return prj

    def get_project(self, workspace_id: str, project_id: str) -> Project:
        """Fetch a project, enforcing that it belongs to the workspace."""
        prj = self.projects.get(project_id)
        if prj is None:
            raise KeyError(f"unknown project {project_id}")
        if prj.workspace_id != workspace_id:
            raise TenantError(
                f"project {project_id} does not belong to workspace {workspace_id}"
            )
        return prj

    def projects_of(self, workspace_id: str):
        return [p for p in self.projects.values() if p.workspace_id == workspace_id]
