请让 Accio Work 根据当前系统执行对应命令，并严格按照返回内容继续安装：

Windows：

```powershell
curl.exe --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/8826fc17cc11348d665c5ca4bbbc4efe8dcc6686/install/laisou-27-agents.txt
```

macOS：

```bash
curl --http1.1 --retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 120 --connect-timeout 15 -fsSL https://raw.githubusercontent.com/Garden-g/test/8826fc17cc11348d665c5ca4bbbc4efe8dcc6686/install/laisou-27-agents.txt
```
