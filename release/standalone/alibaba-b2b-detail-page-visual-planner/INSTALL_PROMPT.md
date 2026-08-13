请把“国际站详情页策划智能体”安装到当前 Accio Work 空间。

ZIP：https://raw.githubusercontent.com/Garden-g/test/main/release/standalone/alibaba-b2b-detail-page-visual-planner/alibaba-detail-page-planner-agent.zip

SHA-256：https://raw.githubusercontent.com/Garden-g/test/main/release/standalone/alibaba-b2b-detail-page-visual-planner/alibaba-detail-page-planner-agent.zip.sha256

请先下载并校验 SHA-256，再用兼容 UTF-8 文件名的方式解压。读取当前 Accio Work 空间配置，确认包内 `profile.jsonc`、`permissions/`、`agent-core/` 和私有 Skill `alibaba-b2b-detail-page-visual-planner` 完整。若包内 Agent ID 与当前空间冲突，请生成新的唯一 `MID-*`，同时修改目录名与 `profile.jsonc.id`。先写入同级 `.installing-<agentId>`，全部校验通过后再原子改名，禁止覆盖已有智能体，也不要把私有 Skill 安装到全局 Skills 目录。

完成后回报智能体名称、最终 ID、安装路径、启用状态、工具白名单、插件依赖和私有 Skill。图片生成和编辑能力取决于目标环境已有的工具与额度；涉及生成或修改图片时，应先确认产品素材和具体范围。提醒我完整退出并重新打开 Accio Work 后，在“智能体 → 个人”中验收。
