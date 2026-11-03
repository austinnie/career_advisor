"""P2 抽取结果确认与修正。单一职责：记录用户修正，产出最终画像。
不静默采纳（阶段 6 契约 §1.5）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

from ..models import UserProfile, EvidenceValue


@dataclass(frozen=True)
class Correction:
    pointer: str
    operation: Literal["confirm", "correct", "delete"]
    old_value: object
    new_value: object = None


@dataclass
class ReviewSession:
    profile: UserProfile
    corrections: list[Correction] = field(default_factory=list)
    confirmed: bool = False


class ProfileReviewer:
    def __init__(self, profile: UserProfile):
        self.session = ReviewSession(profile=profile)

    def confirm(self, pointer: str) -> None:
        self._set_status(pointer, "user_confirmed")
        self.session.corrections.append(
            Correction(pointer, "confirm", self._read(pointer)))

    def correct(self, pointer: str, new_value) -> None:
        old = self._read(pointer)
        self._write(pointer, new_value)
        self._set_status(pointer, "user_corrected")
        self.session.corrections.append(
            Correction(pointer, "correct", old, new_value))

    def delete(self, pointer: str) -> None:
        old = self._read(pointer)
        self._write(pointer, None)
        self._set_status(pointer, "user_skipped")
        self.session.corrections.append(
            Correction(pointer, "delete", old))

    def finalize(self) -> UserProfile:
        """返回用户确认后的画像。未确认的字段状态保持 extracted。"""
        self.session.confirmed = True
        return self.session.profile

    def summary(self) -> dict:
        return {
            "total_fields": len(self.session.corrections),
            "confirmed": sum(1 for c in self.session.corrections
                             if c.operation == "confirm"),
            "corrected": sum(1 for c in self.session.corrections
                             if c.operation == "correct"),
            "deleted": sum(1 for c in self.session.corrections
                           if c.operation == "delete"),
        }

    # ---- 内部 ----

    def _read(self, pointer: str):
        container, key = self._locate(pointer)
        ev = container.get(key)
        return ev.value if isinstance(ev, EvidenceValue) else ev

    def _write(self, pointer: str, value) -> None:
        container, key = self._locate(pointer)
        if value is None:
            container[key] = EvidenceValue.missing()
        else:
            container[key] = EvidenceValue(value, "用户手动输入", "explicit")

    def _set_status(self, pointer: str, status: str) -> None:
        self.session.profile.field_status[pointer] = status

    def _locate(self, pointer: str):
        parts = pointer.strip("/").split("/")
        if len(parts) != 2:
            raise ValueError(f"Unsupported pointer: {pointer}")
        container_name, key = parts
        container = getattr(self.session.profile, container_name)
        return container, key