# 数据许可与来源说明

本文件说明仓库内演示数据的来源和使用边界，不改变原始资料权利人的权利，也不构成
法律意见。

## `data/demo_synthetic/`

该目录由 `scripts/prepare_demo_data.py` 确定性生成。基金、证券、净值、持仓、
行业配置、报告文本和 URL 均为虚构或使用 `.invalid` 保留域名，不对应真实产品、
账户或交易。

这些文件只用于运行、测试和展示本项目。它们不是市场数据，不应被用于投资决策，
也不得被描述为真实历史表现。

## 真实资料的处理

本仓库不包含 `data/sample_real/`、真实基金短摘录、完整 PDF 或完整页面文本。
公开可访问不等于允许再分发；因此这些资料统一分类为
`PRIVATE_OR_RESTRICTED_EXCLUDED` 或 `PUBLIC_SOURCE_LINK_ONLY`。历史研究报告仅保留
作者生成的汇总指标和方法说明，分类为 `DERIVED_AGGREGATE`，不替代原始来源。

逐文件分类见 `data/DATA_MANIFEST.md`。

## 不进入版本控制的数据

以下目录只供维护者本地研究，已由 `.gitignore` 排除：

- `data/private_pdf/`：完整官方 PDF；
- `data/curated/`：真实结构化全量表和原始响应；
- `data/processed/`：完整页文本、chunk、索引、Memo 及其他派生缓存；
- `data/raw/`：任何临时原始下载。

不得把上述文件复制到公开样例目录或 Git 历史中。任何 Token、API Key、账户凭证、
`.env`、本地 secrets 和日志同样不得提交。

## 责任边界

公开数据可能存在披露口径、更新时间、抽样和人工整理误差。哈希只证明本项目内部
使用的文件或文本版本，没有赋予原始资料再分发权。所有输出仅供研究与工程演示，
不构成投资建议、招揽或收益承诺。
