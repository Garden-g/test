#!/usr/bin/env python3
"""
prepare_data.py — 把平台查询结果清洗成 build_xlsx.py 的入参 schema

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
    """兼容平台接口的常见包裹层，取出真正的数据节点。"""
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


def parse_date(value):
    """把常见日期文本转成 date 对象，失败返回 None。

    参数:
        value: 日期文本，例如 YYYY-MM-DD、YYYY/MM/DD 或带时间的字符串。

    返回:
        datetime.date 或 None。

    异常:
        本函数不抛异常；无法识别的值统一返回 None。
    """
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("/", "-")
    match = re.search(r"20\d{2}-\d{1,2}-\d{1,2}", text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d").date()
    except ValueError:
        return None


def date_in_range(value, start, end):
    """判断日期是否落在报告周期内。

    参数:
        value: 需要判断的日期文本。
        start: 周期开始 date。
        end: 周期结束 date。

    返回:
        True 表示落在周期内；False 表示不在周期内或无法解析。

    异常:
        本函数不抛异常。
    """
    parsed = parse_date(value)
    return bool(parsed and start <= parsed <= end)


def rows_from_raw(raw):
    """从常见接口返回结构中提取列表行。

    参数:
        raw: 原始接口返回。

    返回:
        list[dict]，只保留字典行。

    异常:
        本函数不抛异常。
    """
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if not isinstance(raw, dict):
        return []
    for key in (
        "data",
        "object",
        "result",
        "values",
        "rows",
        "list",
        "items",
        "records",
        "tradeList",
        "productList",
        "conversations",
        "messages",
    ):
        value = raw.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = rows_from_raw(value)
            if nested:
                return nested
    return []


def product_payload_matches_period(raw, period_start, period_end):
    """判断商品明细是否明确属于本次报告周期。

    新 collector 会写入 periodStart/periodEnd。历史单页返回可能只在
    downloadUrl 里带 statDate；如果两类证据都没有，就不把该文件当作
    本期商品事实，避免跨运行或跨日期数据混入报告。
    """

    if not isinstance(raw, dict):
        return False
    declared_start = raw.get("periodStart") or raw.get("period_start")
    declared_end = raw.get("periodEnd") or raw.get("period_end")
    if declared_start or declared_end:
        return declared_start == period_start and declared_end == period_end
    text = json.dumps(raw, ensure_ascii=False)
    match = re.search(r"statDate=(20\d{2}-\d{2}-\d{2})", text)
    if match:
        source_date = parse_date(match.group(1))
        start = parse_date(period_start)
        end = parse_date(period_end)
        return bool(source_date and start and end and start <= source_date <= end)
    return False


_ERROR_PATTERNS = (
    "errorCode", "errorMsg", "error_code", "error_message",
    "-32002", "-32001", "Agent 类型不允许", "Traceback",
    "ECONNREFUSED", "at Object.", "stack trace",
    "data connector exited", "Data source returned",
    "accio-" + "mcp-cli exited", "Gate" + "way returned",
)


def sanitize_cell_value(value):
    """过滤系统错误文本，只保留业务可读内容。"""
    if value is None or value == "":
        return value
    text = str(value)
    if any(pat in text for pat in _ERROR_PATTERNS):
        print(f"[sanitize] stripped system error from cell: {text[:120]}", file=sys.stderr)
        return "平台接口异常，数据未返回"
    if text.strip().startswith("{") and ("error" in text.lower() or "success" in text.lower()):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and (obj.get("success") is False or obj.get("errorCode")):
                print(f"[sanitize] stripped error object from cell", file=sys.stderr)
                return "平台接口异常，数据未返回"
        except (json.JSONDecodeError, TypeError):
            pass
    return value


def source_ok(status, name_part):
    """判断某类采集来源是否至少有一个成功记录。

    参数:
        status: _collect_status.json 解析结果。
        name_part: 工具名片段。

    返回:
        bool，True 表示至少一个对应来源成功。

    异常:
        本函数不抛异常。
    """
    needle = str(name_part).lower()
    for tool in status.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        if needle in str(tool.get("tool") or "").lower() and tool.get("ok"):
            return True
    return False


def source_errors(status):
    """把采集失败整理成业务可读的来源问题。

    参数:
        status: _collect_status.json 解析结果。

    返回:
        list[dict]，每条包含模块、问题、影响和处理方式。

    异常:
        本函数不抛异常。
    """
    out = []
    for tool in status.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("ok"):
            continue
        name = str(tool.get("tool") or "")
        if "seller" in name or "chat" in name or "conversation" in name or "subaccount" in name or "contact" in name:
            module = "业务员/询盘"
            impact = "无法完整拆到业务员或会话明细"
        elif "trade" in name:
            module = "订单"
            impact = "无法完整判断订单产出"
        elif "ads" in name or "keyword" in name:
            module = "广告"
            impact = "广告诊断证据不足"
        elif "product" in name:
            module = "商品"
            impact = "商品承接诊断证据不足"
        else:
            module = "经营数据"
            impact = "对应模块只能保守判断"
        out.append({
            "module": module,
            "check": "来源返回失败",
            "status": "黄灯",
            "usable": False,
            "issue": "部分来源未返回",
            "impact": impact,
            "action": "按业务模块补采或导出明细后复查",
        })
    return out


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

    当前接口返回 ``data.data[0].result``。只解析到第一层会让概览、诊断
    结论和问题计划看起来全部为空。公司入口实体仅用于导航，不能冒充
    已取得诊断数据；业务层 410 也必须视为不可用。
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
    product_performance_raw=None,
):
    """商品表现（兼容周月）"""
    product_lookup = product_lookup or {}
    def get_data(seg):
        if not seg: return []
        return seg if isinstance(seg, list) else seg.get('data', [])

    prod_overview = rows_from_raw(product_performance_raw)
    if not prod_overview:
        prod_overview = get_data(weekly_segments.get('EXPOSURE_TOP10_PRODUCT_DATA'))
    prod_overview = sorted(
        prod_overview,
        key=lambda item: to_float(first_present(item, "sumProdShowNum", "totalImpsCnt", "exposure", "imps")) or 0,
        reverse=True,
    )
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
        "exposure_top10": [
            {"rank": i + 1,
             "subject": p.get('subject') or p.get("prodName"),
             "product_id": p.get('productId') or p.get('product_id') or p.get("id") or lookup_product(product_lookup, p.get('subject')).get("product_id"),
             "image": p.get('prodImage') or p.get('image'),
             "is_showcase": p.get('isShowcase') == 'Y',
             "imps": first_present(p, 'sumProdShowNum', 'totalImpsCnt', 'exposure', 'imps'),
             "fb_num": first_present(p, 'sumProdFbNum', 'inquiries', 'inquiry'),
             "fb_uv": p.get('atmFbUv'),
             "fb_rate": p.get('sumProdFbRate'),
             "clk": first_present(p, 'sumProdClickNum', 'totalClkCnt', 'click', 'clk'),
             "ab": first_present(p, 'abCnt', 'ab'),
             "detail_url": p.get("detailUrl") or p.get("productDetailUrl"),
             "source_dates": p.get("_sourceDates") or []}
            for i, p in enumerate(prod_overview[:60])
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


# ---------- 以下为详细化新增 builder ----------

def build_funnel(weekly_segments, period_start=None, period_end=None):
    """构造严格落在用户指定周期内的周度漏斗。"""
    if not weekly_segments:
        return None
    conv = weekly_segments.get('STORE_CONVERSION_RATE_ANALYSIS') or []
    if not isinstance(conv, list):
        conv = []
    start = parse_date(period_start)
    end = parse_date(period_end)
    dated_rows = [
        (parse_date(item.get("statDate") or item.get("statsDate")), item)
        for item in conv
        if isinstance(item, dict)
    ]
    rows_with_dates = [(day, item) for day, item in dated_rows if day]
    if rows_with_dates and start and end:
        selected_rows = [item for day, item in rows_with_dates if start <= day <= end]
    elif rows_with_dates:
        selected_rows = [item for _, item in sorted(rows_with_dates, key=lambda pair: pair[0])[-7:]]
    else:
        selected_rows = conv[-7:] if len(conv) > 7 else conv

    # 有日期时严格按报告周期；只有完全无日期时才使用最后七行降级。
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
            day.isoformat() for day, _ in sorted(rows_with_dates, key=lambda pair: pair[0])
        ],
        'requested_period': {'start': period_start, 'end': period_end},
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


def raw_rows(raw):
    """从常见业务接口结构中提取列表行。

    参数：
        raw: 任意接口返回结构，可能是 list，也可能被 data/object/result 包裹。

    返回：
        list[dict]: 只保留字典行，避免后续分析处理到字符串或数字。

    异常：
        本函数不主动抛异常；无法识别时返回空列表。
    """
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if not isinstance(raw, dict):
        return []
    for key in ("data", "object", "result", "values", "list", "rows"):
        value = raw.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = raw_rows(value)
            if nested:
                return nested
    return []


def compact_cell(value, limit=180):
    """把任意值压缩成适合 Excel 单元格阅读的一行文本。

    参数：
        value: 待展示的值。
        limit: 最长字符数，超出后截断。

    返回：
        str: 清理换行后的短文本。

    异常：
        本函数不主动抛异常。
    """
    if value in (None, ""):
        return ""
    text = str(value).replace("\n", " ").strip()
    for _ in range(4):
        text = re.sub(r"\{[^{}]{5,1200}\}", "买家发送图片/卡片", text)
    text = re.sub(r"https?://\\S+", "买家发送链接/卡片", text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


PURCHASE_SIGNAL_RULES = [
    ("价格", ("price", "quote", "quotation", "cost", "how much", "target price", "budget", "prix", "coût", "combien", "precio", "cuanto", "costo", "报价", "价格", "多少钱", "预算")),
    ("数量/MOQ", ("moq", "quantity", "qty", "pcs", "pieces", "sets", "units", "quantité", "cantidad", "数量", "起订量", "多少件")),
    ("样品", ("sample", "samples", "样品", "打样", "寄样")),
    ("规格/尺寸", ("size", "dimension", "width", "length", "height", "gsm", "material", "fabric", "color", "measurements", "规格", "尺寸", "克重", "材质", "面料", "颜色")),
    ("交期/运输", ("delivery", "lead time", "shipping", "ship", "freight", "receive", "arrive", "tracking", "customs", "交期", "发货", "运费", "运输", "物流")),
    ("定制", ("custom", "customized", "oem", "logo", "design", "style", "定制", "图案", "logo", "款式")),
    ("联系方式", ("whatsapp", "wechat", "phone", "email", "@", "电话", "邮箱", "微信")),
    ("付款/下单", ("paid", "payment", "pay", "invoice", "payment link", "付款", "支付", "已付", "发链接")),
    ("采购计划", ("order", "purchase", "buy", "proceed", "urgent", "project", "import", "订单", "采购", "购买", "下单", "项目", "进口")),
]

GREETING_WORDS = {"hi", "hello", "thanks", "thank you", "ok", "okay", "你好", "谢谢"}


def level_rank(level):
    """把买家 L 等级转成可比较的数字。

    参数：
        level: 类似 L1/L2/L3/L4 的等级文本。

    返回：
        int: L 后面的数字；无法识别时返回 0。

    异常：
        本函数不主动抛异常。
    """
    text = str(level or "").upper()
    for n in range(4, 0, -1):
        if f"L{n}" in text:
            return n
    return 0


def detect_purchase_signals(text):
    """从买家消息里识别强购买意愿信号。

    参数：
        text: 买家消息合并文本。

    返回：
        list[str]: 命中的业务信号名称，例如价格、样品、数量。

    异常：
        本函数不主动抛异常。
    """
    lower = str(text or "").lower()
    signals = []
    for label, keywords in PURCHASE_SIGNAL_RULES:
        if any(word.lower() in lower for word in keywords):
            signals.append(label)
    regex_rules = [
        ("价格", r"[$€£]\s*\d+|\b\d+(?:\.\d+)?\s*(?:usd|dollars?)\b"),
        ("数量/MOQ", r"\b\d+\s*(?:pcs|pieces|sets|units|curtains|cushions|meters|yards)\b"),
        ("规格/尺寸", r"\b\d+\s*(?:cm|mm|inch|inches|gsm)\b|\b\d+\s*[x×]\s*\d+\b"),
        ("交期/运输", r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b"),
    ]
    for label, pattern in regex_rules:
        if label not in signals and re.search(pattern, lower):
            signals.append(label)
    return signals


def _card_field(text, field_name):
    """从平台卡片文案中提取字段值。

    参数：
        text: 平台卡片原文，例如 inquiry card 文案。
        field_name: 字段英文名，例如 Product Name。

    返回：
        str: 提取到的字段值；没有命中时返回空字符串。

    异常：
        本函数不主动抛异常。
    """
    pattern = rf"{re.escape(field_name)}\s+is\s+([^;]+)"
    match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    return compact_cell(match.group(1), 140) if match else ""


def normalize_buyer_message(msg):
    """把买家原始消息清洗成适合老板阅读的一句话。

    参数：
        msg: query_conversation_msg 返回的单条消息对象。

    返回：
        str: 可用于需求摘要和信号判断的文本；纯图片、无业务含义的
        JSON 卡片返回空字符串。

    异常：
        本函数不主动抛异常。
    """
    message_type = str(first_present(msg, "messageType", "type") or "").upper()
    raw = str(first_present(msg, "content", "text", "message", "summary") or "").strip()
    if not raw:
        return ""

    # 图片/文件类 JSON 对老板没帮助，保留它只会把摘要变成“买家发送卡片”。
    if raw.startswith("{") and raw.endswith("}"):
        return ""
    if "PICTURE" in message_type or "IMAGE" in message_type or "FILE" in message_type:
        return ""

    lowered = raw.lower()
    if "inquiry card" in lowered or "signal product card" in lowered or "single product card" in lowered:
        product = _card_field(raw, "Product Name") or _card_field(raw, "product name")
        note = _card_field(raw, "The note") or _card_field(raw, "note")
        product_id = _card_field(raw, "Product id") or _card_field(raw, "product id")
        parts = []
        if product:
            parts.append(f"询盘商品：{product}")
        elif product_id:
            parts.append(f"询盘商品ID：{product_id}")
        if note:
            parts.append(f"买家备注：{note}")
        return compact_cell("；".join(parts), 220) if parts else ""

    if "address card" in lowered:
        return "买家已留下收货地址/联系方式"

    return compact_cell(raw, 220)


def message_business_score(text):
    """给买家消息打业务信息分，帮助摘要优先保留高价值句子。

    参数：
        text: 已清洗的买家消息。

    返回：
        int: 分数越高，越应该进入需求摘要。

    异常：
        本函数不主动抛异常。
    """
    if not text:
        return -100
    signals = detect_purchase_signals(text)
    score = len(signals) * 10
    if "询盘商品" in text:
        score += 8
    if "买家备注" in text:
        score += 6
    if re.search(r"[$€£]\s*\d+|\b\d+\s*(?:pcs|pieces|sets|units)\b", text.lower()):
        score += 5
    if len(text) >= 40:
        score += 3
    if looks_like_greeting_only(text):
        score -= 20
    return score


def build_buyer_digest(messages, fallback=""):
    """从一组买家消息生成需求摘要和购买信号。

    参数：
        messages: 已确认属于买家的消息列表。
        fallback: 无有效消息时使用的会话摘要兜底。

    返回：
        tuple[str, list[str]]: 需求摘要和购买信号列表。

    异常：
        本函数不主动抛异常。
    """
    candidates = []
    for idx, msg in enumerate(messages):
        text = normalize_buyer_message(msg)
        if not text:
            continue
        candidates.append({
            "idx": idx,
            "text": text,
            "score": message_business_score(text),
        })

    full_text = "；".join(item["text"] for item in candidates)
    signals = detect_purchase_signals(full_text)

    useful = [item for item in candidates if item["score"] > -10]
    if not useful and fallback:
        fallback_text = compact_cell(fallback, 220)
        return fallback_text, detect_purchase_signals(fallback_text)
    if not useful:
        return "会话明细未返回买家有效文本", []

    # 先按业务价值挑句子，再按原消息顺序输出，避免摘要像关键词堆砌。
    selected = sorted(useful, key=lambda item: (-item["score"], item["idx"]))[:6]
    selected.sort(key=lambda item: item["idx"])
    summary = "；".join(item["text"] for item in selected)
    return compact_cell(summary, 260), signals


def clean_party_name(value):
    """清洗客户/业务员名称，避免把底层 JSON 当姓名写进报表。

    参数：
        value: 平台返回的姓名字段。

    返回：
        str: 可展示姓名；无法安全展示时返回空字符串。

    异常：
        本函数不主动抛异常。
    """
    text = compact_cell(value, 80)
    if not text:
        return ""
    if text.startswith("{") or text.startswith("["):
        return ""
    return text


def looks_like_greeting_only(text):
    """判断买家内容是否基本只有问候或礼貌语。

    参数：
        text: 买家消息合并文本。

    返回：
        bool: True 表示低信息量问候。

    异常：
        本函数不主动抛异常。
    """
    lower = " ".join(str(text or "").lower().replace(",", " ").replace(".", " ").split())
    if not lower:
        return True
    words = [w for w in lower.split() if w]
    return len(words) <= 4 and any(g in lower for g in GREETING_WORDS)


def quality_flags(row):
    """把沟通质检字段转成老板能看懂的问题标签。

    参数：
        row: 单条质检明细。

    返回：
        list[str]: 问题标签，例如超 12 小时、只回 Hi、未跟进。

    异常：
        本函数不主动抛异常。
    """
    mapping = [
        ("replyOver12h", "超 12 小时回复"),
        ("notFollow", "未跟进"),
        ("onlyHi", "只回 Hi"),
        ("repeatReply", "重复回复"),
        ("rcTooShort", "回复过短"),
        ("offlineMsg", "离线消息"),
        ("buyerRnR", "买家已读未回"),
        ("evaluateUnsatisfied", "买家不满意"),
    ]
    out = []
    for key, label in mapping:
        if to_float(row.get(key)) and to_float(row.get(key)) > 0:
            out.append(label)
    return out


def build_quality_index(raw_dir):
    """读取一周沟通质检明细，并按买家账号聚合。

    参数：
        raw_dir: 原始采集目录。

    返回：
        tuple[list[dict], dict]: 全量质检行，以及按 buyerLoginId 聚合的索引。

    异常：
        本函数不主动抛异常；坏文件在 load_json 阶段会被忽略。
    """
    rows = []
    for path in sorted(raw_dir.glob("query_seller_chat_quality_check_detail*.json")):
        rows.extend(raw_rows(load_json(raw_dir, path.name)))
    by_buyer = {}
    seen = set()
    unique_rows = []
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
        buyer = first_present(row, "buyerLoginId", "buyerAliId", "buyerId")
        if buyer:
            by_buyer.setdefault(str(buyer), []).append(row)
    return unique_rows, by_buyer


def _next_step(signals):
    """根据已识别的采购信号判断下一步推进方向。"""
    if not signals:
        return "报价关键参数(数量/规格/交期)"
    sig_text = "；".join(str(s) for s in signals)
    if "样品" in sig_text:
        return "样品规格和寄样条件"
    if "数量/MOQ" in sig_text and "价格" in sig_text:
        return "报价(已有数量和目标价)"
    if "价格" in sig_text:
        return "正式报价(含MOQ和交期)"
    if "规格/尺寸" in sig_text:
        return "规格确认后报价"
    if "定制" in sig_text:
        return "定制方案和打样费"
    if "交期/运输" in sig_text:
        return "交期确认和运费方案"
    if "联系方式" in sig_text:
        return "线下沟通并确认订单意向"
    if "采购计划" in sig_text:
        return "对接采购计划并报价"
    return "报价关键参数(数量/规格/交期)"


def _identify_missing(signals):
    """识别询盘中缺失的关键报价参数。"""
    all_params = ["数量", "规格", "交期", "预算", "用途", "收货国"]
    present = set()
    sig_text = "；".join(str(s) for s in (signals or []))
    if "数量/MOQ" in sig_text:
        present.add("数量")
    if "规格/尺寸" in sig_text:
        present.add("规格")
    if "交期/运输" in sig_text:
        present.add("交期")
    if "价格" in sig_text:
        present.add("预算")
    missing = [p for p in all_params if p not in present]
    return "、".join(missing[:3]) if missing else "关键参数"


def classify_inquiry_record(record):
    """根据等级、购买信号、低质原因和跟进风险给询盘分层。

    参数：
        record: 已标准化的询盘记录。

    返回：
        dict: 增补 quality、priority、reason、action 字段后的记录。

    异常：
        本函数不主动抛异常。
    """
    record["demand_summary"] = sanitize_cell_value(record.get("demand_summary"))
    record["product_or_need"] = sanitize_cell_value(record.get("product_or_need"))

    signals = record.get("purchase_signals") or []
    flags = record.get("reply_risks") or []
    rank = level_rank(record.get("buyer_level"))
    seller = record.get("seller") or "业务员"
    no_effective_text = "会话明细未返回买家有效文本" in str(record.get("demand_summary") or "")
    low_reasons = []
    if no_effective_text:
        low_reasons.append("会话明细未返回买家有效文本")
    elif looks_like_greeting_only(record.get("demand_summary")):
        low_reasons.append("只有问候或低信息量回复")
    if not signals and rank == 0:
        low_reasons.append("未识别到明确采购信号和 L 等级")

    if no_effective_text and not signals:
        quality = "待判断"
        priority = "P2"
        reason = "只有买家等级，缺少需求文本"
        action = "业务员补看完整会话后再判断，不按 L 等级直接当高质量。"
    elif signals and flags:
        quality = "高质量"
        priority = "P0"
        reason = "明确采购信号且存在跟进风险"
        risk_desc = flags[0] if flags else "跟进风险"
        action = f"主管今天追 {seller}：{risk_desc}，确认{_next_step(signals)}。"
    elif signals:
        quality = "待补信息"
        priority = "P1"
        reason = "已有采购信号，但缺少用户确认的质量分级口径或关键信息"
        action = f"按团队确认时限推进{_next_step(signals)}并追问{_identify_missing(signals)}。"
    elif low_reasons:
        quality = "低质量"
        priority = "P3"
        reason = "；".join(low_reasons)
        action = "礼貌维护；到团队确认的复查节点仍无需求补充时再降优先级。"
    else:
        quality = "待判断"
        priority = "P2"
        reason = "信息不足，需要业务员补充判断"
        action = "主管抽样完整会话后定高低。"

    record.update({
        "quality": quality,
        "priority": priority,
        "quality_reason": reason,
        "low_quality_reason": "；".join(low_reasons),
        "suggested_action": action,
    })
    return record


def build_inquiry_quality(raw_dir):
    """生成询盘质量分析数据。

    参数：
        raw_dir: 原始采集目录，包含会话、消息和质检文件。

    返回：
        dict: summary + records，用于 analysis 和 Excel。

    异常：
        本函数不主动抛异常；没有会话明细时会降级使用质检明细。
    """
    week_messages = load_json(raw_dir, "query_conversation_msg_week.json") or {}
    quality_rows, quality_by_buyer = build_quality_index(raw_dir)
    period_start = (week_messages or {}).get("periodStart")
    period_end = (week_messages or {}).get("periodEnd")
    records = []

    for item in week_messages.get("records") or []:
        if not isinstance(item, dict):
            continue
        conversation = item.get("conversation") or {}
        messages = [m for m in (item.get("messages") or []) if isinstance(m, dict)]
        buyer_messages = []
        for msg in messages:
            if msg.get("isSystemMessage") is True or "SYSTEM" in str(msg.get("messageType") or "").upper():
                continue
            role = str(first_present(msg, "senderRole", "role", "sendRole") or "").lower()
            if role and "buyer" not in role and "customer" not in role:
                continue
            buyer_messages.append(msg)
        buyer_login = first_present(conversation, "buyerLoginId", "contactLoginId", "loginId", "otherLoginId")
        buyer_level = first_present(conversation, "buyerLevel", "contactLevel", "level")
        risks = []
        for q in quality_by_buyer.get(str(buyer_login), []):
            risks.extend(quality_flags(q))
            buyer_level = buyer_level or q.get("buyerLevel")
        fallback_summary = first_present(conversation, "lastMsgSummary", "summary", "content")
        buyer_text, purchase_signals = build_buyer_digest(buyer_messages, fallback_summary)
        customer_name = clean_party_name(first_present(conversation, "contactName", "otherName", "buyerName", "name")) or "未返回"
        seller_name = clean_party_name(item.get("sellerName") or first_present(conversation, "sellerName", "_sellerName")) or "未返回"
        if buyer_text == "会话明细未返回买家有效文本":
            buyer_text = f"{customer_name}：会话明细未返回买家有效文本，需业务员补看完整会话"
        record = {
            "conversation_id": first_present(conversation, "conversationId", "id") or item.get("conversationId"),
            "customer": customer_name,
            "country": first_present(conversation, "contactCountry", "country", "buyerCountry") or "未返回",
            "seller": seller_name,
            "buyer_level": buyer_level or "未返回",
            "product_or_need": compact_cell(first_present(conversation, "productName", "subject", "lastMsgSummary", "summary"), 160),
            "demand_summary": buyer_text,
            "purchase_signals": purchase_signals,
            "reply_risks": sorted(set(risks)),
            "order_status": "待核对订单",
            "evidence": compact_cell(buyer_text, 180),
            "source": "会话明细",
        }
        records.append(classify_inquiry_record(record))

    if not records:
        for row in quality_rows:
            content = compact_cell(first_present(
                row,
                "replyOver12hMsgContent",
                "rcTooShortMsgContent",
                "repeatReplyMsgContent",
                "buyerRnRMsgContent",
            ), 220)
            buyer = " ".join([str(row.get("buyerFirstName") or ""), str(row.get("buyerLastName") or "")]).strip() or row.get("buyerLoginId") or "未返回"
            seller = " ".join([str(row.get("firstName") or ""), str(row.get("lastName") or "")]).strip() or row.get("loginId") or "未返回"
            record = {
                "conversation_id": row.get("buyerLoginId") or "质检样本",
                "customer": buyer,
                "country": str(row.get("buyerLoginId") or "")[:2].upper() or "未返回",
                "seller": seller,
                "buyer_level": row.get("buyerLevel") or "未返回",
                "product_or_need": "质检暴露的买家消息",
                "demand_summary": content or "质检返回但未包含具体消息",
                "purchase_signals": detect_purchase_signals(content),
                "reply_risks": quality_flags(row),
                "order_status": "待核对订单",
                "evidence": content,
                "source": "沟通质检",
            }
            records.append(classify_inquiry_record(record))

    counts = {}
    priority_counts = {}
    for row in records:
        counts[row.get("quality")] = counts.get(row.get("quality"), 0) + 1
        priority_counts[row.get("priority")] = priority_counts.get(row.get("priority"), 0) + 1
    return {
        "period_start": period_start,
        "period_end": period_end,
        "summary": {
            "total_records": len(records),
            "high_quality": counts.get("高质量", 0),
            "low_quality": counts.get("低质量", 0),
            "pending_info": counts.get("待补信息", 0),
            "pending_judgement": counts.get("待判断", 0),
            "p0": priority_counts.get("P0", 0),
            "p1": priority_counts.get("P1", 0),
            "conversation_records": len(week_messages.get("records") or []),
            "quality_records": len(quality_rows),
            "coverage_note": "已按会话明细分析" if week_messages.get("records") else "会话明细未返回，当前用沟通质检样本降级分析",
        },
        "records": records[:200],
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
            # 这些词表本身就是已排序榜单，没有绝对曝光/询盘数时先保留"榜单名+排名"作为证据。
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
    """生成报告前数据质量检查，避免周期错位和缺失字段被误判。

    参数:
        raw_dir: 原始只读数据目录。
        output: 已清洗的 report_data。

    返回:
        dict: 包含模块检查、阻断标记、降级结论和覆盖率。

    异常:
        本函数不主动抛异常；缺失数据统一进入检查结果。
    """
    status = load_json(raw_dir, '_collect_status.json') or {}
    summary = output.get("summary") or {}
    indicators = summary.get("indicators") or []
    filled_indicators = [i for i in indicators if i.get("value") not in (None, "")]
    meta = output.get("meta") or {}
    period_start = parse_date(meta.get("period_start"))
    period_end = parse_date(meta.get("period_end"))
    checks_detail = []
    blocking_flags = {}
    degraded = []

    def add_check(module, check, ok, status_text, issue, impact, action, usable=True, period=None):
        row = {
            "module": module,
            "check": check,
            "status": status_text if ok else status_text,
            "usable": bool(ok and usable),
            "period": period or f"{meta.get('period_start')} 至 {meta.get('period_end')}",
            "issue": "" if ok else issue,
            "impact": impact if not ok else "可用于本期判断",
            "action": action if not ok else "下周继续复查同口径",
        }
        checks_detail.append(row)
        if not ok:
            degraded.append(f"{module}：{impact}")
        return row

    def block(flag, module, issue, impact):
        blocking_flags[flag] = True
        add_check(module, "关键字段", False, "红灯", issue, impact, "补齐字段后再计算相关结论", usable=False)

    if not period_start or not period_end:
        block("period_invalid", "全表", "报告周期无法解析", "全表只能保守阅读")

    collection_start = status.get("period_start") or status.get("periodStart")
    collection_end = status.get("period_end") or status.get("periodEnd")
    collection_calls = status.get("tools") or status.get("calls") or []
    collection_recorded = bool(collection_calls)
    period_match = (
        collection_recorded
        and collection_start == meta.get("period_start")
        and collection_end == meta.get("period_end")
    )
    if not period_match:
        blocking_flags["collection_period_mismatch"] = True
    add_check(
        "全表",
        "采集周期一致",
        period_match,
        "绿灯" if period_match else "红灯",
        (
            f"采集周期 {collection_start} 至 {collection_end}，报告周期 {meta.get('period_start')} 至 {meta.get('period_end')}"
            if collection_recorded
            else "未找到本次运行的采集状态记录"
        ),
        "首页整体状态不能判健康",
        "按同一报告周期重新采集",
        usable=period_match,
    )

    checks = {
        "collection_trace": collection_recorded,
        "summary_indicators": len(filled_indicators) >= max(3, len(indicators) // 2),
        "funnel": bool((output.get("funnel") or {}).get("daily")),
        "region": bool((output.get("region") or {}).get("uv_top") or (output.get("region") or {}).get("imps_top")),
        "ads": bool(
            (output.get("ads") or {}).get("source_available")
            or any(
                row.get("value") not in (None, "")
                for row in (output.get("ads") or {}).get("overview") or []
                if isinstance(row, dict)
            )
        ),
        "products": bool((output.get("products") or {}).get("exposure_top10")
                         or (output.get("products") or {}).get("shelf_products")
                         or (output.get("products") or {}).get("categories")),
        "inquiry_quality": bool((output.get("inquiry_quality") or {}).get("records")),
        "risk": bool(output.get("risk")),
        "market_keywords": bool((output.get("market") or {}).get("keyword_market")),
    }

    # 经营总览。
    add_check(
        "经营总览",
        "核心指标返回",
        checks["summary_indicators"],
        "绿灯" if checks["summary_indicators"] else "黄灯",
        "经营核心指标返回不足",
        "整体经营状态可信度下降",
        "补采店铺经营汇总",
        usable=checks["summary_indicators"],
    )

    # 订单周期和金额完整性。
    funnel_daily = (output.get("funnel") or {}).get("daily") or []
    out_of_period_dates = []
    if period_start and period_end:
        for row in funnel_daily:
            date_value = row.get("date") if isinstance(row, dict) else None
            if date_value and not date_in_range(date_value, period_start, period_end):
                out_of_period_dates.append(str(date_value))
    if out_of_period_dates:
        blocking_flags["order_period_mismatch"] = True
    add_check(
        "订单",
        "订单/漏斗日期在本期内",
        bool(funnel_daily) and not out_of_period_dates,
        "绿灯" if funnel_daily and not out_of_period_dates else "红灯",
        "订单趋势日期不在报告周期内" if out_of_period_dates else "订单趋势未返回",
        "订单趋势不可用于本周健康判断",
        "重新按本周拉取订单/漏斗数据",
        usable=bool(funnel_daily) and not out_of_period_dates,
        period=", ".join(out_of_period_dates[:6]) if out_of_period_dates else None,
    )

    shop_summary = load_json(raw_dir, "data_advisor_shop_summary_current.json")
    summary_rows = rows_from_raw(shop_summary)
    summary_row = summary_rows[0] if summary_rows else {}
    order_amount = first_present(summary_row, "orderAmt", "orderAmount", "payOrdAmt", "crtOrdAmt", "recOrdAmt")
    order_count = first_present(summary_row, "orderCnt", "crtOrdCnt", "orderCntValue", "prepayOrdCnt")
    trade_raw = load_json(raw_dir, "queryTradeListMcp.json")
    trade_rows = [
        row for row in rows_from_raw(trade_raw)
        if not period_start or not period_end or date_in_range(
            first_present(row, "createDate", "gmtCreate", "orderCreateTime"),
            period_start,
            period_end,
        )
    ]
    trade_exact = bool(
        isinstance(trade_raw, dict)
        and str(trade_raw.get("periodStart") or "")[:10] == meta.get("period_start")
        and str(trade_raw.get("periodEnd") or "")[:10] == meta.get("period_end")
    )
    trade_complete = bool(trade_exact and trade_raw.get("complete") is True)
    if trade_exact and not trade_complete:
        blocking_flags["order_pagination_truncated"] = True
    add_check(
        "订单",
        "交易分页完整",
        trade_complete,
        "绿灯" if trade_complete else "红灯",
        (
            f"交易分页未完成，已采 {trade_raw.get('rowCount')} 条"
            if trade_exact
            else "未找到带目标周期和完整性标记的交易清单"
        ),
        "订单数和金额只能视为下限，不能据此判断完整投产",
        "继续按 start/limit 分页到短页或空页",
        usable=trade_complete,
    )
    if order_count in (None, "") and trade_rows:
        order_count = len(trade_rows)
    if order_amount in (None, "") and trade_rows:
        trade_amounts = []
        for trade in trade_rows:
            payment = trade.get("payment") if isinstance(trade.get("payment"), dict) else {}
            amount_node = (
                payment.get("paidOrderAmount")
                or payment.get("receivedAmount")
                or payment.get("totalAmount")
                or {}
            )
            amount = (
                amount_node.get("amount")
                if isinstance(amount_node, dict)
                else amount_node
            )
            numeric_amount = to_float(amount)
            if numeric_amount is not None:
                trade_amounts.append(numeric_amount)
        if trade_amounts:
            order_amount = sum(trade_amounts)
    if order_amount in (None, ""):
        block("order_amount_missing", "订单", "订单金额未返回", "ROI、成交质量、投产回收不可完整判断")
    if order_count in (None, ""):
        block("order_count_missing", "订单", "订单数未返回", "订单产出不可完整判断")

    # 广告关键字段。
    ads = output.get("ads") or {}
    ad_text = " ".join(str(ads.get(key) or "") for key in ("overview_summary", "ai_conclusion"))
    ad_has_cost = any("花费" in str(row.get("name")) and row.get("value") not in (None, "") for row in ads.get("overview") or [] if isinstance(row, dict))
    ad_has_cost = ad_has_cost or bool(re.search(r"花费\s*[0-9]+(?:\.[0-9]+)?", ad_text))
    ad_has_lead = "商机量" in str(ads.get("overview_summary") or "") or "商机量" in str(ads.get("ai_conclusion") or "")
    if not ad_has_cost:
        block("ad_cost_missing", "广告", "广告花费未返回", "广告 ROI、商机成本不可判断")
    add_check(
        "广告",
        "广告商机可识别",
        ad_has_lead,
        "绿灯" if ad_has_lead else "黄灯",
        "广告商机字段未返回",
        "只能看全店询盘，不能判断广告带来的询盘质量",
        "补采广告诊断或投放明细",
        usable=ad_has_lead,
    )

    # 商品、询盘、业务员、平台可见跟进。
    add_check(
        "商品",
        "商品明细可用于承接诊断",
        checks["products"],
        "绿灯" if checks["products"] else "黄灯",
        "商品明细不足",
        "商品承接诊断只能保守判断",
        "补采商品效果、橱窗和广告承接商品",
        usable=checks["products"],
    )
    product_raw = load_json(raw_dir, "data_advisor_shop_product.json") or {}
    product_truncated = bool(
        isinstance(product_raw, dict)
        and product_raw.get("truncated") is True
    )
    add_check(
        "商品",
        "商品分页覆盖",
        checks["products"] and not product_truncated,
        "绿灯" if checks["products"] and not product_truncated else "黄灯",
        (
            f"商品仅覆盖排序样本：聚合 {product_raw.get('rowCount')} 个，"
            f"单日总量最高 {product_raw.get('maximumRecordCount')} 个"
            if product_truncated
            else "商品分页范围或样本说明未返回"
        ),
        "商品象限可用于重点商品诊断，但不能代表全店全部商品",
        "需要全量时提高分页上限，并保留排序和覆盖说明",
        usable=checks["products"],
    )
    add_check(
        "询盘",
        "会话/询盘明细返回",
        checks["inquiry_quality"],
        "绿灯" if checks["inquiry_quality"] else "黄灯",
        "本周询盘会话明细不足",
        "询盘质量只能用汇总和质检降级判断",
        "补拉会话列表和消息明细",
        usable=checks["inquiry_quality"],
    )
    seller_detail_ok = source_ok(status, "subaccount_query") and source_ok(status, "seller_acct")
    add_check(
        "业务员",
        "子账号/业务员明细返回",
        seller_detail_ok,
        "绿灯" if seller_detail_ok else "黄灯",
        "缺子账号或账号诊断明细",
        "不能硬做人效榜，只能展示店铺级响应",
        "补采子账号维度诊断",
        usable=seller_detail_ok,
    )
    service = output.get("service") or {}
    follow_ok = (
        any(service.get(key) not in (None, "") for key in ("reply_over_12h_count", "not_follow_count", "avg_reply_time_30d"))
        or source_ok(status, "query_recent_conversation")
        or source_ok(status, "query_seller_chat_quality_check_detail")
    )
    add_check(
        "业务员/跟进",
        "平台可见跟进信号",
        follow_ok,
        "绿灯" if follow_ok else "黄灯",
        "平台回复或跟进明细不足",
        "无法完整判断平台可见跟进闭环",
        "补采会话、质检和业务员账号诊断",
        usable=follow_ok,
    )

    # 采集失败统一进数据质量，不散落到业务正文。
    checks_detail.extend(source_errors(status))

    ok_count = sum(1 for v in checks.values() if v)
    red_count = sum(1 for row in checks_detail if row.get("status") == "红灯")
    yellow_count = sum(1 for row in checks_detail if row.get("status") == "黄灯")
    if red_count:
        quality_status = "red"
    elif yellow_count or ok_count < len(checks):
        quality_status = "yellow"
    else:
        quality_status = "green"
    return {
        "status": quality_status,
        "coverage_rate": round(ok_count / len(checks), 2),
        "checks": checks,
        "checks_detail": checks_detail,
        "blocking_flags": blocking_flags,
        "degraded_conclusions": degraded[:30],
        "red_count": red_count,
        "yellow_count": yellow_count,
        "summary_indicator_count": len(indicators),
        "summary_indicator_filled": len(filled_indicators),
        "collection": {
            "success": status.get("success"),
            "mode": status.get("mode"),
            "period_start": status.get("period_start") or status.get("periodStart"),
            "period_end": status.get("period_end") or status.get("periodEnd"),
            "ok_count": status.get("ok_count"),
            "failed_count": status.get("failed_count"),
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
    product_performance_raw = load_json(raw_dir, 'data_advisor_shop_product.json')
    if not product_payload_matches_period(
        product_performance_raw,
        args.period_start,
        args.period_end,
    ):
        product_performance_raw = None

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
            product_performance_raw,
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
            product_performance_raw,
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
        "inquiry_quality": build_inquiry_quality(raw_dir),
        "risk": risk,
    }
    output["data_quality"] = build_data_quality(raw_dir, output)

    # 周期错位时隔离受影响数据，防止错误诊断进入正文
    blocking = (output.get("data_quality") or {}).get("blocking_flags") or {}
    if blocking.get("order_period_mismatch") or blocking.get("collection_period_mismatch"):
        quarantined = []
        funnel = output.get("funnel") or {}
        for day in funnel.get("daily") or []:
            if isinstance(day, dict):
                for k in ("imps", "visitor_uv", "fb_uv", "fb_count", "order_count", "pv"):
                    if k in day:
                        day[k] = None
                day["_quarantined"] = True
        if funnel.get("daily"):
            quarantined.append("funnel.daily")
        for ind in (output.get("summary") or {}).get("indicators") or []:
            name = (ind.get("name") or "").lower()
            if any(w in name for w in ("订单", "支付", "转化率", "order")):
                ind["value"] = None
                quarantined.append(f"indicator:{ind.get('name')}")
        if quarantined:
            output["data_quality"]["quarantined_modules"] = quarantined
            print(f"[quarantine] period mismatch — blanked: {quarantined}", file=sys.stderr)

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
