"""追问状态机。单一职责：管理 3 轮追问的生命周期。

状态：IDLE → ASKING(round) → ROUND_DONE(round) → ... → DONE
轮次上限：3 轮，硬编码在 MAX_ROUNDS（阶段 6 契约 §3.1）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from ..models import UserProfile
from .question_templates import QuestionTemplate
from .question_selector import select_round, mark_asked, record_skip


MAX_ROUNDS = 3


class ClarifyState(str, Enum):
    IDLE = "idle"
    ASKING = "asking"
    ROUND_DONE = "round_done"
    DONE = "done"


@dataclass
class ClarifySession:
    profile: UserProfile
    state: ClarifyState = ClarifyState.IDLE
    current_round: int = 0
    current_questions: list[QuestionTemplate] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    # history 项结构：
    # {"round": 1, "template_id": "...", "action": "answered|skipped",
    #  "answer": ..., "filled_fields": [...]}


class ClarifyStateMachine:
    def __init__(self, profile: UserProfile):
        self.session = ClarifySession(profile=profile)

    def start(self) -> "ClarifyStateMachine":
        self._enter_next_round()
        return self

    def current_questions(self) -> list[QuestionTemplate]:
        return list(self.session.current_questions)

    def answer(self, template_id: str, value: dict) -> None:
        """value 结构：{"/interests_riasec/I": 65, "/interests_riasec/C": 70, ...}"""
        t = self._find_template(template_id)
        for pointer, v in value.items():
            self._apply_answer(pointer, v)
        self._record(template_id, "answered", value,
                     list(value.keys()))
        self._advance()

    def skip(self, template_id: str) -> None:
        t = self._find_template(template_id)
        record_skip(self.session.profile, t)
        self._record(template_id, "skipped", None, list(t.target_fields))
        self._advance()

    def skip_round(self) -> None:
        """跳过本轮全部剩余问题。"""
        for t in list(self.session.current_questions):
            record_skip(self.session.profile, t)
            self._record(t.template_id, "skipped", None, list(t.target_fields))
        self.session.current_questions = []
        self._advance()

    def is_done(self) -> bool:
        return self.session.state == ClarifyState.DONE

    def can_enter_matching(self) -> bool:
        """用户可随时看结果，只要画像已达最低信号。"""
        from .question_selector import _has_minimum_signal
        return _has_minimum_signal(self.session.profile)

    # ---- 内部 ----

    def _enter_next_round(self) -> None:
        self.session.current_round += 1
        if self.session.current_round > MAX_ROUNDS:
            self.session.state = ClarifyState.DONE
            self.session.current_questions = []
            return
        questions = select_round(self.session.profile, self.session.current_round)
        if not questions:
            self.session.state = ClarifyState.DONE
            self.session.current_questions = []
            return
        mark_asked(self.session.profile, questions)
        self.session.state = ClarifyState.ASKING
        self.session.current_questions = questions

    def _advance(self) -> None:
        if not self.session.current_questions:
            self.session.state = ClarifyState.ROUND_DONE
            if self.session.current_round >= MAX_ROUNDS:
                self.session.state = ClarifyState.DONE
            else:
                self._enter_next_round()

    def _find_template(self, template_id: str) -> QuestionTemplate:
        for t in self.session.current_questions:
            if t.template_id == template_id:
                return t
        raise KeyError(f"Template {template_id} not in current round")

    def _apply_answer(self, pointer: str, value) -> None:
        from ..models import EvidenceValue
        p = self.session.profile
        if pointer.startswith("/hard_constraints/"):
            key = pointer.rsplit("/", 1)[-1]
            p.hard_constraints[key] = EvidenceValue(value, "用户通过追问回答", "explicit")
        elif pointer.startswith("/interests_riasec/"):
            key = pointer.rsplit("/", 1)[-1]
            p.interests_riasec[key] = EvidenceValue(value, "用户通过追问回答", "explicit")
        elif pointer.startswith("/values_weights/"):
            key = pointer.rsplit("/", 1)[-1]
            p.values_weights[key] = EvidenceValue(value, "用户通过追问回答", "explicit")
        elif pointer == "/skills":
            # value 为 [{skill_id, proficiency, ...}]
            p.skills = value
        p.field_status[pointer] = "user_corrected"
        if pointer in p.missing_fields:
            p.missing_fields.remove(pointer)

    def _record(self, template_id, action, answer, filled_fields) -> None:
        self.session.history.append({
            "round": self.session.current_round,
            "template_id": template_id,
            "action": action,
            "answer": answer,
            "filled_fields": filled_fields,
        })
        self.session.current_questions = [
            t for t in self.session.current_questions if t.template_id != template_id
        ]