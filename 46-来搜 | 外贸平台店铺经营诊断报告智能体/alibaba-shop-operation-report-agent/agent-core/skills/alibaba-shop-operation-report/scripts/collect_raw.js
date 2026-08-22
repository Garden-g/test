#!/usr/bin/env node
/**
 * collect_raw.js
 *
 * Collect Alibaba.com operation-report raw data into the filenames expected by
 * prepare_data.py. This optional adapter requires an explicitly supplied,
 * compatible connector executable; the normal skill flow calls MCP directly.
 *
 * Output files are intentionally named for prepare_data.py. Each tool result is
 * unwrapped from the MCP envelope before writing, so Python scripts can read the
 * business JSON directly.
 */
import { mkdirSync, writeFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

function usage() {
  console.error(`Usage:
  node scripts/collect_raw.js \\
    --raw-dir <RAW_DIR> \\
    --mode weekly|monthly \\
    --period-start YYYY-MM-DD \\
    --period-end YYYY-MM-DD

Optional:
  --accio-cli <path>            Explicit compatible connector executable
  --timeout-ms 120000
`);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) {
      throw new Error(`Unexpected argument: ${key}`);
    }
    const name = key.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const value = argv[i + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${key}`);
    }
    args[name] = value;
    i += 1;
  }
  for (const required of ["rawDir", "mode", "periodStart", "periodEnd"]) {
    if (!args[required]) {
      throw new Error(`Missing required --${required.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`);
    }
  }
  if (!["weekly", "monthly"].includes(args.mode)) {
    throw new Error("--mode must be weekly or monthly");
  }
  if (!args.accioCli) {
    throw new Error("--accio-cli is required for this optional adapter; use direct Accio MCP calls in the normal skill flow");
  }
  const config = {
    rawDir: args.rawDir,
    mode: args.mode,
    periodStart: args.periodStart,
    periodEnd: args.periodEnd,
    accioCli: args.accioCli,
    timeoutMs: Number(args.timeoutMs || process.env.ACCIO_TIMEOUT_MS || 120000),
  };
  return config;
}

function unwrapToolResult(envelope) {
  const data = envelope?.data ?? envelope;
  const result = data?.result ?? data;
  const content = result?.content ?? data?.content;
  if (Array.isArray(content) && content[0]?.text !== undefined) {
    const text = String(content[0].text);
    try {
      return JSON.parse(text);
    } catch {
      return { text };
    }
  }
  return result;
}

function runCli(config, toolName, toolArgs) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      config.accioCli,
      ["call", toolName, "--json", JSON.stringify(toolArgs)],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`timeout after ${config.timeoutMs}ms`));
    }, config.timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(stderr.trim() || `data connector exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        resolve({ text: stdout });
      }
    });
  });
}

async function callTool(config, toolName, toolArgs, filename, statusRows) {
  const startedAt = Date.now();
  const record = {
    tool: toolName,
    filename,
    args: toolArgs,
    ok: false,
    error: null,
    bytes: 0,
    duration_ms: 0,
  };
  try {
    const rawResult = await runCli(config, toolName, toolArgs);
    const inner = unwrapToolResult(rawResult);
    const errorCode = String(inner?.errorCode ?? inner?.code ?? "").trim();
    const failedFlag = inner?.success === false || inner?.ok === false || inner?.isError === true;
    const failedCode = errorCode && !["0", "200"].includes(errorCode);
    if (failedFlag || failedCode) {
      const message = inner?.errorMsg || inner?.error_message || inner?.error || inner?.message;
      throw new Error(message || `platform business error ${errorCode || "unknown"}`);
    }
    const outPath = join(config.rawDir, filename);
    writeFileSync(outPath, JSON.stringify(inner, null, 2), "utf8");
    record.ok = true;
    record.bytes = statSync(outPath).size;
    console.log(`OK ${toolName} -> ${filename} (${record.bytes} bytes)`);
    return inner;
  } catch (error) {
    const outPath = join(config.rawDir, filename);
    const payload = {
      success: false,
      error: error?.message || String(error),
      tool: toolName,
      args: toolArgs,
    };
    writeFileSync(outPath, JSON.stringify(payload, null, 2), "utf8");
    record.error = payload.error;
    record.bytes = statSync(outPath).size;
    console.error(`WARN ${toolName} -> ${filename}: ${payload.error}`);
    return payload;
  } finally {
    record.duration_ms = Date.now() - startedAt;
    statusRows.push(record);
  }
}

function regionArgs(config, dimensionType) {
  return {
    regionQueryParam: {
      dimensionType,
      startDate: config.periodStart,
      endDate: config.periodEnd,
      statisticsType: config.mode === "monthly" ? "month" : "week",
      terminalType: "TOTAL",
    },
  };
}

function previousMonthWindow(periodStart) {
  const current = new Date(`${periodStart}T00:00:00Z`);
  const first = new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth() - 1, 1));
  const last = new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth(), 0));
  const fmt = (d) => d.toISOString().slice(0, 10);
  return { start: fmt(first), end: fmt(last) };
}

function rowsFromTool(raw) {
  if (Array.isArray(raw)) return raw;
  if (!raw || typeof raw !== "object") return [];
  return raw.data || raw.result?.data || raw.values?.data || [];
}

function weeklyProductSubjects(weeklyAll) {
  const reportAll = (
    weeklyAll?.data?.reportAllData
    || weeklyAll?.values?.reportAllData
    || weeklyAll?.reportAllData
    || weeklyAll
    || {}
  );
  const rows = reportAll?.EXPOSURE_TOP10_PRODUCT_DATA || [];
  if (!Array.isArray(rows)) return [];
  return rows
    .map((row) => row?.subject)
    .filter(Boolean)
    .slice(0, 10);
}

function storeDiagnoseCarrier(storeDiagnose) {
  /**
   * Return the business carrier used by current or older store-diagnosis responses.
   *
   * The tool has used both `data` and `values` as transport wrappers. Keeping this
   * normalization here prevents the collector from silently selecting an empty report.
   */
  if (!storeDiagnose || typeof storeDiagnose !== "object") return {};
  return storeDiagnose.data || storeDiagnose.values || storeDiagnose;
}

function selectExactDiagnosisWeek(storeDiagnose, periodStart, periodEnd) {
  /**
   * Select only the diagnosis entry whose natural dates match the requested report.
   *
   * Falling back to index zero is unsafe because that entry is commonly a rolling
   * "recent seven days" window and may not be the user's requested natural week.
   */
  const carrier = storeDiagnoseCarrier(storeDiagnose);
  const weeks = (
    Array.isArray(carrier) ? carrier
      : carrier.aiSalesWeekDiagnoseList || carrier.weekDiagnoseList || []
  );
  if (!Array.isArray(weeks)) return null;
  return weeks.find((week) => {
    const beginDate = String(week?.beginDate || week?.startDate || "").slice(0, 10);
    const endDate = String(week?.endDate || "").slice(0, 10);
    return beginDate === periodStart && endDate === periodEnd;
  }) || null;
}

function eachDate(startDate, endDate) {
  /**
   * Build every ISO calendar date in an inclusive report range.
   *
   * @param {string} startDate - Inclusive YYYY-MM-DD start.
   * @param {string} endDate - Inclusive YYYY-MM-DD end.
   * @returns {string[]} Natural dates in ascending order.
   */
  const dates = [];
  const cursor = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  while (cursor <= end) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

function toolRows(raw) {
  /**
   * Unwrap common Alibaba list carriers into business rows.
   *
   * @param {unknown} raw - Parsed tool response.
   * @returns {object[]} Dictionary rows, or an empty list.
   */
  if (Array.isArray(raw)) return raw.filter((row) => row && typeof row === "object");
  if (!raw || typeof raw !== "object") return [];
  for (const key of ["data", "result", "values", "rows", "list", "items", "records", "productList"]) {
    const value = raw[key];
    if (Array.isArray(value)) return value.filter((row) => row && typeof row === "object");
    if (value && typeof value === "object") {
      const nested = toolRows(value);
      if (nested.length) return nested;
    }
  }
  return [];
}

function stableProductId(row) {
  /**
   * Return a product identifier suitable for page de-duplication.
   *
   * @param {object} row - Product performance row.
   * @returns {string} Stable ID or a deterministic content fallback.
   */
  return String(
    row?.id ?? row?.productId ?? row?.prodId ?? row?.subject ?? row?.prodName
    ?? JSON.stringify(row),
  );
}

function aggregateProductRows(rows) {
  /**
   * Aggregate exact-day product metrics into one report-period product list.
   *
   * @param {object[]} rows - Daily rows carrying `_sourceDate`.
   * @returns {object[]} Aggregated rows sorted by search exposure.
   */
  const sumFields = [
    "sumProdShowNum", "totalImpsCnt", "sumProdClickNum", "totalClkCnt",
    "sumProdVisitorCnt", "sumProdFbNum", "atmFbUv", "mcFbUv", "crtOrd",
    "rtsOnlineAmt", "p4pImpsCnt", "p4pClkCnt", "adImpsCnt", "adClkCnt",
    "addCartCnt", "addCartByrCnt", "fav", "cmp",
  ];
  const grouped = new Map();
  for (const row of rows) {
    const id = stableProductId(row);
    if (!grouped.has(id)) {
      grouped.set(id, { ...row, _sourceDates: [] });
      for (const field of sumFields) grouped.get(id)[field] = 0;
    }
    const target = grouped.get(id);
    if (row._sourceDate && !target._sourceDates.includes(row._sourceDate)) {
      target._sourceDates.push(row._sourceDate);
    }
    for (const field of sumFields) {
      const value = Number(row[field]);
      if (Number.isFinite(value)) target[field] += value;
    }
  }
  for (const target of grouped.values()) {
    target.sumProdClickRate = target.sumProdShowNum > 0
      ? target.sumProdClickNum / target.sumProdShowNum : null;
    target.sumProdFbRate = target.sumProdVisitorCnt > 0
      ? target.sumProdFbNum / target.sumProdVisitorCnt : null;
  }
  return [...grouped.values()].sort(
    (left, right) => (right.sumProdShowNum || 0) - (left.sumProdShowNum || 0),
  );
}

async function collectProductPerformance(config, statusRows) {
  /**
   * Collect a disclosed multi-page product sample for the exact report period.
   *
   * Weekly mode queries each natural day because the tool's week mode ignores
   * `statDate`. The default cap is three pages per day (60 products ordered by
   * views); callers can raise it for an explicitly requested exhaustive run.
   */
  const pageSize = 20;
  const maxPagesPerDate = Number(process.env.ACCIO_MAX_PRODUCT_PAGES_PER_DATE || 3);
  const dates = config.mode === "weekly"
    ? eachDate(config.periodStart, config.periodEnd)
    : [config.periodStart];
  const collected = [];
  let sampledRows = 0;
  let maximumRecordCount = 0;
  let truncated = false;
  for (const date of dates) {
    const seenForDate = new Set();
    let lastRecordCount = null;
    for (let pageNo = 1; pageNo <= maxPagesPerDate; pageNo += 1) {
      const raw = await callTool(
        config,
        "data_advisor_shop_product",
        {
          shopProductQueryParam: {
            statisticsType: config.mode === "weekly" ? "day" : "month",
            statDate: date,
            orderBy: "views",
            orderModel: "DESC",
            pageNo,
            pageSize,
          },
        },
        `data_advisor_shop_product_${date}_p${String(pageNo).padStart(2, "0")}.json`,
        statusRows,
      );
      const rows = toolRows(raw);
      const carrier = raw?.data && typeof raw.data === "object" ? raw.data : raw;
      const recordCount = Number(carrier?.recordCount);
      if (Number.isFinite(recordCount)) {
        lastRecordCount = recordCount;
        maximumRecordCount = Math.max(maximumRecordCount, recordCount);
      }
      let newCount = 0;
      for (const row of rows) {
        const id = stableProductId(row);
        if (seenForDate.has(id)) continue;
        seenForDate.add(id);
        collected.push({ ...row, _sourceDate: date });
        newCount += 1;
      }
      sampledRows += newCount;
      if (rows.length < pageSize || newCount === 0) break;
      if (pageNo === maxPagesPerDate && lastRecordCount > seenForDate.size) truncated = true;
    }
  }
  const data = aggregateProductRows(collected);
  writeFileSync(join(config.rawDir, "data_advisor_shop_product.json"), JSON.stringify({
    success: true,
    data,
    periodStart: config.periodStart,
    periodEnd: config.periodEnd,
    rowCount: data.length,
    sampledRows,
    maximumRecordCount,
    truncated,
    ordering: "views DESC",
    coverage: config.mode === "weekly"
      ? `每日按曝光排序前 ${pageSize * maxPagesPerDate} 个商品后合并`
      : `自然月按曝光排序前 ${pageSize * maxPagesPerDate} 个商品`,
  }, null, 2), "utf8");
}

function shelfProductSubjects(shopInfo) {
  const shelf = shopInfo?.["客户店铺橱窗商品列表"]?.data || shopInfo?.result?.["客户店铺橱窗商品列表"]?.data || {};
  const items = Array.isArray(shelf?.items) ? shelf.items : [];
  return items
    .map((row) => row?.["橱窗商品名称"])
    .filter(Boolean)
    .slice(0, 10);
}

async function collectProductLookups(config, statusRows, subjects) {
  const unique = [];
  const seen = new Set();
  for (const subject of subjects || []) {
    const key = String(subject).trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    unique.push(subject);
  }
  await Promise.all(unique.slice(0, 10).map((subject, idx) => (
    callTool(
      config,
      "list_products",
      { queryDTO: { productName: subject } },
      `list_products_${String(idx + 1).padStart(2, "0")}.json`,
      statusRows,
    )
  )));
}

function inferMainCateId(shopInfo, cateSummary, summaryRaw) {
  const summaryRows = rowsFromTool(summaryRaw);
  if (summaryRows[0]?.cateId) return summaryRows[0].cateId;
  const shopBasic = shopInfo?.["客户店铺基本信息"]?.data || shopInfo?.result?.["客户店铺基本信息"]?.data || {};
  const target = String(shopBasic["客户主营三级行业"] || shopBasic["客户主营二级行业"] || "").toLowerCase();
  const rows = rowsFromTool(cateSummary);
  const matched = rows.find((row) => {
    const lv3 = String(row.cateLv3Desc || "").toLowerCase();
    const lv2 = String(row.cateLv2Desc || "").toLowerCase();
    return target && (target.includes(lv3) || lv3.includes(target) || target.includes(lv2) || lv2.includes(target));
  });
  return matched?.cateLv3Id || rows[0]?.cateLv3Id || null;
}

async function collectOptionalEnrichment(config, statusRows, { shopInfo, cateSummary, summaryRaw = null }) {
  const cateId = inferMainCateId(shopInfo, cateSummary, summaryRaw);
  const keywordBase = {
    requestPage: { pageIndex: 1, pageSize: 10 },
    requestOrderProperty: { orderField: "yearImps", orderType: "desc" },
  };
  if (cateId) keywordBase.cateIdList = [Number(cateId)];

  const calls = [
    callTool(config, "searchKeywordList", { query: { ...keywordBase, productId: 110102001 } }, "searchKeywordList_wending.json", statusRows),
    callTool(config, "searchKeywordList", { query: { ...keywordBase, productId: 110102004 } }, "searchKeywordList_top.json", statusRows),
    callTool(config, "searchNextMonthAuctionResource", { query: { productId: 110102001, sellNode: "nextFirstAuctionWord" } }, "searchNextMonthAuctionResource_wending.json", statusRows),
    callTool(config, "searchNextMonthAuctionResource", { query: { productId: 110102004, sellNode: "nextFirstAuctionWord" } }, "searchNextMonthAuctionResource_top.json", statusRows),
    callTool(config, "getAllBehaviorsSemanticForKeywordRec", {}, "getAllBehaviorsSemanticForKeywordRec.json", statusRows),
  ];
  if (cateId) {
    calls.push(callTool(
      config,
      "data_advisor_product_selection",
      { productSelectionParam: { cateId: Number(cateId), statisticsType: "30d", orderBy: "ab_cnt", order: "desc" } },
      "data_advisor_product_selection_recent_30d.json",
      statusRows,
    ));
  }
  await Promise.all(calls);
}

async function collectWeekly(config, statusRows) {
  const [shopInfo, storeDiagnose, _risk, cateSummary] = await Promise.all([
    callTool(config, "findCustomerShopInfo", {}, "findCustomerShopInfo.json", statusRows),
    callTool(config, "store_diagnose_brief", { qry: {} }, "store_diagnose_brief.json", statusRows),
    callTool(config, "shop_risk_diagnosis", {}, "shop_risk_diagnosis.json", statusRows),
    callTool(config, "queryCustomerGoodsCateSummary", {}, "queryCustomerGoodsCateSummary.json", statusRows),
  ]);

  await Promise.all([
    callTool(config, "data_advisor_shop_region", regionArgs(config, "shop_uv"), "data_advisor_shop_region_uv.json", statusRows),
    callTool(config, "data_advisor_shop_region", regionArgs(config, "total_imps_cnt"), "data_advisor_shop_region_imps.json", statusRows),
    callTool(config, "data_advisor_shop_region", regionArgs(config, "total_bus_cnt"), "data_advisor_shop_region_ab.json", statusRows),
    callTool(
      config,
      "icbu_ads_hateoas_query",
      {
        entityType: "company",
        filters: { summaryTypes: "wholeSite" },
        include: "data,links",
        pageIndex: 1,
        pageSize: 20,
      },
      "icbu_ads_hateoas_query_company.json",
      statusRows,
    ),
    callTool(
      config,
      "icbu_ads_hateoas_query",
      {
        entityType: "diagnosis",
        // Live HATEOAS discovery confirms that account diagnosis accepts the
        // week end date and automatically evaluates the preceding seven days.
        filters: { endDate: config.periodEnd },
        include: "data",
        pageIndex: 1,
        pageSize: 20,
      },
      "icbu_ads_hateoas_query_diagnosis.json",
      statusRows,
    ),
  ]);
  await collectProductPerformance(config, statusRows);
  await collectOptionalEnrichment(config, statusRows, { shopInfo, cateSummary });

  const diagnoseCarrier = storeDiagnoseCarrier(storeDiagnose);
  const week = selectExactDiagnosisWeek(storeDiagnose, config.periodStart, config.periodEnd) || {};
  const encryptReportId = week.encryptedReportId || week.encryptReportId;
  const receipt = diagnoseCarrier?.receipt || storeDiagnose?.receipt || week.receipt;
  if (encryptReportId && receipt) {
    const weeklyAll = await callTool(
      config,
      "service_report_weekly_all_data_query",
      {
        qry: {
          encryptReportId,
          reportAllDataQry: { receipt, reportPageCode: [] },
        },
      },
      "service_report_weekly_all_data_query.json",
      statusRows,
    );
    await collectProductLookups(config, statusRows, weeklyProductSubjects(weeklyAll));
  } else {
    const filename = "service_report_weekly_all_data_query.json";
    const payload = {
      success: false,
      error: "requested natural week has no matching encryptedReportId or receipt from store_diagnose_brief",
      requested_period: { start: config.periodStart, end: config.periodEnd },
      encryptedReportId_found: Boolean(encryptReportId),
      receipt_found: Boolean(receipt),
    };
    writeFileSync(join(config.rawDir, filename), JSON.stringify(payload, null, 2), "utf8");
    statusRows.push({
      tool: "service_report_weekly_all_data_query",
      filename,
      args: null,
      ok: false,
      error: payload.error,
      bytes: statSync(join(config.rawDir, filename)).size,
      duration_ms: 0,
    });
  }

  return shopInfo;
}

async function collectMonthly(config, statusRows) {
  const baseline = previousMonthWindow(config.periodStart);
  const [shopInfo, _risk, cateSummary, _uv, _imps, _ab, currentSummary] = await Promise.all([
    callTool(config, "findCustomerShopInfo", {}, "findCustomerShopInfo.json", statusRows),
    callTool(config, "shop_risk_diagnosis", {}, "shop_risk_diagnosis.json", statusRows),
    callTool(config, "queryCustomerGoodsCateSummary", {}, "queryCustomerGoodsCateSummary.json", statusRows),
    callTool(config, "data_advisor_shop_region", regionArgs(config, "shop_uv"), "data_advisor_shop_region_uv.json", statusRows),
    callTool(config, "data_advisor_shop_region", regionArgs(config, "total_imps_cnt"), "data_advisor_shop_region_imps.json", statusRows),
    callTool(config, "data_advisor_shop_region", regionArgs(config, "total_bus_cnt"), "data_advisor_shop_region_ab.json", statusRows),
    callTool(
      config,
      "data_advisor_shop_summary",
      {
        advisorQueryParam: {
          statisticsType: "30d",
          startDate: config.periodStart,
          endDate: config.periodEnd,
        },
      },
      "data_advisor_shop_summary_current.json",
      statusRows,
    ),
    callTool(
      config,
      "data_advisor_shop_summary",
      {
        advisorQueryParam: {
          statisticsType: "day",
          startDate: config.periodStart,
          endDate: config.periodEnd,
        },
      },
      "data_advisor_shop_summary_day.json",
      statusRows,
    ),
    callTool(
      config,
      "data_advisor_shop_summary",
      {
        advisorQueryParam: {
          statisticsType: "30d",
          startDate: baseline.start,
          endDate: baseline.end,
        },
      },
      "data_advisor_shop_summary_baseline.json",
      statusRows,
    ),
  ]);
  await collectProductPerformance(config, statusRows);
  await collectOptionalEnrichment(config, statusRows, { shopInfo, cateSummary, summaryRaw: currentSummary });
  await collectProductLookups(config, statusRows, shelfProductSubjects(shopInfo));
}

async function main() {
  let config;
  try {
    config = parseArgs(process.argv);
  } catch (error) {
    usage();
    throw error;
  }
  mkdirSync(config.rawDir, { recursive: true });
  const statusRows = [];
  if (config.mode === "weekly") {
    await collectWeekly(config, statusRows);
  } else {
    await collectMonthly(config, statusRows);
  }
  const status = {
    collected_at: new Date().toISOString(),
    mode: config.mode,
    period_start: config.periodStart,
    period_end: config.periodEnd,
    ok_count: statusRows.filter((row) => row.ok).length,
    failed_count: statusRows.filter((row) => !row.ok).length,
    tools: statusRows,
  };
  writeFileSync(join(config.rawDir, "_collect_status.json"), JSON.stringify(status, null, 2), "utf8");
  console.log(`status -> _collect_status.json (${status.ok_count} ok, ${status.failed_count} failed)`);
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exit(1);
});
