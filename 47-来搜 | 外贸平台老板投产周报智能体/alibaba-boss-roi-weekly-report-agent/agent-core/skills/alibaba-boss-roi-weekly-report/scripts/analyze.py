#!/usr/bin/env python3
"""analyze.py — 诊断引擎。

输入：prepare_data.py 输出的 report_data.json
输出：诊断结构 (analysis.json)，包含：
  - quadrants.products: 5 类商品标签 + 动作建议
  - quadrants.keywords: 4 类关键词标签 + 出价建议
  - funnel_diagnosis: 漏斗反常段定位
  - country_channel: 流量归因 (涨幅/跌幅 Top3 + 推测原因)
  - top3_actions: 本周 3 件最该做的事
  - backlog: P0/P1/P2/P3 行动清单
  - kpi_traffic_lights: KPI 红绿灯诊断
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------
# 基准只接受报告里的平台/店铺真实口径。0 表示不可判断，绝不能
# 用某个历史类目的经验阈值替代当前店铺/类目基准。
# ----------------------------------------------------------------------
INDUSTRY_BASELINE = {
    "ctr": 0.0,
    "ctr_good": 0.0,
    "imps_to_visitor": 0.0,
    "visitor_to_inquiry": 0.0,
    "inquiry_to_order": 0.0,
    "details_bounce_rate": 0.0,
}


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def safe_float(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        if isinstance(v, str):
            s = v.strip().replace(",", "")
            if s.endswith("%"):
                return float(s[:-1]) / 100
            return float(s)
        return float(v)
    except (TypeError, ValueError):
        return default


def safe_int(v, default=0) -> int:
    return int(safe_float(v, default))


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def parse_rank_label(label: Any) -> int:
    """把"前7名"这类榜单排名转成数字，失败返回 0。"""
    if not label:
        return 0
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    return int(digits) if digits else 0


def short_title(s: str, max_len: int = 50) -> str:
    if not s:
        return "(无标题)"
    s = s.strip()
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def ability_is_weak(ability: dict) -> bool:
    """Return whether the platform/input explicitly marks an ability as weak."""

    status = str(ability.get("status") or ability.get("diagnosis") or "").lower()
    return bool(ability.get("is_weak")) or status in {
        "weak", "warning", "risk", "below_target", "待提升", "预警", "风险",
    }


def quality_blocked(report_data: dict, flag: str) -> bool:
    """判断某个数据质量阻断项是否存在。

    参数:
        report_data: prepare_data.py 输出的报告数据。
        flag: data_quality.blocking_flags 里的标记名。

    返回:
        True 表示该结论必须降级或不可判断。

    异常:
        本函数不抛异常。
    """
    quality = report_data.get("data_quality") or {}
    return bool((quality.get("blocking_flags") or {}).get(flag))


def owner_from_text(text: str, object_type: str = "", priority: str = "") -> str:
    """根据动作文本、对象类型和优先级分配负责人。"""
    text = (text or "").lower()
    if priority == "P0":
        if any(w in text for w in ["侵权", "禁售", "知产", "处罚", "扣分"]):
            return "运营主管"
        if any(w in text for w in ["回复", "超时", "响应", "询盘"]):
            return "业务主管"
        return "运营主管"
    if object_type in ("关键词", "商品"):
        return "运营"
    if object_type in ("询盘", "业务员"):
        return "业务主管"
    if object_type == "数据质量":
        return "运营"
    if object_type == "经营漏斗":
        return "运营主管"
    if any(w in text for w in ["p4p", "广告", "关键词", "出价", "投放", "预算", "竞价"]):
        return "运营"
    if any(w in text for w in ["商品", "主图", "标题", "详情页", "橱窗", "视频"]):
        return "运营"
    if any(w in text for w in ["询盘", "客户", "回复", "消息", "报价", "样品", "跟进"]):
        return "业务主管"
    if any(w in text for w in ["跟进闭环", "未跟进", "回复"]):
        return "业务主管"
    if any(w in text for w in ["星级", "能力项", "诊断", "漏斗", "风险", "合规"]):
        return "运营主管"
    return "运营主管"


def infer_object(action: dict) -> tuple[str, str]:
    """把动作标题转成对象类型和对象名称。

    参数:
        action: 原始候选动作。

    返回:
        (object_type, object_name)，用于冲突检测和老板行动展示。

    异常:
        本函数不抛异常。
    """
    title = str(action.get("title") or action.get("action") or "")
    for left, right, object_type in [
        ("「", "」", "关键词/商品"),
        ("：", " 的", "询盘"),
    ]:
        if left in title and right in title:
            name = title.split(left, 1)[1].split(right, 1)[0].strip()
            if name:
                if "词" in title or "出价" in title:
                    return "关键词", name
                if "询盘" in title or "客户" in title:
                    return "询盘", name
                if "商品" in title or "款" in title or "主图" in title:
                    return "商品", name
                return object_type, name
    if "服务" in title or "回复" in title:
        return "业务员", "全店响应"
    if "漏斗" in title:
        return "经营漏斗", title.replace("修补", "").replace("优化", "")[:30]
    if "数据" in title:
        return "数据质量", "本期数据"
    return "事项", short_title(title, 28)


def infer_direction(action: dict) -> str:
    """判断动作方向，给冲突检测使用。

    参数:
        action: 原始动作。

    返回:
        increase / stop / fix / follow / check。

    异常:
        本函数不抛异常。
    """
    text = " ".join(str(action.get(key) or "") for key in ("title", "why", "where", "action"))
    if any(word in text for word in ["暂停", "降价", "止损", "下架"]):
        return "stop"
    if any(word in text for word in ["加预算", "出价 +", "出价+", "提价"]):
        return "increase"
    if any(word in text for word in ["询盘", "报价", "客户", "跟进"]):
        return "follow"
    if any(word in text for word in ["复查", "检查", "补采"]):
        return "check"
    return "fix"


def structure_action(action: dict, audience: str = "老板") -> dict:
    """把旧动作转成老板可派工的结构化动作。

    参数:
        action: 旧版动作字典。
        audience: 老板或运营。

    返回:
        结构化动作，包含负责人、验收指标和复查指标。

    异常:
        本函数不抛异常。
    """
    object_type, object_name = infer_object(action)
    text = " ".join(str(action.get(key) or "") for key in ("title", "where", "why"))
    direction = infer_direction(action)
    prio = action.get("priority") or "P2"
    owner = action.get("owner") or owner_from_text(text, object_type, prio)
    due = action.get("due") or action.get("deadline") or "待用户确认"
    title = action.get("title") or action.get("action") or object_name
    if direction == "increase":
        acceptance = "用户确认周期内有效询盘增加或商机成本未恶化"
        review = "下周看商机成本和订单后续"
    elif direction == "stop":
        acceptance = "无效消耗下降，保留高意向流量"
        review = "下周看花费、询盘、订单"
    elif direction == "follow":
        acceptance = "客户下一步明确：报价/样品/规格/付款"
        review = "下周看是否进入报价或订单"
    elif object_type == "数据质量":
        acceptance = "缺失字段补齐，相关结论可判断"
        review = "下周同口径检查数据质量"
    else:
        acceptance = "动作完成且指标可复查"
        review = "下周看同一指标是否转黄/绿"
    return {
        "priority": action.get("priority") or "P2",
        "audience": audience,
        "object_type": object_type,
        "object_name": object_name,
        "problem": title,
        "why": action.get("why") or "证据不足，需复盘",
        "owner": owner,
        "action": action.get("action") or title,
        "due": due,
        "acceptance_metric": action.get("acceptance_metric") or acceptance,
        "review_metric": action.get("review_metric") or review,
        "evidence": action.get("why") or title,
        "conflict_key": f"{object_type}:{object_name}".lower(),
        "direction": direction,
        "where": action.get("where") or "对应后台模块",
    }


def resolve_action_conflicts(actions: list[dict]) -> list[dict]:
    """合并同对象的相反动作，避免报告自相矛盾。

    参数:
        actions: 结构化动作列表。

    返回:
        去重和冲突合并后的动作列表。

    异常:
        本函数不抛异常。
    """
    merged = []
    by_key: dict[str, dict] = {}
    rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    for action in actions:
        key = action.get("conflict_key") or action.get("problem")
        existing = by_key.get(key)
        if not existing:
            by_key[key] = action
            continue
        dirs = {existing.get("direction"), action.get("direction")}
        if {"increase", "stop"}.issubset(dirs):
            existing["priority"] = min(existing.get("priority", "P2"), action.get("priority", "P2"), key=lambda x: rank.get(x, 9))
            existing["action"] = "在用户确认的测试周期内核对有效询盘和商机成本；达到确认条件才提价，否则再确认暂停或降价"
            existing["acceptance_metric"] = "用户确认周期内的有效询盘、商机成本和订单后续均有记录"
            existing["review_metric"] = "下周复查该对象花费、询盘质量和订单"
            existing["direction"] = "check"
            existing["why"] = f"{existing.get('why')}；另有相反动作建议，已合并为条件式处理"
        else:
            if rank.get(action.get("priority", "P3"), 9) < rank.get(existing.get("priority", "P3"), 9):
                by_key[key] = action
    merged.extend(by_key.values())
    merged.sort(key=lambda x: rank.get(x.get("priority", "P3"), 9))
    return merged


def conservative_status(report_data: dict) -> dict:
    """生成首页用的保守红黄绿状态。

    参数:
        report_data: 标准化报告数据。

    返回:
        dict: status、label、reason。

    异常:
        本函数不抛异常。
    """
    quality = report_data.get("data_quality") or {}
    flags = quality.get("blocking_flags") or {}
    service = report_data.get("service") or {}
    if flags.get("collection_period_mismatch") or flags.get("order_period_mismatch"):
        return {"status": "red", "label": "红灯", "reason": "存在周期错位，不能判健康"}
    if flags.get("order_pagination_truncated"):
        return {"status": "red", "label": "红灯", "reason": "订单分页未完成，订单数和金额只能看作下限"}
    if flags.get("order_amount_missing") or flags.get("ad_cost_missing"):
        return {"status": "unknown", "label": "不可判断", "reason": "订单金额或广告花费缺失，ROI 不完整"}
    if service.get("warnings") or service.get("reply_timeout_flag") or service.get("reply_overdue_flag"):
        return {"status": "yellow", "label": "黄灯", "reason": "平台或输入已标记服务响应异常"}
    if quality.get("status") == "red":
        return {"status": "red", "label": "红灯", "reason": "数据质量红灯，结论需降级"}
    if quality.get("status") == "yellow":
        return {"status": "yellow", "label": "黄灯", "reason": "部分数据缺失，结论保守"}
    if not quality.get("status"):
        return {"status": "unknown", "label": "不可判断", "reason": "数据质量状态未返回，不能判绿灯"}
    return {"status": "green", "label": "绿灯", "reason": "核心周期和字段可用"}


# ----------------------------------------------------------------------
# 1. 商品 5-quadrant 分类 + 具体动作
# ----------------------------------------------------------------------
PRODUCT_TAGS = {
    "ink_print": {"emoji": "🔥", "label": "印钞款", "color": "green"},
    "potential": {"emoji": "⚡", "label": "潜力款", "color": "orange"},
    "bleeding":  {"emoji": "🩹", "label": "失血款", "color": "red"},
    "zombie":    {"emoji": "🪦", "label": "僵尸款", "color": "gray"},
    "watch":     {"emoji": "❓", "label": "观察款", "color": "blue"},
}


def tag_products(products_top: list, ctr_baseline: float, inquiry_rate_baseline: float,
                 store_total_imps: float = 0) -> dict:
    """对商品 Top 列表分类。

    只使用平台标签、真实询盘和同周期行业基准；没有基准时退化到
    ``watch``，不套固定曝光量、询盘数或观察天数。
    """
    tagged = {k: [] for k in PRODUCT_TAGS}

    for p in products_top:
        imps = safe_int(p.get("imps"))
        fb_num = safe_int(p.get("fb_num"))
        fb_rate = safe_float(p.get("fb_rate"))
        title = short_title(p.get("subject"))
        pid = p.get("product_id") or ""

        is_showcase = bool(p.get("is_showcase"))
        platform_tag = str(p.get("diagnosis_tag") or p.get("platform_tag") or "").lower()
        if platform_tag in {"low_efficiency", "zombie", "inactive"}:
            tag = "zombie"
            actions = [
                "核对平台低效标签的周期、原因和商品状态",
                "在用户确认后选择优化标题/素材、保留观察或进入下架清单",
            ]
            why = "平台或用户提供了低效商品标签；具体处置仍需确认周期和影响"
        elif is_showcase and imps > 0 and fb_num == 0:
            tag = "bleeding"
            actions = [
                "核对橱窗曝光对应周期、主图、标题和详情承接",
                "若要更换橱窗位，先比较候选商品的同周期询盘率并让用户确认",
            ]
            why = f"橱窗商品在当前返回周期有曝光 {imps}，但询盘为 0；应先核对承接证据"
        elif inquiry_rate_baseline > 0 and fb_num > 0 and fb_rate >= inquiry_rate_baseline:
            tag = "ink_print"
            actions = [
                "列为加码候选；先核订单金额、真实 ROI、预算上限和商品承接，再由用户确认调整幅度",
                "只把已验证的表达元素复用到事实匹配的关联商品",
            ]
            why = f"当前返回周期询盘 {fb_num}，询盘率 {pct(fb_rate)}，达到同周期行业基准 {pct(inquiry_rate_baseline)}"
        elif inquiry_rate_baseline > 0 and fb_num > 0 and fb_rate < inquiry_rate_baseline:
            tag = "potential"
            actions = [
                "按买家问题补充 FAQ、规格和应用证据，不使用未确认参数",
                "核对主图、详情和价格/MOQ表达与实际询盘意图是否一致",
            ]
            why = f"已有 {fb_num} 条询盘，但询盘率 {pct(fb_rate)} 低于同周期行业基准 {pct(inquiry_rate_baseline)}"
        elif inquiry_rate_baseline > 0 and imps > 0 and fb_num == 0:
            tag = "bleeding"
            actions = [
                "核对搜索词、主图、标题和详情承接，先提出预览方案",
                "需要做 A/B 或改图时先确认素材、周期和评价指标",
            ]
            why = f"当前返回周期有曝光 {imps}、询盘 0，且存在行业询盘率基准；需核对承接原因"
        else:
            tag = "watch"
            actions = [
                "补齐同周期行业基准、商品上架时间和询盘质量后再分类",
                "由用户确认观察周期，不自动下架或调预算",
            ]
            why = f"数据不足以做强分类（曝光 {imps}, 询盘 {fb_num}）"

        tagged[tag].append({
            "product_id": pid,
            "title": title,
            "imps": imps,
            "fb_num": fb_num,
            "fb_rate": fb_rate,
            "fb_rate_str": pct(fb_rate),
            "image": p.get("image", ""),
            "is_showcase": is_showcase,
            "rank": p.get("rank"),
            "why": why,
            "actions": actions,
        })

    return tagged


# ----------------------------------------------------------------------
# 2. 关键词 4-quadrant 分类 + 出价建议
# ----------------------------------------------------------------------
KEYWORD_TAGS = {
    "gold":      {"emoji": "⭐", "label": "金主词", "color": "green"},
    "burning":   {"emoji": "💰", "label": "烧钱词", "color": "red"},
    "potential": {"emoji": "🚀", "label": "潜力词", "color": "orange"},
    "expand":    {"emoji": "🌱", "label": "拓展词", "color": "blue"},
}


def tag_keywords(keywords: list, hot_industry_words: list) -> dict:
    """关键词四象限分类。

    输入字段假设（可缺失，缺失则用规则推断）：
      keyword, imps, clk, inquiry, cost, cpc, current_bid, rank
    """
    tagged = {k: [] for k in KEYWORD_TAGS}
    seen = set()

    for k in keywords:
        word = (k.get("keyword") or "").strip()
        if not word or word in seen:
            continue
        seen.add(word)

        imps = safe_int(k.get("imps"))
        clk = safe_int(k.get("clk"))
        inquiry = safe_int(k.get("inquiry"))
        cost = safe_float(k.get("cost"))
        cpc = safe_float(k.get("cpc"))
        current_bid = safe_float(k.get("current_bid"), default=0)
        rank = safe_int(k.get("rank")) or parse_rank_label(k.get("rank_label"))
        ctr = (clk / imps) if imps > 0 else 0
        source_tag = k.get("source_tag") or ""
        rank_label = k.get("rank_label") or (f"前{rank}名" if rank else "")

        if inquiry > 0 or source_tag == "Shop-HighInquiry":
            tag = "gold"
            actions = [
                "列为已产生商机的核心词候选，先核对询盘质量与对应商品",
                "如需调价，先确认当前出价、预算上限、目标商机成本和测试幅度",
                "扩展同义词或长尾词前先确认测试数量与复盘周期",
            ]
            why = f"该词已有 {inquiry} 条实际商机记录{f'，并进入平台高询盘词榜单（{rank_label}）' if rank_label else ''}；仍需核对商机质量和订单后续"
        elif source_tag == "Shop-HighP4P":
            tag = "potential"
            actions = [
                "检查该词对应商品、询盘质量和当前商机成本，不按固定比例自动调价",
                "如要更换落地页，先确认目标商品与现有承接证据",
                "由用户确认测试周期、预算上限和停止条件后再执行投放变更",
            ]
            why = f"进入高 P4P 消耗词榜单{f'（{rank_label}）' if rank_label else ''}，需要确认花费是否带来商机"
        elif source_tag == "Shop-HighTraffic":
            tag = "expand"
            actions = [
                "在事实匹配的主推商品标题或卖点中验证该词相关性",
                "补充与该词意图一致的场景图，避免错配承接页",
                "按用户确认的周期观察询盘质量，再决定是否转为投放词",
            ]
            why = f"进入高引流词榜单{f'（{rank_label}）' if rank_label else ''}，已有自然流量但需验证商机承接"
        elif source_tag:
            tag = "potential"
            actions = [
                "列为出价测试候选；先确认预算上限、转化证据和测试幅度",
                "仅在商品事实匹配时把词根用于标题或卖点",
                "按用户确认的测试周期复盘排名、点击和商机成本，不自动继续加价",
            ]
            why = f"平台返回了该词的业务标签{f'和排名 {rank}' if rank else ''}，但缺少可直接决定调价的同口径基准"
        else:
            continue  # 不归到拓展词

        tagged[tag].append({
            "keyword": word,
            "imps": imps, "clk": clk, "inquiry": inquiry,
            "cost": cost, "cpc": cpc, "rank": rank, "ctr": ctr,
            "rank_label": rank_label,
            "source_tag": source_tag,
            "product_name": k.get("product_name"),
            "current_bid": current_bid,
            "why": why,
            "actions": actions,
        })

    # 拓展词：行业热词中本店未覆盖的
    own = {k.get("keyword", "").lower() for k in keywords}
    for hw in hot_industry_words:
        word = (hw.get("keyword") or hw.get("name") or "").strip()
        if not word or word.lower() in own:
            continue
        tagged["expand"].append({
            "keyword": word,
            "industry_imps": safe_int(hw.get("imps") or hw.get("hot_value")),
            "why": f"行业热搜词，本店未覆盖（行业曝光 {safe_int(hw.get('imps') or hw.get('hot_value'))}）",
            "actions": [
                "列为候选词，先确认类目相关性、预算上限和测试出价",
                "仅在商品事实匹配时尝试用于标题或卖点",
                "按用户确认的测试周期复盘点击、询盘质量和商机成本",
            ],
        })
        if len(tagged["expand"]) >= 8:
            break

    return tagged


# ----------------------------------------------------------------------
# 3. 漏斗诊断（找到反常段）
# ----------------------------------------------------------------------
def analyze_funnel(funnel_data: dict) -> dict:
    """从当前报告周期的漏斗数据找出最反常的一段。

    漏斗 4 段：曝光 → 访客 → 商机 → 订单。
    不把接口未返回的点击数补成 0，避免生成"曝光→点击 0%"误判。
    """
    if not funnel_data:
        return {
            "summary": "漏斗数据不可用",
            "anomalies": [],
            "totals": {"imps": None, "visitor": None, "inquiry": None, "order": None},
            "stages": []
        }
    daily = funnel_data.get("daily", []) or []
    benchmark_rows = funnel_data.get("benchmark", []) or []
    benchmark = {
        str(row.get("metric")): safe_float(row.get("rival_avg"), 0.0)
        for row in benchmark_rows if isinstance(row, dict) and row.get("rival_avg") not in (None, "")
    }
    if not daily:
        return {
            "summary": "漏斗数据不可用，请检查 service_report_weekly_all_data_query 接口",
            "anomalies": [],
        }

    # 加总
    total_imps = sum(safe_float(r.get("imps")) for r in daily)
    total_visitor = sum(safe_float(r.get("visitor_uv")) for r in daily)
    total_fb = sum(safe_float(r.get("fb_count") or r.get("fb_num")) for r in daily)
    total_order = sum(safe_float(r.get("order_count")) for r in daily)

    # 真实链路：曝光 → 访客 → 商机 → 订单
    stages = []
    if total_imps > 0 and total_visitor > 0:
        stages.append(("曝光→访客", total_imps, total_visitor, total_visitor / total_imps,
                       benchmark.get("曝光→访客转化率", 0.0)))

    if total_visitor > 0:
        stages.append(("访客→商机", total_visitor, total_fb, total_fb / total_visitor,
                       benchmark.get("访客→商机率", 0.0)))
    if total_fb > 0:
        stages.append(("商机→订单", total_fb, total_order, total_order / total_fb if total_fb > 0 else 0,
                       benchmark.get("商机→订单率", 0.0)))

    anomalies = []
    evaluated_stages = 0
    for stage, n_in, n_out, rate, base in stages:
        if base <= 0:
            continue
        evaluated_stages += 1
        if rate < base:
            level = "🟡 偏低"
            advice = f"{stage}转化率 {pct(rate)} 低于当前平台/店铺基准 {pct(base)}；优先级需结合样本量和用户口径"
        elif rate > base:
            level = "🟢 高于基准"
            advice = f"{stage}转化率 {pct(rate)} 高于当前平台/店铺基准 {pct(base)}；需结合样本量再判断能否复制"
        else:
            continue
        anomalies.append({
            "stage": stage, "in": int(n_in), "out": int(n_out),
            "rate": rate, "rate_str": pct(rate),
            "baseline": base, "baseline_str": pct(base),
            "level": level, "advice": advice,
        })

    if evaluated_stages == 0:
        summary = "同周期漏斗基准未返回，不能判断整体健康"
    elif not anomalies:
        summary = f"已返回基准的漏斗段均达到或高于基准（曝光 {int(total_imps)} → 商机 {int(total_fb)} → 订单 {int(total_order)}）"
    else:
        worst = anomalies[0]
        summary = f"漏斗反常段：{worst['stage']}（{worst['level']}）— {worst['advice']}"

    return {
        "summary": summary,
        "totals": {
            "imps": int(total_imps) if total_imps else None,
            "visitor": int(total_visitor) if total_visitor else None,
            "inquiry": int(total_fb), "order": int(total_order),
        },
        "stages": [
            {"stage": s, "in": int(n_in), "out": int(n_out), "rate": rate, "baseline": base}
            for s, n_in, n_out, rate, base in stages
        ],
        "anomalies": anomalies,
    }


# ----------------------------------------------------------------------
# 4. 国家 / 渠道 流量归因
# ----------------------------------------------------------------------
def analyze_country_channel(region: dict, channels: dict) -> dict:
    """找涨幅 / 跌幅 Top3 国家 + 推测原因。"""
    region = region or {}
    channels = channels or {}
    uv_top = region.get("uv_top", []) or []
    imps_top = region.get("imps_top", []) or []

    risers = []
    fallers = []
    for r in uv_top:
        crc = safe_float(r.get("cycle_crc"))  # cycle change rate
        country = r.get("country") or r.get("name") or ""
        uv = safe_int(r.get("uv") or r.get("value"))
        if not country:
            continue
        if crc > 0:
            risers.append({"country": country, "uv": uv, "crc": crc, "crc_str": f"+{pct(crc)}"})
        elif crc < 0:
            fallers.append({"country": country, "uv": uv, "crc": crc, "crc_str": pct(crc)})

    risers.sort(key=lambda x: -x["crc"])
    fallers.sort(key=lambda x: x["crc"])
    risers = risers[:3]
    fallers = fallers[:3]

    insights = []
    actions = []

    for r in risers:
        insights.append(f"🟢 {r['country']} 流量爆涨 {r['crc_str']}（UV {r['uv']}）")
        actions.append(f"在 {r['country']} 市场加大 P4P 投放，本地化标题 / 主图")
    for f in fallers:
        insights.append(f"🔴 {f['country']} 流量下滑 {f['crc_str']}（UV {f['uv']}）")
        actions.append(f"调研 {f['country']} 是否为季节性 / 行业整体下滑；若非，检查该国主推商品的排名")

    # 渠道
    rows = channels.get("rows", []) or []
    channel_summary = []
    channel_alerts = []
    for row in rows[:5]:
        ch = row.get("channel") or row.get("name") or ""
        uv = safe_int(row.get("uv") or row.get("detail_uv") or row.get("value"))
        crc = safe_float(row.get("cycle_crc") or row.get("detail_uv_chg"))
        rival = safe_float(row.get("rival_avg"))
        if not ch:
            continue
        channel_summary.append({
            "channel": ch, "uv": uv, "crc": crc,
            "vs_rival": f"{uv}/{rival:.0f}" if rival else f"{uv}/-",
        })
        if crc < 0:
            priority = str(row.get("priority") or row.get("alert_level") or "P2")
            channel_alerts.append({
                "priority": priority,
                "channel": ch,
                "summary": f"渠道「{ch}」UV 环比下滑 {crc * 100:.1f}%；优先级来自平台/输入，缺失时按 P2 待复核",
            })
        if uv == 0 and any(key in ch for key in ["Saving", "Weekly", "Top-Ranking", "New Arrival"]):
            channel_alerts.append({
                "priority": "P2",
                "channel": ch,
                "summary": f"资源位「{ch}」本期 UV 为 0，检查是否可报名或是否缺少匹配商品",
            })

    return {
        "risers": risers,
        "fallers": fallers,
        "channels": channel_summary,
        "channel_alerts": channel_alerts[:6],
        "insights": insights or ["国家流量分布相对稳定，无显著涨跌"],
        "actions": actions or ["继续监测各国流量分布"],
    }


# ----------------------------------------------------------------------
# 5. KPI 红绿灯
# ----------------------------------------------------------------------
def kpi_traffic_lights(indicators: list, conversion_funnel: list) -> list:
    """每个核心 KPI 一行红绿灯诊断，按同行均值 + 同行优秀双基准判断。"""
    lights = []
    for ind in indicators:
        name = ind.get("name", "")
        value = ind.get("value")
        crc = safe_float(ind.get("cycle_crc"))
        rival = safe_float(ind.get("rival_avg"))
        rival_good = safe_float(ind.get("rival_good"))
        if value is None or value == "":
            continue
        v = safe_float(value)

        # 只按平台返回的同行均值/优秀值做直接比较，不套人为比例。
        excellent_gap = None
        if rival_good > 0:
            excellent_gap = (v - rival_good) / rival_good

        if rival > 0:
            ratio = v / rival
            if rival_good > 0 and v >= rival_good:
                light = "🟢"
                diag = f"达到或超过平台同行优秀值；为行业均值 {ratio:.1f}x"
            elif v >= rival:
                light = "🟡"
                diag = f"达到平台同行均值；当前为均值 {ratio:.1f}x"
            else:
                light = "🔴"
                diag = f"低于平台同行均值；当前为均值 {ratio:.1f}x"
        else:
            light = "🟡"
            diag = f"缺少同行基准；仅记录环比 {pct(crc)}，不据此判红绿"

        lights.append({
            "name": name, "value": value, "crc": crc,
            "rival_avg": rival or "-", "rival_good": rival_good or "-",
            "excellent_gap": excellent_gap,
            "light": light, "diag": diag,
        })
    return lights


# ----------------------------------------------------------------------
# 6. 风险归一化为可执行任务
# ----------------------------------------------------------------------
def normalize_risks(risk: dict) -> list:
    """把原始 risk 字段转成"今天可点的处理项"。"""
    risk = risk or {}
    tasks = []
    item_meta = [
        ("forbidden_product_cnt", "P0", "禁售商品", "核对平台违规详情、处置期限和影响后进入确认清单", "卖家中心 - 商品管理 - 违规商品"),
        ("infringing_product_cnt", "P0", "侵权商品", "核对平台通知、证据和处置期限后进入确认清单", "卖家中心 - 知产保护"),
        ("ipr_num", "P0", "知产投诉", "需提交申诉材料，否则商品下架", "卖家中心 - 知产保护"),
        ("repeat_complaint_cnt", "P1", "重复投诉", "本周内核查处理", "卖家中心 - 服务中心"),
        ("high_frequency_complaint_cnt", "P1", "高频投诉买家", "调阅记录，制定话术", "卖家中心 - 客户管理"),
        ("fraud_order_cnt", "P1", "欺诈订单", "本周内审核取消", "卖家中心 - 订单管理"),
        ("punish_point", "P2", "店铺扣分", "查看明细，制定改进计划", "卖家中心 - 服务等级"),
        ("today_punish_num", "P2", "今日扣分", "复盘处罚原因", "卖家中心 - 服务等级"),
    ]
    for field, prio, name, action, where in item_meta:
        n = safe_int(risk.get(field))
        if n > 0:
            tasks.append({
                "priority": prio, "name": name, "count": n,
                "action": action, "where": where,
                "summary": f"{prio} - {name} {n} 项 → {action}",
            })
    return tasks


def build_risk_health(risk: dict) -> list:
    """即使没有风险，也把合规健康项展开成表，避免报告空白。"""
    risk = risk or {}
    items = [
        ("店铺扣分", "punish_point", "0 分为健康；有扣分需看处罚明细", "卖家中心 - 服务等级"),
        ("今日处罚", "today_punish_num", "0 项为健康；有处罚需当天处理", "卖家中心 - 违规记录"),
        ("知产投诉", "ipr_num", "0 项为健康；有投诉需准备申诉材料", "卖家中心 - 知产保护"),
        ("欺诈订单", "fraud_order_cnt", "0 项为健康；有订单需人工审核", "卖家中心 - 订单管理"),
        ("侵权商品", "infringing_product_cnt", "未返回或 0 需定期用风控入口复扫", "卖家中心 - 商品体检"),
        ("禁售商品", "forbidden_product_cnt", "未返回或 0 需定期用风控入口复扫", "卖家中心 - 商品体检"),
    ]
    out = []
    for name, field, standard, where in items:
        raw = risk.get(field)
        n = safe_int(raw, 0)
        if raw is None:
            status = "未返回"
        elif n == 0:
            status = "正常"
        else:
            status = "需处理"
        out.append({
            "name": name,
            "value": "未返回" if raw is None else raw,
            "status": status,
            "standard": standard,
            "where": where,
        })
    if risk.get("ai_auto_raise_url"):
        out.append({
            "name": "智能风控复扫",
            "value": "可用",
            "status": "建议执行",
            "standard": "本期无显性风险时，也建议点一次智能检测确认潜在侵权",
            "where": "风险诊断 - 智能检测店铺潜在侵权风险",
        })
    return out


def analyze_inquiry_quality(report_data: dict) -> dict:
    """把询盘明细汇总成老板复盘会结论。

    参数:
        report_data: prepare_data.py 产出的标准化报告数据。

    返回:
        dict: 包含 summary、high_quality、low_quality、pending_info、
        followup_risks 和 meeting_actions。

    异常:
        本函数不主动抛异常；缺失数据时返回空列表和降级说明。
    """
    inquiry = report_data.get("inquiry_quality") or {}
    records = [row for row in inquiry.get("records") or [] if isinstance(row, dict)]
    summary = inquiry.get("summary") or {}
    high_quality = [row for row in records if row.get("quality") == "高质量"]
    low_quality = [row for row in records if row.get("quality") == "低质量"]
    pending_info = [row for row in records if row.get("quality") in ("待补信息", "待判断")]
    followup_risks = [row for row in records if row.get("priority") == "P0" or row.get("reply_risks")]
    meeting_actions = []

    for row in followup_risks[:10]:
        meeting_actions.append({
            "priority": row.get("priority") or "P1",
            "customer": row.get("customer"),
            "seller": row.get("seller"),
            "title": f"追 {row.get('seller') or '业务员'}：{row.get('customer') or '客户'} 的高意向跟进",
            "why": row.get("quality_reason") or "高意向客户存在回复或跟进风险",
            "action": row.get("suggested_action") or "当天补回并确认下一步。",
        })
    for row in high_quality[:10]:
        if any(item.get("customer") == row.get("customer") for item in meeting_actions):
            continue
        meeting_actions.append({
            "priority": row.get("priority") or "P1",
            "customer": row.get("customer"),
            "seller": row.get("seller"),
            "title": f"推进高质量询盘：{row.get('customer') or '客户'}",
            "why": row.get("quality_reason") or "买家等级或采购信号较强",
            "action": row.get("suggested_action") or "推进报价、样品或规格确认。",
        })
        if len(meeting_actions) >= 12:
            break

    if not meeting_actions and records:
        meeting_actions.append({
            "priority": "P2",
            "customer": "本周询盘池",
            "seller": "主管",
            "title": "抽样复核本周待判断询盘",
            "why": "系统已返回询盘/质检样本，但高意向信号不足",
            "action": "主管抽样完整会话，统一好询盘口径。",
        })

    return {
        "summary": summary,
        "high_quality": high_quality[:50],
        "low_quality": low_quality[:50],
        "pending_info": pending_info[:50],
        "followup_risks": followup_risks[:50],
        "meeting_actions": meeting_actions,
        "records": records[:100],
    }


# ----------------------------------------------------------------------
# 7. 综合：本周 3 件最该做的事
# ----------------------------------------------------------------------
def generate_top3_actions(prods: dict, kws: dict, funnel_diag: dict, risks: list, report_data: dict, inquiry_diag: dict | None = None) -> list:
    """从真实风险、商品、广告、漏斗异常中抽取最多 3 个行动项。"""
    candidates = []
    diagnosis = report_data.get("diagnosis") or {}
    ads = report_data.get("ads") or {}
    service = report_data.get("service") or {}
    inquiry_diag = inquiry_diag or {}
    is_monthly = (report_data.get("meta") or {}).get("mode") == "monthly"
    period_deadline = "本月内" if is_monthly else "本周内"

    # P0 风险
    for r in risks:
        if r["priority"] == "P0":
            candidates.append({
                "priority": "P0",
                "title": f"处理 {r['name']} {r['count']} 项",
                "why": r["action"],
                "where": r["where"],
                "deadline": "今天",
            })

    # 星级/降星类经营诊断
    diag_text = "；".join([
        str(diagnosis.get("conclusion") or ""),
        str((report_data.get("summary") or {}).get("ai_conclusion") or ""),
    ])
    if "降星" in diag_text or "星级" in diag_text:
        weak_ability = None
        for ability in diagnosis.get("abilities") or []:
            score = safe_float(ability.get("score"))
            if ability_is_weak(ability):
                weak_ability = ability
                break
        weak_text = ""
        if weak_ability:
            kpis = weak_ability.get("kpis") or []
            evidence = "；".join(
                f"{k.get('name')} {k.get('value')} / 下一档 {k.get('next_level_avg')}"
                for k in kpis[:2]
            )
            weak_text = f"；核心短板：{weak_ability.get('ability')} {weak_ability.get('score')}（{evidence}）"
        candidates.append({
            "priority": "P0" if "降星" in diag_text else "P1",
            "title": "处理店铺星级/能力项风险",
            "why": (diag_text + weak_text)[:260],
            "where": "生意助手 - 店铺诊断 - 星级能力项",
            "deadline": "今天" if "降星" in diag_text else period_deadline,
        })

    # 高曝光 0 询盘 / 失血款主图
    if prods.get("bleeding"):
        worst = prods["bleeding"][0]
        candidates.append({
            "priority": "P1",
            "title": f"处理高曝光低询盘商品「{worst['title']}」",
            "why": worst["why"],
            "where": "卖家中心 - 商品管理 - 编辑该商品 - 主图",
            "deadline": "周一前",
        })

    # 服务响应红色预警
    service_warnings = service.get("warnings") or []
    if service_warnings:
        candidates.append({
            "priority": "P0",
            "title": "拉起服务响应纪律",
            "why": "；".join(service_warnings[:2]),
            "where": "询盘 / 消息接待工作台 - 智能回复与超时消息",
            "deadline": "今天",
        })

    for action in (inquiry_diag.get("meeting_actions") or [])[:2]:
        if action.get("priority") == "P0":
            candidates.append({
                "priority": "P0",
                "title": action.get("title") or "补回高意向询盘",
                "why": action.get("why") or "高质量询盘存在跟进风险",
                "where": "询盘 / 消息接待工作台 - 该客户会话",
                "deadline": "今天",
            })

    # 烧钱词
    if kws.get("burning"):
        worst_kw = kws["burning"][0]
        candidates.append({
            "priority": "P1",
            "title": f"暂停 OR 降价烧钱词「{worst_kw['keyword']}」",
            "why": worst_kw["why"],
            "where": "P4P 后台 - 关键词管理",
            "deadline": "周二前",
        })

    # 漏斗反常段 — 严重段升 P0
    for ano in funnel_diag.get("anomalies", []):
        if "🔴 严重" in ano.get("level", ""):
            candidates.append({
                "priority": "P0",
                "title": f"修补漏斗反常段：{ano['stage']}",
                "why": ano["advice"],
                "where": "见 §2 流量诊断详情",
                "deadline": "今天",
            })
        elif "🟡" in ano.get("level", ""):
            candidates.append({
                "priority": "P1",
                "title": f"优化漏斗段：{ano['stage']}",
                "why": ano["advice"],
                "where": "见 §2 流量诊断详情",
                "deadline": period_deadline,
            })

    # 广告账户诊断：只有接口真实返回结论时才生成动作
    ad_text = ads.get("overview_summary") or ads.get("ai_conclusion") or ""
    if ad_text and "未返回" not in ad_text and "不展示" not in ad_text:
        candidates.append({
            "priority": "P1",
            "title": "复盘广告账户诊断结论并调整计划",
            "why": str(ad_text)[:180],
            "where": "P4P 后台 - 账户诊断 / 计划管理",
            "deadline": period_deadline,
        })

    # 印钞款加预算（最容易出 ROI）
    if prods.get("ink_print"):
        best_p = prods["ink_print"][0]
        candidates.append({
            "priority": "P1",
            "title": f"复核「{best_p['title'][:30]}…」是否进入加码测试",
            "why": best_p["why"],
            "where": "P4P 后台 - 单品出价 - 加预算",
            "deadline": period_deadline,
        })

    # 金主词加预算
    if kws.get("gold"):
        best = kws["gold"][0]
        candidates.append({
            "priority": "P1",
            "title": f"复核关键词「{best['keyword']}」是否进入出价测试",
            "why": best["why"],
            "where": "P4P 后台 - 关键词出价",
            "deadline": period_deadline,
        })

    # 潜力款详情页
    if prods.get("potential"):
        p = prods["potential"][0]
        candidates.append({
            "priority": "P2",
            "title": f"潜力款「{p['title']}」详情页加视频/FAQ",
            "why": p["why"],
            "where": "卖家中心 - 商品管理 - 编辑详情页",
            "deadline": period_deadline,
        })

    # 只加入真实数据缺口和有基准支撑的 KPI 异常，不为凑满五条补动作。
    data_quality = report_data.get("data_quality") or {}
    if data_quality.get("status") in ("red", "yellow", "partial"):
        candidates.append({
            "priority": "P0" if data_quality.get("status") == "red" else "P1",
            "title": "复查本期未返回的数据字段",
            "why": f"核心数据覆盖率 {data_quality.get('coverage_rate', 0) * 100:.0f}%，红灯 {data_quality.get('red_count', 0)} 项，黄灯 {data_quality.get('yellow_count', 0)} 项。",
            "where": "数据质量检查",
            "deadline": "今天" if data_quality.get("status") == "red" else period_deadline,
        })

    # 有同口径基准的 KPI 异常可进入动作池。
    for light in kpi_traffic_lights((report_data.get("summary") or {}).get("indicators") or [], []):
        if light.get("light") not in ("🔴", "🟡"):
            continue
        if "缺少同行基准" in str(light.get("diag") or ""):
            continue
        candidates.append({
            "priority": "P1" if light.get("light") == "🔴" else "P2",
            "title": f"提升「{light.get('name')}」指标",
            "why": f"本期 {light.get('value')}；{light.get('diag')}",
            "where": "数据参谋 - 店铺总览 / 商品与投流后台",
            "deadline": period_deadline,
        })

    # 最多返回 5 条；证据不足时允许少于 5 条。
    prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    candidates.sort(key=lambda x: prio_order.get(x["priority"], 9))
    structured = [structure_action(item, "老板") for item in candidates]
    return resolve_action_conflicts(structured)[:5]


# ----------------------------------------------------------------------
# 8. Backlog（按优先级聚合）
# ----------------------------------------------------------------------
def build_backlog(prods: dict, kws: dict, risks: list, funnel_diag: dict, report_data: dict | None = None, geo_diag: dict | None = None, inquiry_diag: dict | None = None) -> dict:
    backlog = {"P0": [], "P1": [], "P2": [], "P3": []}
    report_data = report_data or {}
    geo_diag = geo_diag or {}
    inquiry_diag = inquiry_diag or {}
    is_monthly = (report_data.get("meta") or {}).get("mode") == "monthly"
    review_word = "月检" if is_monthly else "周检"
    next_word = "下月" if is_monthly else "下周"

    # ---- P0 ----
    for r in risks:
        if r["priority"] == "P0":
            backlog["P0"].append(r["summary"])
    # 漏斗严重反常段
    for ano in funnel_diag.get("anomalies", []):
        if "🔴 严重" in ano.get("level", ""):
            backlog["P0"].append(f"修补漏斗「{ano['stage']}」段：当前转化率 {ano['rate_str']} vs 行业 {ano['baseline_str']} — {ano['advice']}")

    # 降星/保星风险必须进入 P0，不只出现在首页。
    diagnosis = report_data.get("diagnosis") or {}
    diag_text = "；".join([
        str(diagnosis.get("conclusion") or ""),
        str((report_data.get("summary") or {}).get("ai_conclusion") or ""),
    ])
    if "降星" in diag_text:
        weak_parts = []
        for ability in diagnosis.get("abilities") or []:
            score = safe_float(ability.get("score"))
            if ability_is_weak(ability):
                kpis = ability.get("kpis") or []
                evidence = "；".join(
                    f"{k.get('name')} {k.get('value')} / 下一档 {k.get('next_level_avg')}"
                    for k in kpis[:2]
                )
                weak_parts.append(f"{ability.get('ability')} {ability.get('score')}：{evidence}")
        detail = "；".join(weak_parts[:2]) if weak_parts else diag_text[:120]
        backlog["P0"].append(f"保星处理：预测星级低于当前，今天进入星级中心领取/处理保星任务（{detail}）")

    service = report_data.get("service") or {}
    for warning in (service.get("warnings") or [])[:3]:
        backlog["P0"].append(f"服务响应止血：{warning}；当天补回超时消息并开启智能回复/值班提醒")
    for item in (inquiry_diag.get("meeting_actions") or [])[:5]:
        if item.get("priority") == "P0":
            backlog["P0"].append(f"高意向询盘补回：{item.get('title')}；{item.get('action')}")

    # ---- P1 ----
    for r in risks:
        if r["priority"] == "P1":
            backlog["P1"].append(r["summary"])
    # 印钞款：直接加预算（具体动作）
    for p in prods.get("ink_print", []):
        backlog["P1"].append(f"复核「{p['title'][:30]}…」加码候选（询盘 {p['fb_num']}, 询盘率 {p['fb_rate_str']}）；幅度需按 ROI 和预算确认")
    # 失血款
    for p in prods.get("bleeding", []):
        backlog["P1"].append(f"改商品「{p['title'][:30]}…」主图（曝光 {p['imps']}, CTR/询盘率 {p['fb_rate_str']}）")
    # 烧钱词
    for k in kws.get("burning", []):
        cost_str = f"{k['cost']:.2f}" if k.get('cost') else "—"
        backlog["P1"].append(f"暂停/降价词「{k['keyword']}」（花费 ${cost_str}，0 询盘）")
    # 金主词加价
    for k in kws.get("gold", []):
        backlog["P1"].append(f"复核关键词「{k['keyword']}」出价测试候选（询盘 {k.get('inquiry', '?')}）；幅度需确认")
    # 潜力词冲首屏
    for k in kws.get("potential", []):
        backlog["P1"].append(f"复核潜力词「{k['keyword']}」的出价测试条件（当前排名 {k.get('rank', '?')}），不默认加价")
    # 漏斗中度反常段（🟡）
    for ano in funnel_diag.get("anomalies", []):
        if "🟡" in ano.get("level", ""):
            backlog["P1"].append(f"优化漏斗「{ano['stage']}」段：转化率 {ano['rate_str']} 低于行业 {ano['baseline_str']}")

    # 星级诊断短板
    for ability in diagnosis.get("abilities") or []:
        score = safe_float(ability.get("score"))
        if ability_is_weak(ability):
            kpis = ability.get("kpis") or []
            evidence = "；".join(
                f"{k.get('name')} {k.get('value')} / 下一档均值 {k.get('next_level_avg')}"
                for k in kpis[:2]
            )
            backlog["P1"].append(f"补齐「{ability.get('ability')}」短板（{ability.get('score')}）：{evidence}")
            break

    for alert in (geo_diag.get("channel_alerts") or []):
        if alert.get("priority") == "P1":
            backlog["P1"].append(alert.get("summary"))
    for item in (inquiry_diag.get("meeting_actions") or [])[:10]:
        if item.get("priority") == "P1":
            backlog["P1"].append(f"询盘推进：{item.get('title')}；{item.get('action')}")

    # 广告诊断结论转任务
    ads = report_data.get("ads") or {}
    for text in (ads.get("diagnosis_conclusions") or [])[:3]:
        backlog["P1"].append(f"广告计划处理：{text}；去 P4P 后台检查对应计划预算、出价和落地商品")

    # ---- P2 ----
    for r in risks:
        if r["priority"] == "P2":
            backlog["P2"].append(r["summary"])
    # 潜力款详情页改造
    for p in prods.get("potential", []):
        backlog["P2"].append(f"潜力款「{p['title'][:30]}…」详情页加 FAQ+视频+规格表（曝光 {p['imps']}, 询盘 {p['fb_num']}）")
    # 拓展词
    for k in kws.get("expand", []):
        backlog["P2"].append(f"测试拓展词「{k['keyword']}」（行业热词，本店未覆盖）")
    for k in kws.get("potential", []):
        backlog["P2"].append(f"检查高消耗/潜力词「{k['keyword']}」落地页（{k.get('rank_label') or '榜单词'}）；按用户确认的周期和停止条件决定是否调价")

    for alert in (geo_diag.get("channel_alerts") or []):
        if alert.get("priority") == "P2":
            backlog["P2"].append(alert.get("summary"))

    market = report_data.get("market") or {}
    for k in (market.get("keyword_market") or [])[:5]:
        backlog["P2"].append(
            f"评估行业热词「{k.get('keyword')}」：曝光指数 {k.get('year_imps_index')}，商机转化率 {k.get('business_rate')}，售卖状态 {k.get('sell_status')}"
        )
    for k in (market.get("next_month_auction") or [])[:5]:
        backlog["P2"].append(
            f"提前看次月资源「{k.get('keyword')}」：{k.get('biz_line')}，状态 {k.get('sell_status')}，标签 {k.get('tags')}"
        )
    for p in (market.get("product_selection_recent_30d") or [])[:3]:
        backlog["P3"].append(
            f"参考行业近30天商品「{p.get('product_name')[:30]}…」做补品方向评估（询盘 {p.get('ab_cnt_30d')}，订单 {p.get('order_cnt_30d')}）"
        )
    # 印钞款主图复制
    for p in prods.get("ink_print", []):
        backlog["P2"].append(f"复制印钞款「{p['title'][:30]}…」主图风格到关联类目商品")

    # ---- P3 ----
    for p in prods.get("zombie", []):
        backlog["P3"].append(f"下架/重写僵尸款「{p['title'][:30]}…」（曝光 {p['imps']}, 0 询盘）")
    # 观察款数据补全
    watch = prods.get("watch", [])
    if watch:
        backlog["P3"].append(f"持续追踪 {len(watch)} 款观察款；按用户确认周期并补齐同行基准后重新分群")

    # 风险健康项即使正常，也给一个低优先级定期动作，报告不留白。
    risk_health = build_risk_health(report_data.get("risk") or {})
    normal_count = sum(1 for r in risk_health if r.get("status") == "正常")
    if normal_count:
        backlog["P3"].append(f"保留合规{review_word}：本期 {normal_count} 个风险项正常，{next_word}继续复扫商品体检和知产入口")

    for priority in backlog:
        backlog[priority] = group_backlog_items(backlog[priority])
    return backlog


_GROUP_PATTERNS = {
    "金主词提价": ["金主词「"],
    "烧钱词止损": ["暂停/降价词「", "暂停词「"],
    "潜力词冲首屏": ["潜力词「"],
    "拓展词测试": ["测试拓展词「"],
    "检查高消耗词": ["检查高消耗", "检查高消耗/潜力词"],
    "印钞款加预算": ["印钞款「"],
    "失血款改图": ["改商品「"],
    "潜力款详情页": ["潜力款「"],
    "僵尸款处理": ["下架/重写僵尸款"],
    "印钞款复制": ["复制印钞款"],
    "询盘推进": ["询盘推进："],
    "广告计划": ["广告计划处理："],
    "服务响应止血": ["服务响应止血："],
    "行业热词评估": ["评估行业热词"],
    "次月资源评估": ["提前看次月资源"],
}


def _extract_quoted(text):
    if "「" in text and "」" in text:
        return text.split("「", 1)[1].split("」", 1)[0].strip()
    return None


def group_backlog_items(items: list[str]) -> list[str]:
    """把同类 backlog 项合并为一条，减少行动清单行数。"""
    groups: dict[str, list[str]] = {}
    ungrouped = []
    for item in items:
        matched = False
        for group_key, patterns in _GROUP_PATTERNS.items():
            if any(p in item for p in patterns):
                groups.setdefault(group_key, []).append(item)
                matched = True
                break
        if not matched:
            ungrouped.append(item)
    result = []
    for group_key, members in groups.items():
        if len(members) == 1:
            result.append(members[0])
        else:
            names = [_extract_quoted(m) for m in members]
            names = [n for n in names if n]
            if names:
                sample = "、".join(n[:20] for n in names[:3])
                suffix = f"等 {len(names)} 个" if len(names) > 3 else ""
                result.append(f"{group_key}：{sample}{suffix}统一处理")
            else:
                result.append(f"{group_key}：{len(members)} 项统一处理")
    result.extend(ungrouped)
    return result


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------
def analyze(report_data: dict) -> dict:
    summary = report_data.get("summary", {}) or {}
    indicators = summary.get("indicators", []) or []
    conv_funnel = summary.get("conversion_funnel", []) or []

    # 行业基准（优先用真实数据，回退用 baseline）
    ctr_base = INDUSTRY_BASELINE["ctr"]
    inquiry_rate_base = INDUSTRY_BASELINE["visitor_to_inquiry"]
    if conv_funnel:
        v = conv_funnel[0]
        if v.get("impsToVisitorRateRivalAvg"):
            ctr_base = safe_float(v["impsToVisitorRateRivalAvg"], ctr_base)
        if v.get("visitorToBusRateRivalAvg"):
            inquiry_rate_base = safe_float(v["visitorToBusRateRivalAvg"], inquiry_rate_base)

    products_top = (report_data.get("products") or {}).get("exposure_top10", []) or []

    # 关键词数据：优先使用 keywords_top30，如果没有则从 products/ads 手动合并
    keywords = report_data.get("keywords_top30", [])
    if not keywords:
        ads_data = report_data.get("ads") or {}
        for kw in ads_data.get("p4p_high_imps_low_clk", []) + ads_data.get("p4p_low_imps_high_clk", []) + ads_data.get("p4p_low_relevance", []):
            keywords.append(kw)
        for kw in (report_data.get("products") or {}).get("high_inquiry_words", []) + \
                  (report_data.get("products") or {}).get("high_p4p_words", []):
            keywords.append(kw)

    hot_industry = (report_data.get("expansion_recommend") or {}).get("expansions", []) or []

    total_store_imps = sum(safe_float(r.get("imps")) for r in
                          ((report_data.get("funnel") or {}).get("daily") or [])
                          if isinstance(r, dict))
    prod_q = tag_products(products_top, ctr_base, inquiry_rate_base, total_store_imps)
    kw_q = tag_keywords(keywords, hot_industry)
    funnel_diag = analyze_funnel(report_data.get("funnel", {}))
    if (report_data.get("meta") or {}).get("mode") == "monthly":
        funnel_diag["summary"] = (funnel_diag.get("summary") or "").replace("本周", "本月")
        for ano in funnel_diag.get("anomalies", []):
            if ano.get("advice"):
                ano["advice"] = ano["advice"].replace("本周", "本月")
    geo_diag = analyze_country_channel(
        report_data.get("region", {}),
        report_data.get("channels", {}),
    )
    inquiry_diag = analyze_inquiry_quality(report_data)
    kpi_lights = kpi_traffic_lights(indicators, conv_funnel)
    risks = normalize_risks(report_data.get("risk", {}))
    top3 = generate_top3_actions(prod_q, kw_q, funnel_diag, risks, report_data, inquiry_diag)
    risk_health = build_risk_health(report_data.get("risk", {}))
    backlog = build_backlog(prod_q, kw_q, risks, funnel_diag, report_data, geo_diag, inquiry_diag)
    executive_status = conservative_status(report_data)

    # 一句话战况
    is_monthly = (report_data.get("meta") or {}).get("mode") == "monthly"
    period_word = "本月" if is_monthly else "本周"
    if executive_status.get("label") == "不可判断":
        one_liner = f"{period_word}投产不可完整判断：{executive_status.get('reason')}"
    elif top3:
        one_liner = f"{period_word}{executive_status.get('label')}：先处理 {top3[0]['problem']}"
    elif funnel_diag.get("anomalies"):
        one_liner = funnel_diag["summary"]
    else:
        one_liner = "本期未发现明显告警；可重点关注主推款的爆款培育与新词测试"

    return {
        "one_liner": one_liner,
        "top3_actions": top3,
        "boss_top5_actions": top3,
        "executive_status": executive_status,
        "kpi_traffic_lights": kpi_lights,
        "funnel_diagnosis": funnel_diag,
        "country_channel": geo_diag,
        "inquiry_quality": inquiry_diag,
        "products_quadrant": prod_q,
        "products_quadrant_meta": PRODUCT_TAGS,
        "keywords_quadrant": kw_q,
        "keywords_quadrant_meta": KEYWORD_TAGS,
        "risks": risks,
        "risk_health": risk_health,
        "backlog": backlog,
        "data_quality": report_data.get("data_quality") or {},
    }


def main():
    if len(sys.argv) < 2:
        print("usage: analyze.py <report_data.json> [<analysis.json>]", file=sys.stderr)
        sys.exit(1)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.parent / "analysis.json"
    rd = json.loads(inp.read_text(encoding="utf-8"))
    result = analyze(rd)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"analysis.json written: {out}")
    # 简短总览
    print(f"  one_liner: {result['one_liner']}")
    print(f"  top3 actions: {len(result['top3_actions'])}")
    print(f"  product quadrants: {[(k, len(v)) for k, v in result['products_quadrant'].items()]}")
    print(f"  keyword quadrants: {[(k, len(v)) for k, v in result['keywords_quadrant'].items()]}")
    print(f"  risks: {len(result['risks'])}")
    print(f"  backlog: {[(k, len(v)) for k, v in result['backlog'].items()]}")


if __name__ == "__main__":
    main()
