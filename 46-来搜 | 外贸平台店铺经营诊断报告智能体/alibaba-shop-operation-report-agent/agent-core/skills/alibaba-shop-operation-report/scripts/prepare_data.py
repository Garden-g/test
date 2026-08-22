#!/usr/bin/env python3
"""
prepare_data.py — 把 MCP 工具的原始 JSON 清洗成 build_docx.py 的入参 schema

用法:
    /usr/bin/python3 prepare_data.py \
        --raw-dir /tmp/raw_xxx \
        --mode weekly|monthly \
        --period-start 2026-04-13 \
        --period-end 2026-04-19 \
        --title-period 2026W16 \
        --output /tmp/report_data.json

`--raw-dir` 必须包含以下文件（按工具名命名）:

  周报模式 (weekly):
    findCustomerShopInfo.json          # 必须
    store_diagnose_brief.json          # 可选
    shop_risk_diagnosis.json           # 必须
    queryCustomerGoodsCateSummary.json # 可选
    data_advisor_shop_region_uv.json   # 可选
    data_advisor_shop_region_imps.json # 可选
    data_advisor_shop_region_ab.json   # 可选
    data_advisor_shop_product.json     # 可选，目标周期多页商品表现
    icbu_ads_hateoas_query_company.json   # 可选，广告账户只读入口/导航
    icbu_ads_hateoas_query_diagnosis.json # 可选，目标周账户诊断
    service_report_weekly_all_data_query.json  # 可选

  月报模式 (monthly):
    findCustomerShopInfo.json          # 必须
    shop_risk_diagnosis.json           # 必须
    queryCustomerGoodsCateSummary.json # 可选
    data_advisor_shop_summary_current.json  # 可选 (本月)
    data_advisor_shop_summary_baseline.json # 可选 (上月)
    data_advisor_shop_region_uv.json
    data_advisor_shop_region_imps.json
    data_advisor_shop_region_ab.json

任何文件缺失都不报错，对应章节降级。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# 不进入老板报告的明细段。服务响应只保留摘要指标，不展开聊天/质检明细。
FORBIDDEN_SEGMENTS = {
    'STORE_COMMUNICATION_DATA_OVERVIEW',
    'STORE_COMMUNICATION_HOT_QUESTION',
    'STORE_COMMUNICATION_OPP',
    'STORE_INFRASTRUCTURE_AB_WEEKLY',
    'STORE_INFRASTRUCTURE_VISITOR_WEEKLY',
    'STORE_INFRASTRUCTURE_RANK_WEEKLY',
    'STORE_INFRASTRUCTURE_TM_WEEKLY',
    'STORE_INFRASTRUCTURE_5MIN_RECOVERY_WEEKLY',
    'STORE_ACCOUNT_USAGE',
    'STORE_ACCOUNT_LOGIN_FREQUENCY',
    'SUPPLY_CHAIN_DATA',
    'SUPPLY_CAPABILITY_DATA',
    'BUYER_DISTRIBUTION_DATA',
    'BUSINESS_ASSISTANT_USAGE_DATA',
}

# 18 个允许的运营段（白名单）
ALLOWED_OPERATION_SEGMENTS = {
    'STORE_DATA_OVERVIEW',
    'STORE_DIAGNOSIS',
    'STORE_CONVERSION_RATE_ANALYSIS',
    'FLOW_SOURCE_CHANNEL_ANALYSIS',
    'EXPOSURE_TOP10_PRODUCT_DATA',
    'HOT_PRODUCT_RECOMMEND',
    'PRODUCT_DATA_OVERVIEW',
    'CATEGORY_EXPANSION_SUGGESTION',
    'BRAND_AD_EFFECT_DATA',
    'BRAND_AD_OPPORTUNITY_NEW_OPPORTUNITY',
    'BRAND_AD_OPPORTUNITY_RENEWAL_WORD',
    'WENDING_AND_TOP_EXPRESS_EFFECT_DATA',
    'P4P_SEARCH_WORD_OPTIMIZ_SUGGESTION',
    'STORE_COMMUNICATION_CONVERSION_OVERVIEW_WEEKLY',
    'STAR_LEVEL_DATA_OVERVIEW',
    'OPPORTUNITY_STAR_LEVEL',
    'OPPORTUNITY_STAR_LEVEL_DATA_OVERVIEW',
    'TRADE_STAR_LEVEL',
    'TRADE_STAR_LEVEL_DATA_OVERVIEW',
    'ACTION_SUGGESTION',
}


def load_json(raw_dir: Path, name: str):
    """读取 raw_dir 下指定文件名的 json，失败/不存在返回 None"""
    p = raw_dir / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[warn] failed to parse {name}: {e}", file=sys.stderr)
        return None


def unwrap_data(raw):
    """兼容 MCP/业务接口的常见包裹层，取出真正的数据节点。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return raw
    for key in ("data", "result", "values"):
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return raw


def first_present(data, *keys):
    """从 dict 中按顺序取第一个非空字段，避免把真实 0 当缺失。"""
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def to_float(value):
    """把数字/百分比字符串尽量转成 float，失败返回 None。"""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, str):
            s = value.strip().replace(",", "")
            if s.endswith("%"):
                return float(s[:-1]) / 100
            return float(s)
        return float(value)
    except (TypeError, ValueError):
        return None


def list_from_segment(segment):
    """把 weekly_all 中可能被 data/list 包裹的段统一成 list。"""
    if not segment:
        return []
    if isinstance(segment, list):
        return segment
    if isinstance(segment, dict):
        for key in ("data", "list", "rows"):
            value = segment.get(key)
            if isinstance(value, list):
                return value
    return []


def find_store_indicator(store_diagnose_raw, keyword, period_start=None, period_end=None):
    """从 store_diagnose_brief 的 indicatorList 里按中文指标名找值。"""
    if not isinstance(store_diagnose_raw, dict):
        return {}
    # 新版工具把业务载荷放在 data；旧快照也可能使用 values。两者都只
    # 是返回载体，不应因为载体变化把真实指标误判为“未返回”。
    carrier = (
        store_diagnose_raw.get("data")
        or store_diagnose_raw.get("values")
        or store_diagnose_raw
    )
    if isinstance(carrier, list):
        weeks = carrier
    elif isinstance(carrier, dict):
        weeks = (
            carrier.get("aiSalesWeekDiagnoseList")
            or carrier.get("weekDiagnoseList")
            or carrier.get("data")
            or []
        )
    else:
        weeks = []
    if not weeks:
        return {}
    selected = None
    if period_start and period_end:
        selected = next(
            (
                week for week in weeks
                if isinstance(week, dict)
                and str(week.get("beginDate") or week.get("startDate") or "")[:10] == period_start
                and str(week.get("endDate") or "")[:10] == period_end
            ),
            None,
        )
    if selected is None and not (period_start and period_end):
        selected = weeks[0] if isinstance(weeks[0], dict) else None
    if not isinstance(selected, dict):
        return {}
    for item in selected.get("indicatorList") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("indicatorName") or item.get("name") or "")
        if keyword in name:
            return item
    return {}


def filter_weekly_all(weekly_all_raw):
    """对 service_report_weekly_all_data_query 返回，只保留运营段"""
    if not weekly_all_raw:
        return {}
    # 当前返回优先使用 data；values 是兼容旧快照的降级载体。
    data_carrier = weekly_all_raw.get("data") if isinstance(weekly_all_raw, dict) else None
    values_carrier = weekly_all_raw.get("values") if isinstance(weekly_all_raw, dict) else None
    report_all = (
        (data_carrier.get("reportAllData") if isinstance(data_carrier, dict) else None)
        or (values_carrier.get("reportAllData") if isinstance(values_carrier, dict) else None)
        or weekly_all_raw.get('reportAllData')
        or weekly_all_raw
    )
    if not isinstance(report_all, dict):
        return {}
    cleaned = {}
    dropped = []
    for k, v in report_all.items():
        if k in FORBIDDEN_SEGMENTS:
            dropped.append(k)
            continue
        if k in ALLOWED_OPERATION_SEGMENTS:
            cleaned[k] = v
        else:
            # 未知段：默认丢弃，保险
            dropped.append(k)
    if dropped:
        print(f"[info] dropped {len(dropped)} non-operation segments: {dropped[:10]}",
              file=sys.stderr)
    return cleaned


def build_meta(args, shop_data):
    """组装封面 meta"""
    company = shop_data.get('客户公司名称') if shop_data else None
    login_id = shop_data.get('客户登录id') if shop_data else None
    industry = '-'
    if shop_data:
        lv1 = shop_data.get('客户主营一级行业') or ''
        lv2 = shop_data.get('客户主营二级行业') or ''
        lv3 = shop_data.get('客户主营三级行业') or ''
        industry = '/'.join([s for s in [lv1, lv2, lv3] if s]) or '-'
    return {
        "company_name": company or '未知店铺',
        "login_id": login_id or '-',
        "industry": industry,
        "period_start": args.period_start,
        "period_end": args.period_end,
        "mode": args.mode,
        "title_period": args.title_period,
    }


def build_summary_weekly(
    weekly_segments,
    store_diagnose_raw=None,
    period_start=None,
    period_end=None,
):
    """周报：从 weekly_all 段构造店铺总览"""
    overview = weekly_segments.get('STORE_DATA_OVERVIEW', {}) or {}
    diagnosis = weekly_segments.get('STORE_DIAGNOSIS', {}) or {}
    if isinstance(diagnosis, dict) and isinstance(diagnosis.get('data'), dict):
        diagnosis = diagnosis.get('data') or {}

    def ind(name, prefix, *, fallback=None):
        value = first_present(overview, f'{prefix}Value', prefix)
        if value in (None, "") and fallback:
            value = fallback.get("indicatorValue") or fallback.get("value")
        return {
            "name": name,
            "value": value,
            "cycle_crc": first_present(overview, f'{prefix}CycleCrc', f'{prefix}Crc') or (fallback or {}).get("cycleCRC"),
            "rival_avg": overview.get(f'{prefix}RivalAvg'),
            "rival_good": overview.get(f'{prefix}RivalGood'),
            "vs_avg": (fallback or {}).get("valueVsAvg"),
        }

    return {
        "indicators": [
            ind(
                '全店曝光量',
                'totalImpsCnt',
                fallback=find_store_indicator(
                    store_diagnose_raw,
                    '全店曝光量',
                    period_start,
                    period_end,
                ),
            ),
            ind('搜索曝光', 'seImpsCnt'),
            ind('活动曝光', 'campImpsCnt'),
            ind('访客/PV', 'pvCnt'),
            ind('搜索点击', 'seClkCnt'),
            ind('商机数', 'abCnt'),
            ind('商机转化率', 'uvAbRate'),
            ind('订单数', 'crtOrdCnt'),
            ind('支付转化率', 'uvPayordRate'),
        ],
        "conversion_funnel": weekly_segments.get('STORE_CONVERSION_RATE_ANALYSIS', []) or [],
        "ai_conclusion": diagnosis.get('conclusion', '') or diagnosis.get('summary', ''),
        "star_level": diagnosis.get('starLevel', '') or '',
        "down_star_risk": diagnosis.get('downStarRisk', '') or '',
        "advice": diagnosis.get('advice', '') or '',
    }


def build_summary_monthly(current_summary, baseline_summary):
    """月报：从 data_advisor_shop_summary 构造"""
    if not current_summary:
        return None
    # data_advisor_shop_summary 返回结构: {"result": {...}} 或 {...}
    cur = unwrap_data(current_summary) or {}
    base = unwrap_data(baseline_summary) or {}
    if isinstance(cur, list):
        cur = cur[0] if cur and isinstance(cur[0], dict) else {}
    if isinstance(base, list):
        base = base[0] if base and isinstance(base[0], dict) else {}
    if isinstance(cur, dict) and isinstance(cur.get("data"), dict):
        cur = cur["data"]
    if isinstance(base, dict) and isinstance(base.get("data"), dict):
        base = base["data"]

    def get(d, *keys, default=None):
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d if d is not None else default

    def crc(cur_v, base_v):
        if cur_v is None or base_v in (None, 0):
            return None
        try:
            return (float(cur_v) - float(base_v)) / float(base_v)
        except (TypeError, ValueError):
            return None

    def ind(name, key):
        cur_v = cur.get(key) if isinstance(cur, dict) else None
        base_v = base.get(key) if isinstance(base, dict) else None
        return {
            "name": name,
            "value": cur_v,
            "cycle_crc": crc(cur_v, base_v),
            "rival_avg": cur.get(key + 'RivalAvg') if isinstance(cur, dict) else None,
            "rival_good": cur.get(key + 'RivalGood') if isinstance(cur, dict) else None,
        }

    se_imps = cur.get('seImpsCnt') if isinstance(cur, dict) else None
    camp_imps = cur.get('campImpsCnt') if isinstance(cur, dict) else None
    total_imps = (to_float(se_imps) or 0) + (to_float(camp_imps) or 0)
    total_imps = total_imps if total_imps else None

    return {
        "indicators": [
            {"name": "总曝光", "value": total_imps, "cycle_crc": None, "rival_avg": None, "rival_good": None},
            ind('搜索曝光', 'seImpsCnt'),
            ind('活动曝光', 'campImpsCnt'),
            ind('访客UV', 'uvCnt'),
            ind('浏览PV', 'pvCnt'),
            ind('搜索点击', 'seClkCnt'),
            ind('商机数', 'abCnt'),
            ind('订单数', 'crtOrdCnt'),
        ],
        "conversion_funnel": [],
        "ai_conclusion": '月报模式无 AI 周诊断结论，详见广告与商品章节。',
        "star_level": '',
        "down_star_risk": '',
        "advice": '',
    }


def build_region(uv_raw, imps_raw, ab_raw):
    """3 张地域表"""
    def parse(raw, value_key, rate_key):
        if not raw:
            return []
        # data_advisor_shop_region 返回: {"data": [...]} 或 {"result": {"data": [...]}} 或直接 [...]
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            rows = (
                raw.get('data')
                or (raw.get('result', {}) or {}).get('data')
                or (raw.get('values', {}) or {}).get('data')
                or []
            )
        else:
            rows = []
        if not isinstance(rows, list):
            return []
        out = []
        for r in rows[:10]:
            if not isinstance(r, dict):
                continue
            out.append({
                "country": r.get('countryName') or r.get('country'),
                "region": r.get('regionName') or r.get('region') or '-',
                "value": first_present(r, value_key, 'countryUv', 'countryImps', 'countryAb',
                                       'countryTotalImpsCnt', 'countryTotalBusCnt',
                                       'totalImpsCnt', 'totalBusCnt', 'uv', 'value', 'cnt'),
                "rate": first_present(r, rate_key, 'countryUvRate', 'countryImpsRate',
                                      'countryAbRate', 'rate'),
                "cycle_crc": first_present(r, 'cycleCrc', 'countryUvCycleCrc',
                                           'countryImpsCycleCrc', 'countryAbCycleCrc'),
            })
        return out

    return {
        "uv_top": parse(uv_raw, 'countryUv', 'countryUvRate'),
        "imps_top": parse(imps_raw, 'countryImps', 'countryImpsRate'),
        "ab_top": parse(ab_raw, 'countryAb', 'countryAbRate'),
    }


def unwrap_ads_diagnosis(ads_diag):
    """提取 HATEOAS 广告诊断的真实业务对象。

    当前接口返回 ``data.data[0].result``。旧版解析只停在
    ``data.data[0]``，因此外层调用虽然成功，广告概览、诊断结论和问题
    计划仍全部丢失。公司入口实体只有 companyId/memberId，不应被误判
    为已经拿到诊断数据。
    """
    if not isinstance(ads_diag, dict):
        return {}
    result = ads_diag.get("data") or ads_diag.get("result") or ads_diag
    if isinstance(result, dict) and result.get("code") == 410:
        return {}
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        rows = result.get("data") or []
        result = rows[0] if rows and isinstance(rows[0], dict) else {}
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        result = result["result"]
    if not isinstance(result, dict):
        return {}
    business_keys = {
        "overviewSummary", "summary", "diagnosisConclusions",
        "problemCampaigns", "campaigns", "conclusion",
    }
    return result if business_keys.intersection(result) else {}


def ads_diagnosis_metric_rows(overview_summary):
    """把账户诊断摘要中的四个核心指标转成结构化行。"""
    if not isinstance(overview_summary, str):
        return []
    patterns = (
        ("账户总花费", r"账户花费\s*([0-9]+(?:\.[0-9]+)?)"),
        ("账户广告点击", r"点击量\s*([0-9]+(?:\.[0-9]+)?)"),
        ("账户广告商机", r"商机量\s*([0-9]+(?:\.[0-9]+)?)"),
        ("账户广告商机成本", r"商机成本\s*([0-9]+(?:\.[0-9]+)?)"),
    )
    rows = []
    for name, pattern in patterns:
        match = re.search(pattern, overview_summary)
        if match:
            rows.append({"name": name, "value": float(match.group(1)), "source": "账户诊断"})
    return rows


def build_ads_weekly(weekly_segments, ads_diag, summary_indicators):
    """周报广告"""
    p4p_sugg = weekly_segments.get('P4P_SEARCH_WORD_OPTIMIZ_SUGGESTION', {}) or {}
    if isinstance(p4p_sugg, dict):
        p4p_data = p4p_sugg.get('data', p4p_sugg)
    else:
        p4p_data = {}
    brand_data = weekly_segments.get('BRAND_AD_EFFECT_DATA', {}) or {}
    if isinstance(brand_data, dict) and isinstance(brand_data.get('data'), dict):
        brand_data = brand_data.get('data') or {}

    # 从 weekly STORE_DATA_OVERVIEW 拿 P4P 概览（已被 build_summary_weekly 共用）
    overview = weekly_segments.get('STORE_DATA_OVERVIEW', {}) or {}
    ads_overview = [
        {"name": "P4P花费", "value": overview.get('p4pCostValue'),
         "cycle_crc": overview.get('p4pCostCycleCrc'),
         "rival_avg": overview.get('p4pCostRivalAvg')},
        {"name": "P4P点击", "value": overview.get('p4pClkValue'),
         "cycle_crc": overview.get('p4pClkCycleCrc')},
        {"name": "P4P CPC", "value": overview.get('p4pCpcValue'),
         "cycle_crc": overview.get('p4pCpcCycleCrc')},
    ]

    # AI 诊断 + 问题计划
    ai_concl = '广告诊断接口未返回结论。'
    problem_campaigns = []
    diagnosis_conclusions = []
    overview_summary = None
    ads_source_available = False
    if ads_diag:
        result = unwrap_ads_diagnosis(ads_diag)
        ads_source_available = bool(result)
        overview_summary = (result or {}).get('overviewSummary') or (result or {}).get("summary")
        diagnosis_conclusions = (result or {}).get('diagnosisConclusions') or []
        ai_concl = (overview_summary or
                    '；'.join(str(x) for x in diagnosis_conclusions[:3]) or
                    (result or {}).get('conclusion') or
                    (result or {}).get('summary') or ai_concl)
        problem_campaigns = ((result or {}).get('problemCampaigns') or
                             (result or {}).get('campaigns') or [])[:10]
    account_overview = ads_diagnosis_metric_rows(overview_summary)

    def safe_brand(d):
        d = d or {}
        imps = first_present(d, 'impsCnt', 'imps', 'showCnt', 'topAdImpsCnt')
        clk = first_present(d, 'clkCnt', 'clk', 'clickCnt', 'topAdClkCnt')
        cost = first_present(d, 'cost', 'costAmt')
        imps_num = to_float(imps)
        clk_num = to_float(clk)
        return {
            "imps": imps,
            "clk": clk,
            "cost": cost,
            "ctr": (clk_num / imps_num) if (clk_num is not None and imps_num) else None,
        }

    top_brand = brand_data.get('topBrandEffectData') or brand_data.get('topBrandEffect') or {}
    wending_brand = brand_data.get('wendingBrandEffectData') or brand_data.get('wendingBrandEffect') or {}

    return {
        "overview": account_overview + ads_overview,
        "ai_conclusion": ai_concl,
        "overview_summary": overview_summary,
        "diagnosis_conclusions": diagnosis_conclusions,
        "source_available": ads_source_available,
        "problem_campaigns": [
            {"campaign_id": c.get('campaignId'), "campaign_name": c.get('campaignName'),
             "problem": c.get('problem') or c.get('diagnosis')}
            for c in problem_campaigns
        ],
        "p4p_high_imps_low_clk": (p4p_data.get('HIGH_EXPOSURE_LOW_CLICK') or p4p_data.get('highImpsLowClk') or [])[:5],
        "p4p_low_imps_high_clk": (p4p_data.get('LOW_EXPOSURE_HIGH_CLICK') or p4p_data.get('lowImpsHighClk') or [])[:5],
        "p4p_low_relevance": (p4p_data.get('LOW_RELEVANCE') or p4p_data.get('lowRelevance') or [])[:5],
        "brand_top": safe_brand(top_brand),
        "brand_wending": safe_brand(wending_brand),
    }


def build_ads_monthly(current_summary):
    """月报广告（降级：仅展示账户级指标）"""
    if not current_summary:
        return {
            "overview": [],
            "ai_conclusion": "月报模式不展示广告 AI 诊断（接口仅支持 7 天窗口），如需详细诊断请切换周报。",
            "problem_campaigns": [],
            "p4p_high_imps_low_clk": [],
            "p4p_low_imps_high_clk": [],
            "p4p_low_relevance": [],
            "brand_top": {},
            "brand_wending": {},
        }
    cur = unwrap_data(current_summary) or {}
    if isinstance(cur, list):
        cur = cur[0] if cur and isinstance(cur[0], dict) else {}
    return {
        "overview": [
            {"name": "P4P曝光", "value": cur.get('p4pImpsCnt') if isinstance(cur, dict) else None},
            {"name": "P4P点击", "value": cur.get('p4pClkCnt') if isinstance(cur, dict) else None},
            {"name": "搜索点击", "value": cur.get('seClkCnt') if isinstance(cur, dict) else None},
        ],
        "ai_conclusion": "月报模式不展示词级/计划级 AI 诊断（接口仅支持 7 天窗口），详细广告诊断请回复'出周报'查看。",
        "problem_campaigns": [],
        "p4p_high_imps_low_clk": [],
        "p4p_low_imps_high_clk": [],
        "p4p_low_relevance": [],
        "brand_top": {},
        "brand_wending": {},
    }


def product_lookup_from_raw(raw_dir):
    """读取 list_products_*.json，按商品标题建立标题 -> 商品 ID/详情映射。"""
    lookup = {}
    for path in sorted(raw_dir.glob("list_products_*.json")):
        raw = load_json(raw_dir, path.name)
        rows = extract_result_items(raw)
        if not rows and isinstance(raw, dict) and isinstance(raw.get("data"), list):
            rows = raw.get("data") or []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            title_node = row.get("title") or {}
            title = (
                title_node.get("defaultText")
                if isinstance(title_node, dict)
                else row.get("subject") or row.get("productName")
            )
            if not title:
                continue
            key = str(title).strip().lower()
            lookup[key] = {
                "product_id": row.get("productId") or row.get("id"),
                "title": title,
                "category_id": ((row.get("categoryQueryResultDTO") or {}).get("leafId")),
            }
    return lookup


def lookup_product(product_lookup, subject):
    """按完整标题或前缀模糊匹配商品 lookup。"""
    if not subject:
        return {}
    key = str(subject).strip().lower()
    if key in product_lookup:
        return product_lookup[key]
    for title, value in product_lookup.items():
        if key[:80] and (key[:80] in title or title[:80] in key):
            return value
    return {}


def build_products(
    weekly_segments,
    shop_info,
    cate_summary,
    product_lookup=None,
    product_performance=None,
):
    """商品表现（兼容周月）"""
    product_lookup = product_lookup or {}
    def get_data(seg):
        if not seg: return []
        return seg if isinstance(seg, list) else seg.get('data', [])

    prod_overview = get_data(weekly_segments.get('EXPOSURE_TOP10_PRODUCT_DATA'))
    product_data_overview = weekly_segments.get('PRODUCT_DATA_OVERVIEW') or {}
    if isinstance(product_data_overview, dict) and isinstance(product_data_overview.get('data'), dict):
        product_data_overview = product_data_overview.get('data') or {}
    hot_rec = get_data(weekly_segments.get('HOT_PRODUCT_RECOMMEND'))
    shop_full = (shop_info or {}).get('result') or (shop_info or {})

    def words_from(key):
        node = shop_full.get(key, {}) or {}
        if not isinstance(node, dict): return []
        data = node.get('data', [])
        if isinstance(data, dict):
            return data.get('wordList') or data.get('list') or data.get('data') or []
        return data or []

    if isinstance(cate_summary, list):
        cate_rows = cate_summary
    elif isinstance(cate_summary, dict):
        cate_rows = cate_summary.get('result', cate_summary) or []
    else:
        cate_rows = []
    if not isinstance(cate_rows, list):
        cate_rows = []

    stage_labels = {
        "LOW_QUALITY": "低质品",
        "NORMAL": "普通品",
        "POTENTIAL": "潜力品",
        "PLATFORM_GOOD": "平台优品",
        "PLATFORM_SUPER": "平台爆品",
    }
    product_layers = []
    if isinstance(product_data_overview, dict):
        for layer in product_data_overview.get("productLayer") or []:
            if not isinstance(layer, dict):
                continue
            code = layer.get("stageCode")
            product_layers.append({
                "stage_code": code,
                "stage_name": stage_labels.get(code, code or "未知层级"),
                "prod_cnt": layer.get("prodCnt"),
                "prod_cnt_ratio": layer.get("prodCntRatio"),
                "cate_avg_ratio": layer.get("cateAvgProdCntRatio"),
                "main_cate_avg_ratio": layer.get("mainCateAvgProdCntRatio"),
                "avg_uv_30d": layer.get("avgDuvCnt30d"),
                "avg_inquiry_90d": layer.get("avgWideFbUv90d"),
                "avg_order_90d": layer.get("avgPbCnt90d"),
            })

    top5_categories = []
    if isinstance(product_data_overview, dict):
        for row in product_data_overview.get("top5Category") or []:
            if not isinstance(row, dict):
                continue
            top5_categories.append({
                "type": row.get("type"),
                "visitors": row.get("visitors"),
                "views": row.get("views"),
                "clicks": row.get("clicks"),
                "inquiries": row.get("inquiries"),
                "inquiries_rate": row.get("inquiriesRate"),
                "total": row.get("total"),
            })

    shelf_raw = ((shop_full.get('客户店铺橱窗商品列表', {}) or {}).get('data', {})) or {}
    shelf_items = shelf_raw.get('items') if isinstance(shelf_raw, dict) else []
    shelf_items = shelf_items or []
    supply_summary = []
    if cate_rows:
        supply_summary = [
            {"lv1": c.get('cateLv1Desc'), "lv2": c.get('cateLv2Desc'),
             "lv3": c.get('cateLv3Desc'), "count": c.get('count')}
            for c in cate_rows[:10]
        ]

    return {
        "performance_rows": product_performance or [],
        "exposure_top10": [
            {"rank": i + 1,
             "subject": p.get('subject'),
             "product_id": p.get('productId') or p.get('product_id') or lookup_product(product_lookup, p.get('subject')).get("product_id"),
             "image": p.get('prodImage') or p.get('image'),
             "is_showcase": p.get('isShowcase') == 'Y',
             "imps": p.get('sumProdShowNum') or p.get('exposure') or p.get('imps'),
             "fb_num": p.get('sumProdFbNum') or p.get('inquiry'),
             "fb_uv": p.get('atmFbUv'),
             "fb_rate": p.get('sumProdFbRate'),
             "clk": p.get('click') or p.get('clk'),
             "ab": p.get('abCnt') or p.get('ab')}
            for i, p in enumerate(prod_overview[:10])
        ],
        "hot_recommend": [{"subject": h.get('subject')} for h in hot_rec[:10]],
        "overview": {
            "product_layers": product_layers,
            "total_products": sum(int(to_float(x.get("prod_cnt")) or 0) for x in product_layers) or None,
        },
        "top5_categories": top5_categories,
        "high_p4p_words": [
            {"keyword": w.get('keyword'),
             "cost": (w.get('dynamicRecInfo') or {}).get('cost_ratio') or w.get('cost'),
             "clk": w.get('clk') or 0, "imps": w.get('imps') or 0}
            for w in words_from('店铺高p4p词列表')[:10]
        ],
        "high_traffic_words": [
            {"keyword": w.get('keyword'), "uv": w.get('uv') or 0,
             "clk": w.get('clk') or 0, "imps": w.get('imps') or 0}
            for w in words_from('店铺高引流词列表')[:10]
        ],
        "high_inquiry_words": [
            {"keyword": w.get('keyword'), "inquiry": w.get('inquiry') or 0,
             "clk": w.get('clk') or 0, "imps": w.get('imps') or 0}
            for w in words_from('店铺高询盘词列表')[:10]
        ],
        "categories": supply_summary,
        "shelf_products": [
            {
                "name": item.get("橱窗商品名称"),
                "product_id": lookup_product(product_lookup, item.get("橱窗商品名称")).get("product_id"),
                "position": item.get("橱窗商品展示位置"),
                "category": item.get("橱窗商品类目"),
            }
            for item in shelf_items[:20]
            if isinstance(item, dict)
        ],
        "shelf_total": shelf_raw.get("count") if isinstance(shelf_raw, dict) else len(shelf_items),
        "shelf_concentration": '-',
    }


def build_product_performance(raw, period_start, period_end):
    """把本次运行的多页商品数据规范为经营分析行。

    只有 canonical 文件中的起止日期与报告完全一致时才接入，避免上一轮
    或当前日商品首屏混进历史自然周。
    """
    if not isinstance(raw, dict):
        return []
    source_start = str(raw.get("periodStart") or raw.get("period_start") or "")[:10]
    source_end = str(raw.get("periodEnd") or raw.get("period_end") or "")[:10]
    if source_start != period_start or source_end != period_end:
        return []
    rows = raw.get("data")
    if not isinstance(rows, list):
        return []
    normalized = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append({
            "rank": index,
            "subject": first_present(item, "subject", "prodName", "fullName", "productName"),
            "product_id": first_present(item, "id", "productId", "prodId"),
            "image": first_present(item, "prodImage", "image"),
            "is_showcase": first_present(item, "isShowcase", "is_showcase") in (True, "Y", "true", 1),
            "imps": first_present(item, "sumProdShowNum", "totalImpsCnt", "views"),
            "fb_num": first_present(item, "sumProdFbNum", "inquiries"),
            "fb_uv": first_present(item, "atmFbUv", "mcFbUv"),
            "fb_rate": first_present(item, "sumProdFbRate", "inquiriesRates"),
            "clk": first_present(item, "sumProdClickNum", "totalClkCnt", "clicks"),
            "ab": first_present(item, "abCnt30d", "abCnt"),
            "source_dates": item.get("_sourceDates") or [],
        })
    return normalized


# ---------- 以下为详细化新增 builder ----------

def build_funnel(weekly_segments, period_start=None, period_end=None):
    """构造严格落在报告周期内的业务漏斗。

    如果源行带日期，就只保留用户请求周期内的行。这样即使服务周报返回了
    相邻周，也不会再用“最后七行”冒充指定周期。
    """
    if not weekly_segments:
        return None
    conv = weekly_segments.get('STORE_CONVERSION_RATE_ANALYSIS') or []
    if not isinstance(conv, list):
        conv = []
    dated_rows = []
    undated_rows = []
    for item in conv:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("statDate") or item.get("statsDate")
        parsed_date = None
        if raw_date not in (None, ""):
            try:
                parsed_date = datetime.fromisoformat(str(raw_date)[:10]).date()
            except ValueError:
                parsed_date = None
        (dated_rows if parsed_date else undated_rows).append((parsed_date, item))

    selected_rows = conv[-7:] if len(conv) > 7 else conv
    if dated_rows and period_start and period_end:
        start = datetime.fromisoformat(str(period_start)[:10]).date()
        end = datetime.fromisoformat(str(period_end)[:10]).date()
        selected_rows = [item for item_date, item in dated_rows if start <= item_date <= end]
    elif dated_rows:
        selected_rows = [item for _, item in sorted(dated_rows, key=lambda pair: pair[0])[-7:]]

    # 分日明细：有日期时严格按周期；完全无日期时才保留原有降级逻辑。
    daily = []
    for it in selected_rows:
        if not isinstance(it, dict):
            continue
        shop_pv = first_present(it, 'shopPv', 'visitorUv', 'detailUv')
        imps_to_visitor_rate = to_float(it.get('impsToVisitorRate'))
        estimated_imps = None
        if shop_pv not in (None, "") and imps_to_visitor_rate and imps_to_visitor_rate > 0:
            estimated_imps = float(shop_pv) / imps_to_visitor_rate
        daily.append({
            'date': it.get('statDate') or it.get('statsDate'),
            'imps': first_present(it, 'imps', 'showCnt') or estimated_imps,
            'visitor_uv': shop_pv,
            'fb_uv': it.get('fbUv'),
            'fb_count': it.get('busCount') or it.get('fbCount'),
            'order_count': it.get('orderCount'),
            'fb_rate': it.get('visitorToBusRate') or it.get('uvAbRate'),
            'order_rate': it.get('busToOrdRate'),
        })
    # 行业对标卡片（取最后一行作为代表）
    last = selected_rows[-1] if selected_rows else {}
    benchmark = []
    for label, code in [
        ('曝光→访客转化率', 'impsToVisitorRate'),
        ('访客→商机率', 'visitorToBusRate'),
        ('询盘→订单率', 'busToOrdRate'),
    ]:
        if isinstance(last, dict):
            benchmark.append({
                'metric': label,
                'shop': last.get(code),
                'rival_avg': last.get(code + 'RivalAvg'),
                'rival_good': last.get(code + 'RivalGood'),
            })
    # 漏斗收口（汇总 7 天）
    def _sum(field):
        s = 0
        n = 0
        for d in daily:
            v = d.get(field)
            if v is None:
                continue
            try:
                s += float(v)
                n += 1
            except Exception:
                pass
        return s if n else None
    funnel_total = {
        'imps': _sum('imps'),
        'visitor_uv': _sum('visitor_uv'),
        'fb_uv': _sum('fb_count'),
        'order_count': _sum('order_count'),
    }
    return {
        'daily': daily,
        'benchmark': benchmark,
        'funnel_total': funnel_total,
        'source_dates': [str(item.get("statDate") or item.get("statsDate"))[:10] for item in selected_rows if isinstance(item, dict) and (item.get("statDate") or item.get("statsDate"))],
        'available_source_dates': [
            item_date.isoformat() for item_date, _ in sorted(dated_rows, key=lambda pair: pair[0])
        ],
        'requested_period': {
            'start': period_start,
            'end': period_end,
        },
    }


def build_monthly_funnel(day_summary_raw):
    """月报：用 data_advisor_shop_summary(day) 构造月度每日趋势与真实漏斗。"""
    rows = unwrap_data(day_summary_raw) or []
    if isinstance(rows, dict):
        rows = rows.get("data") or []
    if not isinstance(rows, list):
        return None
    daily = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        se_imps = to_float(it.get("seImpsCnt")) or 0
        camp_imps = to_float(it.get("campImpsCnt")) or 0
        daily.append({
            "date": it.get("statDate"),
            "imps": se_imps + camp_imps,
            "visitor_uv": it.get("uvCnt"),
            "pv": it.get("pvCnt"),
            "fb_count": it.get("abCnt"),
            "order_count": it.get("crtOrdCnt"),
            "search_click": it.get("seClkCnt"),
        })
    return {
        "daily": daily,
        "benchmark": [
            {"metric": "曝光→访客转化率", "shop": None, "rival_avg": None, "rival_good": None},
            {"metric": "访客→商机率", "shop": None, "rival_avg": None, "rival_good": None},
            {"metric": "商机→订单率", "shop": None, "rival_avg": None, "rival_good": None},
        ],
        "funnel_total": {},
    }


def build_channels(weekly_segments):
    """流量渠道分析（FLOW_SOURCE_CHANNEL_ANALYSIS）"""
    if not weekly_segments:
        return None
    flow = weekly_segments.get('FLOW_SOURCE_CHANNEL_ANALYSIS') or []
    if not isinstance(flow, list):
        return None
    rows = []
    for it in flow:
        if not isinstance(it, dict):
            continue
        rows.append({
            'channel': it.get('channelType'),
            'detail_uv': it.get('detailUv'),
            'detail_uv_chg': it.get('detailUvCycleCrc'),
            'tm_uv': it.get('tmUv'),
            'tm_uv_chg': it.get('tmUvCycleCrc'),
            'fb_uv': it.get('fbUv'),
            'fb_uv_chg': it.get('fbUvCycleCrc'),
            'uv_ab_rate': it.get('uvAbRate'),
            'uv_ab_rate_chg': it.get('uvAbRateCycleCrc'),
        })
    return {'rows': rows}


def build_brand_ad_opportunity(weekly_segments):
    """品牌广告关键词机会（BRAND_AD_OPPORTUNITY_NEW_OPPORTUNITY）"""
    if not weekly_segments:
        return None
    bao = weekly_segments.get('BRAND_AD_OPPORTUNITY_NEW_OPPORTUNITY') or {}
    if not isinstance(bao, dict):
        return None
    def _norm(items):
        out = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            out.append({
                'keyword': it.get('keyword'),
                'channel': it.get('channel'),
                'base_price': it.get('baseLocalPrice'),
                'local_price': it.get('localPrice'),
                'discount': it.get('discount'),
                'currency': it.get('currency'),
                'advice': it.get('purchaseAdvice'),
                'reasons': it.get('recReasons') or [],
            })
        return out
    return {
        'top_ranking': _norm(bao.get('topRankingInfoVoList'))[:10],
        'wending_new': _norm(bao.get('wendingNewOpportunityInfoVoList'))[:10],
    }


def build_diagnosis(weekly_segments):
    """经营诊断（STORE_DIAGNOSIS + STAR_LEVEL_DATA_OVERVIEW）"""
    if not weekly_segments:
        return None
    diag = weekly_segments.get('STORE_DIAGNOSIS') or {}
    star = weekly_segments.get('STAR_LEVEL_DATA_OVERVIEW') or {}
    if not isinstance(diag, dict):
        diag = {}
    if not isinstance(star, dict):
        star = {}
    abilities = []
    for it in (diag.get('starAbilityVOList') or []):
        if not isinstance(it, dict):
            continue
        kpis = []
        for k in (it.get('starIndicatorVOList') or [])[:3]:
            if not isinstance(k, dict):
                continue
            kpis.append({
                'name': k.get('indicatorName'),
                'value': k.get('indicatorValue'),
                'next_level_avg': k.get('indicatorNextLevelAvgValue'),
            })
        abilities.append({
            'ability': it.get('abilityItem'),
            'score': it.get('abilityItemValue') or it.get('abilityItemPureValue'),
            'star': it.get('abilityStarLevel'),
            'kpis': kpis,
        })
    advices = []
    for it in (diag.get('starAdviceVOList') or [])[:8]:
        if not isinstance(it, dict):
            continue
        advices.append({
            'indicator': it.get('indicatorName'),
            'details': it.get('adviceDetails') or [],
        })
    # 星级总分 + 轨道
    star_overview = {
        'star_level': (star.get('starLevelDataV2Dto') or {}).get('starLevel'),
        'star_score': (star.get('starLevelDataV2Dto') or {}).get('starScore'),
        'tracks': [t.get('trackName') if isinstance(t, dict) else None
                   for t in (star.get('trackList') or [])][:4],
    }
    return {
        'star_overview': star_overview,
        'abilities': abilities,
        'advices': advices,
        'conclusion': diag.get('conclusion'),
    }


def build_service_summary(weekly_segments):
    """服务力老板摘要，只保留响应纪律指标，不展开沟通明细。"""
    if not weekly_segments:
        return None
    seg = weekly_segments.get('STORE_COMMUNICATION_CONVERSION_OVERVIEW_WEEKLY') or {}
    if not isinstance(seg, dict):
        return None
    quality = seg.get('sellerChatQualityCheckDto') or {}
    week = seg.get('storeCommunicationDataForWeekDTO') or {}
    if not isinstance(quality, dict):
        quality = {}
    if not isinstance(week, dict):
        week = {}

    first_5 = to_float(week.get('selfFst5minReplyRate30d'))
    avg_reply = to_float(week.get('selfAvgReplyTime30d'))
    over_12h = quality.get('replyOver12hCount')
    offline = quality.get('offlineMsgCount')
    not_follow = quality.get('notFollowCount')
    repeat = quality.get('repeatReplyCount')

    warnings = []
    if first_5 is not None:
        warnings.append(f"30天首次5分钟回复率 {first_5 * 100:.1f}%；需对照平台规则、店铺历史或用户目标判断")
    if avg_reply is not None:
        warnings.append(f"30天平均回复时长 {avg_reply:.2f} 小时；需对照平台规则、店铺历史或用户目标判断")
    if to_float(over_12h) and to_float(over_12h) > 0:
        warnings.append(f"上周 12h+ 回复 {int(to_float(over_12h))} 条；按买家优先级和平台服务规则安排复查")

    return {
        "first_5min_reply_rate_30d": first_5,
        "avg_reply_time_30d": avg_reply,
        "reply_over_12h_count": over_12h,
        "offline_msg_count": offline,
        "not_follow_count": not_follow,
        "repeat_reply_count": repeat,
        "warnings": warnings,
        "status": "red" if warnings else "green",
    }


def build_expansion_recommend(weekly_segments):
    """拓品 + 热品推荐（CATEGORY_EXPANSION_SUGGESTION + HOT_PRODUCT_RECOMMEND）"""
    if not weekly_segments:
        return None
    ces = weekly_segments.get('CATEGORY_EXPANSION_SUGGESTION') or []
    hpr_seg = weekly_segments.get('HOT_PRODUCT_RECOMMEND') or []
    expansions = []
    for it in (ces if isinstance(ces, list) else [])[:10]:
        if not isinstance(it, dict):
            continue
        expansions.append({
            'cate_name': it.get('cateLeafCnDesc'),
            'cate_leaf_id': it.get('cateLeafId'),
            'needs_index': it.get('needsIndex'),
            'image': it.get('expImgUrl'),
        })
    hot_products = []
    for scene in (hpr_seg if isinstance(hpr_seg, list) else []):
        if not isinstance(scene, dict):
            continue
        for hp in (scene.get('hotProductList') or [])[:5]:
            if not isinstance(hp, dict):
                continue
            hot_products.append({
                'name': hp.get('prodName'),
                'price_range': hp.get('priceRange'),
                'image': hp.get('prodImage'),
                'scene_id': hp.get('sceneId'),
            })
        if len(hot_products) >= 10:
            break
    return {
        'expansions': expansions,
        'hot_products': hot_products[:10],
    }


def build_risk(risk_raw):
    if not risk_raw:
        return None
    data = risk_raw.get('data', risk_raw) if isinstance(risk_raw, dict) else {}
    return {
        "punish_point": data.get('punishPoint'),
        "today_punish_num": data.get('todayPunishNum'),
        "ipr_num": data.get('iprNum'),
        "fraud_order_cnt": data.get('fraudOrderCnt'),
        "infringing_product_cnt": data.get('infringingProductCnt'),
        "forbidden_product_cnt": data.get('forbiddenProductCnt'),
        "repeat_complaint_cnt": data.get('repeatComplaintCnt'),
        "high_frequency_complaint_cnt": data.get('highFrequencyComplaintCnt'),
        "major_violation_types": data.get('majorViolationTypes') or [],
        "ai_auto_raise_url": data.get('aiAutoRaiseUrl'),
    }


def build_keywords_top30(weekly_segments, shop_info, ads_diag):
    """合并 P4P+引流+询盘等所有关键词，去重"""
    seen = set()
    out = []

    def _add(items, tag):
        for it in items or []:
            if not isinstance(it, dict): continue
            word = (it.get('keyword') or it.get('name') or '').strip()
            if not word or word.lower() in seen: continue
            seen.add(word.lower())
            dynamic = it.get('dynamicRecInfo') or {}
            row = dict(it)
            row['source_tag'] = tag
            row['keyword'] = word
            row['product_id'] = it.get('productId') or it.get('product_id')
            row['product_name'] = it.get('productName') or it.get('product_name')
            row['rank_label'] = (
                dynamic.get('fb_cnt_rank')
                or dynamic.get('90d_dpv_rank')
                or dynamic.get('p4p_cost_rank')
                or it.get('rank')
            )
            row['inquiry_ratio'] = dynamic.get('fb_cnt_ratio')
            # 这些词表本身就是已排序榜单，没有绝对曝光/询盘数时先保留“榜单名+排名”作为证据。
            if tag == 'Shop-HighInquiry':
                row['inquiry'] = 1
            elif tag == 'Shop-HighP4P':
                row['cost'] = 1
            out.append(row)

    # 1. P4P 三类建议
    p4p = (weekly_segments or {}).get('P4P_SEARCH_WORD_OPTIMIZ_SUGGESTION', {}) or {}
    if isinstance(p4p, dict):
        d = p4p.get('data', p4p)
        _add(d.get('HIGH_EXPOSURE_LOW_CLICK') or d.get('highImpsLowClk'), 'P4P-HighImpsLowClk')
        _add(d.get('LOW_EXPOSURE_HIGH_CLICK') or d.get('lowImpsHighClk'), 'P4P-LowImpsHighClk')
        _add(d.get('LOW_RELEVANCE') or d.get('lowRelevance'), 'P4P-LowRelevance')

    # 2. 店铺高引流/高询盘/高P4P词 (来自 findCustomerShopInfo)
    shop_full = (shop_info or {}).get('result') or (shop_info or {})
    def words_from(key):
        node = shop_full.get(key, {}) or {}
        if not isinstance(node, dict): return []
        data = node.get('data', [])
        if isinstance(data, dict):
            return data.get('wordList') or data.get('list') or data.get('data') or []
        return data or []

    _add(words_from('店铺高询盘词列表'), 'Shop-HighInquiry')
    _add(words_from('店铺高引流词列表'), 'Shop-HighTraffic')
    _add(words_from('店铺高p4p词列表'), 'Shop-HighP4P')

    return out[:30]


def build_country_channel_matrix(region, channels):
    """将地域和渠道交叉（如有数据），否则返回结构化数据"""
    return {
        "region_uv": region.get("uv_top", []),
        "region_imps": region.get("imps_top", []),
        "channels": channels.get("rows", []) if channels else [],
    }


def extract_result_items(raw):
    """提取 searchKeywordList/searchNextMonthAuctionResource 等工具的 items。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    node = raw.get("result") or raw
    if isinstance(node, dict):
        data = node.get("data") or node
        if isinstance(data, dict):
            return data.get("items") or data.get("list") or []
        if isinstance(data, list):
            return data
    return []


def build_keyword_market(*raws):
    """品牌广告关键词市场机会：行业热词、搜索指数、售卖状态。"""
    seen = set()
    out = []
    for raw in raws:
        for item in extract_result_items(raw):
            if not isinstance(item, dict):
                continue
            word = item.get("关键词") or item.get("keyword")
            biz = item.get("关键词对应业务线名称") or item.get("businessLine")
            key = (word, biz, item.get("关键词渠道"))
            if not word or key in seen:
                continue
            seen.add(key)
            out.append({
                "keyword": word,
                "biz_line": biz,
                "channel": item.get("关键词渠道"),
                "year_imps_index": item.get("全站搜索曝光指数"),
                "year_click_index": item.get("全站搜索点击指数"),
                "ctr": item.get("全站搜索点击率"),
                "business_rate": item.get("全站商机转化率"),
                "pv_rank": item.get("关键词年PV指数排名"),
                "tags": item.get("关键词标签列表"),
                "sell_status": item.get("关键词售卖状态"),
                "related_good_products": item.get("关联优爆品数量"),
                "price": item.get("关键词折后人名币价格") or item.get("关键词人民币原价"),
                "first_click_rate": item.get("关键词搜索首位点击率"),
            })
    return out[:20]


def build_product_selection(raw):
    """行业选品机会。注意该工具是滚动近 30 天口径，不作为历史月报 KPI。"""
    rows = extract_result_items(raw)
    if not rows and isinstance(raw, dict) and isinstance(raw.get("data"), list):
        rows = raw.get("data") or []

    def sum_index(items):
        total = 0
        for it in items or []:
            if not isinstance(it, dict):
                continue
            total += to_float(it.get("tagValue")) or 0
        return int(total)

    out = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        out.append({
            "product_name": row.get("prodName"),
            "product_id": row.get("prodId"),
            "cate_name": row.get("cateName"),
            "price": row.get("price"),
            "moq": row.get("minOrdQty"),
            "image": row.get("prodImage"),
            "detail_url": row.get("detailUrl"),
            "supplier": row.get("supplierCnName"),
            "ab_cnt_30d": sum_index(row.get("abCntIndex")),
            "order_cnt_30d": sum_index(row.get("prepayOrdCntIndex")),
            "gmv_index_30d": sum_index(row.get("recOrdAmtIndex")),
            "uv_index_30d": sum_index(row.get("uvDetailIndex")),
        })
    return out


def build_behavior_semantics(raw):
    """站内行为语义，作为关键词/广告机会的背景信息。"""
    if not raw:
        return []
    if isinstance(raw, dict):
        result = raw.get("result")
        if isinstance(result, list):
            return [str(x) for x in result[:10]]
        if isinstance(raw.get("data"), list):
            return [str(x) for x in raw.get("data")[:10]]
    if isinstance(raw, list):
        return [str(x) for x in raw[:10]]
    return []


def build_data_quality(raw_dir, output):
    """记录本次报告可用字段覆盖率，避免把接口未返回误写成 0。"""
    status = load_json(raw_dir, '_collect_status.json') or {}
    summary = output.get("summary") or {}
    indicators = summary.get("indicators") or []
    filled_indicators = [i for i in indicators if i.get("value") not in (None, "")]
    funnel = output.get("funnel") or {}
    source_dates = funnel.get("source_dates") or []
    meta = output.get("meta") or {}
    period_aligned = True
    if source_dates and meta.get("period_start") and meta.get("period_end"):
        period_aligned = all(
            str(meta["period_start"]) <= str(day) <= str(meta["period_end"])
            for day in source_dates
        )
    collection_calls = status.get("tools") or status.get("calls") or []
    collection_recorded = bool(collection_calls)
    checks = {
        "collection_trace": collection_recorded,
        "summary_indicators": len(filled_indicators) >= max(3, len(indicators) // 2),
        "funnel": bool(funnel.get("daily")) and period_aligned,
        "region": bool((output.get("region") or {}).get("uv_top") or (output.get("region") or {}).get("imps_top")),
        "ads": bool(
            (output.get("ads") or {}).get("source_available")
            or any(
                item.get("value") not in (None, "")
                for item in (output.get("ads") or {}).get("overview") or []
                if isinstance(item, dict)
            )
        ),
        "products": bool((output.get("products") or {}).get("performance_rows")
                         or (output.get("products") or {}).get("exposure_top10")
                         or (output.get("products") or {}).get("shelf_products")
                         or (output.get("products") or {}).get("categories")),
        "risk": bool(output.get("risk")),
        "market_keywords": bool((output.get("market") or {}).get("keyword_market")),
    }
    ok_count = sum(1 for v in checks.values() if v)
    return {
        "status": "ok" if all(checks.values()) else "partial",
        "coverage_rate": round(ok_count / len(checks), 2),
        "checks": checks,
        "period_aligned": period_aligned,
        "quality_notes": (
            []
            if collection_recorded
            else ["未找到本次运行的采集状态记录，不能把模块有值等同于完整采集。"]
        ),
        "summary_indicator_count": len(indicators),
        "summary_indicator_filled": len(filled_indicators),
        "collection": {
            "success": status.get("success"),
            "mode": status.get("mode"),
            "period_start": status.get("period_start") or status.get("periodStart"),
            "period_end": status.get("period_end") or status.get("periodEnd"),
            "calls": len(collection_calls),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--raw-dir', required=True, help='raw json files directory')
    parser.add_argument('--mode', required=True, choices=['weekly', 'monthly'])
    parser.add_argument('--period-start', required=True, help='YYYY-MM-DD')
    parser.add_argument('--period-end', required=True, help='YYYY-MM-DD')
    parser.add_argument('--title-period', required=True, help='e.g. 2026W16 or 2026-03')
    parser.add_argument('--output', required=True, help='output json file path')
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_dir():
        print(f"[error] raw-dir not found: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    # 通用文件
    shop_info_raw = load_json(raw_dir, 'findCustomerShopInfo.json')
    shop_root = (shop_info_raw or {}).get('result') if isinstance(shop_info_raw, dict) else {}
    if not isinstance(shop_root, dict):
        shop_root = shop_info_raw if isinstance(shop_info_raw, dict) else {}
    shop_data = (shop_root.get('客户店铺基本信息', {}) or {}).get('data') or {}
    risk_raw = load_json(raw_dir, 'shop_risk_diagnosis.json')
    cate_raw = load_json(raw_dir, 'queryCustomerGoodsCateSummary.json')
    region_uv = load_json(raw_dir, 'data_advisor_shop_region_uv.json')
    region_imps = load_json(raw_dir, 'data_advisor_shop_region_imps.json')
    region_ab = load_json(raw_dir, 'data_advisor_shop_region_ab.json')
    product_performance = build_product_performance(
        load_json(raw_dir, 'data_advisor_shop_product.json'),
        args.period_start,
        args.period_end,
    )

    meta = build_meta(args, shop_data)
    product_lookup = product_lookup_from_raw(raw_dir)

    funnel = None
    channels = None
    brand_ad_opp = None
    diagnosis = None
    expansion_recommend = None
    service = None
    weekly_segments = None
    ads_diag = None

    if args.mode == 'weekly':
        weekly_all_raw = load_json(raw_dir, 'service_report_weekly_all_data_query.json')
        store_diagnose_raw = load_json(raw_dir, 'store_diagnose_brief.json')
        ads_diag = (
            load_json(raw_dir, 'icbu_ads_hateoas_query_diagnosis.json')
            or load_json(raw_dir, 'icbu_ads_hateoas_query.json')
            or load_json(raw_dir, 'icbu_ads_hateoas_query_company.json')
        )
        weekly_segments = filter_weekly_all(weekly_all_raw)
        summary = (
            build_summary_weekly(
                weekly_segments,
                store_diagnose_raw,
                args.period_start,
                args.period_end,
            )
            if weekly_segments
            else None
        )
        ads = build_ads_weekly(weekly_segments, ads_diag,
                               summary['indicators'] if summary else [])
        products = build_products(
            weekly_segments,
            shop_info_raw,
            cate_raw,
            product_lookup,
            product_performance,
        )
        funnel = build_funnel(weekly_segments, args.period_start, args.period_end)
        channels = build_channels(weekly_segments)
        brand_ad_opp = build_brand_ad_opportunity(weekly_segments)
        diagnosis = build_diagnosis(weekly_segments)
        service = build_service_summary(weekly_segments)
        expansion_recommend = build_expansion_recommend(weekly_segments)
    else:  # monthly
        cur = load_json(raw_dir, 'data_advisor_shop_summary_current.json')
        base = load_json(raw_dir, 'data_advisor_shop_summary_baseline.json')
        day = load_json(raw_dir, 'data_advisor_shop_summary_day.json')
        summary = build_summary_monthly(cur, base)
        ads = build_ads_monthly(cur)
        products = build_products(
            {},
            shop_info_raw,
            cate_raw,
            product_lookup,
            product_performance,
        )
        funnel = build_monthly_funnel(day)

    region = build_region(region_uv, region_imps, region_ab)
    risk = build_risk(risk_raw)
    keywords_top30 = build_keywords_top30(weekly_segments, shop_info_raw, ads_diag)
    keyword_market = build_keyword_market(
        load_json(raw_dir, 'searchKeywordList_wending.json'),
        load_json(raw_dir, 'searchKeywordList_top.json'),
    )
    next_month_auction = build_keyword_market(
        load_json(raw_dir, 'searchNextMonthAuctionResource_wending.json'),
        load_json(raw_dir, 'searchNextMonthAuctionResource_top.json'),
    )
    product_selection = build_product_selection(
        load_json(raw_dir, 'data_advisor_product_selection_recent_30d.json')
    )
    behavior_semantics = build_behavior_semantics(
        load_json(raw_dir, 'getAllBehaviorsSemanticForKeywordRec.json')
    )

    output = {
        "meta": meta,
        "summary": summary,
        "funnel": funnel,
        "region": region,
        "channels": channels,
        "country_channel_matrix": build_country_channel_matrix(region, channels),
        "ads": ads,
        "brand_ad_opp": brand_ad_opp,
        "products": products,
        "keywords_top30": keywords_top30,
        "expansion_recommend": expansion_recommend,
        "market": {
            "keyword_market": keyword_market,
            "next_month_auction": next_month_auction,
            "product_selection_recent_30d": product_selection,
            "behavior_semantics": behavior_semantics,
            "notes": [
                "product_selection_recent_30d 是行业滚动近 30 天口径，不等同于指定历史月/周窗口。",
                "next_month_auction 是品牌广告次月资源口径，只用于机会提示，不代表当前报告周期表现。",
            ],
        },
        "diagnosis": diagnosis,
        "service": service,
        "risk": risk,
    }
    output["data_quality"] = build_data_quality(raw_dir, output)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[ok] wrote {out_path}")

    # v4: 同时跑诊断引擎，产出 analysis.json 供 build_docx 使用
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from analyze import analyze
        analysis = analyze(output)
        analysis_path = out_path.parent / 'analysis.json'
        analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"[ok] wrote {analysis_path}")
    except Exception as e:
        print(f"[warn] analyze() failed: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
