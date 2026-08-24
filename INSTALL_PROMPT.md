请让 Accio Work 根据当前系统执行对应命令，并严格按照返回内容一次安装全部 47 个来搜课程智能体：

Windows：

```powershell
curl.exe --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/ab8a9ad05e53403bda9f9367588bdf3ee5176bb0/install/laisou-47-agents.txt
```

macOS：

```bash
curl --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/ab8a9ad05e53403bda9f9367588bdf3ee5176bb0/install/laisou-47-agents.txt
```
