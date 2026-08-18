# Phase 6 Gate 报告

**结论：PASS**

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 阶段与旧 Holdout 边界 | PASS | old_holdout_read_count=0 |
| LLM、网络与付费 API 关闭 | PASS | llm=0, network=0, paid_api=0 |
| 十个工具完整注册 | PASS | tools=10 |
| 严格输入输出 Schema | PASS | 10 inputs + 10 outputs |
| 无任意文件、命令或密钥参数 | PASS | forbidden_fields=[] |
| 核心算法与注册数据哈希 | PASS | all protected inputs match |
| Phase 6 产物哈希 | PASS | outputs=4 |
| Phase 6 源码哈希 | PASS | sources=12 |
| 无网络与 Shell 实现能力 | PASS | forbidden_imports=[], forbidden_calls=False |
| NAV 数值一致性 | PASS | 80 common observations |
| 持仓数值一致性 | PASS | Jaccard=1/3, CommonNAVShare=0.133 |
| 离线检索范围与不可信标记 | PASS | top_chunk=SYN001_2026Q1_p001_c001 |
| 官方来源仅本地 Manifest | PASS | example.invalid |
| 引用完整性 | PASS | checks=13 |
| 证据表精确定位 | PASS | exact excerpts only |
| 数字声明回查 | PASS | 2/2 verified |
| Prompt Injection 识别 | PASS | ignore_instructions, secret_exfiltration, tool_escalation |
| 人工审批导出 Gate | PASS | unapproved export rejected |
| 十工具脱敏审计 | PASS | 10 events, hashes only |
| 中文报告与限制披露 | PASS | reports/phase6_tools_report.md |

Phase 6 未读取旧 F7 holdout，未调用 LLM、网络或付费 API。
Gate 通过后必须停止，等待用户明确批准 Phase 7。
