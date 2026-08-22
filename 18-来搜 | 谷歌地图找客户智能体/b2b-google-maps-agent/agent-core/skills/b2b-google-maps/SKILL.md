---
name: b2b-google-maps
displayName: "谷歌地图找客户"
displayDescription: "用谷歌地图查海外实体商家的电话、地址、官网和业务线索"
description: 用 Apify MCP 的 Google Maps Scraper 查找海外实体商家、批发商、分销商、门店、仓库、工厂和本地 B2B 公司线索，导出电话、地址、官网等 CSV/JSON。Use when the user wants Google Maps based B2B leads without APIFY_TOKEN.
---

# 谷歌地图找客户

用 `compass/crawler-google-places` 从 Google Maps 查实体经营地点。适合找批发商、分销商、零售门店、工厂、仓库、办公室等带地址和电话的线索。

## 必问信息

只补问缺失项：

1. 产品或类目
2. 目标国家、区域或城市
3. 客户类型
4. 每个搜索词抓取数量；默认测试用 `maxCrawledPlacesPerSearch=1`
5. 是否开启公司联系方式补全或业务联系人补全；默认不开启，避免额外费用

## 首次初始化

这个 skill 面向小白用户。用户通过 GitHub 安装 skill 后，agent 必须先自动检查 mcpc，不要先要求用户手动配置 `APIFY_TOKEN`。

1. 先读取本机 mcpc 状态：

```bash
command -v mcpc
mcpc --json
```

如果 `mcpc` 不存在，先说明用途并询问是否允许执行 `npm install -g @apify/mcpc`；未经确认不得安装。

2. 如果 `mcpc --json` 里没有 `mcp.apify.com` 的 OAuth profile，执行登录：

```bash
mcpc login mcp.apify.com
```

登录会打开浏览器。等待用户完成 Apify 授权后，再继续。

3. 如果没有 `@apify` session，创建 session：

```bash
mcpc connect mcp.apify.com @apify
```

4. 如果已有 `@apify` 但 `ping` 提示 session 过期，先重启 session：

```bash
mcpc @apify ping || mcpc restart @apify
```

5. 如果重启后仍然失败，再重新登录并重建 session：

```bash
mcpc login mcp.apify.com
mcpc close @apify
mcpc connect mcp.apify.com @apify
mcpc @apify ping
```

初始化成功后，后续所有 Actor 调用都使用 `@apify`，不要改回 Apify REST URL，也不要向用户索要 `APIFY_TOKEN`。

## 执行流程

1. 先说明这是 Maps 实体商家数据，不是普通网页搜索。
2. 生成 2-5 条自然搜索词，不要使用 `site:`、`intitle:`、排除词等 Google Search 语法。
3. 展示搜索地区、数量和费用风险，得到确认后再跑。
4. 运行前先执行“首次初始化”，确认存在可用的 `@apify` session。
5. Actor 可能计费；先展示 Actor、地点/关键词数量、结果上限和 Apify 当前显示的价格信息，取得确认后再用 `scripts/run_mcp_actor.js` 执行。
6. 导出 CSV/JSON，并总结可联系字段。

## 搜索词规则

搜索词要像用户在地图搜索框里输入的一样短：

```text
{product} {customer_type}
{product} {customer_type_synonym}
{customer_type} {product}
```

示例：

```text
pet supplies wholesaler
pet supplies wholesale company
wholesale pet supplies
```

## 推荐 input

```json
{
  "searchStringsArray": ["pet supplies wholesaler"],
  "locationQuery": "United States",
  "maxCrawledPlacesPerSearch": 1,
  "language": "en",
  "countryCode": "us",
  "skipClosedPlaces": false,
  "searchMatching": "all",
  "maxReviews": 0,
  "maxImages": 0,
  "scrapeContacts": false,
  "maximumLeadsEnrichmentRecords": 0
}
```

## 运行命令

```bash
node "$SKILL_ROOT/scripts/run_mcp_actor.js" \
  --actor "compass/crawler-google-places" \
  --input '{"searchStringsArray":["pet supplies wholesaler"],"locationQuery":"United States","maxCrawledPlacesPerSearch":1,"language":"en","countryCode":"us","skipClosedPlaces":false,"searchMatching":"all","maxReviews":0,"maxImages":0,"scrapeContacts":false,"maximumLeadsEnrichmentRecords":0}' \
  --output "$WORKSPACE_ROOT/YYYY-MM-DD_google-maps.csv" \
  --json-output "$WORKSPACE_ROOT/YYYY-MM-DD_google-maps.json"
```

路径约定：

```bash
SKILL_ROOT="$SKILL_INSTALL_PATH"
WORKSPACE_ROOT="$PWD"
```

`SKILL_INSTALL_PATH` 必须使用读取 `$b2b-google-maps` 时返回的 `install_path`，不要硬编码本机目录。

## 字段判断

优先看：

- `title`：商家名
- `phone`：电话
- `website`：官网
- `address`、`city`、`countryCode`：地区
- `categoryName`、`categories`：是否匹配客户类型
- `placeId`：去重主键
