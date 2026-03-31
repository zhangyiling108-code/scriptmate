# ScriptMate CLI

[English](README.md) | **简体中文**

ScriptMate 是一个面向短视频工作流的“文案驱动高质量素材匹配引擎”。

它不试图替代剪辑软件，而是先把“找对素材”这件事做好：把一段文案变成结构化的素材方案包，让后续在任意剪辑工具里更容易完成剪辑。

## 它能做什么

- 将文案拆成语义段落
- 判断每段更适合什么视觉表达
- 根据段落上下文搜索真实素材
- 保持国家、叙事对象、比较关系一致
- 每段尽量给出至少 3 条真实候选素材
- 默认不降级，除非用户显式允许
- 默认优先给素材链接，而不是先把下载拖慢

## 输出内容

一次运行通常会得到：

- `analysis.json`：文案分段、角色、视觉策略
- `manifest.json`：主选、备选、评分、来源和链接
- `summary.md`：人工可读的匹配报告
- `segments_overview.csv`：适合批量筛选的总表
- `segments/<id>/`：每段的详细元数据和素材记录

## 快速开始

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
.venv/bin/scriptmate --help
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate match --file sample.txt -o ./output
```

为了避免系统 PATH 中旧版本命令干扰，推荐优先使用 `.venv/bin/scriptmate`，或者先激活虚拟环境再使用 `scriptmate`。

## 常用命令

```bash
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
.venv/bin/scriptmate analyze --file sample.txt -o ./analysis
.venv/bin/scriptmate match --file sample.txt -o ./output --aspect 9:16 --resolution 1080
.venv/bin/scriptmate search "economic growth" --top 5 --source all --aspect 16:9 --resolution 4K
```

## 配置重点

核心配置分为几类：

- `[planner_model]`：负责文案分段和搜索策略规划，默认 `gpt-4.1-mini`
- `[judge_model]`：负责候选缩略图语义评分，默认 `gpt-4o-mini`
- `[sources]`：当前内置自动搜索源，例如 `pexels`、`pixabay`
- `[[sources.extra]]`：用于声明国内素材库、付费素材库或未来扩展源
- `[matching]`：控制候选数量、搜索深度、画幅、分辨率、评分阈值
- `[generation]`：控制生成型 fallback，但默认不自动开启

## 它的差异化在哪里

ScriptMate 更适合：

- 科普视频
- 医疗健康讲解
- 宏观经济与行业分析
- 需要真人口播搭配 B-roll 的讲解内容

它的匹配逻辑更强调：

- 上下文优先，而不是单词命中
- 叙事正确，而不是“看起来差不多”
- 国家、主体、比较关系一致
- 输出结果便于人工快速筛选和复核

## 文档入口

- [英文说明](README.md)
- [使用说明](docs/usage.md)
- [配置说明](docs/config.md)
- [部署说明](docs/deployment.md)

## V1 当前范围

已包含：

- 文案分段与视觉策略判断
- Pexels + Pixabay 搜索
- 国内/付费素材库的配置声明能力
- AI 语义评分
- 面向下游剪辑的素材方案包输出
- 一键安装脚本和交互式配置流程

暂不包含：

- 自动成片作为主目标
- AI 配音
- 自动字幕
- 以真人口播视频为主的工作流
- 复杂图形界面审核系统
