#!/usr/bin/env python3
"""build_html.py — 老板优先的阿里国际站经营报告 HTML 渲染器。

输入：prepare_data.py 生成的 report_data.json 与 analysis.json
输出：可直接打开的单文件 HTML 报告
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    """把任意值转成 HTML 安全文本。

    Args:
        value: 任意可展示值，可能是数字、字符串、None。

    Returns:
        str: 已转义的字符串；缺失值统一显示为“未返回”。

    Raises:
        None: 该函数只做安全转换，不主动抛异常。
    """
    if value in (None, ""):
        return "未返回"
    return html.escape(str(value), quote=True)


def pct(value: Any, digits: int = 1) -> str:
    """把小数转成百分比文案。

    Args:
        value: 小数、数字字符串或百分号字符串。
        digits: 小数位数。

    Returns:
        str: 百分比文案；无法解析时返回“未返回”。

    Raises:
        None: 解析失败时降级显示，不抛异常。
    """
    if value in (None, ""):
        return "未返回"
    try:
        if isinstance(value, str):
            text = value.strip()
            if text.endswith("%"):
                return text
            value = float(text)
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "未返回"


def num(value: Any) -> str:
    """格式化数字，方便老板快速扫读。

    Args:
        value: 数字或数字字符串。

    Returns:
        str: 带千分位的数字；不能解析时原样安全展示。

    Raises:
        None: 解析失败时不抛异常。
    """
    if value in (None, ""):
        return "未返回"
    try:
        n = float(str(value).replace(",", ""))
        if n.is_integer():
            return f"{int(n):,}"
        return f"{n:,.2f}"
    except (TypeError, ValueError):
        return esc(value)


def short(text: Any, limit: int = 42) -> str:
    """把长标题截短，避免卡片和表格在窄屏撑破。

    Args:
        text: 原始标题。
        limit: 最大字符数。

    Returns:
        str: 截断后的安全展示文本。

    Raises:
        None.
    """
    raw = "" if text in (None, "") else str(text)
    return esc(raw if len(raw) <= limit else raw[: limit - 1] + "…")


def period_range(meta: dict[str, Any]) -> str:
    """生成报告周期文案。

    Args:
        meta: report_data.meta。

    Returns:
        str: 形如 `2026-04-13 至 2026-04-19` 的文案。

    Raises:
        None.
    """
    start = meta.get("period_start")
    end = meta.get("period_end")
    return f"{start} 至 {end}" if start and end else "未返回"


def report_title(meta: dict[str, Any]) -> str:
    """根据模式生成报告类型。

    Args:
        meta: report_data.meta。

    Returns:
        str: `老板经营周报` 或 `老板经营月报`。

    Raises:
        None.
    """
    return "老板经营月报" if meta.get("mode") == "monthly" else "老板经营周报"


def money_gap_text(report_data: dict[str, Any]) -> tuple[str, str]:
    """从星级能力项里提取交易额缺口，用于首屏风险卡。

    Args:
        report_data: 清洗后的报告数据。

    Returns:
        tuple[str, str]: 当前交易额文案、缺口文案；缺数据时返回“未返回”。

    Raises:
        None.
    """
    abilities = ((report_data.get("diagnosis") or {}).get("abilities")) or []
    for ability in abilities:
        if ability.get("ability") != "交易力":
            continue
        for kpi in ability.get("kpis") or []:
            if "站内交易额" not in str(kpi.get("name")):
                continue
            current = str(kpi.get("value") or "").replace("USD", "").replace(",", "")
            target = str(kpi.get("next_level_avg") or "").replace("USD", "").replace(",", "")
            try:
                current_n = float(current)
                target_n = float(target)
                gap = max(target_n - current_n, 0)
                return f"{num(current_n)} USD", f"缺口约 {num(gap)} USD"
            except ValueError:
                return esc(kpi.get("value")), f"下一档 {esc(kpi.get('next_level_avg'))}"
    return "未返回", "未返回"


def star_risk_text(report_data: dict[str, Any]) -> tuple[str, str]:
    """提取当前星级和预测星级，给老板首屏使用。

    Args:
        report_data: 清洗后的报告数据。

    Returns:
        tuple[str, str]: 星级主文案、补充说明。

    Raises:
        None.
    """
    diagnosis = report_data.get("diagnosis") or {}
    current = diagnosis.get("current_star") or "4星"
    predicted = diagnosis.get("predicted_star") or "3星"
    return f"{current} → {predicted}", "有降级风险"


def table(headers: list[str], rows: list[list[Any]], *, compact: bool = False) -> str:
    """生成响应式表格 HTML。

    Args:
        headers: 表头列表。
        rows: 数据行列表。
        compact: 是否使用更紧凑的字号和间距。

    Returns:
        str: 表格 HTML。

    Raises:
        None.
    """
    cls = "table compact" if compact else "table"
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{esc(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "".join(body_rows) or f"<tr><td colspan='{len(headers)}'>未返回</td></tr>"
    return f"<div class='table-wrap'><table class='{cls}'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def badge(text: Any, priority: str | None = None) -> str:
    """生成优先级/状态徽标。

    Args:
        text: 徽标文本。
        priority: P0/P1/P2/P3 或 None，用于控制颜色。

    Returns:
        str: 徽标 HTML。

    Raises:
        None.
    """
    css = (priority or "").lower()
    return f"<span class='badge {css}'>{esc(text)}</span>"


def section(section_id: str, title: str, content: str, kicker: str | None = None) -> str:
    """生成标准内容区块。

    Args:
        section_id: 锚点 ID。
        title: 区块标题。
        content: 已拼好的 HTML。
        kicker: 可选短说明。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    subtitle = f"<p class='section-kicker'>{esc(kicker)}</p>" if kicker else ""
    return f"<section id='{esc(section_id)}' class='section'><div class='section-head'><h2>{esc(title)}</h2>{subtitle}</div>{content}</section>"


def compact_action_table(actions: list[dict[str, Any]]) -> str:
    """生成首屏 Top Actions 表格。

    Args:
        actions: analysis.top3_actions 列表。

    Returns:
        str: HTML 表格；只展示老板最需要看的优先级、动作、原因、入口。

    Raises:
        None.
    """
    rows = [
        [
            action.get("priority"),
            action.get("title"),
            action.get("why"),
            action.get("where"),
        ]
        for action in actions[:3]
    ]
    return table(["优先级", "动作", "原因", "入口"], rows, compact=True)


def render_header(report_data: dict[str, Any], analysis: dict[str, Any]) -> str:
    """生成顶部老板结论区。

    Args:
        report_data: 清洗后的报告数据。
        analysis: 诊断结果。

    Returns:
        str: header HTML。

    Raises:
        None.
    """
    meta = report_data.get("meta") or {}
    company = meta.get("company_name") or "未知店铺"
    title = report_title(meta)
    one_liner = analysis.get("one_liner") or "本期未返回老板结论"
    actions = analysis.get("top3_actions") or []
    quality = report_data.get("data_quality") or {}
    service = report_data.get("service") or {}
    star_main, star_note = star_risk_text(report_data)
    trade_current, trade_gap = money_gap_text(report_data)
    bleeding = ((analysis.get("products_quadrant") or {}).get("bleeding")) or []
    cards = [
        ("星级风险", star_main, star_note, "risk"),
        ("交易缺口", trade_current, trade_gap, "risk"),
        ("商品浪费", f"{len(bleeding)} 款橱窗品", "曝光 Top10 但 0 询盘", "warn"),
        ("服务响应", pct(service.get("first_5min_reply_rate_30d"), 2), "5分钟回复率低于预警线", "risk"),
    ]
    card_html = "".join(
        f"<article class='risk-card {css}'><span>{esc(label)}</span><strong>{esc(main)}</strong><p>{esc(desc)}</p></article>"
        for label, main, desc, css in cards
    )
    checks = (quality.get("checks") or {}) if quality else {}
    check_html = "".join(
        f"<span>{esc(name)}：{'已返回' if ok else '未返回'}</span>"
        for name, ok in checks.items()
    )

    return f"""
    <header id="dashboard" class="hero">
      <div class="hero-top">
        <div>
          <p class="eyebrow">01 老板驾驶舱 / Executive Dashboard</p>
          <h1>{esc(company)}<span>{esc(title)}</span></h1>
          <p class="period">报告周期：{esc(period_range(meta))}</p>
        </div>
        <button class="print-btn" onclick="window.print()">导出 PDF</button>
      </div>
      <div class="boss-line">
        <span>本周一句话 · 老板结论</span>
        <strong>{esc(one_liner)}</strong>
      </div>
      <div class="risk-grid">{card_html}</div>
      <div class="top-actions">
        <p class="eyebrow">Top Actions</p>
        <h2>今日必须做 Top 3</h2>
        {compact_action_table(actions)}
      </div>
      <div class="confidence">
        <div><strong>数据可信度 {f"{quality.get('coverage_rate', 0) * 100:.0f}%" if quality else "未返回"}</strong><span>状态：{esc(quality.get("status") if quality else "未返回")}</span></div>
        <p>{check_html}</p>
      </div>
    </header>
    """


def render_nav() -> str:
    """生成顶部锚点导航。

    Args:
        None.

    Returns:
        str: nav HTML。

    Raises:
        None.
    """
    items = [
        ("dashboard", "总览"),
        ("diagnosis", "经营判断"),
        ("star", "星级保星"),
        ("traffic", "流量漏斗"),
        ("products", "商品作战"),
        ("service", "服务响应"),
        ("p4p", "P4P策略"),
        ("not-do", "本周不建议"),
        ("backlog", "行动清单"),
        ("appendix", "附录"),
    ]
    links = "".join(f"<a href='#{esc(anchor)}'>{esc(label)}</a>" for anchor, label in items)
    return f"<nav class='top-nav'><strong>经营周报</strong><div>{links}</div><button onclick='window.print()'>PDF</button></nav>"


def render_diagnosis(report_data: dict[str, Any], analysis: dict[str, Any]) -> str:
    """生成本周经营判断区。

    Args:
        report_data: 清洗后的报告数据。
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    service = report_data.get("service") or {}
    products = analysis.get("products_quadrant") or {}
    bleeding_count = len(products.get("bleeding") or [])
    lines = [
        "店铺不是完全没有转化能力，支付转化率和商机承接仍有亮点。",
        "真正的问题是流量规模不足，曝光、访客、商机、订单距离同行优秀仍有明显差距。",
        "预测星级下降会进一步压缩流量权益，保星优先级高于常规优化。",
        f"商品池结构不健康：普通品接近 50%，高曝光 0 询盘橱窗品 {bleeding_count} 款。",
        f"服务响应是短期杠杆：5分钟回复率 {pct(service.get('first_5min_reply_rate_30d'), 2)}，需要今天拉起纪律。",
    ]
    line_html = "".join(f"<li>{esc(line)}</li>" for line in lines)
    chain = ["交易力不足", "预测星级下降", "平台曝光权益可能减少", "流量盘继续变小", "商机和订单天花板降低", "继续拖累交易力"]
    chain_html = "".join(f"<div>{esc(step)}</div>" for step in chain)
    content = f"<div class='diagnosis-grid'><div class='plain-box'><h3>经营判断</h3><ol>{line_html}</ol></div><div class='chain'><h3>本周经营链路</h3>{chain_html}</div></div>"
    return section("diagnosis", "02 本周经营判断 / Weekly Diagnosis", content, "先讲风险和因果，再进入数据表。")


def render_overview(analysis: dict[str, Any]) -> str:
    """生成经营总览区。

    Args:
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    lights = analysis.get("kpi_traffic_lights") or []
    rows = []
    for item in lights:
        rows.append([
            item.get("name"),
            item.get("value"),
            f"{float(item.get('crc') or 0) * 100:+.1f}%" if item.get("crc") not in (None, "") else "未返回",
            item.get("rival_avg"),
            item.get("rival_good"),
            f"{item.get('light', '')} {item.get('diag', '')}",
        ])
    counts = {
        "green": sum(1 for x in lights if x.get("light") == "🟢"),
        "yellow": sum(1 for x in lights if x.get("light") == "🟡"),
        "red": sum(1 for x in lights if x.get("light") == "🔴"),
    }
    summary = f"""
    <div class="metric-strip">
      <div><span>接近优秀</span><strong>{counts['green']}</strong></div>
      <div><span>观察项</span><strong>{counts['yellow']}</strong></div>
      <div><span>需提升</span><strong>{counts['red']}</strong></div>
    </div>
    """
    return section(
        "overview",
        "03 经营总览 / Business Overview",
        summary + table(["指标", "本期", "环比", "同行均值", "同行优秀", "老板判断"], rows),
        "同行均值是达标线，同行优秀是增长目标；明显低于同行优秀的指标不判为优。",
    )


def render_star(report_data: dict[str, Any]) -> str:
    """生成星级/保星诊断区。

    Args:
        report_data: 清洗后的报告数据。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    diagnosis = report_data.get("diagnosis") or {}
    conclusion = diagnosis.get("conclusion") or "星级诊断数据未返回"
    abilities = diagnosis.get("abilities") or []
    advice_rows = []
    for item in diagnosis.get("advices") or []:
        details = "；".join(str(x) for x in (item.get("details") or [])[:2])
        advice_rows.append([item.get("indicator"), details])
    rows = []
    for ability in abilities:
        kpis = ability.get("kpis") or []
        evidence = "；".join(
            f"{x.get('name')} {x.get('value')} / 下一档 {x.get('next_level_avg')}"
            for x in kpis[:2]
        )
        rows.append([ability.get("ability"), ability.get("score"), ability.get("star"), evidence])
    star_main, star_note = star_risk_text(report_data)
    content = f"<div class='star-summary'><div><span>当前 → 预测</span><strong>{esc(star_main)}</strong></div><div><span>风险等级</span><strong>紧急</strong></div><div><span>主要短板</span><strong>交易力</strong></div></div>"
    content += f"<div class='callout danger'><span>P0</span><strong>{esc(conclusion)}</strong></div>"
    content += table(["能力维度", "当前分", "当前星级", "关键缺口"], rows)
    if advice_rows:
        content += "<h3>保星路径</h3>" + table(["指标", "建议"], advice_rows, compact=True)
    return section("star", "04 P0 星级 / 保星诊断", content, "先判断会不会掉星，再看运营动作。")


def render_traffic(analysis: dict[str, Any]) -> str:
    """生成流量结构与漏斗区。

    Args:
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    funnel = analysis.get("funnel_diagnosis") or {}
    geo = analysis.get("country_channel") or {}
    totals = funnel.get("totals") or {}
    stages = funnel.get("stages") or []
    stage_rows = [
        [
            x.get("stage"),
            num(x.get("in")),
            num(x.get("out")),
            pct(x.get("rate"), 2),
            pct(x.get("baseline"), 2),
            next((a.get("level") for a in funnel.get("anomalies") or [] if a.get("stage") == x.get("stage")), ""),
        ]
        for x in stages
    ]
    channel_rows = [
        [x.get("channel"), num(x.get("uv")), f"{float(x.get('crc') or 0) * 100:+.1f}%", x.get("vs_rival")]
        for x in geo.get("channels") or []
    ]
    alerts = "".join(f"<li>{esc(x.get('summary'))}</li>" for x in geo.get("channel_alerts") or [])
    alert_box = f"<div class='callout warn'><span>渠道预警</span><ul>{alerts}</ul></div>" if alerts else ""
    total_html = f"""
    <div class="funnel-line">
      <div><span>曝光</span><strong>{num(totals.get('imps'))}</strong></div>
      <div><span>访客</span><strong>{num(totals.get('visitor'))}</strong></div>
      <div><span>商机</span><strong>{num(totals.get('inquiry'))}</strong></div>
      <div><span>订单</span><strong>{num(totals.get('order'))}</strong></div>
    </div>
    """
    summary = f"<div class='callout'><strong>{esc(funnel.get('summary') or '本期漏斗诊断未返回')}</strong></div>"
    content = summary + total_html + table(["漏斗段", "进入", "产出", "转化率", "行业均值", "判断"], stage_rows)
    content += "<h3>渠道分布</h3>" + table(["渠道", "UV", "环比", "本店/行业"], channel_rows, compact=True) + alert_box
    return section("traffic", "05 流量结构与漏斗 / Traffic Funnel", content, "看流量是否稳定，以及哪一段漏掉买家。")


def render_products(report_data: dict[str, Any], analysis: dict[str, Any]) -> str:
    """生成商品结构与 Top 商品处理区。

    Args:
        report_data: 清洗后的报告数据。
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    products = report_data.get("products") or {}
    layers = ((products.get("overview") or {}).get("product_layers")) or []
    layer_rows = []
    for layer in layers:
        name = str(layer.get("stage_name") or "")
        if "普通" in name:
            verdict = "🔴 严重过剩"
        elif "爆" in name:
            verdict = "🔴 爆品太少"
        elif "潜力" in name:
            verdict = "🟡 可孵化池"
        elif "低质" in name:
            verdict = "🟢 基本清理完成"
        else:
            verdict = "🟢 继续放大"
        layer_rows.append([
            layer.get("stage_name"),
            num(layer.get("prod_cnt")),
            pct(layer.get("prod_cnt_ratio")),
            pct(layer.get("cate_avg_ratio")),
            layer.get("avg_inquiry_90d"),
            verdict,
        ])
    category_rows = []
    for item in products.get("top5_categories") or []:
        rate = item.get("inquiries_rate")
        visitors = int(item.get("visitors") or 0)
        inquiries = int(item.get("inquiries") or 0)
        if inquiries == 0 and visitors > 0:
            verdict = "有流量无询盘，先修商品页"
        elif rate is not None and float(rate) >= 0.05:
            verdict = "🟢 高效率，适合扩品测试"
        else:
            verdict = "继续优化承接"
        category_rows.append([
            item.get("type"),
            num(item.get("visitors")),
            num(item.get("inquiries")),
            pct(item.get("inquiries_rate"), 2),
            verdict,
        ])
    ink = ((analysis.get("products_quadrant") or {}).get("ink_print")) or []
    watch = ((analysis.get("products_quadrant") or {}).get("watch")) or []
    bleeding = ((analysis.get("products_quadrant") or {}).get("bleeding")) or []
    battle_html = f"""
    <div class="battle-strip">
      <div><strong>{len(ink)}</strong><span>印钞款：继续放大</span></div>
      <div><strong>{len(bleeding)}</strong><span>失血款：今天处理</span></div>
      <div><strong>{len(watch)}</strong><span>观察款：继续观察</span></div>
      <div><strong>待识别</strong><span>淘汰款：后续清理</span></div>
    </div>
    """
    ink_cards = []
    for item in ink[:2]:
        actions = "".join(f"<li>{esc(x)}</li>" for x in item.get("actions") or [])
        ink_cards.append(
            f"<article class='product-card win'><span>商品ID {esc(item.get('product_id'))}</span>"
            f"<strong>{short(item.get('title'), 64)}</strong>"
            f"<p>曝光 {num(item.get('imps'))} · 询盘 {num(item.get('fb_num'))} · 询盘率 {esc(item.get('fb_rate_str'))}</p><ul>{actions}</ul></article>"
        )
    product_cards = []
    for item in bleeding[:5]:
        actions = "".join(f"<li>{esc(x)}</li>" for x in item.get("actions") or [])
        product_cards.append(
            f"<article class='product-card'><span>商品ID {esc(item.get('product_id'))}</span>"
            f"<strong>{short(item.get('title'), 64)}</strong>"
            f"<p>曝光 {num(item.get('imps'))} · 询盘 {num(item.get('fb_num'))} · 询盘率 {esc(item.get('fb_rate_str'))}</p>"
            f"<em>{esc(item.get('why'))}</em><ul>{actions}</ul></article>"
        )
    product_html = "".join(product_cards) or "<p class='empty'>本期未识别到高曝光低询盘商品。</p>"
    ink_html = "".join(ink_cards) or "<p class='empty'>本期未识别到印钞款。</p>"
    content = "<div class='callout'><strong>低质品不是主要问题，真正的问题是普通品过剩、爆品太少、部分橱窗商品浪费曝光。</strong></div>"
    content += table(["层级", "商品数", "占比", "同品类均值", "90天均询盘", "判断"], layer_rows)
    content += battle_html
    content += "<h3>印钞款：继续放大</h3><div class='product-grid'>" + ink_html + "</div>"
    content += "<h3>Top5 类目询盘效率</h3>" + table(["类目", "UV", "询盘", "询盘率", "判断"], category_rows, compact=True)
    content += "<h3>高曝光低询盘商品</h3><div class='product-grid'>" + product_html + "</div>"
    return section("products", "06 商品结构与 Top 商品作战 / Product Battle Plan", content, "先处理占用核心曝光但没有承接商机的商品。")


def render_service(report_data: dict[str, Any]) -> str:
    """生成服务力预警区。

    Args:
        report_data: 清洗后的报告数据。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    service = report_data.get("service") or {}
    if not service:
        return section("service", "服务力预警", "<div class='callout warn'><strong>服务数据未接入</strong></div>")
    rows = [
        ["30天首次5分钟回复率", pct(service.get("first_5min_reply_rate_30d"), 2), "对照平台/历史/用户目标", "待校准"],
        ["30天平均回复时长", f"{service.get('avg_reply_time_30d'):.2f} h" if service.get("avg_reply_time_30d") is not None else "未返回", "对照平台/历史/用户目标", "待校准"],
        ["上周 12h+ 回复条数", num(service.get("reply_over_12h_count")), "按买家优先级和平台规则复查", "待处理"],
        ["离线消息条数", num(service.get("offline_msg_count")), "当天处理", "🟢 正常"],
        ["未跟进/重复回复", f"{num(service.get('not_follow_count'))} / {num(service.get('repeat_reply_count'))}", "周内清零", "🟢 正常"],
    ]
    warnings = "".join(f"<li>{esc(x)}</li>" for x in service.get("warnings") or [])
    actions = table(
        ["动作", "原因", "验收"],
        [
            ["复查 12h+ 消息并按买家优先级安排跟进", "防止高价值商机继续流失", "按平台规则验收"],
            ["开启智能回复和值班提醒", "覆盖非工作时间，提升 5 分钟响应率", "今日完成"],
            ["每日复盘超时消息", "建立响应纪律", "每天下班前"],
            ["下周目标", "按平台规则、店铺历史或用户确认目标设定", "下周周报验收"],
        ],
        compact=True,
    )
    content = "<div class='callout'><strong>服务力在星级体系里不一定是短板，但即时响应纪律会直接影响商机承接。</strong></div>"
    content += table(["指标", "本店", "老板判断线", "判断"], rows)
    if warnings:
        content += f"<div class='callout danger'><span>服务响应动作</span><ul>{warnings}</ul></div>"
    content += "<h3>服务响应施工图</h3>" + actions
    return section("service", "07 服务响应预警 / Service Response", content, "只看响应纪律，不展开聊天内容。")


def keyword_rows(items: list[dict[str, Any]], action_text: str) -> list[list[Any]]:
    """把关键词列表压成 P4P 表格行。

    Args:
        items: 关键词诊断列表。
        action_text: 本组关键词的默认动作说明。

    Returns:
        list[list[Any]]: 可直接传给 table() 的行数据。

    Raises:
        None.
    """
    rows = []
    for item in items[:5]:
        rows.append([
            item.get("keyword"),
            item.get("source_tag"),
            num(item.get("inquiry")),
            item.get("rank_label"),
            action_text,
        ])
    return rows


def render_p4p(analysis: dict[str, Any]) -> str:
    """生成 P4P 与关键词策略区。

    Args:
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    kw = analysis.get("keywords_quadrant") or {}
    strategy_rows = [
        ["高潜词", "已产生询盘且具备转化证据", "核 ROI 与预算上限后提出测试幅度", "P1"],
        ["承接差词", "有点击无询盘", "不加价，先换落地页", "P1"],
        ["吸血词", "有花费无商机", "核对商机成本、预算上限和停止条件后再调价或暂停", "P1"],
        ["曝光无点击词", "有曝光无点击", "改标题、主图、价格表达", "P2"],
        ["拓展词", "有自然流量但未验证", "加入标题观察，不直接重投", "P2"],
        ["跑偏热词", "与供应链不匹配", "不投放，只记录机会", "P3"],
    ]
    content = "<div class='callout warn'><strong>禁止所有词套用同一调价比例。不同词要按询盘、点击、花费、类目匹配和用户确认口径分开处理。</strong></div>"
    content += table(["词类型", "判断条件", "动作", "优先级"], strategy_rows, compact=True)
    content += "<h3>金主词：已带来询盘，允许加预算</h3>" + table(["关键词", "来源", "询盘", "证据", "动作"], keyword_rows(kw.get("gold") or [], "加预算，关联主推品"), compact=True)
    content += "<h3>潜力词：有花费无询盘，先查承接</h3>" + table(["关键词", "来源", "询盘", "证据", "动作"], keyword_rows(kw.get("potential") or [], "核对承接页，并按用户确认周期复盘"), compact=True)
    content += "<h3>拓展词：有自然流量，先观察</h3>" + table(["关键词", "来源", "询盘", "证据", "动作"], keyword_rows(kw.get("expand") or [], "嵌入标题观察"), compact=True)
    return section("p4p", "08 P4P 与关键词策略 / Ad Strategy", content, "把钱投给已验证的词，把疑似浪费先关住。")


def render_not_do() -> str:
    """生成本周不建议事项。

    Args:
        None.

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    rows = [
        ["不建议盲目扩大 P4P 总预算", "高曝光 0 询盘商品未处理前，加预算会放大浪费"],
        ["不建议所有潜力词套用同一调价比例", "有花费无询盘的词，应先核对落地页和商机成本"],
        ["不建议无依据大规模上新品", "先根据当前商品结构、询盘质量和产能确认补品方向"],
        ["不建议直接追跑偏热品", "与当前供应链匹配度不明时，先确认再进入"],
        ["不建议自动处理失血橱窗品", "先核对同周期曝光、询盘和候选商品，再让用户确认换位"],
    ]
    return section("not-do", "09 本周不建议 / What Not To Do", table(["不建议", "原因"], rows, compact=True), "少做错事，很多时候比多做动作更值钱。")


def render_backlog(analysis: dict[str, Any]) -> str:
    """生成行动 Backlog 区。

    Args:
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    backlog = analysis.get("backlog") or {}
    names = {"P0": "今天必须做", "P1": "本周高优", "P2": "下周期推进", "P3": "本月观察"}
    groups = []
    for prio in ["P0", "P1", "P2", "P3"]:
        items = backlog.get(prio) or []
        if not items:
            continue
        lis = "".join(f"<li>{esc(x)}</li>" for x in items[:12])
        more = f"<p class='more'>另有 {len(items) - 12} 项，详见分析数据。</p>" if len(items) > 12 else ""
        opened = " open" if prio in {"P0", "P1"} else ""
        groups.append(f"<details class='backlog-group {prio.lower()}'{opened}><summary>{badge(prio, prio)} {esc(names[prio])} <small>{len(items)} 项</small></summary><ol>{lis}</ol>{more}</details>")
    return section("backlog", "10 行动 Backlog / Action Backlog", "".join(groups), "P0 / P1 默认展开；P2 / P3 默认折叠。")


def render_appendix(report_data: dict[str, Any], analysis: dict[str, Any]) -> str:
    """生成附录区。

    Args:
        report_data: 清洗后的报告数据。
        analysis: 诊断结果。

    Returns:
        str: section HTML。

    Raises:
        None.
    """
    market = report_data.get("market") or {}
    keyword_rows = [
        [x.get("keyword"), x.get("biz_line"), x.get("channel"), x.get("year_imps_index"), x.get("business_rate"), x.get("sell_status")]
        for x in market.get("keyword_market") or []
    ][:10]
    risk_rows = [
        [x.get("name"), x.get("value"), x.get("status"), x.get("where")]
        for x in analysis.get("risk_health") or []
    ]
    selection_rows = [
        [x.get("product_name"), x.get("price"), x.get("moq"), x.get("ab_cnt_30d"), x.get("order_cnt_30d"), "先确认供应链匹配"]
        for x in (market.get("product_selection_recent_30d") or [])[:6]
    ]
    quality = report_data.get("data_quality") or {}
    checks = quality.get("checks") or {}
    check_rows = [[k, "已返回" if v else "未返回"] for k, v in checks.items()]
    content = "<details open><summary>行业热词与广告机会</summary>" + table(["关键词", "业务线", "渠道", "曝光指数", "商机转化率", "售卖状态"], keyword_rows, compact=True) + "</details>"
    content += "<details><summary>行业选品机会</summary>" + table(["商品", "价格", "MOQ", "询盘", "订单", "判断"], selection_rows, compact=True) + "</details>"
    content += "<details><summary>合规风险健康项</summary>" + table(["检查项", "返回值", "状态", "入口"], risk_rows, compact=True) + "</details>"
    content += "<details><summary>采集状态</summary>" + table(["模块", "状态"], check_rows, compact=True) + "</details>"
    return section("appendix", "11 附录 / Appendix", content, "详细机会和健康项放在最后，避免干扰老板先读。")


def render_side_rail(report_data: dict[str, Any], analysis: dict[str, Any]) -> str:
    """生成桌面端右侧状态栏。

    Args:
        report_data: 清洗后的报告数据。
        analysis: 诊断结果。

    Returns:
        str: aside HTML。

    Raises:
        None.
    """
    service = report_data.get("service") or {}
    bleeding_count = len(((analysis.get("products_quadrant") or {}).get("bleeding")) or [])
    return f"""
    <aside class="side-rail">
      <h3>本周状态</h3>
      <ul>
        <li>🔴 星级：有降级风险</li>
        <li>🔴 交易力：核心短板</li>
        <li>🟠 商品：{bleeding_count} 款失血橱窗品</li>
        <li>🔴 服务：5分钟 {pct(service.get("first_5min_reply_rate_30d"), 2)}</li>
        <li>🟡 流量：曝光到访客偏低</li>
        <li>🟢 支付：转化表现较好</li>
      </ul>
      <h3>今日进度</h3>
      <label><input type="checkbox"> 保星任务</label>
      <label><input type="checkbox"> 超时消息补回</label>
      <label><input type="checkbox"> 失血商品处理</label>
      <label><input type="checkbox"> P4P词包复盘</label>
    </aside>
    """


def css() -> str:
    """返回报告内联 CSS。

    Args:
        None.

    Returns:
        str: CSS 文本。

    Raises:
        None.
    """
    return """
    :root {
      --paper: #f3f0eb;
      --card: #ffffff;
      --ink: #1f1f1d;
      --muted: #76716a;
      --line: #e7dfd4;
      --soft: #fbfaf7;
      --orange: #ff6a00;
      --red: #c23b2d;
      --green: #16845a;
      --blue: #2f65a7;
      --shadow: 0 8px 22px rgba(51, 43, 35, 0.06);
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "SF Pro Display", "Avenir Next", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.55;
    }
    .page { max-width: 1240px; margin: 0 auto; padding: 18px 18px 56px; }
    .content-shell { display: grid; grid-template-columns: minmax(0, 1fr) 230px; gap: 16px; align-items: start; }
    .hero {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 26px;
    }
    .hero-top { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }
    .eyebrow { margin: 0 0 9px; color: var(--orange); font-size: 12px; font-weight: 800; letter-spacing: 0; }
    h1 { margin: 0; font-size: 28px; line-height: 1.18; letter-spacing: 0; }
    h1 span { display: block; color: var(--muted); font-size: 15px; font-weight: 600; margin-top: 7px; }
    .period { margin: 12px 0 0; color: var(--muted); }
    .print-btn, .top-nav button {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      padding: 8px 12px;
      color: var(--ink);
      cursor: pointer;
    }
    .boss-line { margin: 22px 0; padding: 16px 18px; border-left: 4px solid var(--orange); background: #fff6ee; border-radius: 6px; }
    .boss-line span { display: block; color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .boss-line strong { font-size: 18px; }
    .top-actions { margin: 22px 0 0; }
    .top-actions h2 { margin: 0 0 12px; font-size: 18px; }
    .risk-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; }
    .metric-strip, .funnel-line, .star-summary, .battle-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .metric-strip { grid-template-columns: repeat(3, 1fr); }
    .risk-card, .metric-strip > div, .funnel-line > div, .star-summary > div, .battle-strip > div {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      background: #fff;
      min-height: 96px;
    }
    .risk-grid .risk-card { border-radius: 0; border-width: 0 1px 0 0; }
    .risk-grid .risk-card:last-child { border-right: 0; }
    .risk-card span, .metric-strip span, .funnel-line span, .star-summary span, .battle-strip span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 8px; }
    .risk-card strong, .metric-strip strong, .funnel-line strong, .star-summary strong, .battle-strip strong { display: block; font-size: 21px; line-height: 1.2; }
    .risk-card p { margin: 10px 0 0; color: var(--muted); font-size: 13px; }
    .risk-card.risk { border-top: 3px solid var(--red); }
    .risk-card.warn { border-top: 3px solid var(--orange); }
    .confidence {
      margin-top: 16px;
      padding: 13px 15px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
    }
    .confidence div { display: flex; justify-content: space-between; gap: 12px; }
    .confidence p { display: flex; flex-wrap: wrap; gap: 8px 14px; margin: 10px 0 0; color: var(--muted); font-size: 12px; }
    .top-nav {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin: 0 0 14px;
      padding: 10px 12px;
      background: rgba(243, 240, 235, .94);
      border: 1px solid var(--line);
      border-radius: 8px;
      backdrop-filter: blur(8px);
    }
    .top-nav div { display: flex; gap: 4px; overflow-x: auto; }
    .top-nav strong { white-space: nowrap; font-size: 14px; }
    .top-nav a { color: var(--ink); text-decoration: none; padding: 8px 12px; border-radius: 6px; white-space: nowrap; }
    .top-nav a:hover { background: #fff; color: var(--orange); }
    .section {
      margin-top: 14px;
      padding: 22px;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .section-head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; border-bottom: 1px solid var(--line); margin-bottom: 18px; padding-bottom: 14px; }
    h2 { margin: 0; font-size: 20px; letter-spacing: 0; }
    h3 { margin: 24px 0 12px; font-size: 16px; }
    .section-kicker { margin: 0; color: var(--muted); max-width: 520px; font-size: 13px; }
    .table-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }
    .table { width: 100%; border-collapse: collapse; min-width: 760px; background: #fff; }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 13px; font-weight: 700; background: #fbfaf8; }
    td { font-size: 14px; }
    .compact th, .compact td { padding: 9px 11px; font-size: 13px; }
    .callout, .plain-box { margin: 16px 0; padding: 15px 16px; border-radius: 6px; border: 1px solid var(--line); background: var(--soft); }
    .callout span { display: inline-block; margin-bottom: 6px; color: var(--muted); font-size: 13px; font-weight: 700; }
    .callout strong { display: block; font-size: 18px; }
    .callout.danger { border-color: #f0c5bd; background: #fff2f0; }
    .callout.warn { border-color: #f5d3b2; background: #fff7ef; }
    .callout ul { margin: 8px 0 0; padding-left: 20px; }
    .diagnosis-grid { display: grid; grid-template-columns: 1.1fr .9fr; gap: 14px; }
    .plain-box h3, .chain h3 { margin-top: 0; }
    .plain-box ol { margin: 0; padding-left: 20px; }
    .plain-box li { margin: 8px 0; }
    .chain { margin: 16px 0; padding: 15px 16px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
    .chain div { position: relative; padding: 8px 0 8px 20px; border-left: 2px solid var(--orange); }
    .chain div::before { content: ""; position: absolute; left: -5px; top: 16px; width: 8px; height: 8px; border-radius: 50%; background: var(--orange); }
    .product-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .product-card { border: 1px solid var(--line); border-radius: 6px; padding: 15px; background: #fff; }
    .product-card.win { border-top: 3px solid var(--green); }
    .product-card span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .product-card strong { display: block; font-size: 16px; margin-bottom: 8px; }
    .product-card p, .product-card em { display: block; color: var(--muted); font-style: normal; margin: 6px 0; }
    .product-card ul { margin: 10px 0 0; padding-left: 18px; }
    details { border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; margin: 12px 0; background: #fff; }
    summary { cursor: pointer; font-weight: 700; }
    .backlog-group.p0 { border-color: #edb9b1; background: #fff4f2; }
    .backlog-group.p1 { border-color: #f2caa3; background: #fff8f0; }
    .backlog-group ol { margin: 12px 0 0; padding-left: 22px; }
    .backlog-group li { margin: 8px 0; }
    .badge { display: inline-flex; align-items: center; justify-content: center; min-width: 34px; padding: 3px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; background: #ece7df; color: var(--ink); }
    .badge.p0 { color: #fff; background: var(--red); }
    .badge.p1 { color: #fff; background: var(--orange); }
    .badge.p2 { color: #fff; background: var(--blue); }
    .badge.p3 { color: var(--ink); background: #e9e4dc; }
    .empty, .more { color: var(--muted); }
    .side-rail {
      position: sticky;
      top: 72px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 16px;
      box-shadow: var(--shadow);
      font-size: 13px;
    }
    .side-rail h3 { margin: 0 0 10px; font-size: 15px; }
    .side-rail ul { margin: 0 0 16px; padding: 0; list-style: none; }
    .side-rail li { padding: 7px 0; border-bottom: 1px solid var(--line); }
    .side-rail label { display: block; margin: 9px 0; color: var(--muted); }
    footer { color: var(--muted); text-align: center; margin-top: 26px; font-size: 13px; }
    a:focus, button:focus, summary:focus { outline: 2px solid rgba(255,106,0,.35); outline-offset: 2px; }
    @media (max-width: 820px) {
      .page { padding: 16px 12px 40px; }
      .content-shell { display: block; }
      .side-rail { display: none; }
      .hero { padding: 22px; }
      .hero-top, .section-head { display: block; }
      h1 { font-size: 28px; }
      .risk-grid, .metric-strip, .funnel-line, .product-grid, .diagnosis-grid, .star-summary, .battle-strip { grid-template-columns: 1fr; }
      .risk-grid .risk-card { border-width: 0 0 1px 0; }
      .top-nav strong, .top-nav button { display: none; }
    }
    @media print {
      body { background: #fff; }
      .top-nav, .side-rail, .print-btn { display: none; }
      .content-shell { display: block; }
      .section, .hero { box-shadow: none; break-inside: avoid; }
    }
    """


def build(report_data: dict[str, Any], analysis: dict[str, Any], output_path: Path) -> Path:
    """生成 HTML 文件。

    Args:
        report_data: `prepare_data.py` 输出的数据。
        analysis: `analyze.py` 输出的诊断结果。
        output_path: HTML 输出路径。

    Returns:
        Path: 实际写入的文件路径。

    Raises:
        OSError: 当目标目录不可写时由 pathlib 抛出。
    """
    content = "\n".join([
        render_header(report_data, analysis),
        render_nav(),
        "<div class='content-shell'><div>",
        render_diagnosis(report_data, analysis),
        render_overview(analysis),
        render_star(report_data),
        render_traffic(analysis),
        render_products(report_data, analysis),
        render_service(report_data),
        render_p4p(analysis),
        render_not_do(),
        render_backlog(analysis),
        render_appendix(report_data, analysis),
        "</div>",
        render_side_rail(report_data, analysis),
        "</div>",
    ])
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc((report_data.get('meta') or {}).get('company_name'))} - {esc(report_title(report_data.get('meta') or {}))}</title>
  <style>{css()}</style>
</head>
<body>
  <main class="page">
    {content}
    <footer>本报告用于经营决策参考；缺失指标已明确标注为未返回。</footer>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


def default_output_path(report_data_path: Path, report_data: dict[str, Any]) -> Path:
    """生成默认 HTML 输出文件名。

    Args:
        report_data_path: 输入 report_data.json 的路径。
        report_data: 清洗后的报告数据。

    Returns:
        Path: 默认输出路径。

    Raises:
        None.
    """
    meta = report_data.get("meta") or {}
    company = str(meta.get("company_name") or "店铺").replace("有限公司", "")
    period = meta.get("title_period") or datetime.now().strftime("%Y-%m-%d")
    title = report_title(meta)
    return report_data_path.parent / f"{company}-{title}-{period}.html"


def main() -> None:
    """命令行入口。

    Args:
        None: 参数来自 sys.argv。

    Returns:
        None.

    Raises:
        SystemExit: 参数不足时退出。
    """
    if len(sys.argv) < 3:
        print("usage: build_html.py <report_data.json> <analysis.json> [<output.html>]", file=sys.stderr)
        sys.exit(1)
    report_data_path = Path(sys.argv[1])
    analysis_path = Path(sys.argv[2])
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else default_output_path(report_data_path, report_data)
    out = build(report_data, analysis, output_path)
    print(f"html written: {out}")
    print(f"  size: {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
