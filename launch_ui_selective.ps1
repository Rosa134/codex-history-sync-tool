param(
  [switch]$InstallShortcutOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:UiScriptPath = $MyInvocation.MyCommand.Path
$script:ToolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:BackendPath = Join-Path $script:ToolRoot 'sync_backend.py'
$script:LatestState = $null
$script:AllProviders = @()

function Invoke-Backend {
  param([Parameter(Mandatory=$true)][string[]]$Arguments)
  if (-not (Test-Path -LiteralPath $script:BackendPath)) {
    throw "找不到后端脚本: $script:BackendPath"
  }
  $tmpOut = [System.IO.Path]::GetTempFileName()
  $tmpErr = [System.IO.Path]::GetTempFileName()
  try {
    $allArgs = @('-3', $script:BackendPath) + $Arguments
    $proc = Start-Process -FilePath 'py' -ArgumentList $allArgs -NoNewWindow -Wait -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr -PassThru
    $exitCode = $proc.ExitCode
    $text = (Get-Content $tmpOut -Encoding UTF8 -Raw).Trim()
    $errText = (Get-Content $tmpErr -Encoding UTF8 -Raw).Trim()
    if ($errText) {
      $errText -split "`n" | ForEach-Object { if ($_.Trim() -ne "") { Append-Log "[stderr] $_" } }
    }
  } finally {
    Remove-Item $tmpOut, $tmpErr -ErrorAction SilentlyContinue
  }
  if (-not $text) { throw "后端没有返回任何内容。" }
  try { $json = $text | ConvertFrom-Json }
  catch { throw "JSON 解析失败: $($_.Exception.Message)`n$text" }
  if ($exitCode -ne 0 -or -not $json.ok) {
    if ($json.error) { throw [string]$json.error }
    throw "后端执行失败。`n$text"
  }
  return $json
}

function Append-Log {
  param([string]$Message)
  $ts = Get-Date -Format "HH:mm:ss"
  $logBox.AppendText("[$ts] $Message`r`n")
  $logBox.SelectionStart = $logBox.TextLength
  $logBox.ScrollToCaret()
}

function Format-Duration {
  param($Ms)
  if ($null -eq $Ms) { return "0 秒" }
  return "$([Math]::Round([double]$Ms/1000,1)) 秒"
}

function Refresh-State {
  $status = Invoke-Backend @("--json", "status")
  $script:LatestState = $status
  $script:AllProviders = @($status.provider_counts | ForEach-Object { $_.provider })

  $currentLabel.Text = "当前: provider=$($status.current_provider), 模型=$($status.current_model)"
  $totalLabel.Text = "总线程: $($status.total_threads) | 会话文件: $($status.session_file_count) | 侧边栏: $($status.indexed_threads)"

  $sourceList.Items.Clear()
  foreach ($row in $status.provider_counts) {
    $isCurrent = if ($row.provider -eq $status.current_provider) { " [当前]" } else { "" }
    $label = "$($row.provider)  ($($row.count) 条)$isCurrent"
    $idx = $sourceList.Items.Add($label)
    if ($row.provider -ne $status.current_provider) {
      $sourceList.SetItemChecked($idx, $true)
    }
  }

  $targetCombo.Items.Clear()
  foreach ($prov in $script:AllProviders) {
    [void]$targetCombo.Items.Add($prov)
  }
  $currentIdx = $targetCombo.FindStringExact($status.current_provider)
  if ($currentIdx -ge 0) { $targetCombo.SelectedIndex = $currentIdx }

  Update-Preview
  $movable = [int]$status.movable_threads
  if ($movable -gt 0) {
    Append-Log "状态已刷新。$movable 条线程归属与当前不一致，可同步。"
  } else {
    Append-Log "状态已刷新。所有线程归属一致，无需操作。"
  }
}

function Update-Preview {
  $checked = Get-CheckedProviders
  $target = $targetCombo.SelectedItem
  if (-not $target -or $checked.Count -eq 0) {
    $previewLabel.Text = "请勾选来源并选择目标。"
    return
  }
  $total = 0
  foreach ($row in $script:LatestState.provider_counts) {
    if ($checked -contains $row.provider) {
      $total += [int]$row.count
    }
  }
  $sourceStr = ($checked -join ", ")
  $previewLabel.Text = "将 $total 条线程从 [$sourceStr] 迁到 [$target]"
}

function Get-CheckedProviders {
  $checked = @()
  for ($i = 0; $i -lt $sourceList.Items.Count; $i++) {
    if ($sourceList.GetItemChecked($i)) {
      $label = $sourceList.Items[$i]
      $prov = ($label -split "\s+\(")[0]
      $checked += $prov
    }
  }
  return $checked
}

function Set-Busy {
  param([bool]$Busy, [string]$Message="")
  foreach ($b in @($refreshBtn, $syncBtn, $backupBtn, $selectAllBtn, $deselectAllBtn)) {
    if ($b) { $b.Enabled = -not $Busy }
  }
  if ($Busy) {
    $statusLabel.Text = $Message
    $progressBar.Style = "Marquee"
    $progressBar.Visible = $true
  } else {
    $progressBar.Visible = $false
    $statusLabel.Text = "就绪"
  }
}

# ---------- 主窗口 ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = "Codex 历史选择性同步"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(860, 680)
$form.MinimumSize = New-Object System.Drawing.Size(860, 680)
$form.BackColor = [System.Drawing.Color]::FromArgb(246, 248, 251)
$form.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)

# 标题
$header = New-Object System.Windows.Forms.Label
$header.Text = "Codex 历史选择性同步"
$header.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 16, [System.Drawing.FontStyle]::Bold)
$header.AutoSize = $true
$header.Location = New-Object System.Drawing.Point(24, 16)
$form.Controls.Add($header)

$headerSub = New-Object System.Windows.Forms.Label
$headerSub.Text = "勾选要从哪些 provider 迁出，选择迁到哪个 provider。每次操作前自动备份。"
$headerSub.ForeColor = [System.Drawing.Color]::FromArgb(100, 100, 110)
$headerSub.AutoSize = $true
$headerSub.Location = New-Object System.Drawing.Point(26, 48)
$form.Controls.Add($headerSub)

$currentLabel = New-Object System.Windows.Forms.Label
$currentLabel.Text = "加载中..."
$currentLabel.AutoSize = $true
$currentLabel.Location = New-Object System.Drawing.Point(26, 80)
$currentLabel.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($currentLabel)

$totalLabel = New-Object System.Windows.Forms.Label
$totalLabel.Text = ""
$totalLabel.AutoSize = $true
$totalLabel.Location = New-Object System.Drawing.Point(26, 102)
$form.Controls.Add($totalLabel)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "加载中..."
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(28, 84, 160)
$statusLabel.AutoSize = $true
$statusLabel.Location = New-Object System.Drawing.Point(26, 124)
$form.Controls.Add($statusLabel)

$progressBar = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(28, 148)
$progressBar.Size = New-Object System.Drawing.Size(790, 6)
$progressBar.Visible = $false
$form.Controls.Add($progressBar)

# 来源选择
$sourceBox = New-Object System.Windows.Forms.GroupBox
$sourceBox.Text = "来源（勾选要迁出的 provider）"
$sourceBox.Location = New-Object System.Drawing.Point(26, 170)
$sourceBox.Size = New-Object System.Drawing.Size(380, 230)
$form.Controls.Add($sourceBox)

$sourceList = New-Object System.Windows.Forms.CheckedListBox
$sourceList.Location = New-Object System.Drawing.Point(12, 24)
$sourceList.Size = New-Object System.Drawing.Size(356, 146)
$sourceList.CheckOnClick = $true
$sourceBox.Controls.Add($sourceList)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 100
$timer.Add_Tick({
  $timer.Stop()
  Update-Preview
})

$sourceList.Add_ItemCheck({
  $timer.Start()
})

$selectAllBtn = New-Object System.Windows.Forms.Button
$selectAllBtn.Text = "全选"
$selectAllBtn.Size = New-Object System.Drawing.Size(80, 30)
$selectAllBtn.Location = New-Object System.Drawing.Point(12, 186)
$sourceBox.Controls.Add($selectAllBtn)

$deselectAllBtn = New-Object System.Windows.Forms.Button
$deselectAllBtn.Text = "取消全选"
$deselectAllBtn.Size = New-Object System.Drawing.Size(80, 30)
$deselectAllBtn.Location = New-Object System.Drawing.Point(100, 186)
$sourceBox.Controls.Add($deselectAllBtn)

# 目标选择
$targetBox = New-Object System.Windows.Forms.GroupBox
$targetBox.Text = "目标"
$targetBox.Location = New-Object System.Drawing.Point(430, 170)
$targetBox.Size = New-Object System.Drawing.Size(388, 100)
$form.Controls.Add($targetBox)

$targetLbl = New-Object System.Windows.Forms.Label
$targetLbl.Text = "迁到:"
$targetLbl.AutoSize = $true
$targetLbl.Location = New-Object System.Drawing.Point(12, 30)
$targetBox.Controls.Add($targetLbl)

$targetCombo = New-Object System.Windows.Forms.ComboBox
$targetCombo.DropDownStyle = "DropDownList"
$targetCombo.Location = New-Object System.Drawing.Point(55, 28)
$targetCombo.Size = New-Object System.Drawing.Size(260, 24)
$targetBox.Controls.Add($targetCombo)

$targetCombo.Add_SelectedIndexChanged({
  Update-Preview
})

# 预览
$previewBox = New-Object System.Windows.Forms.GroupBox
$previewBox.Text = "预览"
$previewBox.Location = New-Object System.Drawing.Point(430, 285)
$previewBox.Size = New-Object System.Drawing.Size(388, 80)
$form.Controls.Add($previewBox)

$previewLabel = New-Object System.Windows.Forms.Label
$previewLabel.Text = "请勾选来源并选择目标。"
$previewLabel.AutoSize = $true
$previewLabel.Location = New-Object System.Drawing.Point(12, 26)
$previewLabel.MaximumSize = New-Object System.Drawing.Size(360, 40)
$previewBox.Controls.Add($previewLabel)

# 操作按钮
$refreshBtn = New-Object System.Windows.Forms.Button
$refreshBtn.Text = "刷新状态"
$refreshBtn.Size = New-Object System.Drawing.Size(110, 36)
$refreshBtn.Location = New-Object System.Drawing.Point(26, 410)
$form.Controls.Add($refreshBtn)

$syncBtn = New-Object System.Windows.Forms.Button
$syncBtn.Text = "执行同步"
$syncBtn.Size = New-Object System.Drawing.Size(140, 36)
$syncBtn.Location = New-Object System.Drawing.Point(150, 410)
$syncBtn.BackColor = [System.Drawing.Color]::FromArgb(32, 91, 177)
$syncBtn.ForeColor = [System.Drawing.Color]::White
$syncBtn.FlatStyle = "Flat"
$form.Controls.Add($syncBtn)

$backupBtn = New-Object System.Windows.Forms.Button
$backupBtn.Text = "仅备份"
$backupBtn.Size = New-Object System.Drawing.Size(110, 36)
$backupBtn.Location = New-Object System.Drawing.Point(306, 410)
$form.Controls.Add($backupBtn)

# 日志
$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ScrollBars = "Vertical"
$logBox.ReadOnly = $true
$logBox.Location = New-Object System.Drawing.Point(26, 460)
$logBox.Size = New-Object System.Drawing.Size(792, 170)
$logBox.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($logBox)

# 事件
$selectAllBtn.Add_Click({
  for ($i = 0; $i -lt $sourceList.Items.Count; $i++) {
    $sourceList.SetItemChecked($i, $true)
  }
  Update-Preview
})

$deselectAllBtn.Add_Click({
  for ($i = 0; $i -lt $sourceList.Items.Count; $i++) {
    $sourceList.SetItemChecked($i, $false)
  }
  Update-Preview
})

$refreshBtn.Add_Click({
  try { Refresh-State }
  catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "刷新失败", "OK", "Error") | Out-Null
    Append-Log "刷新失败: $($_.Exception.Message)"
  }
})

$syncBtn.Add_Click({
  try {
    $checked = Get-CheckedProviders
    $target = $targetCombo.SelectedItem
    if (-not $target) {
      [System.Windows.Forms.MessageBox]::Show("请先选择目标 provider。", "未选择目标", "OK", "Warning") | Out-Null
      return
    }
    if ($checked.Count -eq 0) {
      [System.Windows.Forms.MessageBox]::Show("请至少勾选一个来源 provider。", "未选择来源", "OK", "Warning") | Out-Null
      return
    }

    $total = 0
    foreach ($row in $script:LatestState.provider_counts) {
      if ($checked -contains $row.provider) { $total += [int]$row.count }
    }

    $msg = "即将把 $total 条线程从以下 provider 迁出:`n$($checked -join ', ')`n`n迁入目标: $target`n`n操作前会自动备份。确定继续？"
    if ([System.Windows.Forms.MessageBox]::Show($msg, "确认同步", "OKCancel", "Question") -ne "OK") {
      Append-Log "用户取消了同步。"
      return
    }

    Set-Busy -Busy $true -Message "正在同步，Codex 忙时会自动等待..."
    $sourceCsv = ($checked -join ",")
    $result = Invoke-Backend @("--json", "selective-sync", "--target-provider", $target, "--source-providers", $sourceCsv)
    Append-Log "同步完成！数据库更新 $($result.updated_rows) 条，会话文件更新 $($result.updated_session_files) 个。"
    Append-Log "备份文件: $($result.backup_path)"
    Append-Log "耗时: $(Format-Duration $result.timing.total_ms)"
    Append-Log "同步前归属: $($result.before_counts | ForEach-Object { "$($_.provider)=$($_.count)" } -join ', ')"
    Append-Log "同步后归属: $($result.after_counts | ForEach-Object { "$($_.provider)=$($_.count)" } -join ', ')"
    Append-Log "侧边栏索引已重建: $($result.rewritten_index_entries) 条"
    $script:LatestState = $result.status
    Refresh-State
    [System.Windows.Forms.MessageBox]::Show("同步完成。如侧边栏未刷新，重启 Codex 即可。", "完成", "OK", "Information") | Out-Null
  } catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "同步失败", "OK", "Error") | Out-Null
    Append-Log "同步失败: $($_.Exception.Message)"
  } finally {
    Set-Busy -Busy $false
  }
})

$backupBtn.Add_Click({
  try {
    Set-Busy -Busy $true -Message "正在创建备份..."
    $result = Invoke-Backend @("--json", "backup")
    Append-Log "备份完成: $($result.backup_path)"
    Append-Log "耗时: $(Format-Duration $result.timing.total_ms)"
    Refresh-State
  } catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "备份失败", "OK", "Error") | Out-Null
    Append-Log "备份失败: $($_.Exception.Message)"
  } finally {
    Set-Busy -Busy $false
  }
})

# 启动
try {
  Refresh-State
} catch {
  Append-Log "初始化失败: $($_.Exception.Message)"
  [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "启动失败", "OK", "Error") | Out-Null
}

if ($InstallShortcutOnly) {
  $desktop = [Environment]::GetFolderPath("Desktop")
  $scPath = Join-Path $desktop "Codex 历史选择性同步.lnk"
  $shell = New-Object -ComObject WScript.Shell
  $sc = $shell.CreateShortcut($scPath)
  $sc.TargetPath = (Join-Path $PSHOME "powershell.exe")
  $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -Sta -File `"$script:UiScriptPath`""
  $sc.WorkingDirectory = $script:ToolRoot
  $sc.IconLocation = "C:\Windows\System32\imageres.dll,15"
  $sc.Description = "Codex 历史选择性同步工具"
  $sc.Save()
  Write-Output "桌面快捷方式已创建: $scPath"
  exit 0
}

[void]$form.ShowDialog()
