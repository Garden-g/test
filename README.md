# TokenMind 27 个 Accio Work 智能体套装

一个适用于 Windows 和 macOS 的可移植 ZIP，包含 27 个一对一智能体。每个智能体都只内置一个对应的完整私有 Skill，并统一使用同一张 Logo。

## 下载

- [tokenmind-27-accio-agents-v1.1.0.zip](release/tokenmind-27-accio-agents-v1.1.0.zip)
- [SHA-256 校验文件](release/tokenmind-27-accio-agents-v1.1.0.zip.sha256)
- [可直接复制给 Accio Work 的安装提示词](INSTALL_PROMPT.md)

安装器会识别当前 Accio 个人或团队空间，为 27 个 Agent 分别生成唯一 `MID-*`，保留私有 Skill 和统一 Logo，不覆盖已有 Agent。安装完成后，它会从当前空间 `agentType=accio` 的主智能体读取本地 `USER.md` 和 `MEMORY.md`，以 TokenMind 标记块合并到 27 个 Agent 的同名文件中。

本次新增的 4 个运营智能体也提供独立安装包：

- [国际站关键词标题智能体](release/standalone/alibaba-title-keyword-builder/)
- [国际站五条卖点智能体](release/standalone/alibaba-five-selling-points-writer/)
- [国际站详情页策划智能体](release/standalone/alibaba-b2b-detail-page-visual-planner/)
- [国际站广告投放控制台智能体](release/standalone/alibaba-ads-control-console/)

Windows 执行 `installer/install-windows.ps1`；macOS 执行 `installer/install-macos.sh`。两者都优先使用 Accio 自带的 Node。安装器不会主动结束或重启 Accio Work。
