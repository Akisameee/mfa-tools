# 本地回放播放器

[English](README.md) | [简体中文](README.zh-CN.md)

本地使用的 HTML/CSS/JavaScript 播放器，无前端框架，也无需构建。
原始录制只读；生成的数据、评分和导出视频均保存在本地。

## 目录结构

```text
src/
  app.mjs           应用组装与画面更新调度
  core/             事件状态、时间映射、帧时钟、呈现逻辑
  render/           游戏画面、工具历史虚拟列表、进度、控制栏
  recording/        Chrome 捕获与 CLI 实现
  style.css         布局、字体、颜色、方块尺寸
recording-plan.json  rec 倍速配置
index.html          播放器页面结构
serve.py            本地服务公开入口
prepare.py          数据准备公开入口
record-browser.mjs  录制公开入口

tools/              数据准备与性能基准工具
tests/              单元测试与浏览器检查
grading/            独立标注评分，参见其 README
legacy/             旧版截图导出器和 HyperFrames 导出器

data/, exports/     已忽略的本地数据和输出
```

## 打开播放器

在工作区根目录运行：

```powershell
.\message-from-aliens-mcp\.venv\Scripts\python.exe .\replay-player\serve.py
```

打开 <http://127.0.0.1:8765/>。播放控制和 `rec` 配置位于计时栏。
如果已有 `data/replay.json`，无需重新准备数据。

## 使用 Chrome 录制

首次使用时安装依赖：

```powershell
$env:PUPPETEER_SKIP_DOWNLOAD = "true"
npm --prefix .\replay-player ci
uv run --isolated --no-project --with imageio-ffmpeg python -c "import imageio_ffmpeg"
```

录制五分钟预览：

```powershell
node .\replay-player\record-browser.mjs --seconds 300 --output exports/browser-preview-5m.mp4
```

省略 `--seconds` 即录制全程。在终端按 Enter 可停止并保存。
命令会自行启动本地服务和隔离的 Chrome，无需提前运行普通播放器服务。
使用 `getDisplayMedia` + `MediaRecorder`，只捕获播放器标签页，
不逐帧截图，也不将页面改写为 Canvas。录制使用已有的 `rec` 倍速配置。

默认参数：1920×1080、请求 60 FPS、1707px CSS 布局、16 Mbps H.264 MP4。
可用 `--width`、`--height`、`--fps`、`--layout-width`、`--bitrate` 覆盖。
`--start 658.85 --seconds 15` 按输出视频时间截取，不是画面中显示的原始游玩时间。
输出路径相对于 `replay-player`；如果目标文件或录制中的临时文件已存在，命令会拒绝覆盖。

录制耗时约为实际播放时长加启动和收尾时间。播放器暂停时会先预热捕获与编码器，
结束时由 FFmpeg 直接复制编码流，移除预热片段，不重新编码。
数据块持续写入 `.partial.mp4`，成功完成后删除该临时文件。
录制元信息作为 JSON 保存在视频旁。可通过 `CHROME_PATH` 和 `FFMPEG_PATH` 指定可执行文件。

Chrome 可能输出可变帧率视频。JSON 的 `rendering` 字段记录源页面的渲染时序。
加上 `--diagnostics` 还会采样原始捕获帧的时间戳，以区分渲染延迟、捕获丢帧和编码文件中的帧间隔。
捕获诊断不会绘制或保存原始图像，只计数并关闭帧。

## 播放架构

实时时钟以累计时间锚点为基准，通过 `requestAnimationFrame` 采样，内容更新每秒最多 60 次。
错过显示帧不会堆积过时的定时器消息，也不会改变工具动画时长或选定的倍速配置。
只应用当前事件范围内的变化；游戏画面保留静态层和特效层。

文字方块只更新发生变化的标注 key，完成进度方块只在进度变化时更新。
历史工具调用完整保留在数据模型中，每个展开分组最多挂载 64 行；向上滚动时重建更早的行及其录制结果。
长历史不会持续累积数千个预览画布。DOM 滚动尺寸集中读取，游戏画面尺寸通过 ResizeObserver 缓存。

即使页面渲染流畅，Chrome 捕获仍可能丢帧。性能基准和录制诊断分别测量这两部分。
实时录制不提供逐帧精确的离线渲染。

## 准备数据与评分

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python .\replay-player\prepare.py
```

准备脚本优先选择直接写入录制根目录的日志，旧版子目录作为兼容回退。
可用 `--recording`、`--conversation`、`--assets` 指定输入。
不重放游戏操作，不修改原始日志或存档。只导入公开消息，不导入隐藏推理。

参见 [播放与数据行为](docs/playback.md) 和 [评分说明](grading/README.zh-CN.md)。

## 外观

下方进度区保持自然高度。游戏画面使用剩余高度，按 16:9 计算左栏宽度，右侧对话占据剩余宽度。
尺寸只在窗口变化时测量，不在播放的每一帧中测量。
如果窗口太小，容纳不下固定尺寸的进度方块，则保留原有布局，避免溢出。

可编辑 [src/style.css](src/style.css) 中的 `#progress --tile-size`（当前 8px）、
`--tile-gap`、`--divider-space`、字号和状态颜色；保留了现有视觉设置。
鼠标和输入动画时长位于 [src/core/motion.mjs](src/core/motion.mjs)，
时间映射位于 [src/core/tempo.mjs](src/core/tempo.mjs)。
`rec` 倍速配置位于 [recording-plan.json](recording-plan.json)。

## 检查

运行浏览器检查和性能基准前，先启动 `serve.py`：

```powershell
npm --prefix .\replay-player test
node .\replay-player\tests\browser.mjs
.\message-from-aliens-mcp\.venv\Scripts\python.exe -m unittest discover -s replay-player/tests -p "test_*.py"
node .\replay-player\tools\benchmark-player.mjs --output artifacts/player-refactor/local.json
```

性能基准采样游玩初期、需要等待的小游戏、后期字典修改和包含 150 个格子的页面，
记录更新间隔、长任务、DOM 数量，以及浏览器布局和脚本耗时。
对比时应使用相同视口和机器负载。
浏览器检查覆盖历史列表大小限制、历史详情、进度、标注、消息动画、跳转、控制栏和兼容导出 API。

## 历史实验

串行导出器位于 `legacy/export_video.py`，HyperFrames 导出器位于 `legacy/export-hyperframes.mjs`。
播放器仍支持它们使用的公开 API，但这些基于截图的方式已与正常播放和录制隔离，
仅保留作对比，不会自动启用。
