/**
 * TokenMind 23 个 Accio Work 智能体套装安装器。
 *
 * 安装器只处理当前 Bundle 中声明的 Agent 模板，主要职责：
 * 1. 识别当前 Accio 个人或团队空间的 agents/ 目录；
 * 2. 为每个 Agent 生成目标空间内唯一的 MID-*；
 * 3. 改写 profile.jsonc.id 与私有 Skill 的 installPath；
 * 4. 先写入隐藏 staging 目录，全部校验后再原子改名；
 * 5. 重复执行时识别已经完整安装的同一来源 Agent，避免重复创建；
 * 6. 从当前空间的 Accio 主智能体同步本地用户画像和记忆；
 * 7. 失败时只回滚本次写入，不覆盖或删除用户原有 Agent。
 */

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const INSTALLER_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const BUNDLE_ROOT = path.dirname(INSTALLER_DIRECTORY);
const MANIFEST_PATH = path.join(BUNDLE_ROOT, "bundle-manifest.json");
const ACCIO_ROOT = path.join(os.homedir(), ".accio");
const ACCOUNTS_ROOT = path.join(ACCIO_ROOT, "accounts");
const USER_CONTEXT_MARKERS = {
  begin: "<!-- TOKENMIND:BEGIN_LOCAL_USER_CONTEXT -->",
  end: "<!-- TOKENMIND:END_LOCAL_USER_CONTEXT -->",
};
const MEMORY_CONTEXT_MARKERS = {
  begin: "<!-- TOKENMIND:BEGIN_LOCAL_MEMORY_CONTEXT -->",
  end: "<!-- TOKENMIND:END_LOCAL_MEMORY_CONTEXT -->",
};

/**
 * 解析允许顶部带整行 // 注释的 JSONC。
 *
 * @param {string} filePath - JSONC 文件绝对路径。
 * @returns {Record<string, unknown>} 解析后的配置对象。
 * @throws {Error} 文件不存在、不可读或 JSON 主体损坏时抛出。
 */
function readJsonc(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(raw.replace(/^\s*\/\/.*$/gm, ""));
}

/**
 * 原子写入 JSON 文件。
 *
 * @param {string} filePath - 最终文件路径。
 * @param {unknown} value - 要序列化的普通对象。
 * @returns {void}
 * @throws {Error} 临时文件写入或原子改名失败时抛出。
 */
function writeJsonAtomically(filePath, value) {
  const temporaryPath = `${filePath}.updating-${process.pid}`;
  try {
    fs.writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    fs.renameSync(temporaryPath, filePath);
  } finally {
    // rename 成功后临时路径已不存在；失败时在这里清理，避免留下更新残片。
    fs.rmSync(temporaryPath, { force: true });
  }
}

/**
 * 原子写入 UTF-8 文本文件。
 *
 * 先在同目录写入临时文件，再通过 rename 替换目标文件，避免安装过程意外中断后留下
 * 半截 USER.md 或 MEMORY.md。临时文件权限只允许当前用户读写。
 *
 * @param {string} filePath - 最终文件绝对路径。
 * @param {string} content - 要写入的完整文本。
 * @returns {void}
 * @throws {Error} 临时文件写入或原子改名失败时抛出。
 */
function writeTextAtomically(filePath, content) {
  const temporaryPath = `${filePath}.updating-${process.pid}`;
  try {
    fs.writeFileSync(temporaryPath, content, {
      encoding: "utf8",
      mode: 0o600,
    });
    fs.renameSync(temporaryPath, filePath);
  } finally {
    // rename 成功后临时路径已不存在；失败时在这里清理，避免留下更新残片。
    fs.rmSync(temporaryPath, { force: true });
  }
}

/**
 * 转义要放进正则表达式的固定字符串。
 *
 * @param {string} value - 原始固定文本。
 * @returns {string} 可安全拼进 RegExp 的文本。
 */
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 在 Markdown 中插入或更新一个 TokenMind 管理的标记块。
 *
 * 已存在同名标记块时只替换块内内容，确保安装器重复执行不会不断追加副本；不存在时
 * 追加到文件末尾，并保留 Agent 模板原有的人设、规则和记忆内容。
 *
 * @param {string} original - 目标 Markdown 的原始内容。
 * @param {{begin: string, end: string}} markers - 块起止标记。
 * @param {string} managedContent - 安装器管理的块内容。
 * @returns {string} 合并后的完整 Markdown。
 */
function upsertManagedBlock(original, markers, managedContent) {
  const normalizedOriginal = original.replace(/\r\n/g, "\n");
  const normalizedContent = managedContent.replace(/\r\n/g, "\n").trimEnd();
  const block = `${markers.begin}\n${normalizedContent}\n${markers.end}`;
  const expression = new RegExp(
    `${escapeRegExp(markers.begin)}[\\s\\S]*?${escapeRegExp(markers.end)}`,
    "g",
  );

  if (expression.test(normalizedOriginal)) {
    return `${normalizedOriginal.replace(expression, block).trimEnd()}\n`;
  }

  const prefix = normalizedOriginal.trimEnd();
  return `${prefix ? `${prefix}\n\n` : ""}${block}\n`;
}

/**
 * 计算 profile 内嵌 Logo 的 SHA-256。
 *
 * Accio Agent 的 Logo 以 data URL 存在 profile.jsonc 中。安装器对实际 Base64 内容计算
 * 摘要，不能只相信 profile 自报的 avatarSha256 字段。
 *
 * @param {Record<string, unknown>} profile - Agent profile 配置。
 * @returns {string} 小写十六进制 SHA-256。
 * @throws {Error} avatar 不是合法 Base64 data URL 时抛出。
 */
function calculateEmbeddedAvatarSha256(profile) {
  const avatar = String(profile.avatar || "");
  const match = avatar.match(/^data:[^;,]+;base64,([A-Za-z0-9+/=\r\n]+)$/);
  if (!match) {
    throw new Error("profile.avatar 不是合法的 Base64 data URL");
  }
  return crypto.createHash("sha256").update(Buffer.from(match[1], "base64")).digest("hex");
}

/**
 * 列出一个 Agent 实际存在的顶层私有 Skill 目录。
 *
 * @param {string} agentDirectory - Agent 根目录。
 * @returns {string[]} 排序后的私有 Skill 目录名。
 * @throws {Error} skills/ 不存在或不可读时抛出。
 */
function listPrivateSkillDirectories(agentDirectory) {
  const skillsRoot = path.join(agentDirectory, "agent-core", "skills");
  return fs
    .readdirSync(skillsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
    .map((entry) => entry.name)
    .sort();
}

/**
 * 解析安装器命令行参数。
 *
 * 支持：
 * - --target-root <绝对路径>：明确指定当前空间 agents/；
 * - --account-key <accountId 或 accountId_teamId>：指定账号空间键；
 * - --dry-run：只做识别和冲突预检，不写入。
 *
 * @param {string[]} argv - process.argv.slice(2)。
 * @returns {{targetRoot: string, accountKey: string, dryRun: boolean}} 参数结果。
 * @throws {Error} 参数缺值或出现未知参数时抛出。
 */
function parseArguments(argv) {
  const result = { targetRoot: "", accountKey: "", dryRun: false };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--dry-run") {
      result.dryRun = true;
      continue;
    }
    if (argument === "--target-root" || argument === "--account-key") {
      const value = argv[index + 1];
      if (!value) {
        throw new Error(`参数 ${argument} 缺少值`);
      }
      if (argument === "--target-root") result.targetRoot = value;
      if (argument === "--account-key") result.accountKey = value;
      index += 1;
      continue;
    }
    throw new Error(`未知参数：${argument}`);
  }

  return result;
}

/**
 * 根据 current-space.json 解析当前个人或团队空间。
 *
 * @returns {{accountKey: string, source: string} | null} 成功时返回账号空间键。
 */
function resolveFromCurrentSpace() {
  const currentSpacePath = path.join(ACCIO_ROOT, "state", "current-space.json");
  if (!fs.existsSync(currentSpacePath)) {
    return null;
  }

  const currentSpace = JSON.parse(fs.readFileSync(currentSpacePath, "utf8"));
  const accountId = String(currentSpace.accountId || "").trim();
  const teamId = String(currentSpace.teamId || "").trim();
  if (!/^\d+$/.test(accountId)) {
    throw new Error("current-space.json 缺少合法 accountId");
  }

  if (currentSpace.kind === "team") {
    if (!/^\d+$/.test(teamId)) {
      throw new Error("团队空间缺少合法 teamId");
    }
    return { accountKey: `${accountId}_${teamId}`, source: "current-space.json" };
  }

  return { accountKey: accountId, source: "current-space.json" };
}

/**
 * 从 Accio 近期 SDK 日志识别当前账号空间。
 *
 * Accio 0.27.3 在账号切换后可能暂时没有 current-space.json，但运行中的客户端会持续
 * 把 Agent/Skill 同步日志写到当前账号目录。这里只接受最近 15 分钟内最新的一条
 * /accounts/<accountKey>/ 路径，且拒绝 guest，避免按目录 mtime 猜账号。
 *
 * @returns {{accountKey: string, source: string} | null} 成功时返回账号空间键。
 */
function resolveFromRecentSdkLog() {
  const logPath = path.join(ACCIO_ROOT, "logs", "sdk.log");
  if (!fs.existsSync(logPath)) {
    return null;
  }

  const stat = fs.statSync(logPath);
  const bytesToRead = Math.min(stat.size, 4 * 1024 * 1024);
  const start = Math.max(0, stat.size - bytesToRead);
  const descriptor = fs.openSync(logPath, "r");
  const buffer = Buffer.alloc(bytesToRead);
  try {
    fs.readSync(descriptor, buffer, 0, bytesToRead, start);
  } finally {
    fs.closeSync(descriptor);
  }

  const cutoff = Date.now() - 15 * 60 * 1000;
  let latest = null;
  for (const line of buffer.toString("utf8").split("\n")) {
    // 原始 JSON 行里的 Windows 反斜杠会被转义；先做宽松预筛，再解析 message。
    if (!line.includes(".accio") || !line.includes("accounts")) {
      continue;
    }

    let record;
    try {
      record = JSON.parse(line);
    } catch {
      continue;
    }

    const timestamp = Number(record.timestamp || 0);
    if (!Number.isFinite(timestamp) || timestamp < cutoff) {
      continue;
    }

    const normalizedMessage = String(record.message || "").replace(/\\/g, "/");
    if (!normalizedMessage.includes("/.accio/accounts/")) {
      continue;
    }
    const match = normalizedMessage.match(
      /\/\.accio\/accounts\/([A-Za-z0-9_-]+)\//,
    );
    if (!match || match[1] === "guest") {
      continue;
    }

    if (!latest || timestamp > latest.timestamp) {
      latest = { accountKey: match[1], timestamp };
    }
  }

  return latest
    ? { accountKey: latest.accountKey, source: "recent Accio sdk.log" }
    : null;
}

/**
 * 验证并规范化 agents/ 目标目录。
 *
 * 允许的唯一形状是 ~/.accio/accounts/<accountKey>/agents，禁止使用根目录、HOME 或
 * 其他任意路径，避免安装器误写到不相关位置。
 *
 * @param {string} targetRoot - 候选 agents/ 绝对路径。
 * @returns {{targetRoot: string, accountKey: string}} 规范化结果。
 * @throws {Error} 路径不在 Accio accounts 下或形状不合法时抛出。
 */
function validateTargetRoot(targetRoot) {
  const resolvedAccountsRoot = path.resolve(ACCOUNTS_ROOT);
  const resolvedTarget = path.resolve(targetRoot);
  const relative = path.relative(resolvedAccountsRoot, resolvedTarget);
  const parts = relative.split(path.sep).filter(Boolean);

  if (
    relative.startsWith("..") ||
    path.isAbsolute(relative) ||
    parts.length !== 2 ||
    parts[1] !== "agents" ||
    !/^[A-Za-z0-9_-]+$/.test(parts[0]) ||
    parts[0] === "guest"
  ) {
    throw new Error(
      `拒绝不安全的安装路径：${resolvedTarget}。目标必须是 ~/.accio/accounts/<当前空间>/agents`,
    );
  }

  const accountRoot = path.dirname(resolvedTarget);
  if (!fs.existsSync(accountRoot)) {
    throw new Error(`当前账号目录不存在：${accountRoot}`);
  }
  fs.mkdirSync(resolvedTarget, { recursive: true, mode: 0o700 });
  return { targetRoot: resolvedTarget, accountKey: parts[0] };
}

/**
 * 解析安装目标，优先级为明确参数、账号键、current-space.json、近期 SDK 日志。
 *
 * @param {{targetRoot: string, accountKey: string}} options - 命令行参数。
 * @returns {{targetRoot: string, accountKey: string, source: string}} 最终目标。
 */
function resolveInstallTarget(options) {
  if (options.targetRoot) {
    return { ...validateTargetRoot(options.targetRoot), source: "--target-root" };
  }
  if (options.accountKey) {
    return {
      ...validateTargetRoot(path.join(ACCOUNTS_ROOT, options.accountKey, "agents")),
      source: "--account-key",
    };
  }

  const resolved = resolveFromCurrentSpace() || resolveFromRecentSdkLog();
  if (!resolved) {
    throw new Error(
      "无法可靠识别当前 Accio 空间。请保持 Accio Work 正在运行，或使用 --account-key <账号空间键> 重试。",
    );
  }

  return {
    ...validateTargetRoot(path.join(ACCOUNTS_ROOT, resolved.accountKey, "agents")),
    source: resolved.source,
  };
}

/**
 * 检查同一来源 Agent 是否已完整安装。
 *
 * @param {string} agentDirectory - 已有 Agent 目录。
 * @param {Record<string, unknown>} manifestAgent - Bundle 清单项。
 * @returns {boolean} profile、索引和 SKILL.md 全部匹配时返回 true。
 */
function isCompleteExistingInstall(agentDirectory, manifestAgent) {
  try {
    const profile = readJsonc(path.join(agentDirectory, "profile.jsonc"));
    const skillsIndex = readJsonc(
      path.join(agentDirectory, "agent-core", "skills", "skills.jsonc"),
    );
    const skillDirectory = path.join(
      agentDirectory,
      "agent-core",
      "skills",
      manifestAgent.runtimeSkillId,
    );
    const privateSkillDirectories = listPrivateSkillDirectories(agentDirectory);
    return (
      profile.sourceAgentId === manifestAgent.sourceAgentId &&
      profile.enabled !== false &&
      profile.avatarSha256 === manifestAgent.avatarSha256 &&
      profile.avatar === profile.avatarUrl &&
      calculateEmbeddedAvatarSha256(profile) === manifestAgent.avatarSha256 &&
      Array.isArray(skillsIndex.skills) &&
      skillsIndex.skills.length === 1 &&
      skillsIndex.skills[0]?.id === manifestAgent.runtimeSkillId &&
      skillsIndex.skills[0]?.enabled === true &&
      privateSkillDirectories.length === 1 &&
      privateSkillDirectories[0] === manifestAgent.runtimeSkillId &&
      fs.existsSync(path.join(skillDirectory, "SKILL.md"))
    );
  } catch {
    return false;
  }
}

/**
 * 扫描目标空间现有 Agent，建立来源与名称索引。
 *
 * @param {string} targetRoot - 当前空间 agents/。
 * @returns {{bySourceAgentId: Map<string, string>, byName: Map<string, string>, usedIds: Set<string>}}
 *   已有 Agent 索引。
 */
function indexExistingAgents(targetRoot) {
  const bySourceAgentId = new Map();
  const byName = new Map();
  const usedIds = new Set();

  for (const entry of fs.readdirSync(targetRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) {
      continue;
    }

    const agentDirectory = path.join(targetRoot, entry.name);
    const profilePath = path.join(agentDirectory, "profile.jsonc");
    if (!fs.existsSync(profilePath)) {
      continue;
    }

    const profile = readJsonc(profilePath);
    usedIds.add(entry.name);
    if (typeof profile.sourceAgentId === "string") {
      bySourceAgentId.set(profile.sourceAgentId, agentDirectory);
    }
    if (typeof profile.name === "string") {
      byName.set(profile.name, agentDirectory);
    }
  }

  return { bySourceAgentId, byName, usedIds };
}

/**
 * 找到当前空间内 Accio 自带的主智能体，并读取该账号已有的 USER.md 与 MEMORY.md。
 *
 * Accio 0.28.6 没有空间根目录级的统一 USER.md/MEMORY.md；用户画像和长期记忆属于
 * 具体 Agent。`agentType: "accio"` 是当前主 Accio Agent 的稳定标记，因此安装器从
 * 该 Agent 读取本地上下文，再同步到本套装的 23 个 Agent。
 *
 * @param {string} targetRoot - 当前空间 agents/ 目录。
 * @param {string} accountKey - 当前个人或团队空间键。
 * @returns {{accountKey: string, sourceAgentId: string, sourceDirectory: string, userContent: string, memoryContent: string, fingerprint: string}}
 *   当前空间个性化来源和不可逆摘要。
 * @throws {Error} 找不到可用的 Accio 主智能体或其核心文件时抛出。
 */
function resolvePersonalizationSource(targetRoot, accountKey) {
  const candidates = [];

  for (const entry of fs.readdirSync(targetRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) {
      continue;
    }

    const agentDirectory = path.join(targetRoot, entry.name);
    const profilePath = path.join(agentDirectory, "profile.jsonc");
    if (!fs.existsSync(profilePath)) {
      continue;
    }

    let profile;
    try {
      profile = readJsonc(profilePath);
    } catch {
      continue;
    }
    if (profile.agentType !== "accio" || profile.enabled === false) {
      continue;
    }

    const userPath = path.join(agentDirectory, "agent-core", "USER.md");
    const memoryPath = path.join(agentDirectory, "agent-core", "MEMORY.md");
    if (!fs.existsSync(userPath) || !fs.existsSync(memoryPath)) {
      continue;
    }

    candidates.push({
      agentDirectory,
      agentId: String(profile.id || entry.name),
      preferred: entry.name.startsWith("DID-F456DA") ? 1 : 0,
      updatedAt: Date.parse(String(profile.updatedAt || "")) || 0,
    });
  }

  candidates.sort(
    (left, right) =>
      right.preferred - left.preferred ||
      right.updatedAt - left.updatedAt ||
      left.agentId.localeCompare(right.agentId),
  );
  const source = candidates[0];
  if (!source) {
    throw new Error(
      "当前空间没有找到 agentType=accio 且包含 USER.md/MEMORY.md 的 Accio 主智能体，无法完成本地个性化。",
    );
  }

  const userContent = fs.readFileSync(
    path.join(source.agentDirectory, "agent-core", "USER.md"),
    "utf8",
  );
  const memoryContent = fs.readFileSync(
    path.join(source.agentDirectory, "agent-core", "MEMORY.md"),
    "utf8",
  );
  const fingerprint = crypto
    .createHash("sha256")
    .update(
      [accountKey, source.agentId, userContent, memoryContent].join("\u0000"),
      "utf8",
    )
    .digest("hex");

  return {
    accountKey,
    sourceAgentId: source.agentId,
    sourceDirectory: source.agentDirectory,
    userContent,
    memoryContent,
    fingerprint,
  };
}

/**
 * 生成要写入目标 USER.md 的当前账号画像块。
 *
 * @param {{accountKey: string, sourceAgentId: string, userContent: string, fingerprint: string}} source - 个性化来源。
 * @returns {string} 带来源与指纹的用户画像 Markdown。
 */
function buildUserContextBlock(source) {
  return [
    "# 当前 Accio 账号本地用户画像",
    "",
    `- 当前空间：${source.accountKey}`,
    `- 来源主智能体：${source.sourceAgentId}`,
    `- 个性化指纹：${source.fingerprint}`,
    "",
    source.userContent.trim() || "_当前主智能体 USER.md 暂无内容。_",
  ].join("\n");
}

/**
 * 生成要写入目标 MEMORY.md 的当前账号记忆块。
 *
 * @param {{accountKey: string, sourceAgentId: string, memoryContent: string, fingerprint: string}} source - 个性化来源。
 * @returns {string} 带来源与指纹的长期记忆 Markdown。
 */
function buildMemoryContextBlock(source) {
  return [
    "# 当前 Accio 账号本地记忆",
    "",
    `- 当前空间：${source.accountKey}`,
    `- 来源主智能体：${source.sourceAgentId}`,
    `- 个性化指纹：${source.fingerprint}`,
    "",
    source.memoryContent.trim() || "_当前主智能体 MEMORY.md 暂无内容。_",
  ].join("\n");
}

/**
 * 将当前账号画像和记忆合并进一个目标 Agent，并返回可用于失败回滚的原始内容。
 *
 * @param {string} agentDirectory - staging 或已安装 Agent 目录。
 * @param {{accountKey: string, sourceAgentId: string, userContent: string, memoryContent: string, fingerprint: string}} source - 个性化来源。
 * @returns {{userPath: string, memoryPath: string, userContent: string, memoryContent: string}}
 *   写入前快照；调用方只应在回滚同一次安装时使用。
 * @throws {Error} 目标核心文件不存在或原子写入失败时抛出。
 */
function personalizeAgentDirectory(agentDirectory, source) {
  const userPath = path.join(agentDirectory, "agent-core", "USER.md");
  const memoryPath = path.join(agentDirectory, "agent-core", "MEMORY.md");
  if (!fs.existsSync(userPath) || !fs.existsSync(memoryPath)) {
    throw new Error(`目标 Agent 缺少 USER.md 或 MEMORY.md：${agentDirectory}`);
  }

  const originalUser = fs.readFileSync(userPath, "utf8");
  const originalMemory = fs.readFileSync(memoryPath, "utf8");
  try {
    writeTextAtomically(
      userPath,
      upsertManagedBlock(
        originalUser,
        USER_CONTEXT_MARKERS,
        buildUserContextBlock(source),
      ),
    );
    writeTextAtomically(
      memoryPath,
      upsertManagedBlock(
        originalMemory,
        MEMORY_CONTEXT_MARKERS,
        buildMemoryContextBlock(source),
      ),
    );
  } catch (writeError) {
    // 即使第二个文件写入失败，也要把第一个文件恢复，避免留下半个性化状态。
    try {
      writeTextAtomically(userPath, originalUser);
      writeTextAtomically(memoryPath, originalMemory);
    } catch (restoreError) {
      const restoreMessage =
        restoreError instanceof Error ? restoreError.message : String(restoreError);
      throw new Error(`个性化写入失败且回滚失败：${restoreMessage}`, {
        cause: writeError,
      });
    }
    throw writeError;
  }

  return {
    userPath,
    memoryPath,
    userContent: originalUser,
    memoryContent: originalMemory,
  };
}

/**
 * 恢复一次个性化写入前的 USER.md 与 MEMORY.md。
 *
 * @param {{userPath: string, memoryPath: string, userContent: string, memoryContent: string}} snapshot - 写入前快照。
 * @returns {void}
 */
function restorePersonalizationSnapshot(snapshot) {
  writeTextAtomically(snapshot.userPath, snapshot.userContent);
  writeTextAtomically(snapshot.memoryPath, snapshot.memoryContent);
}

/**
 * 验证目标 Agent 已包含与当前账号一致的两个个性化块。
 *
 * @param {string} agentDirectory - 目标 Agent 目录。
 * @param {{fingerprint: string}} source - 个性化来源。
 * @returns {void}
 * @throws {Error} 标记或指纹缺失时抛出。
 */
function validatePersonalization(agentDirectory, source) {
  const userContent = fs.readFileSync(
    path.join(agentDirectory, "agent-core", "USER.md"),
    "utf8",
  );
  const memoryContent = fs.readFileSync(
    path.join(agentDirectory, "agent-core", "MEMORY.md"),
    "utf8",
  );
  const expectedFingerprint = `个性化指纹：${source.fingerprint}`;
  const countOccurrences = (content, marker) => content.split(marker).length - 1;
  if (
    countOccurrences(userContent, USER_CONTEXT_MARKERS.begin) !== 1 ||
    countOccurrences(userContent, USER_CONTEXT_MARKERS.end) !== 1 ||
    !userContent.includes(expectedFingerprint) ||
    countOccurrences(memoryContent, MEMORY_CONTEXT_MARKERS.begin) !== 1 ||
    countOccurrences(memoryContent, MEMORY_CONTEXT_MARKERS.end) !== 1 ||
    !memoryContent.includes(expectedFingerprint)
  ) {
    throw new Error(`目标 Agent 的本地个性化校验失败：${agentDirectory}`);
  }
}

/**
 * 列出当前 agents/ 下所有尚未完成的 staging 目录。
 *
 * @param {string} targetRoot - 当前空间 agents/。
 * @returns {string[]} staging 目录名列表。
 */
function listInstallingResidue(targetRoot) {
  return fs
    .readdirSync(targetRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith(".installing-"))
    .map((entry) => entry.name)
    .sort();
}

/**
 * 生成目标空间内唯一的 MID-*。
 *
 * @param {Set<string>} usedIds - 已有和本轮已分配 ID。
 * @returns {string} 唯一 MID-*。
 */
function createUniqueAgentId(usedIds) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const candidate = `MID-${crypto.randomUUID().toUpperCase()}`;
    if (!usedIds.has(candidate)) {
      usedIds.add(candidate);
      return candidate;
    }
  }
  throw new Error("连续生成 20 次仍发生 Agent ID 冲突");
}

/**
 * 校验一个 staging 或正式 Agent 的最小结构和绑定关系。
 *
 * @param {string} agentDirectory - Agent 目录。
 * @param {Record<string, unknown>} manifestAgent - Bundle 清单项。
 * @param {string} expectedAgentId - 本次生成的 MID-*。
 * @param {string} expectedInstallPath - 私有 Skill 最终安装绝对路径。
 * @returns {void}
 * @throws {Error} 文件、ID、头像或 Skill 索引不匹配时抛出。
 */
function validatePreparedAgent(
  agentDirectory,
  manifestAgent,
  expectedAgentId,
  expectedInstallPath,
) {
  const required = [
    "profile.jsonc",
    "agent-core/AGENTS.md",
    "agent-core/IDENTITY.md",
    "agent-core/SOUL.md",
    "agent-core/USER.md",
    "agent-core/MEMORY.md",
    "agent-core/BOOTSTRAP.md",
    "agent-core/HEARTBEAT.md",
    "agent-core/tool-registry.jsonc",
    "agent-core/skills/skills.jsonc",
    `agent-core/skills/${manifestAgent.runtimeSkillId}/SKILL.md`,
    "permissions/policy.jsonl",
  ];
  for (const relativePath of required) {
    if (!fs.existsSync(path.join(agentDirectory, relativePath))) {
      throw new Error(`${manifestAgent.displayName} 缺少 ${relativePath}`);
    }
  }

  const profile = readJsonc(path.join(agentDirectory, "profile.jsonc"));
  const skillsIndex = readJsonc(
    path.join(agentDirectory, "agent-core", "skills", "skills.jsonc"),
  );
  const skillEntry = skillsIndex.skills?.[0];
  const privateSkillDirectories = listPrivateSkillDirectories(agentDirectory);
  if (
    profile.id !== expectedAgentId ||
    profile.name !== manifestAgent.displayName ||
    profile.enabled !== true ||
    profile.sourceAgentId !== manifestAgent.sourceAgentId ||
    profile.avatarSha256 !== manifestAgent.avatarSha256 ||
    profile.avatar !== profile.avatarUrl ||
    calculateEmbeddedAvatarSha256(profile) !== manifestAgent.avatarSha256
  ) {
    throw new Error(`${manifestAgent.displayName} 的 profile 校验失败`);
  }
  if (
    !Array.isArray(skillsIndex.skills) ||
    skillsIndex.skills.length !== 1 ||
    skillEntry?.id !== manifestAgent.runtimeSkillId ||
    skillEntry?.enabled !== true ||
    skillEntry?.installPath !== expectedInstallPath ||
    privateSkillDirectories.length !== 1 ||
    privateSkillDirectories[0] !== manifestAgent.runtimeSkillId
  ) {
    throw new Error(`${manifestAgent.displayName} 的私有 Skill 索引校验失败`);
  }
}

/**
 * 安装全部未安装的 Bundle Agent。
 *
 * @param {Record<string, unknown>} manifest - bundle-manifest.json。
 * @param {{targetRoot: string, accountKey: string, source: string}} target - 当前空间。
 * @param {boolean} dryRun - 是否只做预检。
 * @returns {{installed: Array<Record<string, string>>, skipped: Array<Record<string, string>>, personalizedCount: number, personalizationSourceAgentId: string, personalizationFingerprint: string, installingResidue: string[]}}
 *   新安装、已存在清单和本地个性化校验结果。
 */
function installBundle(manifest, target, dryRun) {
  if (!Array.isArray(manifest.agents) || manifest.agents.length !== 23) {
    throw new Error(`Bundle Agent 数量异常：${manifest.agents?.length ?? "未知"}`);
  }

  const personalizationSource = resolvePersonalizationSource(
    target.targetRoot,
    target.accountKey,
  );
  const existing = indexExistingAgents(target.targetRoot);
  const tasks = [];
  const skipped = [];
  const skippedTasks = [];

  for (const manifestAgent of manifest.agents) {
    const existingSourceDirectory = existing.bySourceAgentId.get(
      manifestAgent.sourceAgentId,
    );
    if (existingSourceDirectory) {
      if (!isCompleteExistingInstall(existingSourceDirectory, manifestAgent)) {
        throw new Error(
          `已存在同来源但不完整的 Agent：${manifestAgent.displayName}（${existingSourceDirectory}）`,
        );
      }
      const skippedEntry = {
        displayName: manifestAgent.displayName,
        sourceAgentId: manifestAgent.sourceAgentId,
        localAgentId: path.basename(existingSourceDirectory),
        directory: existingSourceDirectory,
      };
      skipped.push(skippedEntry);
      skippedTasks.push({ manifestAgent, ...skippedEntry });
      continue;
    }

    const sameNameDirectory = existing.byName.get(manifestAgent.displayName);
    if (sameNameDirectory) {
      throw new Error(
        `发现同名但来源不明的 Agent，拒绝覆盖：${manifestAgent.displayName}（${sameNameDirectory}）`,
      );
    }

    const localAgentId = createUniqueAgentId(existing.usedIds);
    const finalDirectory = path.join(target.targetRoot, localAgentId);
    const stagingDirectory = path.join(
      target.targetRoot,
      `.installing-${localAgentId}`,
    );
    tasks.push({ manifestAgent, localAgentId, finalDirectory, stagingDirectory });
  }

  if (dryRun) {
    return {
      installed: tasks.map((task) => ({
        displayName: task.manifestAgent.displayName,
        localAgentId: task.localAgentId,
        status: "would-install",
      })),
      skipped,
      personalizedCount: 0,
      wouldPersonalizeCount: tasks.length + skipped.length,
      personalizationSourceAgentId: personalizationSource.sourceAgentId,
      personalizationFingerprint: personalizationSource.fingerprint,
      installingResidue: listInstallingResidue(target.targetRoot),
    };
  }

  const staged = [];
  const finalized = [];
  const existingPersonalizationSnapshots = [];
  try {
    for (const task of tasks) {
      if (fs.existsSync(task.stagingDirectory) || fs.existsSync(task.finalDirectory)) {
        throw new Error(`目标目录冲突：${task.localAgentId}`);
      }

      const templateDirectory = path.join(
        BUNDLE_ROOT,
        "agents",
        task.manifestAgent.templateDirectory,
      );
      if (!fs.existsSync(path.join(templateDirectory, "profile.jsonc"))) {
        throw new Error(
          `Bundle 模板缺失：${task.manifestAgent.templateDirectory}`,
        );
      }

      fs.cpSync(templateDirectory, task.stagingDirectory, {
        recursive: true,
        force: false,
        errorOnExist: true,
        preserveTimestamps: true,
      });
      staged.push(task.stagingDirectory);

      const profilePath = path.join(task.stagingDirectory, "profile.jsonc");
      const profile = readJsonc(profilePath);
      writeJsonAtomically(profilePath, {
        ...profile,
        id: task.localAgentId,
        enabled: true,
        accountId: target.accountKey.split("_")[0],
        installedFromBundle: manifest.bundleId,
        installedBundleVersion: manifest.version,
      });

      const finalSkillDirectory = path.join(
        task.finalDirectory,
        "agent-core",
        "skills",
        task.manifestAgent.runtimeSkillId,
      );
      const skillsIndexPath = path.join(
        task.stagingDirectory,
        "agent-core",
        "skills",
        "skills.jsonc",
      );
      const skillsIndex = readJsonc(skillsIndexPath);
      if (!Array.isArray(skillsIndex.skills) || skillsIndex.skills.length !== 1) {
        throw new Error(
          `${task.manifestAgent.displayName} 模板私有 Skill 数量不是 1`,
        );
      }
      skillsIndex.skills[0].installPath = finalSkillDirectory;
      writeJsonAtomically(skillsIndexPath, skillsIndex);

      // 在原子改名前完成个性化，确保 Accio 永远看不到半完成的新 Agent。
      personalizeAgentDirectory(task.stagingDirectory, personalizationSource);

      validatePreparedAgent(
        task.stagingDirectory,
        task.manifestAgent,
        task.localAgentId,
        finalSkillDirectory,
      );
      validatePersonalization(task.stagingDirectory, personalizationSource);
    }

    // 已完整安装的同来源 Agent 不重复创建，但仍刷新为当前账号最新的本地画像和记忆。
    // 写入前保留内存快照；后续任何一步失败都会恢复原文件。
    for (const skippedTask of skippedTasks) {
      const snapshot = personalizeAgentDirectory(
        skippedTask.directory,
        personalizationSource,
      );
      existingPersonalizationSnapshots.push(snapshot);
      validatePersonalization(skippedTask.directory, personalizationSource);
    }

    for (const task of tasks) {
      if (fs.existsSync(task.finalDirectory)) {
        throw new Error(`原子改名前发现并发目录冲突：${task.finalDirectory}`);
      }
      fs.renameSync(task.stagingDirectory, task.finalDirectory);
      finalized.push(task.finalDirectory);
    }

    for (const task of tasks) {
      const finalSkillDirectory = path.join(
        task.finalDirectory,
        "agent-core",
        "skills",
        task.manifestAgent.runtimeSkillId,
      );
      validatePreparedAgent(
        task.finalDirectory,
        task.manifestAgent,
        task.localAgentId,
        finalSkillDirectory,
      );
      validatePersonalization(task.finalDirectory, personalizationSource);
    }

    for (const skippedTask of skippedTasks) {
      validatePersonalization(skippedTask.directory, personalizationSource);
    }

    const personalizedCount = tasks.length + skippedTasks.length;
    if (personalizedCount !== manifest.agents.length) {
      throw new Error(
        `本地个性化数量异常：${personalizedCount}/${manifest.agents.length}`,
      );
    }

    const installingResidue = listInstallingResidue(target.targetRoot);
    if (installingResidue.length > 0) {
      throw new Error(
        `发现未完成的 staging 目录：${installingResidue.join(", ")}`,
      );
    }
  } catch (error) {
    for (const stagingDirectory of staged) {
      fs.rmSync(stagingDirectory, { recursive: true, force: true });
    }
    for (const finalDirectory of finalized) {
      fs.rmSync(finalDirectory, { recursive: true, force: true });
    }
    for (const snapshot of existingPersonalizationSnapshots.reverse()) {
      try {
        restorePersonalizationSnapshot(snapshot);
      } catch (restoreError) {
        const restoreMessage =
          restoreError instanceof Error ? restoreError.message : String(restoreError);
        process.stderr.write(`ROLLBACK_WARNING ${restoreMessage}\n`);
      }
    }
    throw error;
  }

  return {
    installed: tasks.map((task) => ({
      displayName: task.manifestAgent.displayName,
      localAgentId: task.localAgentId,
      runtimeSkillId: task.manifestAgent.runtimeSkillId,
      directory: task.finalDirectory,
    })),
    skipped,
    personalizedCount: tasks.length + skippedTasks.length,
    wouldPersonalizeCount: tasks.length + skippedTasks.length,
    personalizationSourceAgentId: personalizationSource.sourceAgentId,
    personalizationFingerprint: personalizationSource.fingerprint,
    installingResidue: [],
  };
}

/**
 * 执行安装并输出机器可读结果。
 *
 * @returns {void}
 */
function main() {
  const argumentsResult = parseArguments(process.argv.slice(2));
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8"));
  const target = resolveInstallTarget(argumentsResult);
  const result = installBundle(manifest, target, argumentsResult.dryRun);
  const totalCount = result.installed.length + result.skipped.length;
  if (!argumentsResult.dryRun && totalCount !== manifest.agentCount) {
    throw new Error(`安装总数异常：${totalCount}/${manifest.agentCount}`);
  }
  if (
    !argumentsResult.dryRun &&
    result.personalizedCount !== manifest.agentCount
  ) {
    throw new Error(
      `本地个性化总数异常：${result.personalizedCount}/${manifest.agentCount}`,
    );
  }
  if (!argumentsResult.dryRun && result.installingResidue.length > 0) {
    throw new Error(
      `仍有 staging 残留：${result.installingResidue.join(", ")}`,
    );
  }

  const summary = {
    ok: true,
    dryRun: argumentsResult.dryRun,
    bundleId: manifest.bundleId,
    bundleVersion: manifest.version,
    targetRoot: target.targetRoot,
    accountKey: target.accountKey,
    targetResolution: target.source,
    installedCount: result.installed.length,
    skippedCount: result.skipped.length,
    personalizedCount: result.personalizedCount,
    wouldPersonalizeCount: result.wouldPersonalizeCount,
    personalizationSourceAgentId: result.personalizationSourceAgentId,
    personalizationFingerprint: result.personalizationFingerprint,
    installingResidue: result.installingResidue,
    installed: result.installed,
    skipped: result.skipped,
    restartRequired: !argumentsResult.dryRun,
  };

  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  if (argumentsResult.dryRun) {
    process.stdout.write(
      `PRECHECK_OK wouldInstall=${summary.installedCount} skipped=${summary.skippedCount} wouldPersonalize=${summary.wouldPersonalizeCount} target=${summary.targetRoot}\n`,
    );
  } else {
    process.stdout.write(
      `INSTALL_OK installed=${summary.installedCount} skipped=${summary.skippedCount} personalized=${summary.personalizedCount} residue=${summary.installingResidue.length} target=${summary.targetRoot}\n`,
    );
  }
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`INSTALL_FAILED ${message}\n`);
  process.exitCode = 1;
}
