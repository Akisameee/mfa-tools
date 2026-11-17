# Message From Aliens 工作区

[English](README.md) | [简体中文](README.zh-CN.md)

本目录包含 MCP 项目、游戏相关文档，以及本地使用的调查资料。

| 路径 | 内容 |
| --- | --- |
| [中文指令](instruction.zh-CN.md) / [English instructions](instruction.md) | 供智能体开始游玩使用的无剧透指令。 |
| [message-from-aliens-mcp/](message-from-aliens-mcp/README.zh-CN.md) | MCP 源码、测试、包元数据、说明文档、许可证、开发环境及构建产物。 |
| [replay-player/](replay-player/README.zh-CN.md) | 无前端框架的本地回放播放器、浏览器录制、资源准备及标注评分。 |
| [message-from-aliens-mcp/docs/](message-from-aliens-mcp/docs/) | MCP 运行时说明与发布检查。 |
| `artifacts/` | 可选的本地调查资料、诊断文件和生成的预览；不纳入 Git。 |

游戏文档和其他工作区资料可与 MCP 项目并列存放。私有产物已加入忽略列表，不会随包发布。

## 开发 MCP 服务

在项目目录执行开发和发布命令：

```powershell
Set-Location .\message-from-aliens-mcp
uv sync
uv run python -B -m unittest discover -s tests -q
uv run message-from-aliens-mcp --help
uv build --no-sources
```

用户配置参见 [MCP README](message-from-aliens-mcp/README.zh-CN.md)，发布流程参见
[发布检查](message-from-aliens-mcp/docs/releasing.md)。

本地 Codex 直接启动项目 `.venv` 中的 Python，并将 `PYTHONPATH` 指向
`message-from-aliens-mcp/src/`。修改源码后需重新连接 MCP 服务。

可选的 [MCP probe](message-from-aliens-mcp/docs/recording.md) 会记录工具事件和游戏原始网格状态，
供后续回放使用。录制默认关闭。

## 本地产物

`recordings/`、`artifacts/`、播放器生成的数据、导出视频和本地 API 配置均不纳入 Git，
也不包含在本仓库中。已有的本地 `artifacts/` 目录可能包含独立的资料索引。
