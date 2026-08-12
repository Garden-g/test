#!/usr/bin/env bash

# TokenMind 23 个 Accio Work 智能体套装的 macOS 启动器。
#
# 作用：
# 1. 优先定位本机 Accio.app 自带的 Electron/Node 运行时；
# 2. 通过仅对当前子进程生效的 ELECTRON_RUN_AS_NODE 执行 install.mjs；
# 3. 原样转发 --account-key、--target-root 和 --dry-run 等安装器参数；
# 4. 不结束、不重启 Accio Work，也不修改系统级环境变量。

set -euo pipefail

installer_dir="$(cd "$(dirname "$0")" && pwd)"
installer_path="$installer_dir/install.mjs"

if [[ ! -f "$installer_path" ]]; then
  echo "找不到安装器：$installer_path" >&2
  exit 1
fi

# Accio Desktop 的标准安装位置优先；用户级 Applications 作为兼容路径。
accio_candidates=(
  "/Applications/Accio.app/Contents/MacOS/Accio"
  "$HOME/Applications/Accio.app/Contents/MacOS/Accio"
)

accio_executable=""
for candidate in "${accio_candidates[@]}"; do
  if [[ -x "$candidate" ]]; then
    accio_executable="$candidate"
    break
  fi
done

if [[ -n "$accio_executable" ]]; then
  # 变量只传给这次子进程，不会污染用户终端或后续启动的 Accio。
  if ELECTRON_RUN_AS_NODE=1 "$accio_executable" "$installer_path" "$@"; then
    installer_exit_code=0
  else
    installer_exit_code=$?
  fi
  runtime_label="$accio_executable"
elif command -v node >/dev/null 2>&1; then
  # 便携版或非常规安装位置无法定位时，允许回退到用户已有的 Node.js。
  if node "$installer_path" "$@"; then
    installer_exit_code=0
  else
    installer_exit_code=$?
  fi
  runtime_label="$(command -v node)"
else
  echo "没有找到 Accio.app 自带的运行时，也没有找到系统 Node.js。" >&2
  exit 1
fi

if [[ $installer_exit_code -ne 0 ]]; then
  echo "智能体安装器执行失败，退出码：$installer_exit_code" >&2
  exit "$installer_exit_code"
fi

echo "MACOS_INSTALLER_OK runtime=$runtime_label"
