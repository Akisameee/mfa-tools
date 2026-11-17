# 录制笔记自动评分

[English](README.md) | [简体中文](README.zh-CN.md)

离线脚本，使用兼容 Chat Completions 的 API。只在录制下新增 `grading/` 文件；
原有 `events.jsonl`、`manifest.json`、`states/` 不改写。
需要 Python 3.11 或以上版本。

## 配置

首次使用先复制本目录的 `config.example.toml` 为 `config.toml`，再编辑 **`config.toml`**：

```toml
base_url = "https://你的服务地址/v1"
model = "你的模型名"
api_key_env = "GRADING_API_KEY"
api_key = ""
batch_size = 12
concurrency = 2
timeout_seconds = 120
retry_attempts = 3
json_mode = true

[request]
```

在运行脚本的 PowerShell 窗口设置密钥：

```powershell
$env:GRADING_API_KEY = "你的 API Key"
```

也可以直接把密钥写在本地 `config.toml` 的 `api_key` 中。环境变量优先；
本地配置已加入忽略列表，示例 `config.example.toml` 不应放真实密钥。
`GRADING_BASE_URL`、`GRADING_MODEL` 环境变量也能覆盖文件中的设置。

Base URL 填服务商提供的兼容地址；脚本追加 `/chat/completions`。
如果填写的已经是完整 `/chat/completions` 地址，就直接使用。
密钥不会写入评分、元信息或请求统计。

API 使用标准库 HTTP 客户端，不需要安装 SDK。JSON 输出参数依据
[Chat Completions 接口](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
和 [JSON 模式](https://api-docs.deepseek.com/guides/json_mode/)；不支持该参数的服务可以设
`json_mode = false`，返回内容仍须符合 JSON 格式，脚本会严格校验。
模型特有参数可以放在 `[request]` 下，例如服务支持的 `max_tokens` 或
`max_completion_tokens`，不要同时填写两者。不默认添加 temperature 等参数。

## 运行

以下命令均在工作区根目录运行。`uv` 为提取资料提供 UnityPy 和 PyCryptodome。

先只提取资料，**不调用 API**：

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/grading/evaluate.py --prepare-only
```

先评分 20 个未缓存组合，检查尺度：

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/grading/evaluate.py --limit 20
```

评分全部剩余组合：

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/grading/evaluate.py
```

默认处理 `replay-player/data/replay.json` 当前指向的录制。
用 `--recording recordings` 选择直接写入根目录的新录制，
也可用 `--recording recordings/旧录制ID` 选择以前的录制。
没有播放数据时优先读取根目录的非空日志，再兼容旧录制目录。
`--assets` 修改游戏资源路径，`--config` 指定其他配置文件。

重复运行会续跑：已成功评分的相同组合不会重复请求。修改模型、Base URL、请求参数、
提示词或参考资料会使用新的缓存上下文。接口错误不会变成红色评分；日志写入
`errors.jsonl`，下次继续尝试。模型无法确定的项目保存为 `unresolved`，
用 `--retry-unresolved` 重试，或先人工检查理由。

## 结果

```text
recordings/grading/
  reference.json   # 内部英文名、完整字典定义、词性、部件、原始数字/单位记号
  items.json       # 去重后的待评组合及对应参考资料，可供抽查
  scores.jsonl     # 评分与简短理由，保留历次模型/规则结果
  metadata.json   # 当前模型、规则指纹、资源指纹、数量；不含密钥
  requests.jsonl  # 请求对应条目 ID 与接口返回的 token 用量
  errors.jsonl    # 失败请求；只有出现错误时才创建
```

`--prepare-only` 只生成前两个文件，不改变现有评分上下文。标准答案来自游戏
`newalien` 词表：保留 `word` 英文名、`meaning` 原文，并按游戏词条说明的结构补上
词性、部件信息。字典是作者的符号化英文句子，不先自动翻译成中文。部件说明只解释
构字，不替代词义。数字键如 `4e1` 的确切值为 `4×7=28`，参考资料明确记录进制，
原始定义中的数字/单位记号保留原样。

评分对象只来自成功 `note` 调用的 `arguments.text`。字符由该次返回的 `character.key`
对应，不从快照、look 或游戏显示文本提取标注。失败写入、清空和只有 `?` 的输入不请求
评分。不需要解析或剥离游戏自动标注；输入中的括号、数字和单位都是玩家原文，完整保留。

`prompt.md` 是可编辑的评分规则：绿=正确，黄=接近/不完整，红=错误。
问号本身不降级；准确的常用含义不必列出所有用法。缺少可靠依据保留待评分。

## 播放器

运行结束或中断后，已保存的结果会自动写入**匹配这段录制**的
`replay-player/data/grading.json`。这是评分的播放副本，含评分、理由及游戏英文词条和
字典参考资料；播放器单独读取它，评分更新不再重写大型 `replay.json`。
刷新即可看到方块、表头三色进度条和标注底色一起更新。
未评分的已标注字符用空心方块显示；悬停显示当时的译文、游戏参考释义、字典原文和评分理由。回放按当时最近一次成功
note 的原始输入查分；游戏显示里额外追加的数字不参与评分，不把后来的译文倒灌到旧画面。

重新生成播放数据时，`prepare.py` 也会自动带入评分。资源指纹不一致时忽略旧评分。
原始参考资料保留在录制目录，播放器需要的参考词条复制到 `data/grading.json`。

只把已有评分重新接入当前播放器：

```powershell
python replay-player/grading/evaluate.py --attach-only
```

评分其他录制不会覆盖当前播放器。要播放它，运行：

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/prepare.py --recording recordings
```

## 本地验证

下面使用临时录制和本机 HTTP 模拟接口，不使用真实密钥，不产生外部 API 请求：

```powershell
python -m unittest discover -s replay-player/grading -t replay-player -p test_grading.py -v
node replay-player/tests/test-timeline.mjs
```
