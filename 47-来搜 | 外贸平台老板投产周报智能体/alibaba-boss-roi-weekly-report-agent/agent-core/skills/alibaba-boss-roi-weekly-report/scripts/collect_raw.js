#!/usr/bin/env node
/**
 * collect_raw.js
 *
 * Collect read-only Alibaba.com business data for the boss ROI workbook.
 *
 * The script intentionally only calls query/report/diagnosis tools. It never
 * calls tools that send messages, publish products, edit settings, or consume
 * paid credits. Connection details are treated as implementation details and
 * are not written to user-facing report content.
 *
 * Output files are intentionally named for prepare_data.py. Each tool result is
 * normalized before writing, so Python scripts can read the business JSON
 * directly.
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
  --accio-cli <path>            Data connector executable path
  --timeout-ms 120000
	`);
}

const USER_VISIBLE_SOURCE_ERROR = "平台接口异常，数据未返回";

function dataAccessMode(config) {
  return "connector";
}

function sanitizeUserVisibleError(value) {
  const text = String(value || "").trim();
  if (!text) return USER_VISIBLE_SOURCE_ERROR;
  return text;
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

async function runReadOnlyTool(config, toolName, toolArgs) {
  return runCli(config, toolName, toolArgs);
}

function hasNonEmptyBusinessValue(value) {
  /**
   * Decide whether a returned value contains usable business data.
   *
   * Alibaba tools do not share one response shape. Some return `data`, some
   * return `result`, some return `object`, and IM tools commonly nest rows
   * under `object.conversations` or `object.messages`. This helper intentionally
   * treats any non-empty primitive, array, or object as payload so a valid
   * `success: true, errorCode: null, object: [...]` response is never counted as
   * a failure just because it does not use the `data` key.
   */
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value !== "object") return true;
  return Object.values(value).some((child) => hasNonEmptyBusinessValue(child));
}

function firstPayloadCandidate(inner) {
  /**
   * Extract the first known Alibaba payload carrier.
   *
   * The order is intentional: direct carriers first, then common nested carriers.
   * The function returns `undefined` only when the response has no recognizable
   * business carrier at all.
   */
  if (!inner || typeof inner !== "object") return inner;
  const candidates = [
    inner.data,
    inner.result,
    inner.object,
    inner.values,
    inner.content,
    inner.result?.data,
    inner.result?.object,
    inner.result?.values,
    inner.object?.conversations,
    inner.object?.messages,
    inner.object?.records,
    inner.object?.items,
  ];
  return candidates.find((candidate) => candidate !== undefined);
}

function normalizedErrorCode(inner) {
  /**
   * Normalize Alibaba's error code field.
   *
   * `errorCode: null` is a normal success shape for many tools. Only non-empty,
   * non-zero codes should participate in error classification.
   */
  if (!inner || typeof inner !== "object") return null;
  const code = inner.errorCode ?? inner.error_code ?? inner.code;
  if (code === null || code === undefined || code === "" || code === 0 || code === "0") return null;
  if (code === "200" || code === 200) return null;
  return code;
}

function classifyToolResponse(inner, toolName) {
  /**
   * Classify a read-only Alibaba response for collection status.
   *
   * Returns:
   *   ok: true when the call itself succeeded or produced a valid empty result.
   *   empty: true when the call succeeded but no business rows were returned.
   *   error: user-safe error text for real failures.
   *
   * This prevents valid `result`/`object` payloads from being counted as failed,
   * which was the source of the inflated "152 failed" status.
   */
  if (!inner || typeof inner !== "object") {
    return { ok: hasNonEmptyBusinessValue(inner), empty: !hasNonEmptyBusinessValue(inner), error: null };
  }
  if (inner.success === false || inner.ok === false || inner.isError === true) {
    return {
      ok: false,
      empty: false,
      error: sanitizeUserVisibleError(inner.errorMsg || inner.error_message || inner.error || inner.message || "业务数据未返回"),
    };
  }
  const payload = firstPayloadCandidate(inner);
  const hasPayload = hasNonEmptyBusinessValue(payload);
  const errorCode = normalizedErrorCode(inner);
  // Only the documented chat-quality detail tool uses errorCode=300 for a
  // valid empty response. Never generalize that code to unrelated tools.
  const validEmpty300 = toolName === "query_seller_chat_quality_check_detail"
    && String(errorCode) === "300"
    && !hasPayload;
  if (errorCode && !validEmpty300) {
    return {
      ok: false,
      empty: false,
      error: sanitizeUserVisibleError(inner.errorMsg || inner.error_message || inner.error || `平台返回错误 ${errorCode}`),
    };
  }
  if (!hasPayload) {
    return { ok: true, empty: true, error: null };
  }
  return { ok: true, empty: false, error: null };
}

async function callTool(config, toolName, toolArgs, filename, statusRows) {
  const startedAt = Date.now();
  const record = {
    tool: toolName,
    filename,
    args: toolArgs,
    ok: false,
    empty: false,
    error: null,
    bytes: 0,
    duration_ms: 0,
    data_access_mode: dataAccessMode(config),
  };
  try {
    const rawResult = await runReadOnlyTool(config, toolName, toolArgs);
    const inner = unwrapToolResult(rawResult);
    const outPath = join(config.rawDir, filename);
    writeFileSync(outPath, JSON.stringify(inner, null, 2), "utf8");
    const classification = classifyToolResponse(inner, toolName);
    record.ok = classification.ok;
    record.empty = classification.empty;
    record.error = classification.error;
    record.bytes = statSync(outPath).size;
    if (record.ok && record.empty) {
      console.log(`EMPTY ${toolName} -> ${filename} (${record.bytes} bytes)`);
    } else if (record.ok) {
      console.log(`OK ${toolName} -> ${filename} (${record.bytes} bytes)`);
    } else {
      console.error(`WARN ${toolName} -> ${filename}: ${record.error}`);
    }
    return inner;
  } catch (error) {
    const outPath = join(config.rawDir, filename);
    const payload = {
      success: false,
      error: sanitizeUserVisibleError(error?.message || String(error)),
      tool: toolName,
      args: toolArgs,
    };
    writeFileSync(outPath, JSON.stringify(payload, null, 2), "utf8");
    record.error = payload.error;
    record.empty = false;
    record.bytes = statSync(outPath).size;
    console.error(`WARN ${toolName} -> ${filename}: ${payload.error}`);
    return payload;
  } finally {
    record.duration_ms = Date.now() - startedAt;
    statusRows.push(record);
  }
}

function eachDate(start, end) {
  const dates = [];
  const cur = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  while (cur <= last) {
    dates.push(cur.toISOString().slice(0, 10));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return dates;
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
  return raw.data || raw.object || raw.result?.data || raw.values?.data || [];
}

function dayStartMs(dateText) {
  return new Date(`${dateText}T00:00:00+08:00`).getTime();
}

function dayEndMs(dateText) {
  return new Date(`${dateText}T23:59:59+08:00`).getTime();
}

function asRows(raw) {
  if (Array.isArray(raw)) return raw.filter((row) => row && typeof row === "object");
  if (!raw || typeof raw !== "object") return [];
  for (const key of [
    "data", "object", "result", "values", "list", "rows", "items",
    "tradeList", "productList", "conversations", "messages", "records",
  ]) {
    const value = raw[key];
    if (Array.isArray(value)) return value.filter((row) => row && typeof row === "object");
    if (value && typeof value === "object") {
      const nested = asRows(value);
      if (nested.length) return nested;
    }
  }
  return [];
}

function timestampMs(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") {
    return value < 10_000_000_000 ? value * 1000 : value;
  }
  const text = String(value).trim();
  if (/^\d+$/.test(text)) {
    const n = Number(text);
    return n < 10_000_000_000 ? n * 1000 : n;
  }
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}

function firstValue(row, keys) {
  if (!row || typeof row !== "object") return null;
  for (const key of keys) {
    if (row[key] !== undefined && row[key] !== null && row[key] !== "") return row[key];
  }
  return null;
}

function conversationIdOf(row) {
  return firstValue(row, ["conversationId", "conversationID", "cid", "id", "sessionId"]);
}

function conversationUpdateMs(row) {
  return timestampMs(firstValue(row, [
    "updateTime",
    "conversationModifyTime",
    "gmtModified",
    "modifiedTime",
    "lastMessageTime",
    "lastMsgTime",
    "timeStamp",
    "timestamp",
    "sendTime",
  ]));
}

function sellerCandidates(subaccounts, shopInfo) {
  const candidates = [];
  const seen = new Set();
  const add = (aliId, loginId, name) => {
    const idText = aliId === undefined || aliId === null ? "" : String(aliId).trim();
    const loginText = loginId === undefined || loginId === null ? "" : String(loginId).trim();
    const key = idText || loginText;
    if (!key || seen.has(key)) return;
    seen.add(key);
    candidates.push({ aliId: idText, loginId: loginText, name: name || loginText || idText });
  };
  for (const row of asRows(subaccounts)) {
    add(
      firstValue(row, ["aliId", "selfAliId", "memberId", "accountId"]),
      firstValue(row, ["loginId", "accountName"]),
      [row.firstName, row.lastName].filter(Boolean).join(" ") || firstValue(row, ["name", "accountName"]),
    );
  }
  const shopBasic = shopInfo?.["客户店铺基本信息"]?.data || shopInfo?.result?.["客户店铺基本信息"]?.data || {};
  if (!candidates.length && shopBasic["客户登录id"]) {
    add(null, shopBasic["客户登录id"], shopBasic["客户登录id"]);
  }
  return candidates;
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
   * Return the current `data` carrier or the older `values` carrier.
   */
  if (!storeDiagnose || typeof storeDiagnose !== "object") return {};
  return storeDiagnose.data || storeDiagnose.values || storeDiagnose;
}

function selectExactDiagnosisWeek(storeDiagnose, periodStart, periodEnd) {
  /**
   * Select the diagnosis entry matching the requested natural week.
   *
   * Index zero is usually a rolling recent-seven-day window. Using it for a
   * requested natural week caused cross-period data to enter the workbook.
   */
  const carrier = storeDiagnoseCarrier(storeDiagnose);
  const weeks = (
    Array.isArray(carrier) ? carrier
      : carrier.aiSalesWeekDiagnoseList || carrier.weekDiagnoseList || []
  );
  if (!Array.isArray(weeks)) return null;
  return weeks.find((week) => (
    String(week?.beginDate || week?.startDate || "").slice(0, 10) === periodStart
    && String(week?.endDate || "").slice(0, 10) === periodEnd
  )) || null;
}

function isoDateOf(value) {
  /**
   * Extract an ISO calendar date from a date/time value.
   */
  const match = String(value || "").match(/20\d{2}-\d{2}-\d{2}/);
  return match ? match[0] : null;
}

function businessId(row, candidates) {
  /**
   * Return the first stable row identifier, falling back to serialized content.
   */
  const found = firstValue(row, candidates);
  return found === null ? JSON.stringify(row) : String(found);
}

async function collectTradePages(config, statusRows) {
  /**
   * Collect every trade page for the exact report period and write one canonical file.
   */
  const pageSize = 50;
  const maxPages = Number(process.env.ACCIO_MAX_TRADE_PAGES || 50);
  const collected = [];
  const seen = new Set();
  let pagesFetched = 0;
  let serverTotalCount = null;
  let complete = false;
  for (let page = 0; page < maxPages; page += 1) {
    const start = page * pageSize;
    const raw = await callTool(
      config,
      "queryTradeListMcp",
      {
        fieldName_0: {
          createDateFrom: `${config.periodStart} 00:00:00`,
          createDateTo: `${config.periodEnd} 23:59:59`,
          start,
          limit: pageSize,
        },
      },
      `queryTradeListMcp_p${String(page + 1).padStart(2, "0")}.json`,
      statusRows,
    );
    pagesFetched += 1;
    const rows = asRows(raw);
    const carrier = raw?.data && typeof raw.data === "object" ? raw.data : raw;
    const totalCount = Number(carrier?.totalCount);
    if (Number.isFinite(totalCount)) serverTotalCount = totalCount;
    const rowDates = rows
      .map((row) => isoDateOf(firstValue(row, ["createDate", "gmtCreate", "orderCreateTime"])))
      .filter(Boolean);
    let newCount = 0;
    for (const row of rows) {
      const rowDate = isoDateOf(firstValue(row, ["createDate", "gmtCreate", "orderCreateTime"]));
      if (rowDate && (rowDate < config.periodStart || rowDate > config.periodEnd)) continue;
      const id = businessId(row, ["tradeId", "orderId", "contractId", "id"]);
      if (seen.has(id)) continue;
      seen.add(id);
      collected.push(row);
      newCount += 1;
    }
    if (rows.length < pageSize) {
      complete = true;
      break;
    }
    if (newCount === 0) {
      // If the service ignored the filter and is still returning dates newer
      // than the requested window, continue paging until the window is reached.
      if (rowDates.some((date) => date > config.periodEnd)) continue;
      complete = true;
      break;
    }
  }
  writeFileSync(join(config.rawDir, "queryTradeListMcp.json"), JSON.stringify({
    success: true,
    data: collected,
    periodStart: config.periodStart,
    periodEnd: config.periodEnd,
    rowCount: collected.length,
    serverTotalCount,
    pagesFetched,
    complete,
    truncated: !complete,
  }, null, 2), "utf8");
}

function aggregateProductRows(rows) {
  /**
   * Aggregate exact-day product rows into report-period product totals.
   */
  const sumFields = [
    "sumProdShowNum", "totalImpsCnt", "sumProdClickNum", "totalClkCnt",
    "sumProdVisitorCnt", "sumProdFbNum", "atmFbUv", "mcFbUv", "crtOrd",
    "rtsOnlineAmt", "p4pImpsCnt", "p4pClkCnt", "adImpsCnt", "adClkCnt",
    "addCartCnt", "addCartByrCnt", "fav", "cmp",
  ];
  const grouped = new Map();
  for (const row of rows) {
    const id = businessId(row, ["productId", "id", "prodId", "subject", "prodName"]);
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
   * Collect product performance using only current schema fields.
   *
   * Weekly reports use exact natural-day calls because the tool's `week` mode
   * ignores `statDate`. Each day is paged to a bounded top-N sample and then
   * aggregated by product. Monthly mode uses the requested month's first day.
   */
  const pageSize = 20;
  const maxPagesPerDate = Number(process.env.ACCIO_MAX_PRODUCT_PAGES_PER_DATE || 3);
  const dates = config.mode === "weekly" ? eachDate(config.periodStart, config.periodEnd) : [config.periodStart];
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
      const rows = asRows(raw);
      const carrier = raw?.data && typeof raw.data === "object" ? raw.data : raw;
      const recordCount = Number(carrier?.recordCount);
      if (Number.isFinite(recordCount)) {
        lastRecordCount = recordCount;
        maximumRecordCount = Math.max(maximumRecordCount, recordCount);
      }
      let newCount = 0;
      for (const row of rows) {
        const id = businessId(row, ["productId", "id", "prodId", "subject", "prodName"]);
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
        // The live navigation contract uses endDate and automatically covers
        // the preceding seven-day account-diagnosis window.
        filters: { endDate: config.periodEnd },
        include: "data",
        pageIndex: 1,
        pageSize: 20,
      },
      "icbu_ads_hateoas_query_diagnosis.json",
      statusRows,
    ),
  ]);
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

  await collectBossAddons(config, statusRows, { shopInfo });

  return shopInfo;
}

async function collectBossAddons(config, statusRows, { shopInfo }) {
  const dates = eachDate(config.periodStart, config.periodEnd);
  const endDate = config.periodEnd;
  const subaccounts = await callTool(config, "subaccount_query", {}, "subaccount_query.json", statusRows);

  await Promise.all([
    callTool(
      config,
      "data_advisor_shop_summary",
      {
        advisorQueryParam: {
          statisticsType: "7d",
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
      "query_seller_shop_dim_diag_data",
      { buyerType: 0, dateType: 0, queryDate: endDate },
      "query_seller_shop_dim_diag_data.json",
      statusRows,
    ),
    callTool(
      config,
      "query_seller_shop_dim_diag_data",
      { buyerType: 1, dateType: 0, queryDate: endDate },
      "query_seller_shop_dim_diag_data_l1plus.json",
      statusRows,
    ),
    callTool(
      config,
      "query_seller_chat_quality_check_detail",
      { queryDate: endDate },
      "query_seller_chat_quality_check_detail.json",
      statusRows,
    ),
    // The current schema only documents type=0. Other values require a
    // separately verified business dictionary and must not be guessed.
    callTool(config, "query_contact", { type: 0, startVersion: 0 }, "query_contact.json", statusRows),
  ]);

  await Promise.all([
    collectProductPerformance(config, statusRows),
    collectTradePages(config, statusRows),
  ]);

  await Promise.all(dates.map((date, idx) => callTool(
    config,
    "query_seller_chat_quality_check_detail",
    { queryDate: date },
    `query_seller_chat_quality_check_detail_${String(idx + 1).padStart(2, "0")}.json`,
    statusRows,
  )));

  await Promise.all(dates.flatMap((date, idx) => [
    callTool(
      config,
      "query_seller_acct_dim_diag_data",
      { buyerType: 0, dateType: 0, queryDate: date },
      `query_seller_acct_dim_diag_data_${String(idx + 1).padStart(2, "0")}.json`,
      statusRows,
    ),
    callTool(
      config,
      "query_seller_acct_dim_diag_data",
      { buyerType: 1, dateType: 0, queryDate: date },
      `query_seller_acct_dim_diag_data_l1plus_${String(idx + 1).padStart(2, "0")}.json`,
      statusRows,
    ),
  ]));

  await collectInquiryQuality(config, statusRows, { shopInfo, subaccounts });
}

async function collectInquiryQuality(config, statusRows, { shopInfo, subaccounts }) {
  const startMs = dayStartMs(config.periodStart);
  const endMs = dayEndMs(config.periodEnd);
  const maxConversations = Number(process.env.ACCIO_MAX_CONVERSATIONS || 120);
  const sellers = sellerCandidates(subaccounts, shopInfo).slice(0, Number(process.env.ACCIO_MAX_SELLERS || 20));
  const recentRecords = [];
  const messageRecords = [];
  const seenConversations = new Set();

  for (const seller of sellers) {
    let cursor = endMs;
    for (let page = 1; page <= 10; page += 1) {
      const args = {
        request: {
          selfAliId: seller.aliId ? Number(seller.aliId) : undefined,
          limitTimeStamp: cursor,
          domain: "icbu",
        },
      };
      if (!args.request.selfAliId) delete args.request.selfAliId;
      const recent = await callTool(
        config,
        "query_recent_conversation",
        args,
        `query_recent_conversation_${seller.aliId || seller.loginId}_p${page}.json`,
        statusRows,
      );
      const rows = asRows(recent);
      let oldestInPage = null;
      for (const row of rows) {
        const cid = conversationIdOf(row);
        if (!cid || seenConversations.has(cid)) continue;
        const updatedAt = conversationUpdateMs(row);
        if (updatedAt) oldestInPage = oldestInPage ? Math.min(oldestInPage, updatedAt) : updatedAt;
        if (updatedAt && updatedAt < startMs) continue;
        seenConversations.add(cid);
        recentRecords.push({ ...row, _sellerAliId: seller.aliId, _sellerName: seller.name, _updatedAtMs: updatedAt });
      }
      const object = recent?.object || recent?.data?.object || recent?.result?.object || {};
      const nextCursor = object.nextTimeStamp || object.nextPointTimeStamp || recent?.nextTimeStamp || recent?.nextPointTimeStamp;
      if (!object.hasMore || !nextCursor || (oldestInPage && oldestInPage < startMs)) break;
      cursor = nextCursor;
    }
  }

  const selected = recentRecords
    .sort((a, b) => (b._updatedAtMs || 0) - (a._updatedAtMs || 0))
    .slice(0, maxConversations);
  for (const row of selected) {
    const conversationId = conversationIdOf(row);
    const sellerAliId = row._sellerAliId ? Number(row._sellerAliId) : undefined;
    const args = {
      request: {
        conversationId,
        selfAliId: sellerAliId,
        limitTimeStamp: endMs,
        forward: false,
        count: 50,
        domain: "icbu",
      },
    };
    if (!args.request.selfAliId) delete args.request.selfAliId;
    const messages = await callTool(
      config,
      "query_conversation_msg",
      args,
      `query_conversation_msg_${String(messageRecords.length + 1).padStart(3, "0")}.json`,
      statusRows,
    );
    messageRecords.push({
      conversationId,
      sellerAliId: row._sellerAliId,
      sellerName: row._sellerName,
      conversation: row,
      messages: asRows(messages),
    });
  }

  const summary = {
    periodStart: config.periodStart,
    periodEnd: config.periodEnd,
    startMs,
    endMs,
    sellerCount: sellers.length,
    conversationCount: recentRecords.length,
    messageConversationCount: messageRecords.length,
    capped: recentRecords.length > selected.length,
    conversations: selected,
  };
  writeFileSync(join(config.rawDir, "query_recent_conversation_week.json"), JSON.stringify(summary, null, 2), "utf8");
  writeFileSync(join(config.rawDir, "query_conversation_msg_week.json"), JSON.stringify({
    periodStart: config.periodStart,
    periodEnd: config.periodEnd,
    records: messageRecords,
  }, null, 2), "utf8");
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
  await collectOptionalEnrichment(config, statusRows, { shopInfo, cateSummary, summaryRaw: currentSummary });
  await collectProductLookups(config, statusRows, shelfProductSubjects(shopInfo));
  await collectBossAddons(config, statusRows, { shopInfo });
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
    data_access_mode: dataAccessMode(config),
    ok_count: statusRows.filter((row) => row.ok).length,
    empty_count: statusRows.filter((row) => row.ok && row.empty).length,
    failed_count: statusRows.filter((row) => !row.ok).length,
    tools: statusRows,
  };
  writeFileSync(join(config.rawDir, "_collect_status.json"), JSON.stringify(status, null, 2), "utf8");
  console.log(`status -> _collect_status.json (${status.ok_count} ok, ${status.empty_count} empty, ${status.failed_count} failed)`);
}

main().catch((error) => {
  console.error(sanitizeUserVisibleError(error?.message || error));
  process.exit(1);
});
