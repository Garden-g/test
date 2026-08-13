请把“国际站广告投放控制台智能体”安装到当前 Accio Work 空间。

ZIP：https://raw.githubusercontent.com/Garden-g/test/main/release/standalone/alibaba-ads-control-console/alibaba-ads-control-console-agent.zip

SHA-256：https://raw.githubusercontent.com/Garden-g/test/main/release/standalone/alibaba-ads-control-console/alibaba-ads-control-console-agent.zip.sha256

请先下载并校验 SHA-256，再用兼容 UTF-8 文件名的方式解压。读取当前 Accio Work 空间配置，确认包内 `profile.jsonc`、`permissions/`、`agent-core/` 和私有 Skill `alibaba-ads-control-console` 完整。若包内 Agent ID 与当前空间冲突，请生成新的唯一 `MID-*`，同时修改目录名与 `profile.jsonc.id`。先写入同级 `.installing-<agentId>`，全部校验通过后再原子改名，禁止覆盖已有智能体，也不要把私有 Skill 安装到全局 Skills 目录。

完成后回报智能体名称、最终 ID、安装路径、启用状态、工具白名单、插件依赖和私有 Skill。该智能体需要目标环境已安装并授权相应的 Alibaba.com 与表格能力；暂停计划、修改预算出价、增删商品或定向等写操作，必须再次确认具体对象、参数和影响范围。提醒我完整退出并重新打开 Accio Work 后，在“智能体 → 个人”中验收。
