# 🧭 职业规划助手 (Career Advisor)

一个结合了**结构化规则算法**与**大语言模型 (LLM)** 的智能职业规划与前景分析系统。

用户只需提供一段自由文本、中文/英文/日文简历，系统将通过大模型抽取用户画像，基于**纯代码、可复现的匹配算法**（涵盖兴趣、技能、价值观与硬约束），输出 Top-N 职业推荐，并由 LLM 生成附带【事实】/【推断】/【预测】标签的 10 年前景解释报告。

## 🌟 核心特性

1. **零幻觉防篡改**：解释层（LLM）只负责“组织语言”，绝不参与“计算分数”。所有生成文本必须通过**强校验器**（数值白名单、引用校验），严防大模型篡改数据或编造无源结论。
2. **纯结构化的排序**：匹配层完全解耦 LLM，基于 O*NET 真实数据、RIASEC 距离、技能迁移（含邻居匹配）和惩罚项进行确定性打分，确保相同画像的输出 100% 可复现。
3. **多语言无缝支持**：支持中文、英文、日文简历输入，内部统一映射为英文标准词表（O*NET），并支持多语言解释报告输出。
4. **真实全量数据**：接入 O*NET 31.0 数据库，涵盖 910+ 个真实职业及其所需的技能、兴趣和工作环境属性。
5. **兜底与鲁棒性**：在 L1 抽取层和 L4 解释层均设置了代码级的正则兜底与强结构清洗，即使大模型输出格式崩溃，系统也能优雅降级。

## 🏗️ 系统架构

系统严格遵循分层架构，确保数据与逻辑解耦：

~~~text
[用户输入 / 简历]
       │
       ▼
┌──────────────┐
│ L1 画像抽取  │ (LLM 接入，带证据提取与正则兜底)
└──────────────┘
       │ (结构化 UserProfile)
       ▼
┌──────────────┐
│ L2 匹配打分  │ (纯代码：硬约束过滤 + 软维度打分 + 多样性约束)
└──────────────┘
       │ (RankedMatchResult)
       ▼
┌──────────────┐
│ L3 结果组装  │ (提取打分细节、冲突点与前景数据)
└──────────────┘
       │ (ExplanationInput)
       ▼
┌──────────────┐
│ L4 解释生成  │ (LLM 生成自然语言 + 强校验器拦截幻觉)
└──────────────┘
       │ (ExplanationOutput)
       ▼
┌──────────────┐
│ L5 Web UI    │ (Streamlit 渲染：卡片、进度条、标签)
└──────────────┘
~~~

## 🚀 快速开始

### 1. 环境准备

确保你已安装 Python 3.10+。
~~~bash
pip install streamlit openai python-dotenv
~~~

### 2. 配置大模型环境

在项目根目录（与 `app.py` 同级）创建 `.env` 文件。系统支持任何兼容 OpenAI 接口的模型（如 DeepSeek, Agnes, 本地 Ollama 等）：

~~~env
# 选择引擎: deepseek / agnes / ollama
LLM_PROVIDER=deepseek

# 1. DeepSeek 配置
DEEPSEEK_API_KEY=sk-你的APIKey
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# 2. 本地 Ollama 配置 (无需真实 Key)
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434/v1
# OLLAMA_MODEL=qwen2.5:7b
~~~
> ⚠️ **安全提示**：请不要将包含真实 Key 的 `.env` 文件提交到 Git 仓库，本项目的 `.gitignore` 已默认忽略该文件。

### 3. 准备职业库数据

1. 前往 [O*NET Resource Center](https://www.onetcenter.org/database.html) 下载 **O*NET 31.0 Database (CSV)** 格式。
2. 将解压后的所有 `.csv` 文件放入 `data/db_31_0_csv/` 目录。
3. 运行构建脚本生成系统快照：
~~~bash
python -m career_advisor.data.build_snapshot --onet-dir "data/db_31_0_csv"
~~~
*构建成功后，终端将输出解析成功数，并在 `data/snapshots/` 下生成 `occupations.json` 和 `skills_adjacency.json`。*

### 4. 启动 Web 界面

~~~bash
streamlit run app.py
~~~
在浏览器中打开 `http://localhost:8501` 即可开始使用。

## 📂 项目结构

~~~text
career_advisor/
├── app.py                     # Streamlit Web UI 入口
├── config.py                  # 读取 .env 配置
├── llm_client.py              # OpenAI 兼容客户端封装
├── models.py                  # 核心数据类 (Occupation, Prospect, UserProfile 等)
├── region_scope.py            # 地域映射表 (中国、美国、日本等)
├── data/                      # 数据层
│   ├── onet_adapter.py        # O*NET CSV 解析器
│   ├── seed_loader.py         # 职业库加载器 (快照+大典合并)
│   ├── skill_adjacency.py     # 技能邻接表构建器
│   └── snapshots/             # 构建产物 (JSON)
├── matching/                  # 匹配层
│   ├── engine.py              # 核心编排器
│   ├── config.py              # 权重与阈值配置
│   ├── scorers.py             # 兴趣、技能、价值观打分器
│   ├── hard_filter.py         # 学历、执照、地域硬约束过滤
│   └── diversity.py           # Top-N 多样性族约束
├── profile/                   # 画像抽取层
│   ├── extractor.py           # L1 抽取引擎 (含正则兜底与截断)
│   └── prompts.py             # L1 强约束 Prompt
├── explanation/               # 解释层
│   ├── generator.py           # L4 生成器 (强结构清洗)
│   ├── input_builder.py       # 输入数据投影
│   ├── validator.py           # 幻觉校验器 (白名单比对)
│   └── prompts.py             # L4 Prompt
└── interaction/               # 交互辅助
    └── preference_adjuster.py # P7 偏好调节与 Diff
~~~

## 🛡️ 红线落地说明

1. **数据溯源与预测禁用**：匹配层 (L2) 的 `score_values` 仅允许读取 `median_wage` 和 `employment_size_current` 等当前观测类指标。预测类数据（如增长率）**仅进入解释层展示，绝不参与打分**。
2. **解释层数值白名单**：`explanation/validator.py` 在接收 LLM 输出后，会遍历所有文本段落提取数字，逐一与 `ExplanationInput` 中的原始数值进行 `1e-4` 精度的比对。任何大模型自行编造的数值（如“增长 12%”、“19年经验”）如果不在输入中，会触发违规并强制降级为模板输出。
3. **无数据强制兜底**：当 `Prospect` 数据完全缺失时，`generator.py` 会屏蔽大模型生成逻辑，强制注入「该职业暂无可靠的前景数据，以下内容不含趋势判断」，确保大模型无法凭空想象行业前景。
4. **免责声明与执照提示**：前端 Web 界面在渲染结果时，强制从底层字段读取并展示免责声明；若职业要求执照，会醒目提示用户自行核实当地政策。

## ⚠️ 免责声明

本系统生成的职业推荐与前景分析仅供参考，不构成就业承诺、投资建议或任何形式的专业决策依据。受限于数据源的覆盖范围（当前主要基于美国 O*NET 数据库），跨地域（如中国、日本）的职业前景可能存在偏差。涉及执照、资质要求的职业，请务必自行核实当地最新法律法规与政策。