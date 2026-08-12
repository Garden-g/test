# TokenMind 23 个 Accio Work 智能体套装

一个适用于 Windows 和 macOS 的可移植 ZIP，包含23个一对一智能体。每个智能体都内置对应的完整私有 Skill，并统一使用同一张 Logo。

## 下载

- [tokenmind-23-accio-agents-v1.0.2.zip](release/tokenmind-23-accio-agents-v1.0.2.zip)
- [SHA-256 校验文件](release/tokenmind-23-accio-agents-v1.0.2.zip.sha256)
- [可直接复制给 Accio Work 的安装提示词](INSTALL_PROMPT.md)

安装器会识别当前 Accio 个人或团队空间，为23个 Agent 分别生成唯一 `MID-*`，保留私有 Skill 和统一 Logo，不覆盖已有 Agent。安装完成后，它会从当前空间 `agentType=accio` 的主智能体读取本地 `USER.md` 和 `MEMORY.md`，以 TokenMind 标记块合并到23个 Agent 的同名文件中。

Windows 执行 `installer/install-windows.ps1`；macOS 执行 `installer/install-macos.sh`。两者都优先使用 Accio 自带的 Node。安装器不会主动结束或重启 Accio Work。
