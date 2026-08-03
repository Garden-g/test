# TokenMind 23 个 Accio Work 智能体套装

一个面向 Windows 的可移植 ZIP，包含 23 个一对一智能体。每个智能体都内置对应的完整私有 Skill，并统一使用同一张 Logo。

## Windows 下载

- [tokenmind-23-accio-agents-v1.0.1.zip](release/tokenmind-23-accio-agents-v1.0.1.zip)
- [SHA-256 校验文件](release/tokenmind-23-accio-agents-v1.0.1.zip.sha256)
- [可直接复制给 Accio Work 的 Windows 安装提示词](INSTALL_PROMPT.md)

SHA-256：

```text
d3392fd38e3622c123d23681b4d3a5f269a07a32f156d6fc9951b677ebd631c4
```

安装器会识别当前 Windows 用户的 Accio 个人或团队空间，为 23 个 Agent 分别生成唯一 `MID-*`，改写 `profile.jsonc.id` 和私有 Skill 安装路径，不覆盖现有 Agent，也不要求另装 Node.js。安装完成后需要用户手动完整退出并重新打开 Accio Work。
