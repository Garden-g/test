---
name: b2b-google-search
displayName: "谷歌搜索找客户"
displayDescription: "用谷歌搜索批量查海外客户官网候选线索并导出可核验结果"
description: 用 Apify MCP 的 Google Search Results Scraper 查找海外 B2B 客户官网、进口商、批发商、分销商、品牌方、零售商和公司网页线索，并导出 CSV/JSON。Use when the user asks to find overseas buyers or company websites from Google Search without APIFY_TOKEN.
---

# 谷歌搜索找客户

用 `apify/google-search-scraper` 从 Google 搜索结果里找有独立官网或网页痕迹的海外客户。这个 skill 独立运行，不依赖 `leads-generation-create`，也不读取 `.env` 里的 `APIFY_TOKEN`。

## 必问信息

只补问缺失项：

1. 产品或类目
2. 目标国家、区域或城市
3. 客户类型：进口商、批发商、分销商、品牌方、零售商等
4. 期望数量或页数；默认先小批量测试 `maxPagesPerQuery=1`

## 首次初始化

这个 skill 面向小白用户。用户通过 GitHub 安装 skill 后，agent 必须先检查 `mcpc`，不要先要求用户手动配置 `APIFY_TOKEN`。安装软件会改变用户环境，因此缺少 `mcpc` 时必须先说明用途并取得确认，不能自动下载或全局安装。

1. 先读取本机 mcpc 状态：

```bash
command -v mcpc
mcpc --json
```

如果 `command -v mcpc` 没有输出，先询问用户是否允许执行 `npm install -g @apify/mcpc`；只有明确同意后才安装。若用户不同意，停止并给出手动安装命令。

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

1. 先用中文复述业务目标。
2. 生成最多 10 条 Google 搜索词，并展示给用户确认。
3. 运行前先执行“首次初始化”，确认存在可用的 `@apify` session；Actor 可能计费，必须展示 Actor、输入规模、页数/条数上限和 Apify 当前显示的价格信息，取得用户确认后再运行。
4. 用 `scripts/run_mcp_actor.js` 调用 `call-actor`，不要使用 Apify REST URL，也不要要求 `APIFY_TOKEN`。
5. 导出 CSV；需要保留原始数据时同时导出 JSON。
6. 用中文总结记录数、文件路径、关键字段和下一步筛选建议。

## 搜索词规则

基础格式：

```text
"{product}" {customer_type} {country}
"{product}" {customer_type_synonym} {country}
intitle:"{customer_type}" "{product}" {country}
```

默认追加排除词，减少平台和目录噪声：

```text
-alibaba -amazon -made-in-china -aliexpress -ebay -walmart -dhgate -globalsources
```

客户类型同义词：

| 客户类型 | 英文同义词 |
| --- | --- |
| importer | import company, importing company, import agent |
| wholesaler | wholesale company, wholesale supplier, bulk supplier |
| distributor | distribution company, authorized distributor, regional distributor |
| brand | manufacturer brand, private label, brand owner |
| retailer | retail store, retail shop, retail chain |

## 推荐 input

英语市场：

```json
{
  "queries": "\"pet supplies\" importer United States -alibaba -amazon -made-in-china -aliexpress -ebay",
  "maxPagesPerQuery": 1,
  "countryCode": "us",
  "languageCode": "en"
}
```

非英语市场可以加本地语言搜索词，但先小批量验证方向；不要一开始放很大页数。

## 运行命令

```bash
node "$SKILL_ROOT/scripts/run_mcp_actor.js" \
  --actor "apify/google-search-scraper" \
  --input '{"queries":"\"pet supplies\" importer United States -alibaba -amazon","maxPagesPerQuery":1,"countryCode":"us","languageCode":"en"}' \
  --output "$WORKSPACE_ROOT/YYYY-MM-DD_google-search.csv" \
  --json-output "$WORKSPACE_ROOT/YYYY-MM-DD_google-search.json"
```

路径约定：

```bash
SKILL_ROOT="$SKILL_INSTALL_PATH"
WORKSPACE_ROOT="$PWD"
```

其中 `SKILL_INSTALL_PATH` 必须取自读取 `$b2b-google-search` 时返回的 `install_path`；不要猜测或硬编码开发机路径。

## 结果筛选

优先保留：

- 有独立官网的公司
- 标题或摘要能匹配客户类型的记录
- 来源 URL 不是平台、黄页、目录站或 marketplace

交付时提醒用户：Google Search 结果是候选网页线索，不等于已验证联系人；邮箱和联系人可后续用 Leads Finder 或官网补全。
