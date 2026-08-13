请安装这个赢单 27 智能体套装到当前 Accio Work 空间：

ZIP：
https://raw.githubusercontent.com/Garden-g/test/main/release/yingdan-27-accio-agents-v1.2.0.zip

SHA-256：
https://raw.githubusercontent.com/Garden-g/test/main/release/yingdan-27-accio-agents-v1.2.0.zip.sha256

下载并校验后解压，先读取包内 `INSTALL_PROMPT.txt`，再执行当前系统对应的安装器：Windows 使用 `installer/install-windows.ps1`，macOS 使用 `installer/install-macos.sh`。不要走“创建智能体”流程，不要覆盖已有智能体。

27个智能体的名称必须全部以“赢单｜”开头，并使用同一个黑橙色赢单 Logo。安装器会把当前 Accio 主智能体中的本地用户画像和记忆融合进这27个智能体；同来源旧版智能体已经存在时，保留其 ID 和目录并更新名称与 Logo，不要重复创建。只有出现 `INSTALL_OK`，且安装数加跳过数、品牌更新数、个性化数均为27并且没有 `.installing-*` 残留时，才能报告成功。不要自动重启 Accio，完成后提醒我手动完整退出并重新打开。
