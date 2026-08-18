# 证据约束型基金研究 Agent

本项目面向一个具体问题：在基金净值、公开前十大持仓和报告摘录不完整且口径异构时，
如何只基于可追溯证据回答有限问题，而不是把缺失证据扩写成结论。

仓库合并了原始的确定性基金研究平台和 V2 单 Agent 运行时，包括净值与公开持仓诊断、
TF-IDF 检索、引用核验、数值回算、安全拒答、FastAPI、健康检查、指标和 Docker。

默认公开路径只使用合成数据，运行模式为 `MOCK_ONLY`，模型调用、网络请求、Token 和
成本均为零，不需要 API Key。它证明的是软件契约和安全控制，不是真实 LLM 质量、真实基金
表现、投资建议或生产系统能力。

English documentation: [README.md](README.md)

## V1 平台与 V2 Agent

- 确定性研究平台：计算净值收益/波动/回撤、公开前十大集中度、同报告期重合和行业配置变化；
- V2 单 Agent：通过严格 Schema 和工具白名单路由请求，校验引用与数字，在证据不足或请求不
  安全时拒答；
- 服务层：FastAPI 请求 ID、健康检查、Prometheus 风格指标、安全降级和 Docker；
- 可选在线适配器：OpenAI Responses API/Agents SDK 合约边界，但默认关闭，公开版本不声称真实
  API 评测结果。

公开演示使用 `SYN001`、`SYN002`、`SYN003` 和四个虚构报告期。真实基金文件和完整 PDF 不会
进入仓库，详见 [DATA_LICENSE.md](DATA_LICENSE.md) 与
[data/DATA_MANIFEST.md](data/DATA_MANIFEST.md)。

## 快速运行

```powershell
python -m pip install -e ".[dev]"
python scripts/run_pipeline.py --profile demo_synthetic
python -m pytest -q
```

输出应包含 `network_calls=0`、`api_keys_required=0`，并分别通过一个回答案例和一个证据不足
拒答案例。

启动本地 API：

```powershell
$env:FUND_AGENT_MODE = "MOCK_ONLY"
python -m uvicorn fund_agent_v2.api:app --app-dir src --host 127.0.0.1 --port 8000
```

接口包括 `/health/live`、`/health/ready`、`/metrics` 和 `POST /v1/research`。Docker 演示：

```powershell
docker compose up --build
```

Compose 只读挂载合成数据，使用非 root 用户、移除 Linux capabilities，并绑定本机回环地址。

## 离线评测

V2 离线题集共有 32 个固定案例，分为七组：adversarial 4、citation integrity 4、development
5、numeric consistency 4、prompt injection 5、refusal 5、tool selection 5。该确定性合成题集
的结果为 32/32。

检查内容包括工具路由、Schema、基金与报告期范围、引用完整性、数字回算、拒答、Prompt
Injection 阻断和审计输出。模型调用、网络请求、Token 和成本均为零，因此不能证明真实 LLM
推理、语言质量、语义检索、泛化能力或生产性能。详见
[reports/evaluation.md](reports/evaluation.md)。

## 主要限制

- 合成基金、净值、持仓、文本、哈希和 `.invalid` URL 均为虚构，不代表真实基金或历史表现；
- 所有持仓指标只基于公开前十大，不能代表完整组合暴露；
- TF-IDF 是词面检索，不是语义 RAG，`0.31` 是当前语料的相关性门槛而不是概率；
- 固定离线题集规模较小，全部通过不代表任意问题上的泛化能力；
- 可选 OpenAI 适配器默认关闭，公开版本未完成真实 LLM 质量评测；
- 系统不提供实时行情、实时风险、交易信号、收益预测或投资建议。

架构说明见 [reports/architecture.md](reports/architecture.md)，评测说明见
[reports/evaluation.md](reports/evaluation.md)，数据权利见 [DATA_LICENSE.md](DATA_LICENSE.md)。
