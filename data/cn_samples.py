"""大典职业骨架样本。

⚠️ 本文件为**人工整理的样本**，非人社部权威数据。
   仅用于架构验证，生产环境必须替换为真实大典 CSV。
   真实数据获取途径：人社部发布的《职业分类大典》正文/公示材料，
   或经用户确认的可信结构化数据源。

共 30 条样本，覆盖 6 个中类，每条包含细类码与 1-2 句描述。"""

from __future__ import annotations
from pathlib import Path
import csv, io

from ..models import Occupation
from .cn_dadian_adapter import CnDadianAdapter


SAMPLE_CSV = """major_group,medium_group,minor_group,detailed_code,name,description
2,信息传输、软件和信息技术服务人员,10,2-02-10-08,软件工程师,从事软件开发、测试、维护的技术人员
2,信息传输、软件和信息技术服务人员,10,2-02-10-07,数据分析师,从事数据采集、清洗、分析与可视化的人员
2,信息传输、软件和信息技术服务人员,10,2-02-10-05,信息系统分析工程技术人员,从事信息系统分析与设计的技术人员
3,办事人员,01,3-01-05-02,行政专员,从事行政事务、文书处理与协调的人员
2,卫生专业技术人员,05,2-05-02-01,护士,从事病人护理、健康宣教的卫生技术人员
"""


def load_sample_cn_occupations() -> list[Occupation]:
    """加载内置样本（通过真实 CnDadianAdapter 解析同一 CSV 格式，
    避免双路径）。样本 CSV 未来替换为真实数据时，调用方不需要修改。"""
    adapter = CnDadianAdapter()
    payload = adapter.fetch_from_string(SAMPLE_CSV)
    return adapter.normalize_occupations(payload)