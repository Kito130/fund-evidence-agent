# 证据约束型基金研究 Agent

本项目将基金研究拆成三个可审计问题：哪些数字可以从登记表格确定性计算，哪些文本
结论有页码和片段支持，以及证据不足或请求越界时是否应该拒答。公开版本使用完全
合成数据和确定性 `MOCK_ONLY` 路由，用于验证工具、证据和安全契约，不代表真实 LLM
质量、真实基金事实或投资建议。

英文主文档：[README.md](README.md)

## 项目概览

| 模块 | 实现 | 公开证据 |
| --- | --- | --- |
| 基金诊断 | 净值收益、波动、回撤，公开前十大集中度、重合和行业变化 | 三只合成基金、四个虚构报告期 |
| 证据检索 | 中文 2-4 字符 gram TF-IDF，基金/报告期过滤，页码、片段和哈希核验 | 已登记合成 chunk 和确定性索引 |
| Agent 运行时 | 意图路由、十个白名单工具、严格 Schema、数字/引用校验和拒答 | 七组 32 个固定离线案例 |
| 服务层 | FastAPI、请求 ID、健康/就绪检查、指标和安全降级 | 本地 loopback Docker 服务 |

## 公开边界

默认运行时只使用 `SYN001`、`SYN002`、`SYN003`，净值、持仓、文本、哈希和
`.invalid` URL 均为虚构。运行过程不调用模型和网络，也不需要 API Key。它证明的是
确定性路由、工具和证据控制，不能证明真实模型推理、语义检索泛化、生产能力或真实
基金表现。逐文件分类见 [data/DATA_MANIFEST.md](data/DATA_MANIFEST.md)。

## 系统设计

```text
登记后的合成文件
        |
        +--> 确定性基金指标
        |
        +--> 限定范围的 TF-IDF 检索 --> 页码、chunk、哈希核验
                                        |
                                        v
                              有界 Agent 状态机
                                        |
                         ANSWERED / REFUSED / DEGRADED
                                        |
                          FastAPI + 脱敏审计指标
```

单次请求最多执行六步工具。工具调用前会拒绝个性化投资建议、收益保证、伪造证据、
密钥/文件/命令请求、Prompt Injection 和工具预算滥用。数字结论必须从已登记 CSV
重新计算；文本证据必须通过基金、报告期、相关性门槛、页码、chunk 和来源哈希校验。
`0.31` 只是当前语料的词面相关性门槛，不是置信概率。

详细架构见 [reports/architecture.md](reports/architecture.md)，运行契约见
[docs/agent_runtime.md](docs/agent_runtime.md)。

## 已验证 API 示例

请求：

```json
{"query":"请计算SYN001的净值指标。"}
```

响应核心字段：

```json
{
  "status": "ANSWERED",
  "answer": "SYN001 累计收益 0.094260，年化波动 0.061029，最大回撤 -0.066125",
  "reason_codes": ["NUMERICALLY_VERIFIED"],
  "usage": {
    "model_calls": 0,
    "network_requests": 0,
    "estimated_cost_usd": 0.0
  }
}
```

证据不足或请求不安全时，系统返回 `REFUSED` 和机器可读原因码，而不是扩写结论。

## 离线评测

固定题集共 32 例：adversarial 4、citation integrity 4、development 5、numeric
consistency 4、prompt injection 5、refusal 5、tool selection 5。当前确定性合成语料
结果为 32/32，模型调用、网络请求、Token 和 API 成本均为零；旧 holdout 读取为零，
也没有创建新的最终 holdout。

这些结果只验证既定路由、Schema、数字复算、引用完整性、拒答和注入阻断，不证明
任意问题上的泛化或语言质量。详见 [reports/evaluation.md](reports/evaluation.md)。

## 本地运行

```powershell
python -m pip install -e ".[dev]"
python scripts/run_pipeline.py --profile demo_synthetic
python -m pytest -q
```

启动 API：

```powershell
$env:FUND_AGENT_MODE = "MOCK_ONLY"
python -m uvicorn fund_agent_v2.api:app --app-dir src --host 127.0.0.1 --port 8000
```

Docker 验证：

```powershell
docker compose up --build --wait
python scripts/run_container_smoke.py
docker compose down
```

容器使用非 root 用户、只读文件系统和合成数据挂载、移除 Linux capabilities，并只
绑定本机回环地址。

## 目录

- `src/`：确定性基金分析与 Agent 运行时；
- `configs/`：运行、工具和评测契约；
- `data/demo_synthetic/`：可复现的合成登记表与数据；
- `eval/`：固定确定性评测案例；
- `tests/`：分析、安全、API 和运行时测试；
- `scripts/`：数据准备、评测和服务入口；
- `reports/`：架构、评测、限制和演示指南。

## 主要限制

- 字符 gram TF-IDF 是词面检索，不是语义 RAG；
- 小规模固定题集不能证明任意问题上的泛化；
- 公开前十大持仓不能代表完整组合暴露；
- 可选在线适配器默认关闭，公开版本没有真实 LLM 质量评测；
- 系统不提供实时数据、预测、交易信号、个性化建议或线上部署。

数据权利见 [DATA_LICENSE.md](DATA_LICENSE.md)，完整限制见
[reports/limitations.md](reports/limitations.md)。源代码使用 [MIT License](LICENSE)，
不覆盖基金文档、市场数据、供应商响应或商标。
