# Message From Aliens MCP

[English](README.md) | [简体中文](README.zh-CN.md)

为 **Message From Aliens（外星来信）** 提供的 MCP 服务。这是一款破译象形外星语言的游戏。
模型可通过此服务读取当前页面、查看字形、点击字符和保存标注。

读取、点击和标注均可在后台进行，不会移动系统鼠标或激活游戏窗口。
启动游戏时，Steam 或新建的游戏窗口可能会显示到前台。

## 运行要求

- Windows x64；不支持 Linux 和 macOS。
- 已安装 [Steam 上的 Message From Aliens](https://store.steampowered.com/app/1858720/)，
  且 Steam 可用并已登录。
- 推荐使用 [uv](https://docs.astral.sh/uv/getting-started/installation/)，
  MCP 客户端需支持本地 stdio 服务。
- Python 3.10 或以上版本；必要时 uv 可自动准备兼容的解释器。
- 服务与游戏需使用相同的 Windows 用户和权限级别运行。
- 截图模式需要 Windows.Graphics.Capture 支持，游戏窗口须已显示且未最小化。
  图片结果需要 MCP 客户端和模型支持图片内容；表格、ASCII 字符画及路径结果均为纯文本。

服务会自动选择 Mono 或 IL2CPP 运行时绑定。已验证的当前 Windows x64 Mono 版本为
Steam 构建 `26564542`，使用 Unity `6000.6.8f1`。早期 IL2CPP 集成已在
Unity `6000.6.6f1` 上验证，其适配器仍然保留。游戏更新后可能需要调整集成代码。

## 配置

包发布到 PyPI 后，在 MCP 客户端中添加以下 stdio 服务配置：

```json
{
  "mcpServers": {
    "message-from-aliens": {
      "command": "uvx",
      "args": ["message-from-aliens-mcp"]
    }
  }
}
```

修改配置后，重启客户端或重新连接 MCP 服务。如果找不到 `uvx`，请将 `command`
改为 `uvx.exe` 的绝对路径。

uvx 会按需将包及依赖安装到隔离环境，无需另行执行 `pip install`。
如需固定到某个已发布版本，可使用 `"args": ["message-from-aliens-mcp==0.1.6"]`。

发布前，可在源码目录试运行：

```powershell
uv run message-from-aliens-mcp --help
```

发布后也可持久安装：

```powershell
uv tool install message-from-aliens-mcp
```

兼容命令别名 `aliens-mcp` 仍然可用。

## 工具

所有网格坐标从零开始：行号 `0..8` 从上到下，列号 `0..23` 从左到右。

| 工具 | 用途 |
| --- | --- |
| `launch_game()` | 通过 Steam 启动游戏，或连接已有的游戏实例。 |
| `look(type="table", force=False)` | 读取当前 9×24 网格，包含标注和布局标记。 |
| `look(type="screenshot", force=False)` | 获取游戏窗口的 PNG 截图，附带像素尺寸和窗口样式信息。 |
| `click(row, col, type="left")` | 使用左键或右键点击任意格子（包括空白），返回目标和结果。 |
| `note(hash, text)` | 为字符的所有出现位置保存标注；字符无需出现在当前页面。 |
| `wait(seconds)` | 在支持的页面推进游戏时间，执行正常的时间更新并保存结果。 |
| `glyph(hash, format="image")` | 以 PNG、ASCII 字符画或坐标路径查看字形。 |

### 读取和识别字符

表格单元使用 `hash:annotation` 格式，例如 `abcd:我的标注`。hash 由四位小写字母或数字组成。
同一连接期间，同一字符在不同页面保持相同 hash。重新连接或重启游戏后，需再次调用 `look`
获取当前 hash。

表格保留分隔线，并使用 `\underline{...}` 标记下划线、`\hl{...}` 标记高亮、
`\dim{...}` 标记暗色文字，`[...]` 标记边框。边框反映可见的矩形轮廓，而非内部交互槽位。
跨行卡牌保留整体分组：首行使用 `┌...┐`，中间行使用 `│...│`，末行使用 `└...┘`。
空格也会保留相同的边框。每个格子的点击坐标保持不变。
标注取自游戏实时显示的文字，也包括开启相应设置后出现的数字和单位自动翻译。

下划线取自游戏当前 LineRenderer 的几何数据；暗色文字由各字形渲染器的颜色和当前配色判断。
这些都是运行时渲染状态，不根据菜单解锁条件或隐藏条目推断样式。
矩形轮廓来自具有五个顶点的闭合 LineRenderer，并通过字形位置映射到网格，包含空白格子。
点击目标的标签使用同一份状态与边框信息。

表格和截图各有独立的内存缓存。每次调用都会读取当前状态；如果结果完全一致，
只返回简短的未变化提示，不重复输出内容。使用 `force=True` 可强制返回完整结果。

截图只捕获游戏窗口；有窗口边框时也会一并捕获。窗口被其他窗口遮挡时仍可截图，
无需激活或调整尺寸。`click` 使用表格坐标。

### 点击和标注

从当前表格选择坐标。`click` 接受 `type="left"` 或 `type="right"`，
并以与 `look` 相同的格式报告目标。交互后调用 `look` 查看新页面。
空白格子（包括空答案框）也可点击，返回 `blank` 或 `[blank]`，不会虚构字符 hash。
已验证窗口未获得焦点时的后台点击；未单独验证最小化窗口的点击。

如果点击请求打开外部链接，服务会返回目标 URL，并阻止本次点击打开浏览器。
如果游戏关闭，结果会指引模型调用 `launch_game()`；MCP 服务本身仍然可用。

`note(hash, text)` 接受来自 `look` 的 hash，更新该字符在所有页面的标注，
并通过游戏原有的标注处理流程保存。字符无需仍在当前页面。
文字须为单行，长度不超过 49 个 UTF-16 单位。空字符串会清除标注。
成功结果包含 `ok`、`hash` 和 `text`。

### 推进游戏时间

在支持的页面，`wait(seconds)` 无需实际等待即可推进游戏时间。
例如 `wait(60)` 可跳过一分钟现实等待时间。单次接受 0.001 至 86400 秒，
四舍五入到毫秒。游戏会执行正常的时间更新、刷新页面并保存结果。

在不支持的页面调用会返回错误，不会修改系统时间。

### 字形

`glyph` 接受当前 `look` 提供的 hash，只返回所选的一种格式：

- `"image"`（默认）：根据游戏矢量几何数据绘制固定 64×64 PNG，
  白底、两像素宽黑色线条，带抗锯齿。不包含截图或 DPI 元数据。
- `"ascii"`：使用空格和 `#` 绘制自适应字符画，至少 10×10，
  上限为 121 行、241 列。应以等宽字体显示；达到尺寸上限后，过近的线条可能黏连。
- `"paths"`：按比例缩放到 100×100 坐标范围内的 JSON 折线。
  原点在左上角，x 向右增加，y 向下增加。只连接同一路径内的相邻点。
  首尾点相同表示闭合路径，单点表示一个点。这些是绘制路径，不是书写笔顺。

字形和表格均不暴露游戏内部词条 key 或含义。

## 备份、清空与恢复存档

以下步骤适用于开始全新游玩或准备模型测试。操作会影响游戏数据目录内所有槽位及
Steam 账号子目录中的本地标注、答案、完成记录、书签和其他进度。
Steam 成就单独管理。

### 修改存档前

1. 在 MCP 客户端中断开或禁用本服务，然后退出游戏。
   在任务管理器中确认 `MessageFromAliens.exe` 已停止运行。
   运行中的游戏可能将内存进度重新写回，覆盖文件修改。
2. 在 Steam 库中右键游戏，打开 **属性 > 通用**，关闭此游戏的 Steam 云同步。
   重置和验证期间保持关闭，避免云端副本覆盖本地测试存档。
   参见 [Steam 云说明](https://help.steampowered.com/en/faqs/view/68D2-35AB-09A9-7678)。
3. 按 **Win+R**，打开：

   ```text
   %USERPROFILE%\AppData\LocalLow\Artless Games
   ```

游戏数据文件夹名为 `MessageFromAliens`。其中可能同时存在旧版根目录存档和
数字 Steam ID 子目录内的新版存档：

```text
MessageFromAliens/
├── alienmessage1.sav
├── alienmessage2.sav
├── alienmessage3.sav
├── alienmessage1.sav<version>.backup
├── setting.sav
└── <SteamID>/
    ├── alienmessage1.sav
    └── setting.sav
```

具体文件取决于游戏版本和使用过的槽位。请备份整个目录，包括账号子目录和版本备份；
只复制根目录的 `alienmessage1.sav` 可能漏掉实际使用的存档。

### 创建备份

将整个 `MessageFromAliens` 文件夹复制到游戏数据目录之外、以日期命名的位置，例如：

```text
%USERPROFILE%\MessageFromAliens-backups\<timestamp>\MessageFromAliens
```

等待复制完成，并检查文件及子目录是否齐全。后续创建测试备份时保留这份原始备份。
存档经过加密，请保留原始文件，不要作为文本编辑。

### 清空进度

如果使用源码仓库或源码分发包，先关闭游戏、禁用 Steam 云同步，再运行独立的
PowerShell 辅助脚本。脚本会保留所有 `setting.sav`，将各槽位和账号的进度文件
（含迁移备份）移到 Windows 回收站。不额外创建备份，也不启动游戏：

```powershell
# 预览具体文件，不做修改：
.\scripts\reset-save.ps1 -WhatIf

# 清空进度：
.\scripts\reset-save.ps1
```

若 `MessageFromAliens.exe` 仍在运行，或存档路径包含符号链接、目录联接，脚本会拒绝操作。
可选参数 `-SaveDirectory` 必须指向 `Artless Games` 内名为 `MessageFromAliens` 的目录。
脚本不会修改 Steam 云同步设置，也不会重置 Steam 成就。如需手动归档后重置，请使用以下步骤。

完成备份、关闭游戏并禁用 Steam 云同步后：

1. 在 `Artless Games` 下，将已有的 `MessageFromAliens` 文件夹重命名为
   `MessageFromAliens.before-reset-<timestamp>`。放在原位置旁边，不要放进新的游戏数据目录。
   这样可一并归档所有旧槽位及迁移备份。
2. 如需同时重置**进度与设置**，保持原目录名不存在。
   如需**保留设置**，新建空的 `MessageFromAliens` 文件夹，只从备份复制 `setting.sav`，
   保持相对路径，包括 `<SteamID>/setting.sav`。这样会保留显示、配色和翻译偏好。
   不要把进度文件复制到新目录。
3. 通过 Steam 启动游戏，或重新连接 MCP 并调用 `launch_game()`。
   游戏会在正常的数据目录内创建全新进度。
4. 调用 `look(force=True)`，确认旧标注已消失，并可进入初始页面。
   未标注字符通常显示为 `?`。保留设置时，数字和单位的自动翻译仍可能出现；
   如测试不需要翻译提示，请在游戏中关闭这些选项。

只移动某一个存档文件，可能留下其他槽位、账号副本或可迁移的旧版存档。
归档整个文件夹可避免这些副本残留在当前数据目录。
隔离测试期间保持 Steam 云同步关闭；关闭期间，本地文件不会备份到 Steam。

### 恢复原有进度

1. 断开 MCP 服务、关闭游戏，并保持 Steam 云同步关闭。
2. 将当前 `MessageFromAliens` 文件夹重命名为
   `MessageFromAliens.before-restore-<timestamp>`，把测试进度也保留在当前数据目录之外。
3. 将备份的整个 `MessageFromAliens` 文件夹复制回 `Artless Games`，保持目录名完全一致。
   请恢复完整目录，不要与测试存档合并，否则可能残留较新的账号或槽位文件。
4. 启动游戏并重新连接 MCP。调用 `look(force=True)` 检查恢复后的标注和进度，重新读取当前 hash。

之后若重新开启 Steam 云同步，请先确认希望同步哪份存档。
如果 Steam 提示冲突，选择包含所需进度的副本；旧云端存档可能与重置或恢复后的本地存档不同。

## 常见问题

| 问题 | 处理方法 |
| --- | --- |
| 游戏未运行 | 调用 `launch_game()`；其他工具不会自动启动游戏。 |
| 启动超时 | 确认 Steam 已登录且游戏可正常启动，再重试。 |
| 服务无法附加到游戏 | 检查两个进程的 Windows 用户和权限级别。 |
| 最小化时截图失败 | 恢复游戏窗口；可继续被其他窗口遮挡。 |
| 客户端不显示图片 | 使用表格模式，以及 `glyph(format="ascii")` 或 `glyph(format="paths")`。 |
| 重连后 hash 无效 | 使用 `look` 读取新表格。 |
| Frida 无法写入临时文件 | 在服务环境中将 `ALIENS_MCP_TMP` 设置为可写目录。 |

## 开发

可选的本地工具与网格录制功能参见 [MCP probe 录制](docs/recording.md)。
默认关闭，不捕获截图或字形资源。

在源码目录运行：

```powershell
uv sync
uv run python -B -m unittest discover -s tests -v
uv run message-from-aliens-mcp --status
uv run message-from-aliens-mcp --look
```

不带 CLI 参数时，命令通过 stdio 提供 MCP 服务。`--status` 检查游戏连接和检测到的运行时；
`--look` 输出当前表格，`--look --json` 输出 JSON。
`--look --raw` 会暴露开发用的内部词条 key，可能剧透谜题。

模块职责以及修改游戏操作、工具描述和提示文本的位置参见 [架构说明](docs/architecture.md)；
实现细节参见 [运行时说明](docs/runtime.md)；兼容性测试与发布流程参见 [发布检查](docs/releasing.md)。

## 许可证

MIT，参见 [LICENSE](LICENSE)。这是非官方集成，不分发游戏资源、反编译代码、存档或玩家标注文件。
服务使用 Frida 对运行中的游戏进行动态插桩，不修改游戏文件。
