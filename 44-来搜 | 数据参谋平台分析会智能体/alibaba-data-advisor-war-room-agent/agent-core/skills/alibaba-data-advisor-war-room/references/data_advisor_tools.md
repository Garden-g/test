# Data Advisor 15 Tools Reference

Use this reference after the skill triggers and before calling tools. The skill workflow stays in `SKILL.md`; this file keeps the 15-tool detail compact and discoverable.

## Weekly Period Defaults

- Default to the latest 7 complete natural days.
- If Data Advisor sources have T-2 delay, end at the latest complete returned date and state that delay in `数据覆盖与缺口`.
- If the user says "this week", use Monday through the latest complete returned date, then add recent 7-day context when the week is too short.
- Do not treat missing current-day data as zero.

## Store-Side Tools

| Tool | Main use | Grain | Notes |
|---|---|---|---|
| `data_advisor_shop_summary` | Store funnel and peer comparison: exposure, clicks, visitors, inquiries, orders, amount, product counts. | 7d/30d summary | Use first after period parsing. Compare 本店 / 同行均值 / 同行优秀. |
| `data_advisor_account_summary` | Employee or subaccount contribution: product, inquiry, TM, order, amount, online time. | day/week/month | Use for owner assignment only when the returned account can be read clearly. |
| `data_advisor_shop_flow` | Traffic source trend: search, scenario, interaction, self-growth and sub-sources. | day x source | Use to explain where traffic changed before judging product or sales. |
| `data_advisor_shop_channel` | Weekly/monthly channel split such as search, in-store, offsite, recommendation, direct visit. | week/month | Good for channel ROI and channel health. |
| `data_advisor_shop_region` | Country/region performance; call for `shop_uv`, `total_imps_cnt`, `total_bus_cnt` when available. | day/week/month | Compare store countries with industry country ranking. |
| `data_advisor_shop_product` | Product-level performance, product layer, tags, search exposure, clicks, inquiry and AB. | day/week/month | Current schema uses `shopProductQueryParam.statisticsType/statDate/pageNo/pageSize`; `pageSize` is at most 20. Do not pass `startDate/endDate`. For an exact historical week, collect each natural day and aggregate; `week` mode ignores `statDate`. |
| `data_advisor_visitor_detail` | Visitor list: country, keywords, PV, stay time, level, TM/inquiry signal. | detail | Sample high-value visitors only. Useful filters: country, TM/inquiry, keyword, stay time, visit PV. |
| `data_advisor_shop_flow_profile` | Traffic profile: visitor country, category preference, channel scene preference. | 30d profile | Typical `indexName`: `visitor_country`, `cate_total`, `channel_total`; typical `sourceType`: total/search/scenario/interaction/increase traffic. |
| `data_advisor_to_product` | Products also viewed by visitors who visited this shop. | day | Use for competitor-flow diagnosis and product/price/MOQ gap analysis. |

## Category And Opportunity Tools

| Tool | Main use | Grain | Notes |
|---|---|---|---|
| `data_advisor_category_infer` | Infer category ID from natural language. | category lookup | Use only when shop true category or user-selected category is missing. |
| `data_advisor_category_prediction` | Predict category ID from natural language. | category lookup | Cross-check with infer; if both conflict with shop profile, ask user or use shop true category. |
| `data_advisor_industry_cate_rank` | Subcategory ranking by market size, growth, supply-demand, or conversion. | 30d industry | Known risk: some categories can return NaN serialization errors. Retry orderBy/rankType; then mark platform data abnormal. |
| `data_advisor_industry_country_rank` | Country ranking under an industry/category. | 30d industry | Use to decide which countries are platform opportunity countries, then compare with shop traffic countries. |
| `data_advisor_opportunity_discovery` | Segment opportunity discovery by category/country/scene. | 30d/90d | Output opportunities, demand index trend, business-product share and example products. |
| `data_advisor_product_selection` | Hot product selection under category/country and filters such as AB, GMV, price, MOQ. | 1d/7d/30d | Treat as platform opportunity context, not exact weekly shop result. |

## Recommended Call Order

1. `data_advisor_shop_summary`
2. `data_advisor_account_summary`
3. `data_advisor_shop_flow`
4. `data_advisor_shop_channel`
5. `data_advisor_shop_region`
6. `data_advisor_shop_product`
7. `data_advisor_visitor_detail`
8. `data_advisor_shop_flow_profile`
9. `data_advisor_to_product`
10. `data_advisor_category_infer`
11. `data_advisor_category_prediction`
12. `data_advisor_industry_country_rank`
13. `data_advisor_industry_cate_rank`
14. `data_advisor_opportunity_discovery`
15. `data_advisor_product_selection`

If category tools return a category that does not match the actual shop, do not proceed blindly. Use the shop category, the user-confirmed category, or mark the opportunity layer as pending confirmation.

## Diagnosis Outputs From Tool Combinations

These combinations are the minimum evidence patterns for the diagnostic subagent. A single metric can be a signal, but it should not become a firm diagnosis unless another module supports it.

| Combination | Diagnosis to produce |
|---|---|
| `shop_summary` + `shop_flow` + `shop_channel` | Diagnose whether the store problem is traffic volume, traffic quality, channel mix, or conversion after traffic arrives. |
| `shop_summary` + `account_summary` | Diagnose whether inquiry/order gaps are mainly service response, team execution, or product/traffic quality. |
| `shop_region` + `shop_flow_profile` + `industry_country_rank` | Diagnose country mismatch: countries already visiting, countries with platform demand, and countries to prioritize next week. |
| `shop_product` + `to_product` + `visitor_detail` | Diagnose whether buyers are leaking because of product selection, price/MOQ, visual positioning, category mismatch, or missing trust proof. |
| `shop_channel` + `shop_product` | Diagnose whether high-traffic channels are landing on the right products and whether product pages convert that traffic. |
| `visitor_detail` + `account_summary` | Diagnose which buyer groups and which internal roles need follow-up, without inventing named owners. |
| `industry_cate_rank` + `opportunity_discovery` + `product_selection` + `shop_product` | Diagnose which platform opportunities should enter the opportunity pool, which need product validation, and which are only watchlist ideas. |

Every boss-facing diagnosis should contain:

1. Signal: what changed or stands out.
2. Gap calculation: current value vs peer excellent/average, previous period, or expected resource share.
3. Decision type: 加码, 暂停, 修复, 验证, 补数, or 分流.
4. Operation lever: keyword, product page, main image, detail page, P4P, showcase, country, account, quote, or visitor follow-up.
5. Cross-module evidence: at least two supporting facts when possible.
6. Business impact: what this means for inquiry, order, buyer trust, or resource allocation.
7. Root-cause hypothesis: likely reason, not guaranteed truth.
8. Next action: owner role, concrete object, target value, deadline, failure rule, and review metric.

## Decision-Grade Output Rules

- Boss page: only keep the top 3 decisions. Use `加码/暂停/修复/验证/补数/分流` as the decision verb. Long evidence belongs in the appendix.
- Funnel: show current value, target/benchmark, gap, decision, and failure rule. Example: formal inquiries 11 vs excellent 16 means the target gap is +5, not just "inquiry is weak".
- Account race: calculate resource share, result share, efficiency, and treatment. A high-resource low-efficiency account should trigger resource split, SOP repair, or response review; a low-resource high-efficiency account should trigger controlled traffic allocation.
- Product surgery: each SKU or product group must be tagged as 主攻, 修复, 测试, 观察, or 暂停/移出主推. Do not only say "product focus is scattered".
- Channel diagnosis: every channel issue must land on one of four objects: 入口商品, 入口词, 落地页, or 承接账号.
- Country/product/keyword matrix: connect priority countries to product groups and keyword packs. Do not list countries and keywords separately when the business action is one main attack line.
- Visitor follow-up: convert TM/high-stay/high-PV/priority-country visitor groups into follow-up queues with target conversion to formal inquiry.
- Opportunity validation: score platform opportunities by country match, category match, MOQ testability, price band, transaction index, and store readiness. Output a validation plan and stop rule, not a generic "consider selection" note.
- Process tasks are not enough. "Review", "analyze", "split", or "export a list" only count as actions when tied to a concrete business result and review metric.

## Failure Handling

- Tool unavailable: write `未返回` and explain the business impact.
- Empty but valid response: write `未返回/样本不足`, not zero.
- NaN or serialization error: retry safe parameter variants; if repeated, mark platform data abnormal.
- Pagination: record total count and sampled rules. `data_advisor_shop_product` must page with `pageNo/pageSize`; do not silently equate page 1 with full coverage. Keep complete reviewed detail in the appendix while the boss page stays concise.
- Period mismatch: keep source facts but downgrade claims that compare exact weekly performance.
