# Codex History Sync Tool (增强版)

> 基于 [GODGOD126/codex-history-sync-tool](https://github.com/GODGOD126/codex-history-sync-tool) 二次开发，新增**选择性同步**与**中文图形界面**，并支持**一键打包为 EXE**。

## 这是什么？

Codex Desktop 的本地聊天历史偶尔会出现"文件明明在，但侧边栏不显示"的情况——通常发生在切换 API、provider、模型或登录方式之后。

原版工具只能**全量同步**所有线程到当前 provider。本增强版支持：

- **选择性同步**：勾选要从哪些 provider 迁出，选择迁到哪个 provider
- **中文 tkinter 图形界面**：无需命令行，双击即可操作
- **单文件 EXE**：不需要安装 Python，直接运行

## 与原版的区别

| 功能 | 原版 | 本增强版 |
|------|------|----------|
| 全量同步 | ✅ | ✅ |
| 选择性同步（指定来源→目标） | ❌ | ✅ |
| 中文 GUI | ❌ | ✅ |
| EXE 打包 | ❌ | ✅ |
| Web UI | ❌ | ✅ (实验性) |
| 备份恢复 | ✅ | ✅ |
| 侧边栏索引重建 | ✅ | ✅ |

## 下载使用

从 [Releases](../../releases) 页面下载 CodexSyncTool.exe，双击运行即可。

> **注意**：首次运行时如果 Codex Desktop 正在运行，工具会自动等待数据库空闲后再操作，不会损坏数据。

## 功能说明

### 主界面

1. 打开后自动加载当前状态——显示每个 provider 下有多少条历史线程
2. 勾选要迁出的来源 provider（当前使用的 provider 默认不勾选）
3. 选择目标 provider
4. 预览区域会显示将迁移多少条线程
5. 点击「执行同步」——自动备份 → 更新数据库 → 更新会话文件 → 重建侧边栏索引

### CLI 命令

`ash
# 查看状态
python sync_backend.py status

# 全量同步（同原版）
python sync_backend.py sync

# 选择性同步
python sync_backend.py selective-sync --target-provider openai --source-providers deepseek,myproxy

# 手动备份
python sync_backend.py backup

# 恢复备份
python sync_backend.py restore --backup <路径>
`

## 从源码构建 EXE

需要 Python 3.11+（**完整安装版**，非 embeddable）：

`ash
pip install pyinstaller
pyinstaller --onefile --windowed --name CodexSyncTool --add-data "sync_backend.py;." sync_ui.py
`

构建产物在 dist/CodexSyncTool.exe。

## 项目结构

`
├── sync_backend.py      # 核心逻辑：数据库读写、会话同步、索引重建
├── sync_ui.py           # tkinter 中文图形界面
├── sync_web_ui.py       # Web 界面（实验性，浏览器中操作）
├── launch_ui.ps1        # PowerShell 启动脚本
├── launch_ui_selective.ps1  # 选择性同步启动脚本
└── tests/               # 单元测试
`

## 技术细节

- 操作前自动备份 state_5.sqlite 到 .codex/history_sync_backups/
- 更新数据库中的 model_provider 和 model 字段
- 同步更新每个会话 JSONL 文件的第一行元数据
- 重建侧边栏索引 session_index.jsonl
- 使用 WAL 模式等待锁，避免与运行中的 Codex Desktop 冲突

## 致谢

- 原版作者 [GODGOD126](https://github.com/GODGOD126) 提供了数据库读写、会话同步、索引重建的核心逻辑
- 增强功能：选择性同步、中文 GUI、EXE 打包

## 许可

MIT License — 详见 [LICENSE](LICENSE)