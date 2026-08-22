<#
来搜 Accio Work 智能体套装的 Windows 启动器。

作用：
1. 找到正在运行的 Accio.exe；
2. 把 Accio 自带的 Electron 运行时临时切换为 Node 模式；
3. 执行同目录下的 install.mjs；
4. 由 install.mjs 按 Bundle 清单完成全部 Agent 的原子安装和当前账号本地个性化；
5. 恢复原来的环境变量，不主动结束或重启 Accio。
#>

param(
    [string]$AccountKey = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$installerPath = Join-Path $PSScriptRoot "install.mjs"

if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
    throw "找不到安装器：$installerPath"
}

# 把 PowerShell 风格参数转换成 install.mjs 接受的跨平台参数。
$installerArguments = @()
if ($AccountKey) {
    $installerArguments += "--account-key"
    $installerArguments += $AccountKey
}
if ($DryRun) {
    $installerArguments += "--dry-run"
}

# 接收方正从 Accio Work 发起安装时，主进程通常正在运行；直接读取进程路径最可靠。
# 只查询 Accio 相关进程，避免读取其他受保护进程的 Path 属性。
$accioExecutable = Get-Process -Name "Accio", "Accio Work" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path } |
    Select-Object -First 1 -ExpandProperty Path

# 进程路径不可读时，再检查常见安装位置。这里只接受确实存在的可执行文件。
if (-not $accioExecutable) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Accio\Accio.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Accio Work\Accio Work.exe"),
        (Join-Path $env:LOCALAPPDATA "Accio\Accio.exe"),
        (Join-Path $env:ProgramFiles "Accio\Accio.exe")
    )

    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Accio\Accio.exe"
    }

    $accioExecutable = $candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
}

if ($accioExecutable) {
    $previousElectronMode = [Environment]::GetEnvironmentVariable(
        "ELECTRON_RUN_AS_NODE",
        "Process"
    )

    try {
        # Electron 支持用这个进程级变量运行其内置 Node；不会修改系统级环境变量。
        [Environment]::SetEnvironmentVariable("ELECTRON_RUN_AS_NODE", "1", "Process")
        & $accioExecutable $installerPath @installerArguments
        $installerExitCode = $LASTEXITCODE
    }
    finally {
        [Environment]::SetEnvironmentVariable(
            "ELECTRON_RUN_AS_NODE",
            $previousElectronMode,
            "Process"
        )
    }
}
else {
    # 极少数便携版 Accio 无法暴露进程路径时，允许使用用户已安装的 Node.js。
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        throw "没有找到正在运行的 Accio.exe，也没有找到系统 Node.js。请保持 Accio Work 正在运行后重试。"
    }

    & $nodeCommand.Source $installerPath @installerArguments
    $installerExitCode = $LASTEXITCODE
}

if ($installerExitCode -ne 0) {
    throw "智能体安装器执行失败，退出码：$installerExitCode"
}

$runtimeLabel = if ($accioExecutable) { $accioExecutable } else { $nodeCommand.Source }
Write-Host "WINDOWS_INSTALLER_OK runtime=$runtimeLabel"
