import sys
import os

# 将父目录加入路径，确保能 import career_advisor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
from datetime import datetime, timezone

from career_advisor.config import get_default_llm_client
from career_advisor.profile.extractor import LLMProfileExtractor
from career_advisor.explanation.generator import LLMExplanationGenerator
from career_advisor.explanation.input_builder import build_explanation_input
from career_advisor.explanation.validator import validate
from career_advisor.data.seed_loader import load_occupations
from career_advisor.matching.engine import match
from career_advisor.matching.config import ScoringConfig
from career_advisor.models import Prospect, IndicatorType, FieldProvenance

# 页面配置
st.set_page_config(page_title="职业规划助手", page_icon="🧭", layout="wide")

st.title("🧭 职业规划助手")
st.markdown("输入你的中文、英文或日语简历/个人描述，AI 将为你匹配最适合的职业并生成 10 年前景分析。")

# 侧边栏：多语言与模型配置
with st.sidebar:
    st.header("⚙️ 设置")
    lang = st.selectbox("输出语言", ["中文", "English", "日本語"])
    try:
        client = get_default_llm_client()
        st.info(f"当前 LLM 引擎: {client.model}")
    except Exception as e:
        st.error(f"LLM 加载失败: {e}")
    if st.button("清除缓存并重置"):
        st.session_state.clear()
        st.rerun()

# 主界面：输入区
raw_text = st.text_area("📝 你的简历或自我描述", height=200, 
    placeholder="例如：\n我今年30岁，本科读的是汉语言文学，毕业后做了6年行政助理...\nOR\nI have 5 years of experience in Python backend development...\nOR\n私は5年間のフロントエンド開発経験があります...")

# 准备模拟的 Prospect 数据（因为目前只有 demo 数据）
def get_demo_prospects():
    now = datetime.now(timezone.utc)
    return [
        Prospect(occupation_id="CN-2022-2-02-10-08", source_name="BLS", issuing_authority="BLS",
                 publication_year=2025, data_year_or_horizon="2024-2034", region="US",
                 indicator_type=IndicatorType.EMPLOYMENT_CHANGE_RATE.value, indicator_value=17.9, indicator_unit="percent",
                 provenance=FieldProvenance("BLS", "url", now)),
    ]

if st.button("🚀 开始匹配", type="primary"):
    if not raw_text.strip():
        st.warning("请先输入简历或描述。")
    else:
        with st.spinner("LLM 正在抽取画像并匹配职业..."):
            try:
                extractor = LLMProfileExtractor(client)
                
                # 1. L1 抽取
                profile = extractor.extract(raw_text)
                st.success("✅ 画像抽取完成！")
                
                # 用 expander 展示抽取结果（透明化）
                with st.expander("查看 AI 提取的画像详情"):
                    st.json({
                        "学历": profile.hard_constraints.get("education_level", {}).value if hasattr(profile.hard_constraints.get("education_level"), 'value') else None,
                        "地域": profile.hard_constraints.get("region", {}).value if hasattr(profile.hard_constraints.get("region"), 'value') else None,
                        "技能": [s["skill_id"] for s in profile.skills],
                        "缺失字段": profile.missing_fields
                    })

                # 2. L2 匹配
                occupations = load_occupations()
                prospects = get_demo_prospects()
                result = match(profile, occupations, prospects, ScoringConfig())
                
                if result.status != "ok" or not result.ranked_items:
                    st.error("画像信息不足，无法匹配。请补充更多信息。")
                else:
                    st.subheader("🎯 Top 职业推荐")
                    
                    # 取前 3 名展示
                    for item in result.ranked_items[:3]:
                        with st.container(border=True):
                            col1, col2 = st.columns([1, 4])
                            with col1:
                                st.metric(label=f"排名 {item.rank}", value=f"{item.total_score:.3f} 分")
                            with col2:
                                st.subheader(item.occupation_name)
                                st.caption(f"所属族: {item.occupation_family}")
                                
                                # 显示子分数（防止越界报错）
                                c1, c2, c3 = st.columns(3)
                                c1.progress(max(0.0, min(1.0, item.sub_scores['interest'].raw or 0.0)), text="兴趣匹配")
                                c2.progress(max(0.0, min(1.0, item.sub_scores['skill_transfer'].raw or 0.0)), text="技能迁移")
                                c3.progress(max(0.0, min(1.0, item.sub_scores['values'].raw or 0.0)), text="价值观契合")
                                
                                # 展开看 LLM 解释
                                with st.expander("查看 10 年前景与解释报告（点击生成）"):
                                    with st.spinner("正在调用 L4 生成报告..."):
                                        occ = next(o for o in occupations if o.occupation_id == item.occupation_id)
                                        occ_prospects = [p for p in prospects if p.occupation_id == occ.occupation_id]
                                        
                                        exp_input = build_explanation_input(
                                            item, occ, profile, occ_prospects, {},
                                            {"no_data_phrase": "暂无可靠数据", "no_trend_phrase": "暂无趋势判断"}
                                        )
                                        # 注入语言偏好
                                        exp_input["target_language"] = lang
                                        
                                        generator = LLMExplanationGenerator(client)
                                        try:
                                            output = generator.generate(exp_input)
                                            violations = validate(output, exp_input)
                                            if violations:
                                                st.error(f"生成被校验器拦截：{violations}")
                                            else:
                                                st.markdown(f"**【匹配结论·推断】**\n{output['match_conclusion']['why_match']['text']}")
                                                st.markdown(f"**【主要冲突·推断】**\n{output['match_conclusion']['conflicts']['text']}")
                                                st.markdown(f"**【事实】**\n{output['prospect_10y']['facts']['text']}")
                                                st.markdown(f"**【预测】**\n{output['prospect_10y']['prediction']['text']}")
                                        except Exception as e:
                                            st.error(f"LLM 生成失败: {e}")

            except Exception as e:
                st.error(f"发生错误: {e}")