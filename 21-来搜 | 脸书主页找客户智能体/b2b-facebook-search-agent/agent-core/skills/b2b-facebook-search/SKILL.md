---
name: b2b-facebook-search
displayName: "脸书主页找客户"
displayDescription: "用脸书搜索查海外企业主页、公开业务信息和联系方式"
description: 用 Apify MCP 的 Facebook Search Scraper 查找海外 Facebook 企业主页、商家页、品牌页和社媒活跃客户，导出 raw 数据并标准化为 B2B CSV。Use when the user wants Facebook page based B2B leads without APIFY_TOKEN.
---

# Facebook主页找客户

用 `apify/facebook-search-scraper` 查 Facebook 企业页、商家页、品牌页。适合官网弱但 Facebook 活跃的市场，也适合先拿企业主页、电话、邮箱、官网、粉丝量等线索。

## 必问信息

只补问缺失项：

1. 产品或类目
2. 目标国家、区域或城市
3. 客户类型
4. 抓取数量；默认先测 `resultsLimit=1`

## 首次初始化

这个 skill 面向小白用户。用户通过 GitHub 安装 skill 后，agent 必须先自动检查 mcpc，不要先要求用户手动配置 `APIFY_TOKEN`。

1. 先读取本机 mcpc 状态：

```bash
command -v mcpc
mcpc --json
```

如果 `mcpc` 不存在，先说明它用于连接 Apify MCP，并询问用户是否允许执行 `npm install -g @apify/mcpc`；未经确认不得下载或全局安装。

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

1. 生成 2-6 条 `categories` 搜索词；英语市场只用英文，非英语市场可混合本地语言。
2. `locations` 单独填写地区，不要把地区拼进每条关键词。
3. 展示费用风险和默认数量，确认后执行。
4. 运行前先执行“首次初始化”，确认存在可用的 `@apify` session。
5. Actor 可能计费；先展示 Actor、输入规模、结果上限和 Apify 当前显示的价格信息，取得确认后再用 `scripts/run_mcp_actor.js` 执行，并保留 raw CSV 和 raw JSON。
6. 用 `scripts/normalize_facebook_search.js` 把 raw JSON 转成统一 B2B CSV。

## 搜索词规则

| 客户类型 | 默认关键词 |
| --- | --- |
| importer | `{product} importer`, `{product} import agent`, `{product} sourcing partner` |
| wholesaler | `{product} wholesaler`, `{product} wholesale supplier`, `{product} bulk supplier` |
| distributor | `{product} distributor`, `{product} authorized distributor`, `{product} distribution partner` |
| brand | `{product} brand`, `{product} brand owner`, `{product} private label brand` |
| retailer | `{product} retailer`, `{product} retail chain`, `{product} multi-store retailer` |

## 推荐 input

```json
{
  "categories": ["pet supplies wholesaler"],
  "locations": ["United States"],
  "resultsLimit": 1
}
```

## 运行命令

```bash
node "$SKILL_ROOT/scripts/run_mcp_actor.js" \
  --actor "apify/facebook-search-scraper" \
  --input '{"categories":["pet supplies wholesaler"],"locations":["United States"],"resultsLimit":1}' \
  --output "$WORKSPACE_ROOT/YYYY-MM-DD_facebook-search-raw.csv" \
  --json-output "$WORKSPACE_ROOT/YYYY-MM-DD_facebook-search-raw.json"

node "$SKILL_ROOT/scripts/normalize_facebook_search.js" \
  --input-json "$WORKSPACE_ROOT/YYYY-MM-DD_facebook-search-raw.json" \
  --output "$WORKSPACE_ROOT/YYYY-MM-DD_facebook-search-b2b.csv" \
  --customer-type "wholesaler"
```

路径约定：

```bash
SKILL_ROOT="$SKILL_INSTALL_PATH"
WORKSPACE_ROOT="$PWD"
```

`SKILL_INSTALL_PATH` 必须使用读取 `$b2b-facebook-search` 时返回的 `install_path`，不要硬编码本机目录。

## 交付物

默认交付两份文件：

- raw CSV/JSON：仅保留完成 B2B 开发所需的公司公开字段；默认删除或遮蔽私人邮箱、私人手机号、个人住址和无关个人资料
- 标准化 B2B CSV：统一为公司名、官网、邮箱、电话、Facebook 链接、备注等字段

只有用户明确说明合法用途并确认需要时，才保留额外个人联系方式；不得因为 Actor 返回了字段就默认交付。临时原始文件在标准化和复核完成后删除，除非用户明确要求保留。
