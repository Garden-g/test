# Alibaba Boss ROI Weekly Report Tools

Use this reference to choose Accio Alibaba read-only tools for the weekly XLSX report. Keep the final workbook business-facing: tool names may guide the agent, but workbook cells should describe business impact.

## Core Store Context

| Tool | Use for | Required args |
| --- | --- | --- |
| `findCustomerShopInfo` | Shop basics, main industry, showcase products, high-inquiry words, high-P4P-cost words | none |
| `store_diagnose_brief` | Weekly diagnosis entry, report IDs, high-level diagnosis | `qry` |
| `shop_risk_diagnosis` | Shop/product risk signals | none |
| `queryCustomerGoodsCateSummary` | Product category structure | none |
| `service_report_weekly_all_data_query` | Full weekly report segments after `store_diagnose_brief` returns report ID and receipt | `qry` |

## Spend, Traffic, Orders, And Product Performance

| Tool | Use for | Required args |
| --- | --- | --- |
| `data_advisor_shop_summary` | Spend-adjacent shop performance, leads, orders, order amount when returned | `advisorQueryParam` |
| `data_advisor_shop_region` | Country/region distribution; call for `shop_uv`, `total_imps_cnt`, `total_bus_cnt` | `regionQueryParam` |
| `data_advisor_shop_product` | Product exposure, click, inquiry, and conversion data | `shopProductQueryParam.statisticsType/statDate/pageNo/pageSize`; `pageSize` 最大 20，禁止传 `startDate/endDate` |
| `icbu_ads_hateoas_query` | Current ad-account entry and read-only drill-down links | `entityType=company`, `filters.summaryTypes=wholeSite`, `include=data,links`, `pageIndex`, `pageSize` |
| `icbu_ads_hateoas_query` | Exact seven-day account diagnosis | `entityType=diagnosis`, `filters.endDate=<period end>`, `include=data`, `pageIndex=1`, `pageSize=20` |
| `queryTradeListMcp` | Trade/order contract list for the exact period | `fieldName_0.createDateFrom/createDateTo/start/limit`; continue paging until a short/empty page or no new trade ID |
| `list_products` | Backfill product IDs and links from product titles | `queryDTO` |
| `queryGoodsInfoByGoodsIdList` | Optional product detail by IDs | `query` |
| `list_products_by_id` | Optional exact product lookup | `productId` |

## Keyword And Advertising Opportunity

| Tool | Use for | Required args |
| --- | --- | --- |
| `searchKeywordList` | Brand ad keyword opportunities, hot words, sell status | `query` |
| `searchNextMonthAuctionResource` | Next-month auction/tagging resources | `query` |
| `getAllBehaviorsSemanticForKeywordRec` | Platform behavior signals for keyword decisions | none |
| `data_advisor_product_selection` | Rolling recent 30-day industry product opportunities | `productSelectionParam` |
| `icbu_ads_hateoas_query` | Optional campaign/product entity review by following returned read-only links | `entityType`, `filters`, `include`, `pageIndex`, `pageSize` |
| `icbu_ads_campaign_diagnosis` | Optional campaign-level diagnosis | `campaignId`, `startDate`, `endDate`, `question` |
| `icbu_ads_report_execute_sql` | Optional ad SQL execution after datasource loading | `sqlQueries` |

`icbu_ads_account_diagnosis` and `icbu_ads_report_load_datasource` currently return business 410 and must not be used as primary or fallback calls. The retired account diagnosis can still show outer `success:true`; inspect the nested business payload before calling it usable. Current HATEOAS `diagnosis` returns through `data.data[0].result`, containing `overviewSummary`, `diagnosisConclusions`, and `problemCampaigns`. When deeper report data is needed, use the link/filter contract exposed by HATEOAS; if no usable read-only link is returned, mark ad detail as unavailable.

Exact product-period rule:

- Weekly: call `statisticsType=day` for every date in the report period, paginate with `pageNo/pageSize`, then aggregate the same product across dates.
- Monthly: use `statisticsType=month` and set `statDate` to the first day of the month.
- `statisticsType=week` ignores `statDate`; do not use it to pretend an arbitrary historical natural week was queried.
- Default product review: at least 3 pages per date or until a short/no-new-ID page. Preserve `recordCount`, sampled rows, ordering and truncation. If the user requests every product, continue to the returned total or disclose the explicit cap and uncovered count.
- Canonical trade output must preserve the exact period plus `rowCount/serverTotalCount/pagesFetched/complete/truncated`. If `complete` is false, order count and amount are lower bounds and ROI stays degraded.

## Inquiry Quality And Seller Reply

| Tool | Use for | Required args |
| --- | --- | --- |
| `subaccount_query` | Seller/subaccount candidates | none |
| `query_seller_shop_dim_diag_data` | Shop-level reply and service diagnosis | `buyerType`, `dateType`, `queryDate` |
| `query_seller_acct_dim_diag_data` | Account-level reply/service diagnosis | `buyerType`, `dateType`, `queryDate` |
| `query_seller_chat_quality_check_detail` | Chat quality issues: read-unreplied, timeout, repeated replies | `queryDate` |
| `query_recent_conversation` | Recent conversation list with time-cursor pagination | `request.selfAliId`, `request.limitTimeStamp`, `request.domain`; do not send `pageIndex` or `dateRange` |
| `query_conversation_msg` | Messages for selected conversations | outer `request` containing `conversationId`, optional `selfAliId`, `limitTimeStamp`, `forward`, `count`, `domain` |
| `query_contact` | Contact list for platform-visible follow-up context | `type`, `startVersion` |
| `get_buyer_basic_info` | Optional buyer profile, country, buyer level | `contactAliId` |
| `get_seller_basic_info` | Optional seller/business knowledge | none |
| `query_im_card_info` | Optional semantic description for message cards | `language`, `appkey`, `baseRequest` |

## Response Object Rules

Alibaba read-only tools use several valid response shapes. Do not mark a call as failed just because it lacks a top-level `data` field.

| Tool family | Valid payload carrier | Notes |
| --- | --- | --- |
| `findCustomerShopInfo` | `result` | Contains Chinese-named business sections such as `客户店铺基本信息`, `客户店铺橱窗商品列表`, `店铺高询盘词列表`. |
| `queryCustomerGoodsCateSummary` | `result[]` | Category rows. `success:true` and `errorCode:null` is normal. |
| `searchKeywordList` | `result.data.items[]` | Brand ad keyword rows. |
| `searchNextMonthAuctionResource` | `result.data.items[]` | Next-month auction/resource keyword rows. |
| `getAllBehaviorsSemanticForKeywordRec` | `result[]` | Behavior semantic text rows. |
| `query_seller_shop_dim_diag_data` | `object[]` | Shop-level reply/service metric rows. |
| `query_seller_acct_dim_diag_data` | `object[]` or `content[]` | Account-level reply/service rows; empty arrays mean no rows for that date/type. |
| `query_seller_chat_quality_check_detail` | `object[]` | Chat-quality issue rows. `errorCode:300` with `object:null` means empty/no detail for that query, not a tool failure. |
| `query_recent_conversation` | `object.conversations[]` | Conversation list. Use `subaccount_query` seller `aliId` as `request.selfAliId`; do not use shop customer ID as seller ID. |
| `query_conversation_msg` | `object.messages[]` | Message list for a selected conversation. |
| `data_advisor_shop_product` | `data.data[]` or `data[]` | Required arg key is `shopProductQueryParam`, not `productQueryParam`. |
| `queryTradeListMcp` | `data.tradeList[]`, `data.list[]`, or equivalent returned list | Client-side verify every `createDate` is inside the requested period after pagination. |
| `icbu_ads_hateoas_query` | Company: `data.data[]` plus `links`; diagnosis: `data.data[0].result` | A company ID alone proves only that the account entry is readable. Spend/ROI fields require the diagnosis result or another exact-period source. |

Failure classification:

- Real failure: `success:false`, `ok:false`, `isError:true`, a non-empty/non-200 error code without any payload, or a nested business payload such as `data.code=410` even when the outer envelope says `success:true`.
- Empty but valid: `success:true` with an empty payload or `errorCode:300` and no `object`.
- Success: any non-empty `data`, `result`, `object`, `values`, `content`, `object.conversations`, or `object.messages`.

## Prohibited Tool Types

Do not use tools that mutate data, send messages, publish or edit products, modify ads, consume credits, upload assets, or change automation settings. If a tool name implies `send`, `publish`, `edit`, `set`, `save`, `submit`, `create`, `delete`, `consume`, `upload`, or batch optimization, treat it as unsafe unless the user explicitly asks for that separate action.
