/**
 * TokenMind 23 个 Accio Work 智能体套装安装器。
 *
 * 安装器只处理当前 Bundle 中声明的 Agent 模板，主要职责：
 * 1. 识别当前 Accio 个人或团队空间的 agents/ 目录；
 * 2. 为每个 Agent 生成目标空间内唯一的 MID-*；
 * 3. 改写 profile.jsonc.id 与私有 Skill 的 installPath；
 * 4. 先写入隐藏 staging 目录，全部校验后再原子改名；
 * 5. 重复执行时识别已经完整安装的同一来源 Agent，避免重复创建；
 * 6. 失败时只回滚本次新建目录，不覆盖或删除用户原有 Agent。
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
  fs.writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  fs.renameSync(temporaryPath, filePath);
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
    if (!line.includes("/.accio/accounts/")) {
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

    const match = String(record.message || "").match(
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
    return (
      profile.sourceAgentId === manifestAgent.sourceAgentId &&
      profile.enabled !== false &&
      Array.isArray(skillsIndex.skills) &&
      skillsIndex.skills.length === 1 &&
      skillsIndex.skills[0]?.id === manifestAgent.runtimeSkillId &&
      skillsIndex.skills[0]?.enabled === true &&
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
  if (
    profile.id !== expectedAgentId ||
    profile.name !== manifestAgent.displayName ||
    profile.enabled !== true ||
    profile.sourceAgentId !== manifestAgent.sourceAgentId ||
    profile.avatarSha256 !== manifestAgent.avatarSha256
  ) {
    throw new Error(`${manifestAgent.displayName} 的 profile 校验失败`);
  }
  if (
    !Array.isArray(skillsIndex.skills) ||
    skillsIndex.skills.length !== 1 ||
    skillEntry?.id !== manifestAgent.runtimeSkillId ||
    skillEntry?.enabled !== true ||
    skillEntry?.installPath !== expectedInstallPath
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
 * @returns {{installed: Array<Record<string, string>>, skipped: Array<Record<string, string>>}}
 *   新安装和已存在清单。
 */
function installBundle(manifest, target, dryRun) {
  if (!Array.isArray(manifest.agents) || manifest.agents.length !== 23) {
    throw new Error(`Bundle Agent 数量异常：${manifest.agents?.length ?? "未知"}`);
  }

  const existing = indexExistingAgents(target.targetRoot);
  const tasks = [];
  const skipped = [];

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
      skipped.push({
        displayName: manifestAgent.displayName,
        sourceAgentId: manifestAgent.sourceAgentId,
        directory: existingSourceDirectory,
      });
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
    };
  }

  const staged = [];
  const finalized = [];
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

      validatePreparedAgent(
        task.stagingDirectory,
        task.manifestAgent,
        task.localAgentId,
        finalSkillDirectory,
      );
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
    }
  } catch (error) {
    for (const stagingDirectory of staged) {
      fs.rmSync(stagingDirectory, { recursive: true, force: true });
    }
    for (const finalDirectory of finalized) {
      fs.rmSync(finalDirectory, { recursive: true, force: true });
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
    installed: result.installed,
    skipped: result.skipped,
    restartRequired: !argumentsResult.dryRun && result.installed.length > 0,
  };

  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  process.stdout.write(
    `INSTALL_OK installed=${summary.installedCount} skipped=${summary.skippedCount} target=${summary.targetRoot}\n`,
  );
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`INSTALL_FAILED ${message}\n`);
  process.exitCode = 1;
}
