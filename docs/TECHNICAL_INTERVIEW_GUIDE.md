# 证据约束型基金研究 Agent：技术面试深挖指南

这份文档用于作者本人复习。公开版本默认读取 `data/demo_synthetic/` 的合成基金
资料，以 `MOCK_ONLY` 确定性状态机验证工具契约；它不是已经证明真实 LLM 质量的产品。

## 一分钟介绍

我搭建了一个受限的基金研究 Agent：在登记的基金和报告期范围内计算净值指标、比较
公开前十大持仓、检索报告片段、核验页码与哈希，并在证据不足、越界或危险请求时拒答。
系统把确定性工具层、严格 Pydantic Schema、工具白名单、审计元数据和 FastAPI 服务
组合起来。公开评测 32/32 通过，证明冻结的软件契约和安全路由可重复，不证明真实
大模型的语言质量或泛化能力。

## 产品问题与边界

目标不是预测基金收益或提供投资建议，而是回答“登记资料中能否支持这个问题”。默认
数据包含虚构的 `SYN001`、`SYN002`、`SYN003` 和有限报告期。公开前十大持仓不等于
完整组合；系统也不是实时风控、生产部署或语义 RAG。

## 从请求到响应的数据流

```text
HTTP POST /v1/research
  -> src/fund_agent_v2/api.py::research
  -> guardrails.classify_request
  -> DeterministicMockSingleAgent.run
  -> FundToolbox + ToolRuntime
  -> DatasetRepository (registered files + SHA-256)
  -> calculations / retrieval_engine
  -> AgentResponse + redacted audit metadata
```

离线脚本入口包括 `scripts/run_phase6.py`、`scripts/run_phase7_offline.py`、
`scripts/run_phase9_http_smoke.py`。工具配置在 `configs/phase6_tools.yaml`，Agent
运行配置在 `configs/phase7_agent.yaml`，公开默认模式在 `configs/v2_agent.yaml`。

## 为什么先做确定性 baseline

直接接 LLM 会同时引入模型版本、提示词、网络、成本和不可重复语言输出，难以判断
错误来自工具、证据还是模型。确定性 baseline 先冻结这些低层契约：工具是否只读登记
数据、数字是否重新计算、引用是否可定位、危险请求是否零工具调用。以后接 LLM 时，
可以在相同工具、预算和题集上比较增量，而不是把“调用成功”误当成研究质量。

## 工具与数据层

`src/fund_agent_v2/tools.py::FundToolbox` 暴露十个受限工具，典型链路如下：

1. `load_fund_profile` 读取登记的基金和报告期范围；
2. `calculate_nav_metrics` 在共同日期窗口上重算收益、年化波动和最大回撤；
3. `compare_holdings` 只比较同一报告期的公开前十大持仓；
4. `retrieve_report_evidence` 使用登记索引检索不可信原文片段；
5. `verify_citations` 校验 URL、文档、基金、报告期、物理页、chunk 和哈希；
6. `validate_numeric_claims` 回查登记 CSV，而不是相信调用方给的数字；
7. `export_research_memo` 需要显式人工批准，并将输出限制在 export root。

真实实现还包含基金比较、官方来源 manifest 查询和证据表生成。工具输入输出在
`src/fund_agent_v2/schemas.py` 中定义，strict model 使用 `extra=forbid`，不接受路径、
Shell、环境变量或密钥字段。

## 数学与检索

净值简单收益为：

```text
r_t = NAV_t / NAV_(t-1) - 1
vol_annual = sample_std(r_t) * sqrt(252)
drawdown_t = NAV_t / running_max(NAV_t) - 1
```

持仓诊断包括 C10、HHI10、NameJaccard 和 CommonNAVShare。比较严格限定同一报告期，
避免把不同市场时期误当成持仓关系。

`src/fund_agent_v2/retrieval_engine.py` 使用中文字符 2--4 gram TF-IDF 和余弦相似度：

1. `normalize_for_search` 做 Unicode 规范化、小写和可检索字符过滤；
2. `character_ngrams` 生成 2 到 4 字符片段；
3. `query_vector` 使用 IDF 形成单位向量；
4. `retrieve` 先按基金和报告期过滤，再按分数排序；
5. 低分、低覆盖或空结果进入保守拒答。

这是词面检索，不是语义 RAG。每张证据卡把原文标为不可信内容，避免报告中的文字
改变工具权限或系统规则。

## 引用、哈希和数值回算

`src/fund_agent_v2/repository.py::DatasetRepository._registered_path` 只允许配置中
登记的文件，并在每次读取前核对 SHA-256。`verify_citations` 同时检查来源 URL、
`doc_id`、基金、报告期、物理页、chunk、文本哈希、页面哈希和来源 PDF 哈希。引用不
是“模型说有依据”，而是可定位的精确来源关系。

数值结论由 `src/fund_agent_v2/calculations.py` 和 `FundToolbox` 重新计算，再由
`validate_numeric_claims` 和登记数据比较。Agent 不接受用户直接提供的参考答案作为
真值。

## 权限、状态机和安全

`src/fund_agent_v2/guardrails.py::classify_request` 在工具调用前检查：基金和报告期
allowlist、输入长度、个性化建议、收益保证、伪造引用、密钥/文件/命令请求、工具预算
滥用和 Prompt Injection。命中危险规则时工具步数为零。

`src/fund_agent_v2/single_agent.py::DeterministicMockSingleAgent.run` 负责意图路由、
最多工具步数、连续失败上限、工具调用摘要和最终响应。`src/fund_agent_v2/audit.py::ToolRuntime`
再执行工具 allowlist、超时、错误分类和脱敏审计，只保存输入/输出哈希、工具名、状态、
耗时和请求 ID，不保存查询原文、证据全文或密钥。

状态的区别：

- `ANSWERED`：工具成功、证据和数值校验满足门槛；
- `REFUSED`：请求越界、危险或证据不足，且不调用工具；
- `ERROR`：工具执行失败或连续失败超限，没有生成研究结论；
- `DEGRADED`：HTTP 服务初始化、完整性检查或运行时异常，服务安全降级。

## 32/32 评测意味着什么

`src/fund_agent_v2/phase7_eval.py::run_phase7_offline` 使用 32 个新的固定离线案例，
覆盖 development、adversarial、tool selection、numeric consistency、citation
integrity、refusal 和 prompt injection。结果证明状态、路由、参数范围、工具预算、
引用/数字校验和拒答契约在当前 mock 数据上可重复。它不证明真实 LLM 的语言质量、
语义检索泛化、任意问题准确率或实际 API 成本。旧 holdout 读取数为零，也没有创建新的
final holdout。

## 最容易被质疑的五个问题

### 1. 这是真正的 Agent 还是 if/else？

当前公开实现是有意设计的确定性单 Agent 状态机。它先验证工具和安全边界，为未来
模型接入提供可比较 baseline；不把 mock 包装成真实 LLM。

### 2. TF-IDF 为什么不算 RAG？

它是字符 n-gram 的词面检索，没有 embedding 语义空间或模型生成。优势是依赖少、
可解释、可重复；缺点是同义表达可能检索不到。

### 3. Prompt Injection 如何处理？

报告片段被标记为不可信内容；查询在 `classify_request` 阶段先匹配注入、密钥、命令
和越权模式，命中后直接 `REFUSED`，不会先把内容交给工具。

### 4. 32/32 是否等于模型准确率 100%？

不是。它是 32 个固定软件契约案例的通过率，当前模型调用和网络请求都是零，不能
外推真实语言质量或开放域泛化。

### 5. 为什么不让 Agent 直接访问网页和 PDF？

公开版本需要可复现和安全边界。官方 URL 只通过本地 manifest 查询，网络请求数为零；
真实采集需要额外的数据许可、缓存、版本和失败重试设计。

## 三段现场代码

1. `src/fund_agent_v2/retrieval_engine.py::retrieve`：展示索引校验、基金/报告期
   过滤和确定性排序。
2. `src/fund_agent_v2/guardrails.py::classify_request`：展示工具前拒答和意图路由。
3. `src/fund_agent_v2/audit.py::ToolRuntime.invoke`：展示 allowlist、超时、错误分类
   和脱敏事件记录。

另外应能解释 `src/fund_agent_v2/api.py::FundAgentService.readiness` 和
`src/fund_agent_v2/api.py::research` 如何提供健康检查、请求 ID、指标及安全降级。

## 最小现场演示

在仓库根目录执行：

```powershell
$env:FUND_AGENT_MODE = "MOCK_ONLY"
python scripts/run_phase7_offline.py
python scripts/run_phase9_http_smoke.py
python -m pytest -q
```

公开服务只使用 `data/demo_synthetic/`，不需要网络或 API Key。HTTP smoke 会验证健康
检查、研究请求、在线模式拒绝和 Prometheus 风格指标。

## 如果未来接入 LLM

先保持同一工具 Schema、allowlist、输入过滤和最大步数；只替换决策层。开发集用于调试
路由和提示词，另建未触碰 holdout，冻结题目、gold 引用和评测器后只运行一次。应记录
每题工具步骤、延迟、输入/输出 token、拒答正确率、引用支持率、数字误差、错误类型、
网络请求和美元成本。模型结果必须和确定性 baseline 并排报告，不能用语言流畅度掩盖
引用或数值失败。

## 未实现及原因

- 没有真实 LLM 质量结论：公开默认是 `MOCK_ONLY`，避免不可重复和无证据宣传；
- 没有语义 embedding 检索：当前目标是可审计的词面基线；
- 没有实时数据和生产部署：数据许可、更新策略、SLA、监控和灾备尚未定义；
- 没有自动导出研究 Memo：导出工具需要人工批准，防止未经审阅的外部材料生成；
- 没有读取旧 holdout：保护既有评测边界，避免把保留集变成调参集。

## 复习边界

最重要的回答顺序是：先说明数据和运行模式，再说明工具与证据门控，最后谈评测数字。
不要把合成基金代码当成真实基金，也不要把“有 Agent 类名”表述成已经验证了真实
大模型研究能力。
