# ScriptMate MCP · 文案驱动的真实素材匹配

[![CI](https://github.com/zhangyiling108-code/scriptmate/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangyiling108-code/scriptmate/actions/workflows/ci.yml)
[安装与配置教程](docs/mcp.md) · [下载发布包](https://github.com/zhangyiling108-code/scriptmate/releases/latest) · [CLI 中文说明](README.zh-CN.md) · [English](README.en.md)

把短视频文案变成可审核的素材方案包：**文案分段 → 视觉策略 → 搜索真实图片/视频 → 评分与主选/备选 → 审核页和来源链接**。

ScriptMate 提供独立的本地 MCP 服务和 CLI，适用于科普、行业分析、讲解视频的前期素材准备。支持本地 stdio MCP 的客户端可以发现并调用它，无需特定 Agent、Skill 或提示词。使用者提供自己的模型/素材源密钥，配置、缓存和产物保存在自己的电脑上。

## 快速开始

### 1. 安装

先按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/) 安装 uv，再执行以下命令。macOS、Linux 和 Windows PowerShell 均可使用；uv 会准备 Python 3.11 和隔离的依赖环境：

```bash
uv tool install --python 3.11 "copy-material-matcher[mcp] @ https://github.com/zhangyiling108-code/scriptmate/releases/download/v0.2.1/copy_material_matcher-0.2.1-py3-none-any.whl"
```

若提示 `scriptmate` 不在 PATH，执行 `uv tool update-shell`，然后重新打开终端。

### 2. 配置

```bash
scriptmate setup-mcp
```

向导会让你选择完整匹配或仅搜索公开素材，隐藏输入 API Key，配置规划/评分模型、图片核验与素材源，然后自动生成：

- `config.toml`：本机私有配置；POSIX 系统文件权限为 600。
- `mcp-client.json`：可供通用 MCP 客户端使用的真实命令与绝对路径。
- `mcp-codex.toml`：Codex 的 TOML 配置片段。
- 可直接复制执行的 Codex / Claude Code 添加命令。

默认文件位于 `~/.config/scriptmate/`。接入文件不含密钥；已有配置默认保留。需要修改时运行 `scriptmate setup-mcp --reconfigure`，向导会先保存私有备份。

### 3. 检查并接入

```bash
scriptmate check-mcp
```

看到 **“MCP 连接成功：发现 6 个工具”**，表示服务能启动、配置能读取、协议连接正常。这一步不调用模型或素材源 API，也不会消耗其额度。

随后执行向导生成的添加命令，或在客户端的 MCP 设置中填写 `mcp-client.json` 里的 `command` 和 `args`，重新连接后即可使用。[详细客户端接入步骤](docs/mcp.md#连接客户端)

### 4. 第一次使用

可以先对 AI 客户端说：

> 使用 ScriptMate 检查配置，再从 NASA 搜索 3 张 space mission 的 16:9 图片，保留来源链接。

完整匹配示例：

> 使用 ScriptMate 为下面的文案匹配素材，比例 9:16，1080，每段 3 个候选。保留真实来源，不下载、不降级。开始后等待任务完成，再给我审核页路径和未匹配段落。

把文案接在后面即可。完整匹配先返回任务 ID，再通过 `get_result` 查询进度和分页结果，不需要重复启动任务。

## 需要什么

| 使用方式 | 需要准备 |
| --- | --- |
| 仅搜索 NASA / Wikimedia Commons 公开素材 | 本地 stdio MCP 客户端与网络，无需模型密钥 |
| 文案分段、完整素材匹配 | 自己的规划/评分模型 API 密钥和额度 |
| 通用 B-roll 搜索 | 可选 Pexels、Pixabay、Coverr 的素材源密钥 |
| 实际图片核验 | 支持图片输入的评分模型，并在向导中明确启用 |

MCP 是调用入口。配置中的模型 API 费用与聊天客户端的订阅额度分别计算。NASA / Commons 的题材范围有限；具体国家、主体、动作与比较关系仍需要审核。

## 得到什么

`analysis.json`、`manifest.json`、`review.html`、`summary.md`、`segments_overview.csv`、`attributions.md` 和 `segments/<id>/segment.json`。可在本机浏览器打开审核页，查看主选、备选、评分细项、来源与许可。

默认链接优先，不下载完整素材；所有降级默认关闭。没有达到质量门槛的主选保留人工复核状态。视频目前只核对封面，完整动作、可剪辑片段和最终授权仍需人工核对。

## MCP 工具

| 工具 | 作用 |
| --- | --- |
| `doctor` | 配置就绪、模型/素材源和核验范围；不显示密钥 |
| `analyze_script` | 分段和视觉/搜索策略 |
| `search_materials` | 单次真实素材搜索 |
| `match_script` | 启动完整匹配，返回任务 ID |
| `get_result` | 进度、摘要、分页候选和文件路径 |
| `cancel_match` | 取消任务并保留已有文件 |

## 其他安装方式与维护

- [源码安装、手动配置、升级、卸载与排错](docs/mcp.md)
- [仅 CLI 使用](README.zh-CN.md)
- [模型与素材源配置](docs/config.md)
- [视觉核验范围](docs/open-media.md)
- [更新记录](CHANGELOG.md)
- [报告问题](https://github.com/zhangyiling108-code/scriptmate/issues)

开发验证使用 `python -m pip install '.[mcp,dev]'` 和 `python -m pytest tests -q`。基础 CLI 支持 Python 3.9+；MCP 支持 Python 3.10+。测试不消耗真实模型额度，真实账户与素材质量需要分别验证。
