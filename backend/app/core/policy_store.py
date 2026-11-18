"""
Policy store: versioned, append-only storage for the client's RenewalPolicy.

Each save writes a new file `policy_v{NNN}.json` in the policy directory and never
overwrites an older one, so every past brief can be traced to the policy it used.
Version 0 means "no saved policy yet; built-in defaults are in use".

Policies live in backend/policies/.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

try:
    from backend.app.models.policy_models import RenewalPolicy
except ImportError:
    from app.models.policy_models import RenewalPolicy

DEFAULT_POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"
_FILE_RE = re.compile(r"^policy_v(\d+)\.json$")


@dataclass
class StoredPolicy:
    version: int                 # 0 = built-in defaults (nothing saved yet)
    policy: RenewalPolicy
    saved_by: Optional[str] = None
    saved_at: Optional[str] = None
    note: Optional[str] = None

    @property
    def is_default(self) -> bool:
        return self.version == 0

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "is_default": self.is_default,
            "saved_by": self.saved_by,
            "saved_at": self.saved_at,
            "note": self.note,
            "policy": self.policy.model_dump(),
        }


class PolicyStore:
    def __init__(self, directory: Path = DEFAULT_POLICY_DIR):
        self.directory = Path(directory)

    def _versions(self) -> List[int]:
        if not self.directory.exists():
            return []
        return sorted(int(m.group(1)) for f in self.directory.iterdir() if (m := _FILE_RE.match(f.name)))

    def _path(self, version: int) -> Path:
        return self.directory / f"policy_v{version:03d}.json"

    def _read(self, version: int) -> StoredPolicy:
        with open(self._path(version), "r", encoding="utf-8") as f:
            data = json.load(f)
        return StoredPolicy(
            version=version,
            policy=RenewalPolicy.model_validate(data["policy"]),
            saved_by=data.get("saved_by"),
            saved_at=data.get("saved_at"),
            note=data.get("note"),
        )

    def load_current(self) -> StoredPolicy:
        """Latest saved version, or the built-in defaults (version 0) when nothing has been saved."""
        versions = self._versions()
        if not versions:
            return StoredPolicy(version=0, policy=RenewalPolicy(), saved_by="built-in defaults")
        return self._read(versions[-1])

    def load(self, version: int) -> StoredPolicy:
        if version == 0:
            return StoredPolicy(version=0, policy=RenewalPolicy(), saved_by="built-in defaults")
        if version not in self._versions():
            raise KeyError(f"Policy version {version} not found")
        return self._read(version)

    def history(self) -> List[StoredPolicy]:
        """All saved versions, newest first."""
        return [self._read(v) for v in reversed(self._versions())]

    def save(self, policy: RenewalPolicy, saved_by: str, note: Optional[str] = None) -> StoredPolicy:
        """Validate, then write as the next version. Raises pydantic.ValidationError on an invalid policy."""
        policy = RenewalPolicy.model_validate(policy.model_dump() if isinstance(policy, RenewalPolicy) else policy)
        if not saved_by or not saved_by.strip():
            raise ValueError("saved_by is required")
        self.directory.mkdir(parents=True, exist_ok=True)
        version = (self._versions() or [0])[-1] + 1
        stored = StoredPolicy(
            version=version,
            policy=policy,
            saved_by=saved_by.strip(),
            saved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            note=note,
        )
        payload = {k: v for k, v in stored.to_dict().items() if k != "is_default"}
        # "x" mode never overwrites an existing version
        with open(self._path(version), "x", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return stored


def default_store() -> PolicyStore:
    return PolicyStore(DEFAULT_POLICY_DIR)
