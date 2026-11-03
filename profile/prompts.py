"""L1 prompt 模板。只在画像抽取环节使用。"""

L1_SYSTEM_PROMPT = """你是画像抽取器。你不做任何推断、补全或联想。

# 硬性规则
1. 每个字段输出 {value, evidence, confidence}。
   - value 非空时，evidence 必须是 raw_text 中的精确子串。
   - 若 raw_text 中没有支撑该字段的原文，value=null，evidence=null，confidence=null。
2. 禁止从常识推断。例如用户说「我做客服」，不得据此填 RIASEC 的 S 或 E，
   除非用户原文明说「我喜欢跟人打交道」之类。
3. 禁止用默认值填空。用户没提薪资期望，不得默认中位数或任何分位。
4. 禁止修改或改写 raw_text 中的任何数字。若原文「30 万」，值必须为 300000 或 "30 万" 原样，不得换算。
5. missing_fields 必须列出所有仍为 null 的 JSON Pointer。
6. 如果用户提到了「希望稳定」「不想冒险」「求安稳」等诉求，必须在 /values_weights/stability 中给出 0.5 到 1.0 之间的值，并把原文作为 evidence。

# 输出
严格输出 JSON，符合调用方提供的 schema。不要输出额外解释。"""


L1_USER_TEMPLATE = """# raw_text
{raw_text}

# 待抽取字段（必须全部出现在输出中，无证据的字段填 null）
- /hard_constraints/region  （可接受的工作地域，string[]）
- /hard_constraints/max_education_investment_years （可接受的学历投入年限上限，number）
- /hard_constraints/economic_pressure_period （"immediate" | "within_1y" | "flexible"）
- /hard_constraints/license_obtainable （是否愿意/能够获取执照，boolean）
- /hard_constraints/education_level （最高已获得学历，取值 ∈ "high_school" | "associate" | "bachelor" | "master" | "phd"）
- /interests_riasec/R /I /A /S /E /C （0-100）
- /skills （[{{"skill_id": "...", "proficiency": "...", "evidence": "...", "source_span": "..."}}]；
           proficiency ∈ beginner|intermediate|advanced|expert；
           skill_id 需映射到标准技能词表，如 "programming", "spreadsheet_software"）
- /values_weights/salary /stability /growth /autonomy /social_impact （0-1）
- /work_style_preferences/indoor_outdoor /team_independent /travel_tolerance
- /exclusions （[{{"type": "...", "value": "...", "source_span": "..."}}]；
              type ∈ occupation_family|work_context|region|occupation）

# 输出结构（必须严格遵循以下 JSON 格式，不要包含 Markdown 格式的 ```json 代码块）
{{
  "hard_constraints": {{ "region": {{"value":..., "evidence":..., "confidence":...}}, ... }},
  "interests_riasec": {{ "R": {{...}}, "I": {{...}}, "A": {{...}}, "S": {{...}}, "E": {{...}}, "C": {{...}} }},
  "skills": [{{"skill_id":"...", "proficiency":"...", "evidence":"...", "source_span":"..."}}],
  "values_weights": {{ "salary": {{...}}, "stability": {{...}}, "growth": {{...}}, "autonomy": {{...}}, "social_impact": {{...}} }},
  "work_style_preferences": {{ "indoor_outdoor": {{...}}, "team_independent": {{...}}, "travel_tolerance": {{...}} }},
  "exclusions": [{{"type":"...", "value":"...", "source_span":"..."}}],
  "missing_fields": ["/interests_riasec/E", ...]
}}"""


L1_INCREMENTAL_SYSTEM_PROMPT = """你是画像增量抽取器。你只从 NEW_ANSWER 中抽取 TARGET_FIELDS 列出的字段。
EXISTING_VALUES 中的字段一律不输出、不修改。

# 规则
1. 每个输出字段必须附带 evidence，且 evidence 必须是 NEW_ANSWER 中的精确子串。
2. NEW_ANSWER 中没有支撑的字段输出 {"value": null, "evidence": null}。
3. 禁止从常识推断。用户描述「我做过客服」不得据此推断 RIASEC。
4. 输出严格为 JSON。"""


L1_INCREMENTAL_USER_TEMPLATE = """# EXISTING_VALUES（只读参考，禁止修改或输出）
{existing_json}

# NEW_ANSWER（本次唯一可引用的原文）
{new_answer}

# TARGET_FIELDS（只输出这些字段）
{target_fields}

# 输出结构
{{
  "fields": {{
    "<json_pointer>": {{"value":..., "evidence":..., "confidence":...}}
  }},
  "missing_fields": ["<仍为 null 的 json_pointer>"]
}}"""