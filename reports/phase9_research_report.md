# Historical Phase 9 Engineering Record

> This file is retained as historical evidence. The public-facing description
> is in `README.md`, `reports/architecture.md`, and `reports/evaluation.md`.

## 1. 执行结论

本阶段把 Phase 6 的确定性基金工具和 Phase 7 的单 Agent mock 状态机封装为一个本地 FastAPI 服务，并加入健康检查、请求 ID、结构化脱敏日志、Prometheus 风格指标和安全降级。服务默认 `MOCK_ONLY`，不会访问真实 OpenAI API，也不会读取 API Key。

Phase 7 离线评测通过 32/32，通过率 100.0%；Phase 7 离线 Gate 为 `PASS`（26/26）。本报告的数字来自机器可读结果，不是大模型自报。

## 2. 研究问题与岗位相关性

研究对象是证据可追溯的公募基金诊断平台：在受限基金和报告期范围内回答净值指标、公开前十大持仓重合和报告原文证据问题。它展示量化研究员岗位需要的数值回算、数据边界、拒答机制、可观察性和可部署工程能力。

## 3. 部署架构

```text
HTTP client
  -> FastAPI typed service
  -> request-id and scope boundary
  -> DeterministicMockSingleAgent
  -> ten Phase 6 deterministic tools
  -> numeric/citation validation
  -> AgentResponse or safe refusal
  -> redacted logs and metrics
```

FastAPI 在这里解决健康检查、可编程调用、结构化日志和运行指标问题；没有同时堆叠 Streamlit、React 或队列系统。Docker 只使用仓库内的 `data/demo_synthetic`，该目录可通过只读 volume 挂载。

## 4. 数据与时间边界

- 数据 profile：`demo_synthetic`，三只虚构基金、四个合成报告期。
- NAV 和持仓数据沿用 Phase 6 已注册、哈希锁定的数据。
- 这些结果属于 `HISTORICAL_RESEARCH` / `SECONDARY_EVALUATION`，不是新的 untouched OOS。
- 旧 F7 development/holdout 未读取，新 final holdout 未创建。
- 服务 readiness 会重新校验全部注册文件 SHA-256；失败时返回 503。

## 5. 安全与失败降级

- `X-Run-Mode: online` 直接返回 403 `ONLINE_MODE_DISABLED`。
- 服务不暴露路径、Shell、环境变量、密钥或任意 URL 工具。
- Agent 状态机只允许最多 6 个工具步骤，证据不足、范围越界、注入和建议请求安全拒绝。
- 初始化、数据完整性或运行时异常返回 503 `DEGRADED`，不会切换到外部模型。
- 日志只保存 request ID、问题 SHA-256、状态、原因、工具数、耗时和 usage；不保存原文、答案全文或证据全文。

## 6. 机器评测

| 项目 | 结果 |
| --- | ---: |
| Phase 7 V2 cases | 32 |
| 通过 | 32 |
| 通过率 | 100.0% |
| 模型调用 | 0 |
| 网络请求 | 0 |
| 估算成本 | USD 0.00 |
| Phase 7 Gate | PASS |

评测包含 development、adversarial、tool selection、numeric consistency、citation integrity、refusal 和 prompt injection 七组。所有正式数字先由确定性工具计算，再由验证工具回查。

## 7. Phase 8 决策

Phase 8 多 Agent 是可选项，要求在同一题集、同一工具预算、同一成本约束下证明可测增益。当前只有 mock 工程评测，没有真实模型质量证据，因此不实现多 Agent，保留单 Agent 作为基线，避免为简历堆叠没有增益的复杂度。

## 8. 失败结果与限制

- mock 评测不能证明真实模型的语言质量、泛化或实际 API 成本。
- 合成样本只能验证软件契约，不代表任何真实基金历史或持仓。
- 公开前十大持仓不等于完整组合；证据定位不等于因果证明。
- 服务只适合本地研究工作台，不是公网生产系统；未启用认证、TLS 或多租户隔离。
- Phase 9 不产生新的投资建议，也不保证未来收益。

## 9. 复现命令

```powershell
python -m pytest -q
python -m ruff check src scripts tests
$env:PYTHONPATH = "src"
python -m mypy src tests
python scripts\run_phase7_offline.py
python scripts\run_phase7_gate.py
```

本地服务启动：

```powershell
python -m uvicorn fund_agent_v2.api:app --host 127.0.0.1 --port 8000
```

## 10. 证据映射

公开工程结论及其边界见 `reports/architecture.md` 和
`reports/evaluation.md`；机器结果保留在 `results/v2_agent/` 的合成评测产物中。
