# ScriptMate MCP：独立安装与分享

ScriptMate MCP 将素材匹配引擎提供给支持 **本地 stdio MCP** 的 AI 客户端。它不依赖特定 Agent、Skill、提示词或你的电脑配置。AI 客户端发现工具后即可调用；现有 CLI 仍可单独使用。

每位使用者需要自己的模型密钥。素材源需要的密钥也由使用者提供；默认不共享作者的账户、额度或素材库。MCP 是调用入口，文案规划和评分仍由配置中的模型执行，不会自动使用聊天客户端的模型或订阅额度。

## 安装：推荐 uv

macOS / Linux 安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell 可使用：

```powershell
winget install --id=astral-sh.uv -e
```

安装后重新打开终端，执行 `uv --version`。其他方法见 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)。

从 GitHub 发布包安装固定版本：

```bash
uv tool install --python 3.11 "copy-material-matcher[mcp] @ https://github.com/zhangyiling108-code/scriptmate/releases/download/v0.2.1/copy_material_matcher-0.2.1-py3-none-any.whl"
```

uv 会管理 Python 和依赖，无需手动激活虚拟环境。如果命令不在 PATH，运行 `uv tool update-shell`，重新打开终端。安装方式参照 [uv 工具说明](https://docs.astral.sh/uv/guides/tools/)。

## 配置向导

```bash
scriptmate setup-mcp
```

向导中按实际目标选择：

1. **完整匹配**：需要规划和评分模型密钥。DeepSeek 预设使用 `deepseek-flash`；其他服务选择“OpenAI 兼容”，填写服务端点和账户支持的模型名称。
2. **仅搜索**：跳过模型配置，先体验 NASA / Commons 的素材搜索。无需模型 API 额度，素材源仍受速率和题材范围限制。
3. **评分模型**：可以复用规划服务、模型和密钥，也可以单独配置。
4. **图片核验**：默认关闭。只有确认评分模型支持图片、接受发送缩略图与额外 API 用量后再启用。DeepSeek 图片输入参见[官方视觉文档](https://api-docs.deepseek.com/guides/vision/)。
5. **素材源**：Pexels / Pixabay 密钥可留空跳过；仅启用已配置的来源。完整商业 B-roll 建议补充素材来源，不要期待 NASA 覆盖全部题材。

获取自己的密钥：[DeepSeek 控制台](https://platform.deepseek.com/)、[Pexels API](https://www.pexels.com/api/)、[Pixabay API](https://pixabay.com/api/docs/)。模型权限、价格、授权和额度以自己的账户为准。

默认创建 `~/.config/scriptmate/config.toml`；客户端文件与它放在同一个目录。密钥输入隐藏，不放进接入 JSON、命令或日志；POSIX 新建配置与备份权限为 600。接入文件使用当前安装环境的真实绝对路径，图形客户端不需要依赖终端 PATH。

定制路径：

```bash
scriptmate setup-mcp --config "/path/to/config.toml" --output-root "/path/to/material-results"
```

已有配置默认保留，只重新生成接入文件。需要修改时：

```bash
scriptmate setup-mcp --reconfigure
```

先备份为 `config.toml.<随机编号>.bak`。用户已修改的接入文件不会被直接覆盖，改为输出另一个带编号的文件，请使用本次向导打印的路径。

无交互模式只创建空白模板，不把环境密钥复制到配置中：

```bash
scriptmate setup-mcp --non-interactive --search-only
```

配置完成后运行：

```bash
scriptmate check-mcp
```

这会启动真实 stdio 连接、列出工具并调用 `doctor`，不搜索素材或请求模型。成功会显示工具数量与就绪提示。**“配置已填写”不代表密钥有效或模型权限已验证**；需要真实调用才能验证账号与额度。警告会指出缺少规划/评分密钥、素材源密钥或图片核验设置。

自定义路径的检查需带相同的 `--config`，接入客户端时也使用向导生成的相同路径。

若密钥只在环境变量中，`check-mcp` 会将相关配置变量传给检查进程；接入文件仍不包含其值。图形客户端不一定继承终端环境，需要在客户端中显式注入这些变量，或在向导中把密钥填入私有配置。客户端连接后的 `doctor` 才能反映那个客户端实际可读的配置。

## 安装分享包 / 不使用 uv

需要 Python 3.10 或更新版本、网络和支持 stdio MCP 的客户端。建议使用 Python 3.11/3.12。安装文件中的 `[mcp]` 会安装固定版本的官方 Python MCP SDK。

解压分享包，在解压目录执行：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install './copy_material_matcher-0.2.1-py3-none-any.whl[mcp]'
.venv/bin/scriptmate setup-mcp
.venv/bin/scriptmate-mcp --help
```

Windows 使用 `py -3.11 -m venv .venv`，然后把上述命令中的 `.venv/bin/` 换成 `.venv\Scripts\`，MCP command 指向 `scriptmate-mcp.exe`。

也可以从源码安装：

```bash
git clone https://github.com/zhangyiling108-code/scriptmate.git
cd scriptmate
git checkout v0.2.1
python3.11 -m venv .venv
.venv/bin/python -m pip install '.[mcp]'
.venv/bin/scriptmate setup-mcp
```

在 `config.toml` 中填写 `[planner_model]`、`[judge_model]` 的密钥、模型名称和端点，也可通过 `PLANNER_MODEL_API_KEY`、`JUDGE_MODEL_API_KEY` 或 `DEEPSEEK_API_KEY` 注入。模型名称应以你的供应商和账户支持的能力为准。

示例启用 NASA 与 Wikimedia Commons，无需素材源密钥，但搜索范围有限。通用商业 B-roll 建议自行配置 Pexels、Pixabay 或 Coverr，并将它们加入 `[sources].enabled`。国内/付费扩展源仍按原项目逻辑提供人工搜索入口，不能将配置声明当作已完成自动接入。

示例要求主选具有实际图片核验，且关闭视觉评分。使用前为 judge 配置支持图片的模型，设置 `supports_vision=true` 和 `[judge].vision=true`；否则元数据候选供人工复核，通常不会自动产生主选。视频目前只核对封面，完整动作和可剪辑片段仍需人工确认。

手动使用 `config.mcp.example.toml` 时也可检查配置：

```bash
.venv/bin/scriptmate doctor --config config.toml
```

`doctor` 只检查配置与密钥是否存在，不调用模型或证明密钥有效。自动分析/评分需要模型 API 费用；搜索受素材源的额度、速率和可用性限制。

## 连接客户端

`setup-mcp` 输出本机的接入文件和命令。仓库链接用于下载安装；客户端使用生成的 **command + args** 启动本地服务。

### Codex

执行向导打印的 `codex mcp add scriptmate -- ...` 命令，再用 `codex mcp list` 检查并重新连接。手动配置时，将 `mcp-codex.toml` 片段合并到自己的 Codex 配置中，保留其他设置。服务名已存在时先检查已有条目，避免重复添加。

### Claude Code

执行向导打印的 `claude mcp add --transport stdio --scope user scriptmate -- ...` 命令，再用 `claude mcp get scriptmate` 或会话内 `/mcp` 检查连接。格式参照 [Claude Code 官方 MCP 说明](https://code.claude.com/docs/en/mcp)。

### 通用桌面 MCP 客户端

打开生成的 `mcp-client.json`，在客户端 MCP 管理中添加本地 stdio 服务，填写 command 和 args。如果接受 `mcpServers` JSON，可合并 ScriptMate 条目；不要用单服务文件覆盖已有的整个客户端配置。

向导生成的文件已替换占位路径。完全手动配置时也可使用发布包中的示例：

使用分享包中的 `mcp-client.example.json`，将三个 `/ABSOLUTE/PATH/...` 替换为真实绝对路径，按客户端的 MCP 配置方式添加：

```json
{
  "mcpServers": {
    "scriptmate": {
      "command": "/path/to/ScriptMate/.venv/bin/scriptmate-mcp",
      "args": [
        "--config", "/path/to/ScriptMate/config.toml",
        "--output-root", "/path/to/ScriptMate/results"
      ]
    }
  }
}
```

这是一份常见的 stdio 连接格式，不同客户端的导入入口和配置文件结构可能不同。将 command 与 args 填到对应字段即可。服务由客户端启动，不需要手动运行后台进程；命令直接运行时会等待 stdin 消息，这属于正常状态。

凭据由服务端读取配置，不在工具参数或结果中返回。输出根目录由启动参数控制，每次匹配创建独立 UUID 目录，避免覆盖历史结果。素材库和缓存的相对路径相对于配置文件解析；配置每次启动读取，修改后重启连接生效。默认输出目录是 `~/.local/share/scriptmate/jobs`。

## 可用工具

| 工具 | 输入与结果 | API / 写入行为 |
| --- | --- | --- |
| `doctor` | 查看模型、素材源、视觉核验范围和本机路径 | 无网络调用 |
| `analyze_script` | `text`、`aspect` → 分段与视觉策略 | 调用规划模型、写缓存 |
| `search_materials` | `query`、`aspect`、来源/图片或视频/数量 → 候选与真实链接 | 调用素材源、写缓存；不做语义或画面评分 |
| `match_script` | `text`、`aspect`、可选画质/数量 → `job_id` | 调用规划/评分模型与素材源，写素材方案包 |
| `get_result` | `job_id`、可选分页与等待 → 状态、进度、摘要、候选和文件路径 | 无 API 调用 |
| `cancel_match` | `job_id` → 取消状态 | 停止后续工作，保留已有文件 |

支持比例 `9:16`、`16:9`、`4:3`、`3:4`、`1:1`，画质 `720`、`1080`、`4K`。文案最长 20000 字符；搜索 query 最长 500 字符；top 为 1–20，完整匹配至少保留 3 条候选，真实素材不足时不会编造候选凑数。

完整匹配直接包含分析。仅需要完整结果时，无需先调用 `analyze_script` 再重复匹配。下载和所有 fallback 默认关闭，只在使用者明确要求时开启。

`match_script` 立即返回任务 ID；随后调用：

```json
{"job_id": "返回的32位ID", "wait_seconds": 20}
```

`get_result` 的默认 `limit=0` 只返回摘要和文件入口。读取候选时使用 `offset=0, limit=5`，再按 `next_offset` 翻页；最多每页 20 段，等待最长 30 秒。进度记录已处理段落数；规划完成前总段数为 null。状态为 `running`、`completed`、`failed`、`cancelled` 或 `interrupted`。

每个服务进程一次执行一个完整匹配。查询状态不会重跑任务，不要用重复 `match_script` 检查进度。取消不能退回已经消耗的模型/素材源额度。服务正常退出会取消未完成匹配；意外退出后保留部分文件，重启读取会报告 `interrupted`，不会自动重试付费调用。

## 输出与人工审核

完成任务返回本机文件路径，包括 `analysis.json`、`manifest.json`、`summary.md`、`review.html`、`segments_overview.csv`、`attributions.md` 和 `segments/<id>/segment.json`。客户端可以读取其可访问的文件；在浏览器打开 `review.html` 审核缩略图与来源。MCP 不保证所有客户端自动显示本机 HTML 或视频。

默认提供来源链接，完整视频、叙事主体/地理/事实关系、授权和最终剪辑选择仍需要人工核对。本版不包含自动成片、配音、公开云服务、托管密钥或计费系统。

## 开发与验证

```bash
.venv/bin/python -m pip install '.[mcp,dev]'
make test
```

基础 CLI 保持 Python 3.9 兼容，未安装 MCP 时会跳过协议测试。MCP 验证需 Python 3.10+ 和 `[mcp]` 依赖；测试覆盖真实 stdio 握手、工具 schema、任务状态/取消/失败、重启读取、分页、来源链接和输出文件。模拟的模型/素材源调用不代表真实账户验证。

## 常见问题

| 现象 | 处理方法 |
| --- | --- |
| `scriptmate` 找不到 | uv 安装后运行 `uv tool update-shell` 并重开终端；虚拟环境安装则使用该环境命令 |
| Python 版本低或缺少 MCP | 用 uv 命令安装，或用 Python 3.10+ 安装 `[mcp]` 依赖 |
| 配置不存在 / TOML 无法读取 | 运行 `setup-mcp`；修正格式后重跑 `check-mcp`，不要将密钥或整个私有配置贴到 Issue |
| MCP 已连接，但完整匹配不可用 | 根据提示补规划/评分密钥与素材源；连接成功不会自动获得模型权限 |
| 有候选，主选为空 | 检查质量门槛与 `judge.vision`；无实际图片证据时保留人工复核，不自动放宽 |
| 模型 401 / 403 / 余额或速率错误 | 核对密钥、账户权限、端点、余额与供应商限制；客户端订阅不会支付工具内部 API 调用 |
| 直接运行 MCP 命令没有界面 | 服务等待 stdio 消息；用 `check-mcp` 诊断，通过客户端调用工具 |
| 找不到审核页 | `get_result` 返回本机路径；在运行服务的电脑上打开 `review.html` |
| 更新后接入失效 | 重跑 `setup-mcp`，更新客户端中的当前环境路径后重连 |

## 升级与卸载

更新到本教程对应版本时重新执行安装命令；从旧版替换安装可添加 `--force`，之后重跑 `setup-mcp` 和 `check-mcp`。配置和素材方案包在安装环境外，默认保留；升级不会自动重试历史付费任务。

```bash
uv tool uninstall copy-material-matcher
```

卸载不会删除自己的配置与素材结果。需要停止调用时，在客户端中移除 ScriptMate 条目。
