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
    """每个适配器单一职责：从一个数据源取得原始载荷，并将其映射为标准化结构。
    适配器不负责合并、排序、打分或任何推断。"""

    @property
    @abstractmethod
    def source_id(self) -> str:
        ...

    @property
    @abstractmethod
    def source_category(self) -> SourceCategory:
        ...

    @property
    @abstractmethod
    def expected_refresh_days(self) -> int:
        """该源的预期更新周期（天）。用于新鲜度判断的参考基线。"""
        ...

    @abstractmethod
    def fetch(self, **params) -> RawPayload:
        """获取原始数据。允许的参数由各适配器自行定义。"""

    @abstractmethod
    def normalize_prospects(self, payload: RawPayload) -> list:
        """返回 Prospect 列表。空列表是合法的。"""

    def normalize_occupations(self, payload: RawPayload) -> list:
        """默认不贡献职业（BLS 等前景源）。分类体系源需覆写。"""
        return []