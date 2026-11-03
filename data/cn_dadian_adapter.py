"""人社部职业分类大典适配器。

输入：CSV，列名固定如下（UTF-8）：
  major_group, medium_group, minor_group, detailed_code, name, description
示例行：
  2, 02, 10, 2-02-10-08, 软件工程师, 从事软件开发、测试、维护的技术人员

产出：Occupation 骨架。skill_vector / riasec_profile / work_context /
typical_requirements 一律为 None —— 大典本身不提供这些字段。
下游通过 cn_enricher 从 O*NET 快照补充。
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path

from ..models import Occupation
from .adapters import DataSourceAdapter, RawPayload, SourceCategory
from .family_mapping import CONTROLLED_FAMILIES


# 大典中类名 → 本系统 20 个受控族。
# 覆盖常见的 20+ 个中类；其余中类保守返回 None（职业不进族，不进匹配）。
CN_MEDIUM_GROUP_TO_FAMILY: dict[str, str] = {
    "工程技术人员": "工程与制造",
    "科学研究人员": "科学研究",
    "农业技术人员": "农业与环境",
    "卫生专业技术人员": "健康服务",
    "经济和金融专业人员": "金融与会计",
    "教学人员": "教育与培训",
    "法律、社会和宗教专业人员": "法律与公共安全",
    "文学艺术、体育专业人员": "艺术设计与传媒",
    "新闻出版、文化专业人员": "艺术设计与传媒",
    "办事人员": "商业与行政管理",
    "安全和消防及辅助人员": "法律与公共安全",
    "邮政和电信业务人员": "供应链与物流",
    "批发与零售服务人员": "销售与客户服务",
    "交通运输、仓储和邮政业服务人员": "交通与运维",
    "住宿和餐饮服务人员": "旅游与酒店",
    "信息传输、软件和信息技术服务人员": "信息技术与数字技术",
    "金融服务人员": "金融与会计",
    "房地产服务人员": "建筑与房地产",
    "租赁和商务服务人员": "商业与行政管理",
    "技术辅助服务人员": "其他专业服务",
    "水利、环境和公共设施管理服务人员": "农业与环境",
    "居民服务人员": "社会服务",
    "电力、燃气及水供应服务人员": "工程与制造",
    "修理及制作服务人员": "工程与制造",
    "文化和教育服务人员": "教育与培训",
    "健康、体育及休闲服务人员": "健康服务",
}


def family_for_cn_medium_group(medium_group: str) -> str | None:
    return CN_MEDIUM_GROUP_TO_FAMILY.get(medium_group.strip())


_REQUIRED_COLUMNS = ("major_group", "medium_group", "minor_group",
                     "detailed_code", "name", "description")


class CnDadianAdapter(DataSourceAdapter):
    source_id = "CN-DADIAN-2022"
    source_category = SourceCategory.TAXONOMY
    expected_refresh_days = 1825  # 约 5 年一次修订

    def fetch(self, csv_path: str, **params) -> RawPayload:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"大典 CSV 不存在: {csv_path}")
        return RawPayload(
            source_id=self.source_id,
            retrieved_at=datetime.now(timezone.utc),
            source_url_or_file=str(path.resolve()),
            content=path.read_text(encoding="utf-8"),
            content_type="csv",
        )

    def normalize_prospects(self, payload: RawPayload) -> list:
        return []  # 大典不提供前景数值

    def normalize_occupations(self, payload: RawPayload) -> list[Occupation]:
        reader = csv.DictReader(payload.content.splitlines())
        if reader.fieldnames is None:
            return []
        missing = [c for c in _REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"大典 CSV 缺少列: {missing}")

        results: list[Occupation] = []
        for row in reader:
            code = row["detailed_code"].strip()
            name = row["name"].strip()
            if not code or not name:
                continue
            family = family_for_cn_medium_group(row["medium_group"])
            if family is None:
                continue  # 未映射中类 → 跳过，不兜底

            results.append(Occupation(
                occupation_id=f"CN-2022-{code}",
                preferred_name=name,
                occupation_family=family,
                taxonomy_refs={"cn_dadian_2022": {
                    "major_group": row["major_group"].strip(),
                    "medium_group": row["medium_group"].strip(),
                    "minor_group": row["minor_group"].strip(),
                    "detailed_code": code,
                }},
                riasec_profile=None,
                skill_vector=None,
                typical_requirements=None,
                work_context=None,
                core_tasks=[{"task_id": "desc", "task_statement": row["description"].strip(),
                             "source": "CN_DADIAN"}],
                entry_barriers={"license_required": "unknown", "license_note": None},
                data_quality_flags=["cn_dadian_skeleton_only"],
            ))
        return results

    def fetch_from_string(self, csv_text: str, source_url: str = "inline:cn_samples") -> RawPayload:
        return RawPayload(
            source_id=self.source_id,
            retrieved_at=datetime.now(timezone.utc),
            source_url_or_file=source_url,
            content=csv_text,
            content_type="csv",
        )          

      