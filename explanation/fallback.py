"""模板化降级。校验失败两次后由确定性代码渲染，不经 LLM。"""

def render_fallback(explanation_input: dict) -> dict:
    inp = explanation_input
    occ = inp["occupation"]; m = inp["match"]
    subs = m["sub_scores"]
    any_data = any(p.get("status") == "available" for p in inp["prospects"])

    facts_text = "该职业暂无可靠的前景数据，以下内容不含趋势判断" if not any_data else \
        "；".join(
            f"{p['indicator_type']}（{p['indicator_value']} {p.get('indicator_unit') or ''}，"
            f"{p['source_name']}，{p['publication_year']}，{p['region']}）"
            for p in inp["prospects"] if p.get("status") == "available")
    citations = [
        {"indicator_type": p["indicator_type"], "value": p["indicator_value"],
         "unit": p.get("indicator_unit"), "source_name": p["source_name"],
         "publication_year": p["publication_year"], "region": p["region"]}
        for p in inp["prospects"] if p.get("status") == "available"
    ]

    return {
        "occupation_id": occ["occupation_id"],
        "match_conclusion": {
            "scores_block": {
                "rank": m["rank"], "total_score": m["total_score"],
                "sub_scores": {k: {"raw": s["raw"], "weight_effective": s["weight_effective"],
                                   "contribution": s["contribution"]}
                               for k, s in subs.items()},
                "penalties_total": m.get("penalties", {}).get("total", 0),
            },
            "why_match": {
                "tag": "推断",
                "text": "匹配分来自结构化计算。具体命中技能：" + (
                    "、".join(m.get("matched_skills") or []) or "无") + "。",
                "evidence_refs": ["match.matched_skills"],
            },
            "conflicts": {
                "tag": "推断",
                "text": "未命中的关键技能：" + (
                    "、".join(m.get("unmatched_critical_skills") or []) or "无") + "。",
                "conflict_refs": ["match.unmatched_critical_skills"],
            },
            "hard_constraint_alerts": [
                {"constraint": e["constraint"], "status": e["status"],
                 "prominent": e["status"] in ("unknown", "soft_penalty"),
                 "detail": e["detail"]}
                for e in m.get("hard_constraint_eval", [])
                if e["status"] in ("unknown", "soft_penalty")
            ],
        },
        "prospect_10y": {
            "facts": {"tag": "事实", "text": facts_text, "citations": citations},
            "inference": {"tag": "推断",
                          "text": ("由于缺乏前景数据，以下推断仅基于职业任务性质：该职业核心任务见职业库。"
                                   if not any_data else
                                   "基于上述事实数据推导，具体驱动因素需结合地区产业结构分析。"),
                          "derivation_chain": ["prospects"] if any_data
                                              else ["occupation.core_tasks"]},
            "prediction": {"tag": "预测",
                           "text": "暂无外部机构对该职业的 10 年期预测。" if not any_data
                                   else "外部机构预测见数据引用。",
                           "institution_predictions": [],
                           "counter_scenarios": []},
        },
        "entry_path": {
            "text": "典型学历要求：" + str(
                (occ.get("typical_requirements") or {}).get("entry_education") or "暂无信息")
                + "；执照要求：" + str(occ.get("license_required") or "unknown") + "。",
            "based_on": ["occupation.typical_requirements.entry_education",
                         "occupation.license_required"],
        },
    }