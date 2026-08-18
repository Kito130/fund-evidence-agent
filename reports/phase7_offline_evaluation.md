# Phase 7 单 Agent 离线评测报告

## 阶段结论

本阶段在 Phase 6 十个确定性工具之上实现了一个单 Agent，并使用全新 V2 题集执行确定性 mock 评测。共 32 个用例，通过 32 个，通过率 100.0%。失败用例：无。

这不是大模型质量评测。mock 运行只证明状态机、工具路由、参数范围、数字回算、引用定位、拒答策略、提示注入防御以及审计链能够在离线条件下按冻结规则工作，不能证明真实模型的语言质量或泛化能力。

## 分组结果

| 评测集 | 通过 | 总数 | 通过率 |
| --- | ---: | ---: | ---: |
| adversarial | 4 | 4 | 100.0% |
| citation_integrity | 4 | 4 | 100.0% |
| development | 5 | 5 | 100.0% |
| numeric_consistency | 4 | 4 | 100.0% |
| prompt_injection | 5 | 5 | 100.0% |
| refusal | 5 | 5 | 100.0% |
| tool_selection | 5 | 5 | 100.0% |

## 安全与证据边界

- 单次最多 6 个工具步骤；离线单例延迟门槛为 2000 ms。
- 数值回答必须经过 `validate_numeric_claims` 回查注册数据。
- 文档回答必须依次完成检索、引用完整性验证和原文精确定位。
- 个性化投资建议、未来收益保证、伪造证据、密钥/文件/命令请求、工具预算滥用和 Prompt Injection 均在调用工具前拒绝。
- 本地 trace 已脱敏，不保存原始问题、回答或证据全文。
- 正式 Memo 导出仍需外部人工审批，本阶段没有导出。

## 成本、网络与 Holdout

- 模型调用：0
- 网络请求：0
- Token：0
- 估算成本：USD 0.00
- 旧 F7 holdout 读取次数：0
- 新 final holdout 打开次数：0

所有题目均为全新 V2 development/adversarial 工程评测题。旧 F7 development 与 holdout 没有读取、复制或运行；本阶段也没有创建 final holdout。

## 在线 Gate

候选在线配置已冻结为 Responses API、官方 Python Agents SDK、`gpt-5.6-terra`、`reasoning.effort=medium`、`text.verbosity=medium`、`store=false`、串行工具调用和 SDK tracing 关闭。真实 API 评测尚未运行，必须同时满足用户单独明确授权和环境变量 `OPENAI_API_KEY`，并继续遵守 USD 1.00 单请求成本上限。
