# 企业知识库问答智能体安装提示词

把下面对应系统的命令发送给当前 Accio Work 中具有下载、解压和本地文件写入权限的 Agent。该入口只安装一个智能体，不会重装现有 47-Agent 套装，也不会覆盖“企业 AI 底座搭建智能体”。

Windows：

```powershell
curl.exe --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/be8f5fc222cf4ae408f1f706c2dca3346bed6f80/install/enterprise-knowledge-base-qa-agent.txt
```

macOS：

```bash
curl --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/be8f5fc222cf4ae408f1f706c2dca3346bed6f80/install/enterprise-knowledge-base-qa-agent.txt
```

安装完成后，请完整退出并重新打开 Accio Work，再到“智能体 → 个人”检查名称、来搜 Logo、`knowledge-base-plugin` 依赖、私有 Skill 和知识库引用规则。
