"""Two-page offline Streamlit interface for the public research demo."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.dashboard import (
    DEFAULT_PROFILE,
    PAGE_LABELS,
    PROJECT_ROOT,
    PROFILE_LABELS,
    available_periods,
    available_profiles,
    correlation_matrix,
    drawdown_chart_frame,
    fund_labels,
    holding_snapshot,
    industry_change_snapshot,
    load_dashboard_data,
    load_research_engine,
    nav_chart_frame,
    nav_metric_snapshot,
    overlap_snapshot,
    profile_metadata,
    public_evaluation_summary,
    research_scope,
    run_research_query,
    validate_f7_gate,
)
from src.memo import REFUSAL_MESSAGE, SYSTEM_NAME


APP_TITLE = "证据可追溯的公募基金研究台"


def _configure_page() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="◫",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        :root {
          --ink: #132a2b;
          --muted: #5b6d6d;
          --accent: #087e72;
          --paper: #f6f5ef;
          --line: #dce3df;
        }
        .stApp {
          background:
            radial-gradient(circle at 92% 0%, #dcece7 0, transparent 28rem),
            var(--paper);
          color: var(--ink);
        }
        [data-testid="stSidebar"] {
          background: #102f31;
        }

        /* 仅给侧栏普通文本使用浅色，避免污染浅色输入组件。 */
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] small {
          color: #eef5f2;
        }

        /* Selectbox 使用浅色背景和深色文字。 */
        [data-testid="stSidebar"]
        [data-testid="stSelectbox"]
        div[data-baseweb="select"] > div {
          background-color: #f6f5ef !important;
          border-color: #087e72 !important;
        }

        [data-testid="stSidebar"]
        [data-testid="stSelectbox"]
        div[data-baseweb="select"],
        [data-testid="stSidebar"]
        [data-testid="stSelectbox"]
        div[data-baseweb="select"] * {
          color: #132a2b !important;
          -webkit-text-fill-color: #132a2b !important;
          opacity: 1 !important;
        }

        [data-testid="stSidebar"]
        [data-testid="stSelectbox"]
        div[data-baseweb="select"] svg {
          color: #132a2b !important;
          fill: #132a2b !important;
        }

        /* 展开后的下拉选项。 */
        div[data-baseweb="popover"] [role="option"],
        div[data-baseweb="popover"] [role="option"] * {
          color: #132a2b !important;
          -webkit-text-fill-color: #132a2b !important;
          opacity: 1 !important;
        }
        .hero {
          border: 1px solid var(--line);
          border-radius: 22px;
          padding: 1.6rem 1.8rem;
          background: rgba(255,255,255,.76);
          box-shadow: 0 18px 46px rgba(19,42,43,.08);
          margin-bottom: 1.2rem;
        }
        .eyebrow {
          color: var(--accent);
          font-size: .76rem;
          font-weight: 750;
          letter-spacing: .14em;
          text-transform: uppercase;
        }
        .hero h1 {
          color: var(--ink);
          font-size: clamp(2rem, 4vw, 3.7rem);
          letter-spacing: -.045em;
          line-height: 1.02;
          margin: .42rem 0 .7rem;
          max-width: 900px;
        }
        .hero p {
          color: var(--muted);
          font-size: 1rem;
          line-height: 1.75;
          margin: 0;
          max-width: 900px;
        }
        .status-pill {
          display: inline-block;
          margin-top: 1rem;
          padding: .38rem .72rem;
          border-radius: 999px;
          background: #dff2eb;
          color: #09675f;
          font-size: .78rem;
          font-weight: 700;
        }
        [data-testid="stMetric"] {
          background: rgba(255,255,255,.78);
          border: 1px solid var(--line);
          border-radius: 16px;
          padding: .85rem 1rem;
        }
        div[data-testid="stDataFrame"] {
          border: 1px solid var(--line);
          border-radius: 14px;
          overflow: hidden;
        }
        div[data-testid="stExpander"] {
          background: rgba(255,255,255,.62);
          border-color: var(--line);
          border-radius: 14px;
        }
        .boundary {
          border-left: 4px solid #d4a72c;
          background: #fff8df;
          padding: .9rem 1rem;
          border-radius: 0 12px 12px 0;
          color: #554510;
          line-height: 1.65;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def _f7_gate() -> dict[str, Any]:
    return validate_f7_gate(PROJECT_ROOT)


@st.cache_data(show_spinner=False)
def _dashboard_data(profile: str) -> dict[str, pd.DataFrame]:
    return load_dashboard_data(PROJECT_ROOT, profile=profile)


@st.cache_resource(show_spinner=False)
def _research_engine(
    profile: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return load_research_engine(PROJECT_ROOT, profile=profile)


def _hero(kicker: str, title: str, body: str, status: str) -> None:
    st.markdown(
        f"""
        <section class="hero">
          <div class="eyebrow">{kicker}</div>
          <h1>{title}</h1>
          <p>{body}</p>
          <span class="status-pill">{status}</span>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_diagnostics(
    bundle: dict[str, pd.DataFrame],
    gate: dict[str, Any],
    *,
    profile: str,
    metadata: dict[str, Any],
) -> None:
    if profile == "demo_synthetic":
        status = "完全合成 · 默认公开演示"
    elif profile == "sample_real":
        status = "短片段真实样例 · 不含完整 PDF"
    else:
        status = "F1–F8 已审计 · 私有本地"
    _hero(
        "PAGE 01 · DIAGNOSTICS",
        "基金与组合诊断",
        "把净值路径、风险、公开持仓结构与行业披露放在同一视图中。"
        "所有指标均读取已审计的本地结果，不在界面中重新定义研究口径。",
        status,
    )

    nav = bundle["nav"]
    date_values = pd.to_datetime(nav["date"])
    fund_count = int(nav["fund_code"].nunique())
    report_count = int(bundle["manifest"]["doc_id"].nunique())
    common_observations = int(
        nav.groupby("fund_code")["date"].nunique().min()
    )
    holdout_value = gate.get("holdout_end_to_end")
    metric_columns = st.columns(4)
    metric_columns[0].metric("研究基金", f"{fund_count} 只")
    metric_columns[1].metric("文档样本", f"{report_count} 份")
    metric_columns[2].metric(
        "共同净值窗口",
        f"{date_values.min():%Y-%m-%d}",
        f"至 {date_values.max():%Y-%m-%d}",
    )
    metric_columns[3].metric(
        "一次性保留题",
        f"{holdout_value}/5" if holdout_value is not None else "未附带",
        "历史审计仅运行 1 次",
    )
    st.caption(
        f"数据版本：{metadata.get('dataset_version', profile)}；"
        f"当前模式共 {common_observations} 个共同净值观察日。"
    )

    nav_tab, holdings_tab, industry_tab = st.tabs(
        ("净值与风险", "公开持仓结构", "行业变化")
    )

    with nav_tab:
        left, right = st.columns((1.7, 1), gap="large")
        with left:
            st.subheader("累计净值")
            st.caption(
                f"{fund_count} 只基金的 {common_observations} 个共同观察日；"
                "不填充日历空档。"
            )
            st.line_chart(nav_chart_frame(nav), height=360)
        with right:
            st.subheader("区间风险摘要")
            st.dataframe(
                nav_metric_snapshot(bundle["nav_metrics"]),
                hide_index=True,
                width="stretch",
                column_config={
                    "区间累计变化(%)": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                    "年化波动率(%)": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                    "最大回撤(%)": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                },
            )

        st.subheader("动态回撤")
        st.caption("口径：当日累计净值 ÷ 历史峰值 − 1，单位为百分比。")
        st.line_chart(drawdown_chart_frame(nav), height=280)

        st.subheader("收益相关性")
        paired = int(
            pd.to_numeric(
                bundle["correlation"]["paired_observations"],
                errors="raise",
            ).min()
        )
        st.caption(
            f"基于共同窗口内 {paired} 个相邻实际观察日简单收益。"
        )
        st.dataframe(
            correlation_matrix(bundle["correlation"]).round(3),
            width="stretch",
        )

    with holdings_tab:
        periods = available_periods(bundle)
        selected_period = st.selectbox(
            "报告期",
            periods,
            index=len(periods) - 1,
            key="diagnostics_period",
        )
        left, right = st.columns((1, 1.4), gap="large")
        with left:
            st.subheader("C10 与 HHI10")
            st.dataframe(
                holding_snapshot(
                    bundle["holding_metrics"],
                    selected_period,
                ),
                hide_index=True,
                width="stretch",
                column_config={
                    "C10 (%)": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                    "HHI10": st.column_config.NumberColumn(
                        format="%.4f"
                    ),
                },
            )
        with right:
            st.subheader("公开前十大重合")
            st.dataframe(
                overlap_snapshot(bundle["overlap"], selected_period),
                hide_index=True,
                width="stretch",
                column_config={
                    "NameJaccard (%)": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                    "CommonNAVShare (%)": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                },
            )
        with st.expander("指标口径"):
            st.markdown(
                """
                - **C10**：公开前十大持仓占基金净值比例之和。
                - **HHI10**：前十大内部标准化权重的平方和。
                - **NameJaccard**：两只基金公开前十大名称交集占并集的比例。
                - **CommonNAVShare**：共同股票的两基金 NAV 权重取较小值后求和。
                """
            )

    with industry_tab:
        labels = fund_labels(bundle)
        left, right = st.columns((1, 1), gap="large")
        with left:
            industry_fund = st.selectbox(
                "基金",
                list(labels),
                format_func=labels.get,
                key="industry_fund",
            )
        periods = available_periods(bundle)
        with right:
            industry_period = st.selectbox(
                "本期报告",
                periods[1:],
                index=len(periods[1:]) - 1,
                key="industry_period",
            )
        comparison = industry_change_snapshot(
            bundle["industry"],
            fund_code=industry_fund,
            current_period=industry_period,
        )
        st.subheader(
            f"{comparison['previous_period']} → "
            f"{comparison['current_period']} 行业披露变化"
        )
        st.caption(
            "报告表空白保持为空白，不擅自填零；变化值只对连续披露的数值计算。"
        )
        st.dataframe(
            comparison["table"],
            hide_index=True,
            width="stretch",
            column_config={
                "上期(%)": st.column_config.NumberColumn(format="%.2f"),
                "本期(%)": st.column_config.NumberColumn(format="%.2f"),
                "变化(百分点)": st.column_config.NumberColumn(
                    format="%+.2f"
                ),
            },
        )

    st.markdown(
        """
        <div class="boundary">
          <strong>披露边界：</strong>
          持仓比较仅覆盖季报公开前十大，不代表完整持仓重合；行业表空白不自动解释为零。
          净值与文本相关性均不构成收益预测、投资建议或未公开意图判断。
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_evidence_cards(cards: list[dict[str, Any]]) -> None:
    st.subheader(f"Top-{len(cards)} 证据卡")
    if not cards:
        st.info("所选范围内没有可展示的检索结果。")
        return
    for card in cards:
        citation = card["citation"]
        document_name = (
            f"{citation['fund_name']} {citation['period']} 季度报告"
        )
        with st.container(border=True):
            top = st.columns((3, 1))
            top[0].markdown(
                f"**证据 {card['rank']}｜{document_name}**"
            )
            top[1].metric("余弦相似度", f"{card['score']:.4f}")
            st.caption(
                f"文档：{citation['doc_id']}　｜　"
                f"PDF 物理页：{citation['physical_page']}　｜　"
                f"Chunk：{citation['chunk_id']}"
            )
            file_url = str(citation.get("file_url", ""))
            if file_url.startswith("https://"):
                st.markdown(f"[打开官方 PDF]({file_url})")
            else:
                st.caption("合成文档：无外部 PDF。")
            with st.expander("查看本地证据正文"):
                st.write(card["evidence_text"])
                st.caption(
                    f"文本 SHA-256：{citation['text_hash']}"
                )


def _render_research(profile: str) -> None:
    _hero(
        "PAGE 02 · EVIDENCE",
        "研究证据与 Memo",
        "先限定基金与报告期，再检索本地官方文档。回答只能引用命中的物理页；"
        "证据不足时严格拒答。",
        SYSTEM_NAME,
    )
    index, chunks = _research_engine(profile)
    funds, periods = research_scope(chunks)
    fund_labels_map = {
        code: f"{code}｜{name}" for code, name in funds.items()
    }

    selection_columns = st.columns((1.35, 1, 0.65), gap="large")
    with selection_columns[0]:
        fund_code = st.selectbox(
            "选择基金",
            list(funds),
            format_func=fund_labels_map.get,
        )
    with selection_columns[1]:
        period = st.selectbox(
            "选择报告期",
            periods,
            index=len(periods) - 1,
        )
    with selection_columns[2]:
        top_k = st.select_slider(
            "证据卡数量",
            options=(1, 2, 3),
            value=3,
        )

    scope_key = (fund_code, period, top_k)
    stored = st.session_state.get("research_result")
    if stored and stored.get("scope_key") != scope_key:
        del st.session_state["research_result"]

    with st.form("research_form", clear_on_submit=False):
        query = st.text_area(
            "输入研究问题",
            placeholder="例如：基金管理人如何描述本季度的市场环境？",
            height=110,
        )
        submitted = st.form_submit_button(
            "检索并生成 Memo",
            type="primary",
            width="stretch",
        )
    if submitted:
        try:
            with st.spinner("正在检索本地文档并核验证据……"):
                payload = run_research_query(
                    query,
                    fund_code=fund_code,
                    period=period,
                    top_k=top_k,
                    index=index,
                    chunks=chunks,
                )
            st.session_state["research_result"] = {
                **payload,
                "scope_key": scope_key,
            }
        except ValueError as exc:
            st.warning(str(exc))

    result = st.session_state.get("research_result")
    if not result:
        st.info(
            "请选择范围并输入问题。问题只在当前本地会话中处理，不写入日志或项目文件。"
        )
    else:
        st.divider()
        _render_evidence_cards(result["cards"])
        st.divider()
        memo = result["memo"]
        st.subheader("模板化 Memo")
        if memo["status"] == "REFUSED":
            st.warning(REFUSAL_MESSAGE)
        else:
            st.success(
                f"已通过证据门槛，引用 {len(memo['citations'])} 张证据卡。"
            )
            st.markdown(memo["markdown"])
        markdown = memo["markdown"]
        if not markdown.endswith("\n"):
            markdown += "\n"
        st.download_button(
            "导出 Markdown",
            data=markdown.encode("utf-8"),
            file_name=f"{fund_code}_{period}_memo.md",
            mime="text/markdown",
            width="stretch",
        )

    st.markdown(
        """
        <div class="boundary">
          <strong>系统边界：</strong>
          本页是离线 TF-IDF 检索与模板化 Memo，不是完整 LLM RAG。
          检索分数只代表文本相关性；输出不构成投资建议或收益预测。
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _configure_page()
    profiles = available_profiles(PROJECT_ROOT)
    if DEFAULT_PROFILE not in profiles:
        st.error("默认合成演示数据缺失，请先运行数据准备脚本。")
        st.stop()
    with st.sidebar:
        st.markdown("## FUND TRACE")
        st.caption("Local research console")
        profile = st.selectbox(
            "数据模式",
            profiles,
            index=profiles.index(DEFAULT_PROFILE),
            format_func=PROFILE_LABELS.get,
        )
        page = st.radio(
            "页面",
            PAGE_LABELS,
            label_visibility="collapsed",
        )
    try:
        gate = (
            _f7_gate()
            if profile == "local_full"
            else public_evaluation_summary(PROJECT_ROOT)
        )
        bundle = _dashboard_data(profile)
        metadata = profile_metadata(profile, PROJECT_ROOT)
    except (OSError, ValueError) as exc:
        st.error(f"数据输入闸门未通过：{exc}")
        st.stop()

    with st.sidebar:
        st.divider()
        st.caption(
            "本地运行 · 无外部模型 · 不上传私有 PDF\n\n"
            f"当前数据：{PROFILE_LABELS[profile]}\n\n"
            f"F7 holdout：{gate.get('holdout_end_to_end')}/5"
        )

    if page == PAGE_LABELS[0]:
        _render_diagnostics(
            bundle,
            gate,
            profile=profile,
            metadata=metadata,
        )
    else:
        _render_research(profile)


if __name__ == "__main__":
    main()
