# 企业 AI 底座搭建智能体安装提示词

把下面对应系统的命令发送给当前 Accio Work 中具有下载、解压、执行脚本和本地文件写入权限的 Agent。该入口只安装一个智能体，不会重装现有 47-Agent 套装。

Windows：

```powershell
curl.exe --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/64a019ea42c30b999acef34fc0becb31b0431391/install/enterprise-ai-foundation-agent.txt
```

macOS：

```bash
curl --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/64a019ea42c30b999acef34fc0becb31b0431391/install/enterprise-ai-foundation-agent.txt
```

安装完成后，请完整退出并重新打开 Accio Work，再到“智能体 → 个人”检查名称、来搜 Logo、知识库插件依赖和私有 Skill。
