# -*- coding: utf-8 -*-
"""Project Identity Gate — manual/runtime hard gate (ACCEPTED_BUT_NOT_IMPLEMENTED in BBM).

Tonight Sol executes this once at kickoff; runtime also re-checks on open/write.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .types import IdentityError

EXPECTED_UUID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
EXPECTED_NAME = "shadowV2"
EXPECTED_REPO = "matith/shadowV2"
EXPECTED_ROOT_MARKER = "blackbox"


@dataclass(frozen=True)
class ProjectIdentity:
    project_uuid: str
    project_name: str
    repo: str
    local_root: str
    canonical_generation: str


def verify_identity(identity: ProjectIdentity) -> None:
    if identity.project_uuid != EXPECTED_UUID:
        raise IdentityError(
            f"project uuid mismatch: got={identity.project_uuid} expected={EXPECTED_UUID}"
        )
    if identity.project_name != EXPECTED_NAME:
        raise IdentityError(
            f"project name mismatch: got={identity.project_name} expected={EXPECTED_NAME}"
        )
    if identity.repo != EXPECTED_REPO:
        raise IdentityError(f"repo mismatch: got={identity.repo} expected={EXPECTED_REPO}")
    root = Path(identity.local_root)
    if not root.exists():
        raise IdentityError(f"local root missing: {identity.local_root}")
    if not (root / EXPECTED_ROOT_MARKER).exists():
        raise IdentityError(f"local root has no {EXPECTED_ROOT_MARKER}/ canonical")
    if not identity.canonical_generation:
        raise IdentityError("canonical generation empty")


def identity_from_repo_root(root: str | Path, generation: str = "g000259") -> ProjectIdentity:
    root = Path(root)
    return ProjectIdentity(
        project_uuid=EXPECTED_UUID,
        project_name=EXPECTED_NAME,
        repo=EXPECTED_REPO,
        local_root=str(root),
        canonical_generation=generation,
    )
