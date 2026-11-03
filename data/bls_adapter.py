# data/bls_adapter.py
"""BLS 适配器示例。无任何硬编码前景数值；publication_year 来自 release metadata。"""
import csv, io
from datetime import datetime, timezone
from pathlib import Path

from .adapters import DataSourceAdapter, RawPayload, SourceCategory
from ..models import Prospect, IndicatorType, FieldProvenance


class BLSNationalMatrixAdapter(DataSourceAdapter):
    source_id = "BLS-EP-2024-2034"
    source_category = SourceCategory.AUTHORITATIVE_STATISTICAL
    expected_refresh_days = 730

    FIELD_MAP = [
        ("Employment Percent Change, 2024-2034", IndicatorType.EMPLOYMENT_CHANGE_RATE, "percent"),
        ("Employment Change, 2024-2034",         IndicatorType.JOB_GROWTH_COUNT,     "thousands"),
        ("Annual Openings",                      IndicatorType.ANNUAL_OPENINGS,      "thousands"),
        ("Median Wage",                          IndicatorType.MEDIAN_WAGE,          "currency_usd"),
    ]

    def fetch(self, csv_path: str, release_meta_path: str, **params) -> RawPayload:
        csv_bytes = Path(csv_path).read_bytes()
        meta = Path(release_meta_path).read_text(encoding="utf-8")
        return RawPayload(
            source_id=self.source_id,
            retrieved_at=datetime.now(timezone.utc),
            source_url_or_file=f"{csv_path}|{release_meta_path}",
            content={"csv": csv_bytes, "release_meta": meta},
            content_type="csv+meta",
        )

    def normalize_prospects(self, payload: RawPayload) -> list[Prospect]:
        pub_year = self._parse_release_year(payload.content["release_meta"])
        rows = list(csv.DictReader(io.StringIO(
            payload.content["csv"].decode("utf-8-sig"))))
        out: list[Prospect] = []

        for idx, row in enumerate(rows, start=2):
            soc = (row.get("Occupation Code") or "").strip()
            if not self._looks_like_soc(soc):
                continue
            for raw_field, indicator, unit in self.FIELD_MAP:
                raw_val = row.get(raw_field)
                value = self._parse_float_or_none(raw_val)
                out.append(Prospect(
                    occupation_id=soc,
                    source_name="BLS National Employment Matrix",
                    issuing_authority="U.S. Bureau of Labor Statistics",
                    publication_year=pub_year,
                    data_year_or_horizon=("as_of_2024" if indicator == IndicatorType.MEDIAN_WAGE
                                          else "2024-2034"),
                    region="US",
                    indicator_type=indicator.value,
                    indicator_value=value,
                    indicator_unit=unit,
                    confidence_note=self._confidence_note(indicator, value),
                    freshness_status=self._freshness(payload.retrieved_at),
                    provenance=FieldProvenance(
                        source_id=self.source_id,
                        source_url_or_file=payload.source_url_or_file,
                        retrieved_at=payload.retrieved_at,
                        original_field_name=raw_field,
                        original_record_locator=f"row {idx}, code {soc}",
                    ),
                ))
        return out

    @staticmethod
    def _parse_release_year(meta: str) -> int:
        # release_meta 是人工从 BLS release note 提取的文本；格式 "release_year: 2025"
        for line in meta.splitlines():
            line = line.strip()
            if line.startswith("release_year:"):
                year = int(line.split(":", 1)[1].strip())
                if not (1990 <= year <= 2100):
                    raise ValueError(f"implausible release_year: {year}")
                return year
        raise ValueError("release_meta missing 'release_year' field")

    @staticmethod
    def _looks_like_soc(code: str) -> bool:
        parts = code.split("-")
        return len(parts) == 2 and all(p.isdigit() for p in parts) and len(parts[0]) == 2

    @staticmethod
    def _parse_float_or_none(raw) -> float | None:
        if raw is None:
            return None
        s = str(raw).strip().replace(",", "")
        if s in {"", "-", "—", "N/A", "nan", "NaN"}:
            return None
        try:
            v = float(s)
            return None if v != v else v
        except ValueError:
            return None

    def _confidence_note(self, indicator: IndicatorType, value) -> str | None:
        if value is None:
            return "BLS did not publish a value for this occupation/field " \
                   "(may be fewer than 50 jobs, confidential, or poor-quality data). Not an estimate."
        if indicator == IndicatorType.EMPLOYMENT_CHANGE_RATE:
            return ("BLS 10-year projection under specific assumptions. "
                    "Not a forecast of the future; actual values will differ if assumptions fail.")
        return None

    def _freshness(self, retrieved_at: datetime) -> str:
        age_days = (datetime.now(timezone.utc) - retrieved_at).days
        return "HISTORICAL_REFERENCE_ONLY" if age_days > self.expected_refresh_days else "CURRENT"