"""Versioning v2 passport registry — lifecycle management.

Manages passport files (immutable config) + mutable state (status, timestamps).
Status lifecycle: generated → backtested → paper_live → candidate → production → retired → archived
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from bot.research.generator import generate_passport_id


VALID_TRANSITIONS: dict[str, list[str]] = {
    "generated": ["backtested"],
    "backtested": ["paper_live", "retired"],
    "paper_live": ["candidate", "retired"],
    "candidate": ["production", "retired"],
    "production": ["retired"],
    "retired": ["archived"],
    "archived": [],
}


class PassportRegistry:
    """Manages passport versioning with immutable configs and mutable status."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.passports_dir = os.path.join(base_dir, "passports")
        self.registry_path = os.path.join(base_dir, "registry.json")
        os.makedirs(self.passports_dir, exist_ok=True)
        self._registry = self._load_registry()

    def _load_registry(self) -> dict:
        if os.path.exists(self.registry_path):
            with open(self.registry_path) as f:
                return json.load(f)
        return {}

    def _save_registry(self):
        with open(self.registry_path, "w") as f:
            json.dump(self._registry, f, indent=2)

    def register(
        self,
        slug: str,
        family: str,
        version: str,
        config: dict,
        parent_id: Optional[str] = None,
        lineage_type: Optional[str] = None,
    ) -> str:
        """Register a new passport. Returns passport_id."""
        passport_id = generate_passport_id()

        # Build lineage
        lineage = {
            "parent_passport_id": parent_id,
            "root_passport_id": None,
            "lineage_type": lineage_type,
        }
        if parent_id and parent_id in self._registry:
            parent = self._registry[parent_id]
            parent_lineage = parent.get("lineage", {})
            lineage["root_passport_id"] = parent_lineage.get("root_passport_id") or parent_id
        elif parent_id:
            lineage["root_passport_id"] = parent_id

        # Write immutable passport file
        passport_data = {
            "passport_id": passport_id,
            "slug": slug,
            "family": family,
            "version": version,
            "config": config,
            "lineage": lineage,
            "created_at": time.time(),
        }
        passport_path = os.path.join(self.passports_dir, f"{passport_id}.json")
        with open(passport_path, "w") as f:
            json.dump(passport_data, f, indent=2)

        # Add to mutable registry
        self._registry[passport_id] = {
            "slug": slug,
            "family": family,
            "version": version,
            "status": "generated",
            "lineage": lineage,
            "created_at": passport_data["created_at"],
            "updated_at": passport_data["created_at"],
        }
        self._save_registry()

        return passport_id

    def get(self, passport_id: str) -> Optional[dict]:
        """Get passport registry entry."""
        return self._registry.get(passport_id)

    def update_status(self, passport_id: str, new_status: str):
        """Update passport status with transition validation."""
        entry = self._registry.get(passport_id)
        if entry is None:
            raise ValueError(f"Passport {passport_id} not found")

        current = entry["status"]
        valid = VALID_TRANSITIONS.get(current, [])
        if new_status not in valid:
            raise ValueError(
                f"Invalid transition: {current} → {new_status}. "
                f"Valid transitions: {valid}"
            )

        entry["status"] = new_status
        entry["updated_at"] = time.time()
        self._save_registry()

    def list_by_family(self, family: str) -> list[dict]:
        """List all passports for a family."""
        return [
            {"passport_id": pid, **entry}
            for pid, entry in self._registry.items()
            if entry.get("family") == family
        ]

    def list_by_status(self, status: str) -> list[dict]:
        """List all passports with a given status."""
        return [
            {"passport_id": pid, **entry}
            for pid, entry in self._registry.items()
            if entry.get("status") == status
        ]

    def list_all(self) -> list[dict]:
        """List all registered passports."""
        return [
            {"passport_id": pid, **entry}
            for pid, entry in self._registry.items()
        ]
