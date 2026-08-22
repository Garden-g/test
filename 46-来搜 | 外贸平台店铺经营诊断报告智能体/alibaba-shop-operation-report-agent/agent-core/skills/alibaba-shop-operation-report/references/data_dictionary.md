# 数据字典：MCP 工具字段说明

> 所有字段都是真实 API 返回，已实测确认。若返回字段名变化，以实际为准。

## 1. `findCustomerShopInfo`
入参：`{}`

返回 `result` 下 5 个段（key 为中文）：

| 段名 | 关键字段 |
|---|---|
| `客户店铺基本信息` | `data.客户公司名称`、`data.客户登录id`、`data.大区名称`、`data.客户主营一级行业` / `二级` / `三级`、`data.店铺主营产品` / `产品2` |
| `客户店铺橱窗商品列表` | `data[]` 列表，每项含 `橱窗位置`、`商品名称`、`类目` |
| `店铺高p4p词列表` | `data[]`，每项含 `关键词`、消耗、点击、曝光等 |
| `店铺高引流词列表` | 同上 |
| `店铺高询盘词列表` | 同上 |

## 2. `store_diagnose_brief`
入参：`{"qry":{}}`

当前返回优先读取 `data.aiSalesWeekDiagnoseList[]`；历史返回可能使用 `values.aiSalesWeekDiagnoseList[]`，只能作为兼容载体：
- `beginDate`、`endDate` — 周窗口。必须选择与用户请求起止日期完全一致的项，禁止固定取第 1 项，因为第 1 项经常是滚动近 7 天而不是自然周。
- `indicatorList[]` — 每项含 `indicatorName`、`value`、`cycleCRC`（环比%）、`valueVsAvg`、`valueVsGood`
- `maTaskList[]` — `taskName`、`actionUrl`、关联商品
- `diagnoseSummary`、`diagnoseTitle`
- `receipt` — 喂给 weekly_all_data_query
- `encryptedReportId` — 同上

## 3. `service_report_weekly_all_data_query`
入参：
```json
{"qry":{"encryptReportId":"<encryptedReportId>","reportAllDataQry":{"receipt":"<receipt>","reportPageCode":[]}}}
```

⚠️ `reportPageCode` 实测无效，必传空数组，客户端自行裁剪。

当前返回优先读取 `data.reportAllData`；历史返回可能使用 `values.reportAllData`。**只用以下运营段**：

| 段名 | 内容 |
|---|---|
| `STORE_DATA_OVERVIEW` | 店铺总览，扁平字段：`abCntValue`、`abCntCycleCrc`、`abCntRivalAvg`、`abCntRivalGood`、`campImpsCntValue`、`shopUvValue`、`shopClkValue`、`shopAbValue`、`p4pImpsCntValue` 等。每个指标都有 `*Value`、`*CycleCrc`（环比）、`*RivalAvg`、`*RivalGood`、`*VsGood` 五件套 |
| `STORE_DIAGNOSIS` | `data.advice`、`data.conclusion`、`data.starLevel`、`data.downStarRisk` |
| `STORE_CONVERSION_RATE_ANALYSIS` | 37 项漏斗：曝光->点击->深度访问->AB->订单各环节转化率 |
| `FLOW_SOURCE_CHANNEL_ANALYSIS` | `data[]` 21 行，每行 `channelType`、`detailUv`、`fbUv`、`uvAbRate`、环比 |
| `EXPOSURE_TOP10_PRODUCT_DATA` | `data[]` 10 行：`productId`、`subject`、`pic`、`exposure`、`click`、`abCnt` |
| `HOT_PRODUCT_RECOMMEND` | `data[]` 推荐商品 |
| `PRODUCT_DATA_OVERVIEW` | 商品分层 + Top5 类目业绩 |
| `CATEGORY_EXPANSION_SUGGESTION` | `data[]` 建议扩展类目 + 需求指数 |
| `BRAND_AD_EFFECT_DATA` | 顶展/问鼎曝光、点击、CTR、花费 |
| `BRAND_AD_OPPORTUNITY_NEW_OPPORTUNITY` | 新机会词 |
| `BRAND_AD_OPPORTUNITY_RENEWAL_WORD` | 续约词 |
| `WENDING_AND_TOP_EXPRESS_EFFECT_DATA` | 问鼎/顶展明细 |
| `P4P_SEARCH_WORD_OPTIMIZ_SUGGESTION` | `highImpsLowClk[]`、`lowImpsHighClk[]`、`lowRelevance[]` 三组词 |
| `STAR_LEVEL_DATA_OVERVIEW` / `OPPORTUNITY_STAR_LEVEL` / `TRADE_STAR_LEVEL` | 三类星级 |
| `BUSINESS_ASSISTANT_USAGE_DATA` | 生意助手使用情况 |
| `ACTION_SUGGESTION` | `busCount`（28 天每日序列）+ `warningMaTask[]` |

**红线，绝不取**：`STORE_COMMUNICATION_*`、`STORE_INFRASTRUCTURE_*_WEEKLY`、`STORE_ACCOUNT_*`、`SUPPLY_*`、`BUYER_DISTRIBUTION_DATA`

## 4. `data_advisor_shop_summary`
入参：
```json
{"advisorQueryParam":{"statisticsType":"7d|30d","startDate":"YYYY-MM-DD","endDate":"YYYY-MM-DD"}}
```

返回 `data[0]` 单条扁平宽表，含 100+ 字段。运营关键字段：

| 字段 | 含义 |
|---|---|
| `abCnt` / `abCntRivalAvg` / `abCntRivalGood` | 商机数 + 行业均值/优秀 |
| `campImpsCnt` / `campImpsCntRivalAvg` | 总曝光 |
| `shopUv` / `shopUvRivalAvg` | 店铺 UV |
| `shopClk` / `shopClkRivalAvg` | 店铺点击 |
| `p4pImpsCnt` / `p4pClkCnt` / `p4pCost` | P4P 广告 |
| `topAdImpsCnt` / `topAdClkCnt` | 顶展广告 |
| `wendingImpsCnt` / `wendingClkCnt` | 问鼎广告 |
| `prodCnt` / `abProdCnt` | 商品总数 / 有商机商品数 |
| `addCartCnt` / `addCartByrCnt` | 加购数据 |
| `orderCnt` / `orderAmt` | 订单（仅做总览数字，不展开业务分析） |

## 5. `data_advisor_shop_region`
入参：
```json
{"regionQueryParam":{"dimensionType":"<dim>","startDate":"...","endDate":"...","statisticsType":"week|month","terminalType":"TOTAL"}}
```

当前 collector 只使用已核对的 `shop_uv`、`total_imps_cnt`、`total_bus_cnt`。每次执行仍须以当前工具 schema 为准；不要沿用旧地域枚举，也不要因为历史文档出现过某个值就自行扩展。

返回 `data[]`，每条：`countryName`、`regionName`（大洲）、`countryUv`（数值）、`countryUvRate`（占比）、`statDate`、`uv`（=值，redundant）、`uvRate`

## 6. `icbu_ads_hateoas_query`
入参：
```json
{"entityType":"company","filters":{"summaryTypes":"wholeSite"},"include":"data,links","pageIndex":1,"pageSize":20}
```

`icbu_ads_account_diagnosis` 已返回业务 410，不再作为主流程或 fallback。注意它可能出现外层 `success:true`、内层 `data.code:410`；必须检查业务层。HATEOAS 公司实体用于获取当前广告账户入口和只读下钻链接；目标周账户诊断使用：

```json
{"entityType":"diagnosis","filters":{"endDate":"2026-07-19"},"include":"data","pageIndex":1,"pageSize":20}
```

当前返回路径为 `data.data[0].result`，其中包含 `overviewSummary`、`diagnosisConclusions` 和 `problemCampaigns`。需要计划/报告明细时，继续按返回的 `links` 和当前 schema 查询，不猜旧工具参数。

常见返回为 `data.data[]`，实体字段会随 `include` 和账号权限变化。返回只有公司标识时，只能证明广告账户入口可读，不能写成已取得消耗、ROI 或计划诊断。

## 7. `icbu_ads_campaign_diagnosis`
入参：
```json
{"campaignId":"<id>","startDate":"...","endDate":"..."}
```

针对单个问题计划下钻分析。

## 7.1 商品与交易的精确周期规则

- `data_advisor_shop_product` 只接受 `shopProductQueryParam.statisticsType/statDate/pageNo/pageSize` 等当前 schema 字段，`pageSize` 最大 20；不要传 `startDate/endDate`。精确自然周应逐日采集并按商品聚合。canonical 文件名为 `data_advisor_shop_product.json`，必须带 `periodStart/periodEnd/rowCount/sampledRows/maximumRecordCount/truncated/ordering/coverage`。默认每日至少 3 页（按曝光前 60）或直到短页/无新增；`recordCount` 大于采集数时明确标成样本，不能把首屏 20 条当全店。
- `queryTradeListMcp` 的日期和分页必须包在 `fieldName_0`：`createDateFrom`、`createDateTo`、`start`、`limit`。持续分页到短页、空页或无新增交易号，不能只取前 20 条。

## 8. `queryCustomerGoodsCateSummary`
入参：`{}`

返回 `result[]`，每行含 `cateLv1Id`/`cateLv1Desc`、`cateLv2Id`/`cateLv2Desc`、`cateLv3Id`/`cateLv3Desc`、商品数。

## 9. `shop_risk_diagnosis`
入参：`{}`

返回 `data`：
- `fraudOrderCnt` — 欺诈订单数
- `iprNum` — IPR 投诉数
- `punishPoint` — 累计扣分
- `todayPunishNum` — 今日处罚数
- `majorViolationTypes[]` — 主要违规类型
- 各种风险计数：`infringingProductCnt`、`forbiddenProductCnt`、`repeatComplaintCnt`、`highFrequencyComplaintCnt` 等
- `aiAutoRaiseUrl` — 一键跳转处理链接

---

## 通用约定

- 默认由 agent 直接调用当前 Accio MCP 只读工具，并按本表的固定文件名保存返回；不要在用户交付中暴露连接器、鉴权或运行时类型信息。当前 search 不到的工具直接记为数据缺口，不调用旧快照名称。
- 周窗口规则：周一 ~ 周日（统一用 ISO 周）
- 月窗口规则：自然月 YYYY-MM-01 ~ 月末
