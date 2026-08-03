请把下面这个 TokenMind 23 智能体套装安装到我当前登录的 Accio Work 账号。不要只预览 ZIP，也不要走“创建智能体”注册向导；要完成真实本机安装并验证。

ZIP 下载地址：
https://raw.githubusercontent.com/Garden-g/test/main/release/tokenmind-23-accio-agents-v1.0.0.zip

SHA-256 校验文件：
https://raw.githubusercontent.com/Garden-g/test/main/release/tokenmind-23-accio-agents-v1.0.0.zip.sha256

请严格执行：
1. 在安全临时目录下载 ZIP 和 .sha256，先运行 SHA-256 校验；校验失败立即停止。
2. 使用 macOS 自带的 ditto -x -k 解压，兼容 UTF-8 文件名；不要把 ZIP 文件本身直接丢进 agents/。
3. 阅读解压目录里的 README.md 和 bundle-manifest.json，确认 bundleId 是 tokenmind-23-accio-agents、版本 1.0.0、Agent 数量 23。
4. 运行解压目录中的 installer/install.mjs。优先使用 Accio 自带 Node：
   ELECTRON_RUN_AS_NODE=1 /Applications/Accio.app/Contents/MacOS/Accio <installer绝对路径>
   如果该路径不存在，再使用系统 node <installer绝对路径>。
5. 安装器必须识别当前个人/团队空间，为每个 Agent 生成唯一 MID-*，让目录名与 profile.jsonc.id 一致，并把对应完整私有 Skill 放在 agent-core/skills/ 下。
6. 禁止覆盖现有 Agent；同一套装已经完整安装时允许跳过。不要复制会话、审计日志、tool-results、运行缓存、其他账号路径或凭据。
7. 只有终端出现 INSTALL_OK，且回报 installedCount + skippedCount = 23、每个 Agent 恰好一个私有 Skill、Logo 一致、没有 .installing-* 残留，才能告诉我安装成功。
8. 不要自动重启 Accio。完成后告诉我目标账号空间、安装数量、跳过数量和目录，让我自己完整退出并重新打开 Accio。
