---
name: alibaba-boss-roi-weekly-report
displayName: "阿里老板投产周报"
displayDescription: "生成阿里国际站老板投产复盘表格并明确标记数据边界"
description: "Generate a boss-facing Alibaba.com ROI weekly report as a safe XLSX workbook. Use when the user asks to review Alibaba.com spend, ad ROI, inquiry quantity or quality, order output, product rhythm, keyword opportunities, seller reply quality, follow-up risk, or any weekly/monthly business recap for a boss. Final deliverable must be .xlsx."
---

# 阿里老板投产周报

## Goal

Generate an Alibaba.com boss ROI workbook that answers one question first: **这周钱花得值不值？**

Default to the previous complete natural week. If the user gives dates, use those exact dates. Write every sheet summary in boss-friendly spoken Chinese: short, direct, judgment-first, and tied to money, inquiries, orders, or follow-up risk.

## Output Workbook

Create exactly these 8 sheets:

1. `老板结论`
2. `投产看板`
3. `询盘质量`
4. `订单产出`
5. `商品节奏`
6. `关键词与广告机会`
7. `业务员回复与跟进`
8. `数据质量检查`

Do not mention external CRM brand names anywhere in the workbook. If the available tools cannot confirm an external CRM loop, say only that the platform-visible follow-up loop is not fully confirmable.

Each business sheet must start with a spoken summary line, not a technical explanation. Use this pattern:

- `老板口径`: one sentence on what the boss should know.
- `关键证据`: the 2-4 most important numbers or facts.
- `今天动作`: what should be done today.
- `下周复查`: the metric to check next week.

Use ordinary cells, fills, merged cells, status labels, and openpyxl `DataBarRule` conditional formatting only. Do not create Excel charts, drawings, images, shapes, or Excel Table objects. DataBar lives inside the worksheet `<conditionalFormatting>` node and survives the sanitize step that strips `xl/drawings/` and `xl/tables/`.

## Sheet Layout Contract

Every business sheet (and the boss page, with a small variation) is rendered as four physical regions, in this exact order. The four-region split is what makes the workbook scannable — a single mixed table with one header row is what made the old version hard to read.

1. **Title band** — row 1, merged across all columns, dark-blue fill, white text. Format: `<sheet name>  ｜  <subtitle>  ｜  <status pill>`.
2. **Paragraph rows** — `老板口径 / 关键证据 / 今天动作 / 下周复查` (and on the boss page, the six boss-level paragraphs). Column A holds the label with a light-blue fill; columns B through the last column are merged and hold one full sentence. Row height auto-grows for long text.
3. **Visual cards** — preceded by a section band reading `可视化看板：<topic>`. Each card row carries six cells: `类型 | 对象 | 数值 | 比例 | 状态 | 提示`. The 比例 column stores a numeric 0–1 ratio with `0%` number format; a `DataBarRule` is registered on that column so Excel renders an in-cell coloured bar. Use blue (`638EC6`) for positive metrics and red (`C00000`) when the card represents a warning (failed ROI, 12h+ unreplied, bleeding products, missing data).
4. **Detail table** — preceded by a section band, then a row of proper column headers (dark-blue fill, white bold text), then the detail rows. `freeze_panes` must anchor immediately below the detail header. `auto_filter.ref` covers only the detail range (header through last detail row); paragraph and visual regions stay outside the filter.

Between regions, insert blank spacer rows (height ~6pt) so the regions are visually separated even on screens without grid lines.

`build_xlsx.py` exposes `Block` constructors — `title_block / paragraph_block / section_block / visual_block / detail_header_block / detail_block / blank_block` — and a `write_blocks(...)` layout engine that owns merging, fills, borders, fonts, row heights, DataBar registration, freeze anchor, autoFilter scope, and tab colour. Builders must return `list[Block]`; do not write rows to worksheets directly.

## Status Palette

Status text is normalised through the `STATUS_PALETTE` dict in `build_xlsx.py`. Every status word (`红灯 / 黄灯 / 绿灯 / P0 / P1 / P2 / P3 / 高质量 / 低质量 / 待补信息 / 预警 / 健康 / 印钞款 / 失血款 / 潜力款 / 观察款 / 金词 / 烧钱词 / 潜力词 / 拓展词 / 未返回 / 不可判断 / 可判断 / 可用`) maps to one (fill, font) pair so the same word always looks the same across all eight sheets. `未返回 / 不可判断 / 未拆人 / 周期错位` cells are additionally dimmed (italic grey, light fill) so they never compete with real data for the boss's eye. Tab colours are set from this palette based on the boss-level status (and the data-quality sheet's own status for that one tab).

## Read-Only Tool Plan

Read `references/tools.md` when deciding which Accio Alibaba tools to call. The core collection chain must be explicit and read-only.

### 1. Store and weekly report backbone

Call these first:

- `findCustomerShopInfo`: shop profile, main categories, showcase products, high-inquiry words, high-P4P-cost words.
- `store_diagnose_brief` with `{ "qry": {} }`: weekly diagnosis entry and weekly report IDs.
- `shop_risk_diagnosis`: shop and product risk signals.
- `queryCustomerGoodsCateSummary`: product category structure.

If `store_diagnose_brief` returns `encryptedReportId` and `receipt`, call:

- `service_report_weekly_all_data_query`: full weekly report segments.

### 2. Spend, traffic, orders, and products

Call:

- `data_advisor_shop_summary`: shop business summary for the report period.
- `data_advisor_shop_region`: call three times for `shop_uv`, `total_imps_cnt`, and `total_bus_cnt`.
- `data_advisor_shop_product`: product performance. Use only `shopProductQueryParam.statisticsType/statDate/pageNo/pageSize`; `pageSize` is at most 20. For an exact seven-day report, collect each natural day and aggregate by product. Default to at least 3 pages per day or stop on a short/no-new-ID page; disclose `recordCount`, sampled count, ordering, and truncation. Never pass unsupported `startDate/endDate`.
- `icbu_ads_hateoas_query`: first use `entityType=company`, `filters.summaryTypes=wholeSite`, and `include=data,links` for the current account entry and navigation. Then follow the returned `diagnose` contract with `entityType=diagnosis`, `filters.endDate=<period end>`, and `include=data` to retrieve the exact seven-day account spend, clicks, inquiries, lead cost, and diagnosis. Do not call retired `icbu_ads_account_diagnosis`; its outer envelope may say success while the business payload is `code=410`.
- `queryTradeListMcp`: order/contract list. Put exact dates and pagination in `fieldName_0.createDateFrom/createDateTo/start/limit`; continue until a short/empty page or no new trade ID.
- `list_products`: backfill product ID and links from product titles.

Optional only when needed:

- `queryGoodsInfoByGoodsIdList` or `list_products_by_id` for product details.
- `data_advisor_account_summary` for employee data if available.
- `data_advisor_visitor_detail` for visitor detail if needed for a deeper review.

### 3. Keyword and ad opportunity

Call:

- `searchKeywordList`: brand ad keyword opportunities and keyword layers.
- `searchNextMonthAuctionResource`: next-month auction/tagging resources.
- `getAllBehaviorsSemanticForKeywordRec`: platform behavior signals.
- `data_advisor_product_selection`: recent 30-day industry product opportunities. Mark this as rolling 30-day context, not the exact weekly period.

Optional only when a campaign-level diagnosis is needed:

- Follow read-only `links` returned by `icbu_ads_hateoas_query`, or call `icbu_ads_hateoas_query` for the linked entity and filters.
- `icbu_ads_campaign_diagnosis`
- Use the report link/filter contract exposed by `icbu_ads_hateoas_query` for datasource loading; do not call the retired `icbu_ads_report_load_datasource`.
- `icbu_ads_report_execute_sql`

### 4. Inquiry quality, seller reply, and follow-up risk

Call:

- `subaccount_query`: seller/subaccount candidates.
- `query_seller_shop_dim_diag_data`: shop-level reply and service diagnosis.
- `query_seller_acct_dim_diag_data`: account-level reply/service diagnosis.
- `query_seller_chat_quality_check_detail`: chat quality issues such as read-unreplied, timeout, repeated replies.
- `query_recent_conversation`: recent conversations in the period.
- `query_conversation_msg`: selected conversation messages for quality judgment.
- `query_contact`: contact list if needed for follow-up context.

Optional only when available and useful:

- `get_buyer_basic_info`: buyer level, country, and buyer profile.
- `get_seller_basic_info`: seller/business knowledge.
- `query_im_card_info`: semantic card descriptions when message cards need explanation.

Never call write, publish, edit, message-send, ad-mutation, credit-consuming, or optional automation/growth toolkit tools. Examples to avoid include `send_msg`, `publish_product`, `batch_edit_product`, `batchReserveKeywords`, `icbu_ads_entity_campaign_product_create`, and `icbu_ads_entity_campaign_product_delete`.

## Execution

Use the current Accio conversation Run workspace, with `RAW_DIR=./raw` and `OUTPUT_DIR=./outputs`. This Skill does not create, modify, or replace Accio's Run/Run ID. Every raw response, normalized file, narrative file, and workbook must stay in the current conversation workspace, and another conversation's files must never be used as fallback data.

Collect read-only data by searching and calling the current Accio MCP tools directly, then save each returned business payload under the fixed raw filename documented in `references/tools.md` inside this run's `RAW_DIR`. Do not depend on an unverified local CLI. `scripts/collect_raw.js` is only an optional adapter when the environment explicitly provides a compatible connector; in that case it requires `--accio-cli <path>`.

Normalize data:

```bash
/usr/bin/python3 <skill_dir>/scripts/prepare_data.py \
  --raw-dir <RAW_DIR> \
  --mode weekly \
  --period-start YYYY-MM-DD \
  --period-end YYYY-MM-DD \
  --title-period YYYYWww \
  --output <OUTPUT_DIR>/report_data.json
```

Analyze:

```bash
/usr/bin/python3 <skill_dir>/scripts/analyze.py \
  <OUTPUT_DIR>/report_data.json \
  <OUTPUT_DIR>/analysis.json
```

Build the Agent narrative fact pack:

```bash
/usr/bin/python3 <skill_dir>/scripts/build_narrative_brief.py \
  --report-data <OUTPUT_DIR>/report_data.json \
  --analysis <OUTPUT_DIR>/analysis.json \
  --output <OUTPUT_DIR>/narrative_brief.json
```

Then read `references/narrative_prompt.md`. The executing Accio Agent must use its own model capability to read the current run's `narrative_brief.json`, `analysis.json`, and `report_data.json`, then write `<OUTPUT_DIR>/narrative.json`. Do not ask the user for an API key and do not call any third-party LLM provider from scripts. If Accio supports a subagent for this step, it may write `narrative.json`; otherwise the current Agent writes it directly.

Build and validate XLSX:

```bash
/usr/bin/python3 <skill_dir>/scripts/build_xlsx.py \
  --report-data <OUTPUT_DIR>/report_data.json \
  --analysis <OUTPUT_DIR>/analysis.json \
  --raw-dir <RAW_DIR> \
  --narrative <OUTPUT_DIR>/narrative.json \
  --output <OUTPUT_DIR>/<公司简称>-老板投产周报-<YYYYWww>.xlsx
```

If any source is supplemented, a period is corrected, or `narrative.json` changes, rerun normalization, analysis, narrative fact-pack generation, workbook build, and validation in the current conversation workspace. Do not report the supplemented data as complete while an older workbook is still on disk.

## Sheet Intent

- `老板结论`: 1-minute boss view. State whether spend looks worthwhile, whether ROI can be judged, the biggest risk, the biggest opportunity, and the Top actions.
- `投产看板`: spend, inquiries/leads, order count, order amount, lead cost, and whether ROI can be judged. Missing spend or order amount means “回报算不清”.
- `询盘质量`: high-quality, low-quality, pending-info, P0/P1 follow-up risks, and row-level actions. Judge by L level plus buying signals such as price, MOQ, sample, spec, quantity, delivery time, payment, customization, contact info, and purchase plan.
- `订单产出`: inquiry-to-order funnel, order count, amount, trade details, and period alignment. If period is mismatched, do not output trend values.
- `商品节奏`: winning/potential products, high-exposure zero-inquiry products, new-product availability, product IDs, titles, links, and actions.
- `关键词与广告机会`: gold words, burning-money words, potential words, next-month auction resources, and platform behavior signals.
- `业务员回复与跟进`: 5-minute reply rate, average reply time, 12h+ unreplied, not-followed, repeated replies, seller ranking, and platform-visible follow-up risk.
- `数据质量检查`: source availability, period alignment, missing fields, failed sources, conclusions that must be degraded, and how to handle them.

## Data Quality Rules

Never turn missing data into 0. Use `未返回`, `不可判断`, or `平台可见跟进不足` as appropriate.

- If order amount is missing, do not calculate ROI.
- If ad spend is missing, do not judge ad ROI.
- If report period and module period are mismatched, the home page cannot say the business is healthy.
- If conversation detail is missing, downgrade inquiry quality to chat-quality/summary judgment and say so.
- Do not put Markdown, raw JSON, tool envelopes, stack traces, `errorCode`, `errorMsg`, `-32002`, or internal connector text into workbook cells.
- Put source failures only in `数据质量检查`; business sheets should describe business impact.

## Agent Narrative Rules

The workbook should not read like a template. After deterministic analysis, let the executing Accio Agent write the narrative layer:

- Use `scripts/build_narrative_brief.py` to generate the current run's `<OUTPUT_DIR>/narrative_brief.json`.
- Read `references/narrative_prompt.md` before writing `<OUTPUT_DIR>/narrative.json`.
- The Agent may rewrite summaries and repeated actions, but must not change facts, numbers, dates, priority, owners, or ROI degradation.
- The Agent must merge repeated product, keyword, inquiry, and seller actions into natural business language.
- Do not use a third-party provider API, do not ask for user API keys, and do not mention this narrative step in the workbook.
- If `<OUTPUT_DIR>/narrative.json` is unavailable, `build_xlsx.py` can fall back to deterministic copy for validation, but final boss delivery should include the Agent-written narrative file from the current conversation.

## Excel Safety

Final delivery must pass `build_xlsx.py` validation. The package-safety checks run first; the visual-layout checks run last.

Package safety:

- LibreOffice headless re-save.
- Removal of table, drawing, `tableParts`, and drawing relationship residue.
- Sheet count and names check.
- Boss conclusion one-page check (≤ 25 rows × 8 columns).
- ROI degradation check when order amount or ad spend is missing.
- `unzip -t`.
- `openpyxl.load_workbook()`.
- Package scan for forbidden internal text and unsafe workbook objects.

Visual layout (enforced for every sheet):

- Row 1 carries a merged title band.
- Every sheet except `老板结论` has at least one `DataBarRule` (`老板结论` is intentionally text-only).
- `freeze_panes` is anchored at the detail-header row (row index ≥ 9, never `A1` or `A2`).
- `auto_filter.ref` covers only the detail-table range and starts at row ≥ 8; `老板结论` has no autoFilter because it holds two short detail tables.
- `sheet_properties.tabColor` is set on all eight tabs.

If any validation step fails, fix the workbook generation and rerun validation before delivery.

## Final Reply

After success, reply briefly:

```markdown
报告已生成：[文件名](outputs/文件名.xlsx)

老板结论：<analysis.one_liner>

本周必抓：
1. <top action>
2. <top action>
3. <top action>
```

Do not expand raw collection details in the user-facing reply.
