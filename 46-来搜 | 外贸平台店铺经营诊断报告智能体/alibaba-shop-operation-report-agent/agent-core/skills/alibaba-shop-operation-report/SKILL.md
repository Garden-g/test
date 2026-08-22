---
name: alibaba-shop-operation-report
displayName: "阿里店铺经营诊断报告"
displayDescription: "把店铺真实数据诊断成三页老板经营周报或月报表格"
description: "生成阿里巴巴国际站老板优先的店铺经营周报/月报 XLSX 工作簿。Use this skill when the user asks for 店铺运营报告、老板周报、经营周报、经营月报、保星诊断、阿里国际站复盘、店铺数据分析、上周/上月经营情况、明天先做哪几件事, especially when they need a concise manager-ready workbook whose visible facts are diagnosed by an operations-expert LLM. Final deliverable must be .xlsx."
---

# 阿里国际站老板经营周月报

## What This Skill Does

生成一份给老板先看的阿里国际站经营决策 `.xlsx` 工作簿，而不是普通数据罗列。报告要先回答：

- 店铺有没有降星、交易力或服务力风险？
- 本周钱和增长卡在哪里？
- 今天 / 本周必须让谁做什么？
- 哪些商品、渠道、关键词应该马上处理？

报告正文使用业务语言。可以在执行说明里写清业务采集步骤，但最终 XLSX 工作簿不要出现原始技术报错、JSON 字段名或内部执行细节。

## Output Structure

默认生成周报；用户明确说月报、上月、某月时生成月报。

老板版工作簿固定只包含 3 个 sheet：

| Sheet | 内容 |
|---|---|
| `本周结论` | 一句话结论，以及最多 3 个“发生了什么、为什么、怎么解决、怎么复查”。 |
| `经营问题诊断` | 由运营专家 LLM 合并后的问题组，每行都有证据、判断、原因和解决方案。 |
| `行动与复查` | 最多 8 个根因级动作，不按商品、关键词或渠道机械拆任务。 |

原始指标、商品明细、关键词、采集状态和确定性分析继续保存在当前
Run 的 JSON 文件中，供诊断和追溯使用，但不再作为数据附录搬进 XLSX。

## Execution Workflow

0. 使用当前 Accio 对话 Run 已分配的工作目录。本技能不创建、修改或替换 Accio 的 Run/Run ID；设置 `RAW_DIR=./raw`、`OUTPUT_DIR=./outputs`，只读写当前对话目录，不读取其他对话的文件。
1. 判断报告模式：
   - 周报：默认上一个完整自然周，周一到周日。
   - 月报：上一个完整自然月；用户指定月份时按指定月。
2. 采集原始数据到本次 `RAW_DIR`。每个调用都保留完整原始返回，便于回溯。
3. 运行清洗和确定性分析脚本：
   ```bash
   /usr/bin/python3 <skill_dir>/scripts/prepare_data.py \
     --raw-dir <RAW_DIR> \
     --mode weekly \
     --period-start 2026-04-13 \
     --period-end 2026-04-19 \
     --title-period 2026W16 \
     --output <OUTPUT_DIR>/report_data.json
   ```
4. 读取 `references/diagnosis_prompt.md`，把本次
   `report_data.json` 和 `analysis.json` 作为事实包，交给运营专家 LLM
   重新诊断，保存为 `<OUTPUT_DIR>/management_diagnosis.json`。
   `analysis.json` 里的规则信号和机械清单只能作为证据候选，不能直接成为
   XLSX 结论或行动。
5. 生成 XLSX：
   ```bash
   /usr/bin/python3 <skill_dir>/scripts/build_xlsx.py \
     <OUTPUT_DIR>/report_data.json \
     <OUTPUT_DIR>/analysis.json \
     <OUTPUT_DIR>/management_diagnosis.json \
     <OUTPUT_DIR>/<公司简称>-老板经营周报-<YYYYWww>.xlsx
   ```
6. 如果构建器报告诊断质量失败，只把失败行连同原始证据交给运营专家
   LLM 重写 1 次。第二次仍失败就停止交付，不能退回数据搬运版。
7. 若补采、纠正周期或替换了任何原始返回，必须在当前对话工作目录重新运行第 3 至 6 步并重新校验 XLSX。旧工作簿不得继续作为最终交付。

`prepare_data.py` 会自动连带生成 `analysis.json`，不要手写字段映射或临时拼报告。

`scripts/build_html.py` 和 `scripts/build_docx.py` 只作为附加导出能力。老板经营报告的主交付物始终是 XLSX；只有用户明确追加 HTML 或 Word，且 XLSX 已生成后，才可以再生成附加版本。

## Data Collection

默认由 agent 直接 search/call 当前 Accio MCP 的只读工具，并把每次返回保存为 `prepare_data.py` 约定的固定文件名。文件名与字段映射见 `references/data_dictionary.md`；不要依赖未验证的本机 CLI。`scripts/collect_raw.js` 仅作为环境明确提供兼容数据连接器时的可选适配器，必须显式传 `--accio-cli <path>`，不是正常用户主链。

关键输入文件名由 `prepare_data.py` 读取；详细字段和工具说明见 `references/data_dictionary.md`。只有需要排查字段时才读取该 reference。

- `store_diagnose_brief` 必须按 `beginDate/endDate` 选择目标自然周；第 1 条常是滚动最近 7 天，禁止固定取索引 0。
- 广告先查 HATEOAS 公司入口，再用 `entityType=diagnosis`、`filters.endDate=<周日>` 取目标 7 天账户诊断，分别保存为 `icbu_ads_hateoas_query_company.json` 和 `icbu_ads_hateoas_query_diagnosis.json`。不能只看外层 `success`；业务层 `code=410` 仍是失败。
- 商品明细 `pageSize` 最大 20。默认至少取前 3 页或直到短页/无新增；如果 `recordCount` 大于已采数，必须记录采样范围。用户明确要求“全量商品”时继续分页到 `recordCount` 或明确安全上限，并披露未覆盖数量。
- 订单查询把日期和分页放在 `fieldName_0` 内，按 `start/limit` 继续到短页/空页或无新增交易 ID；禁止把首屏当整周订单。

## Boss-First Diagnosis Rules

- **KPI 双基准**：同行均值是达标线，同行优秀是增长目标。高于均值但明显低于优秀时，写“达标但离优秀差距大”，不要写“表现优异”。
- **星级风险优先**：只要出现降星、预测星级低于当前或交易力低分，就进入首页候选重点，由运营专家结合影响和证据完整度排序。
- **高曝光 0 询盘品优先**：Top 曝光商品里，只要是橱窗品且 0 询盘，就列为高优先级处理，不要归入普通观察款。
- **商品结构要落地**：展示低质品、普通品、潜力品、平台优品、平台爆品，并指出普通品过剩、爆品过少、潜力品孵化方向。
- **服务力只做摘要**：展示 5 分钟回复率、平均回复时长、12h+ 回复条数等老板指标；不展开聊天记录、买家对话或业务员质检细节。
- **渠道稳定性要判断**：搜索、系统推荐、会场、活动、付费资源位出现明显下滑或为空时，要生成具体动作。
- **问题少而重**：老板首页最多 3 个问题，行动表最多 8 个动作。相同根因的商品、关键词、渠道或客户必须合并，并保留最多 3 个代表对象。
- **LLM 先诊断再展示**：任何指标、对象和变化进入 XLSX 前，都必须补齐专家判断、核心原因和解决方案。脚本只能渲染诊断结果。
- **负责人不补造**：真实姓名只有在事实包明确返回时才可展示；没有姓名时，店铺、商品、流量、广告、关键词写“运营”，询盘、客户、报价和跟进写“业务”；无法可靠归类就省略负责人列。

## Report Language Rules

- 全程中文。
- 工作簿正文不写原始工具字段、JSON 字段名、技术报错或内部执行细节。
- 可以写阿里后台业务入口，例如“生意助手 - 店铺诊断 - 星级能力项”。
- 不编造数据。获取不到且不影响结论的字段直接删除；只有确实阻断判断时，才在首页底部用一句业务语言说明限制。
- 不显示 `未返回`、`待确认`、`不可判断`、原始字段名或整块采集状态。
- Sheet 名和表头使用自然中文，不使用 Backlog、P0/P1、赛马、手术台等黑话。

## Delivery Reply

生成后回复用户：

```markdown
报告已生成：[文件名](outputs/文件名.xlsx)

老板结论：<management_diagnosis.executive_conclusion>

本期必抓：
1. <diagnosed action>
2. <diagnosed action>
3. <diagnosed action>
```

如果是周报，可补一句“下次说出 X 月月报即可切换月报”；如果是月报，可补一句“需要下钻最近一周动作时，说出周报即可”。

## Excel Safety

最终交付前必须由 `scripts/build_xlsx.py` 完成安全流程：LibreOffice headless 重存，清理 `xl/tables/`、空 `xl/drawings/`、`tableParts`、drawing/table relationships，再通过 `unzip -t`、`openpyxl.load_workbook()` 和包内残留扫描。任一步失败都不要交付 XLSX，先修复后重新生成。
