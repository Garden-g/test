# Accio Work 智能体安装 Prompt

把下面整段复制给当前 Accio Work 里的 Agent：

```text
请安装这个 Accio Work 智能体 ZIP：
/Users/garden/Self/TokenMindOmni/delivery/合作交付/磐西/Accio Work/智能体安装包/28-来搜 | 展会名单客户开发智能体/b2b-trade-show-leads-agent.zip

要求：
1. 使用兼容 UTF-8 文件名的方式读取并解压 ZIP。
2. 读取 ~/.accio/state/current-space.json 确认当前空间，不要根据最近修改目录猜测。
3. 校验 profile.jsonc、agent-core/、permissions/ 和 agent-core/skills/skills.jsonc。
4. 确认 profile.jsonc.id 在当前空间唯一；如有冲突，生成新的 MID-*，并保持目标目录名与 profile.jsonc.id 完全一致。
5. 确保 profile.jsonc.enabled 为 true。
6. 确认目标 agents/<agentId>/ 不存在，禁止覆盖。先复制到同级 .installing-<agentId>，全部校验通过后再原子改名。
7. 保留 agent-core/skills/ 中的私有 Skill，不要单独安装到全局 skills 目录。
8. 安装完成后回报智能体名称、ID、最终路径、启用状态、工具白名单、插件依赖和私有 Skill 清单。
9. 提醒我完整退出并重新启动 Accio Work，再到“智能体 → 个人”验收名称、来搜 Logo、描述和独立对话页。
10. 若当前 Agent 没有读取 ZIP 或写入目标目录的权限，停止并明确说明缺少的权限，不要声称安装成功。

本包声明的插件依赖：spreadsheets。插件依赖不代表目标环境已经安装或授权。
```
