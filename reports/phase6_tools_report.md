# Phase 6 基金 Agent 确定性工具层报告

## 阶段结论

Phase 6 已实现十个受限确定性工具。工具层可以读取预注册基金资料、重算净值指标、比较公开前十大持仓、执行离线 TF-IDF 检索、核对本地官方来源 manifest、验证引用与数字，并在人工批准后导出 Markdown Memo。本阶段没有接入 LLM、OpenAI API、真实网络或付费服务。

## 数据与研究边界

- 数据配置：`demo_synthetic`，包含 3 只虚构基金和 4 个合成报告期。
- NAV 样本共同窗口：2026-01-05 至 2026-04-24，共 80 个观测。
- 文档内容、基金代码、净值、持仓和 URL 均为确定性生成的合成数据。
- 核心确定性计算源码与注册合成数据均以 SHA-256 校验。
- 旧 F7 holdout 状态为 `FROZEN_DO_NOT_READ`，本阶段未读取、未运行、未用于设计。

## 工具与权限

十个工具均使用 `extra=forbid` 与 strict Pydantic schema；调用由统一运行时执行 allowlist、超时、错误分类和脱敏审计。工具输入不包含路径、Shell、环境变量或密钥字段。`fetch_official_source` 的结果模式为 `LOCAL_MANIFEST_ONLY`，网络请求数为 0。

正式导出具有双重约束：文件名必须通过安全格式校验，目标目录固定在 V2 输出根；同时必须提供人工批准、审批人和审批编号。冒烟测试中的未批准导出结果为 `APPROVAL_REQUIRED`。

## 数值一致性

净值收益、年化波动率和最大回撤均从 `nav_daily.csv` 的共同日期窗口重算；C10、HHI10、NameJaccard 与 CommonNAVShare 均从同报告期的公开前十大持仓重算。数值验证工具不接受调用方提供的参考结果，而是回查注册数据。冒烟测试数值验证为 `all_valid=True`。

## 引用与检索

检索保留 V1 中文字符 2-4 gram TF-IDF 确定性基线。检索结果按基金和报告期强制过滤，并标记为不可信内容。引用验证同时核对 URL、doc_id、基金、报告期、物理页、chunk、文本哈希、页面哈希与 PDF 哈希。冒烟测试引用验证为 `all_valid=True`。

证据表只确认“引用可定位且摘录为原文精确子串”，不会把文本相关性包装成语义蕴含或因果证明。PDF 或网页内出现的提示词被视为普通不可信数据，不能改变权限。

## 审计与错误

本次冒烟流程共产生 10 条审计事件，其中 9 条成功、1 条预期拒绝。审计只保存请求 ID、工具名、时间、耗时、状态以及输入/输出 SHA-256，不保存查询原文、证据全文或密钥。

错误分为 `INVALID_INPUT`、`POLICY_VIOLATION`、`NOT_FOUND`、`DATA_INTEGRITY`、`TIMEOUT`、`APPROVAL_REQUIRED` 与 `INTERNAL_ERROR`。Phase 6 仅把超时标为可重试。

## 限制与下一阶段 Gate

- 本阶段不是 Agent，只是 Agent 将来可调用的确定性工具层。
- 本阶段没有真实网页抓取；所谓官方来源获取只是本地 manifest/cache 定位。
- 本阶段没有语义模型、Embedding、BM25、reranker 或自动 Judge。
- 合成样本只能验证软件契约，不能证明真实基金研究质量。
- 未产生新的 holdout 结果，也没有 post-freeze forward 证据。

只有用户明确批准 Phase 7 后，才可根据当前官方文档核对 API、接入单 Agent，并创建新的开发与对抗评测。真实 API 调用仍需另行显式授权。
