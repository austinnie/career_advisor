# data/adapters.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class SourceCategory(str, Enum):
    AUTHORITATIVE_STATISTICAL = "authoritative_statistical"
    TAXONOMY = "taxonomy"
    RECRUITMENT_MARKET = "recruitment_market"


@dataclass(frozen=True)
class RawPayload:
    source_id: str
    retrieved_at: datetime
    source_url_or_file: str
    content: Any
    content_type: str


class DataSourceAdapter(ABC):
    @property @abstractmethod
    def source_id(self) -> str: ...
    @property @abstractmethod
    def source_category(self) -> SourceCategory: ...
    @property @abstractmethod
    def expected_refresh_days(self) -> int: ...
    @abstractmethod
    def fetch(self, **params) -> RawPayload: ...
    @abstractmethod
    def normalize_prospects(self, payload: RawPayload) -> list:
        """返回 Prospect 列表。空列表是合法的。"""
    def normalize_occupations(self, payload: RawPayload) -> list:
        return []                    # 默认不贡献职业（BLS 等前景源）