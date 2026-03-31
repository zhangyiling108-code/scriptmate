# ScriptMate CLI 使用说明

## 1. 这是什么

ScriptMate CLI 是一个“文案驱动的高质量素材匹配引擎”。

它的目标不是直接帮你成片，而是把一段文案拆解成多个段落，并为每段输出：

- 推荐的视觉类型
- 推荐素材
- 至少 3 条真实候选素材链接
- 备选素材
- 可读的匹配报告

你可以把输出结果继续拿去剪映、CapCut、Premiere 或其他剪辑工具中使用。

当前版本默认遵循这 5 条规则：

- 段落上下文驱动搜索，而不是单词命中
- 地域、国家、叙事对象必须一致
- 每段优先稳定给出至少 3 条真实候选
- 默认不降级，任何 fallback 都需要显式允许
- 默认优先输出可直接剪辑的高质量链接，不先把下载拖慢

内置真实搜索源当前是：

- Pexels
- Pixabay

同时现在已经支持在 `config.toml` 里声明额外的国内或付费素材库元信息，例如：

- 国内：VJ师网/光厂、潮点视频
- 国际付费：Pond5、Adobe Stock、Shutterstock、iStock、Artgrid、Storyblocks、Envato Elements

V1 目前不会自动直接查询这些额外库的 API，但会把它们按段落生成搜索链接写进输出结果，方便你直接去对应平台挑素材。

---

## 2. 安装

在项目目录下执行：

```bash
cd /path/to/scriptmate

bash scripts/bootstrap.sh
source .venv/bin/activate
```

安装完成后，你可以使用两个命令入口：

```bash
.venv/bin/scriptmate --help
.venv/bin/cmm --help
```

`scriptmate` 是新的主入口，`cmm` 是兼容入口。
如果你已经激活了虚拟环境，也可以直接使用 `scriptmate --help`。

建议先看这三个帮助页：

```bash
.venv/bin/scriptmate --help
.venv/bin/scriptmate init --help
.venv/bin/scriptmate match --help
```

---

## 3. 配置

推荐直接使用交互式初始化：

```bash
.venv/bin/scriptmate init --config config.toml
```

如果你想手动配置，也可以先复制模板：

```bash
cp config.example.toml config.toml
```

### 3.1 真实模型配置

当前版本默认直接使用真实模型，不再提供 mock provider。

初始化完成后，建议马上执行：

```bash
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
```

其中：

- `doctor`：检查 Python、配置文件、模型设置、素材库 key、匹配默认值
- `config-show`：查看当前实际生效的配置摘要，并自动掩码敏感 key

如果你要接真实模型，至少要配置：

```toml
[planner_model]
provider = "openai"
model = "gpt-4.1-mini"
api_key = "你的 API Key"
base_url = "https://api.openai.com/v1"

[judge_model]
provider = "openai"
model = "gpt-4o-mini"
api_key = "你的 API Key"
base_url = "https://api.openai.com/v1"

[sources]
enabled = ["pexels", "pixabay"]

[sources.pexels]
api_key = "你的 Pexels Key"

[sources.pixabay]
api_key = "你的 Pixabay Key"
```

也可以不把 key 写进 `config.toml`，直接使用环境变量：

```bash
export OPENAI_API_KEY="你的 OpenAI Key"
export PEXELS_API_KEY="你的 Pexels Key"
export PIXABAY_API_KEY="你的 Pixabay Key"
```

如果你后续要换成别的兼容 provider，也可以继续用 `planner_model` / `judge_model` 独立配置覆盖。

### 3.2 声明额外付费素材库

如果你想把其他付费素材库提前登记进系统，可以在配置里加：

```toml
[[sources.extra]]
name = "pond5"
enabled = true
kind = "manual"
license = "paid"
priority = 20
home_url = "https://www.pond5.com/"
search_url_template = "https://www.pond5.com/search?kw={query}"
api_key_env = "POND5_API_KEY"
notes = "Preferred for cinematic b-roll"
```

这类配置当前的作用是：

- 记录你可用的外部素材库
- 保存官网、搜索模板、优先级和密钥环境变量
- 为后续真正接 API 或人工检索工作流保留统一入口

当前 V1 内置自动搜索仍然只会查询：

- `pexels`
- `pixabay`

推荐默认分工：

- `planner_model = gpt-4.1-mini`
  - 更适合脚本分段、视觉策略和搜索词规划
- `judge_model = gpt-4o-mini`
  - 更适合对候选缩略图做多模态语义评分

---

## 4. 常用命令

### 4.0 初始化与自检

```bash
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
```

适合把项目分享给其他人时先跑这一组命令。

### 4.1 只分析文案

```bash
.venv/bin/scriptmate analyze --file sample.txt -o ./analysis-output
```

作用：

- 拆分文案段落
- 生成 `segment_role`
- 生成 `visual_type`
- 生成多层搜索词

输出：

- `analysis-output/analysis.json`

适合用来先看脚本被怎么理解。

### 4.2 完整匹配素材

```bash
.venv/bin/scriptmate match --file sample.txt -o ./output
```

或者直接传一句文本：

```bash
.venv/bin/scriptmate match "近年来我国GDP持续增长，已经突破120万亿。最后总结一下核心观点。" -o ./output
```

常用参数：

```bash
.venv/bin/scriptmate match --file sample.txt -o ./output --top 3 --aspect 9:16 --resolution 1080 --style atlas
```

参数说明：

- `--file`：输入文案文件
- `-o, --output`：输出目录
- `--top`：每段保留多少个候选
- `--aspect`：画幅比例，会直接影响素材方向筛选
- `--resolution`：素材最低分辨率要求，支持 `4K`、`1080`（默认）、`720`
- `--style`：风格名，目前主要影响卡片风格
- `--library-root`：本地素材库目录
- `--library-meta`：本地素材 metadata 文件
- `--download`：下载主选和备选到本地；默认只给链接
- `--allow-planner-fallback`：允许 planner 失败时退回本地规则
- `--allow-judge-fallback`：允许 judge 失败时退回启发式评分
- `--allow-search-fallback`：允许真实搜索不足时使用 fallback 查询
- `--allow-generated-fallback`：允许降级到生成型卡片或图表

当前支持的常用画幅：

- `9:16`：优先竖屏素材
- `16:9`：优先横屏素材
- `1:1`：优先接近方形的素材

当前支持的分辨率档位：

- `4K`：优先 2160p 级别素材
- `1080`：默认，优先 Full HD
- `720`：最低档位，放宽搜索门槛

补充说明：

- 系统会优先满足你指定的分辨率档位
- 如果在该档位下找不到足够合适的真实素材，会自动补到更低一档
- 但最低不会低于 `720p`
- 默认每个 provider 会先拉取比最终 shortlist 更多的原始候选，再做语义评分和排序

### 4.3 单独搜索某个词

```bash
.venv/bin/scriptmate search "economic growth" --top 5 --source all
```

可选 source：

- `all`
- `pexels`
- `pixabay`

如果你只是想测试某个关键词搜出来的素材质量，这个命令很方便。

---

## 5. 输出目录说明

执行 `match` 后，输出目录大致如下：

```text
output/
├── analysis.json
├── manifest.json
├── summary.md
├── cache/
└── segments/
    ├── 001/
    │   └── segment.json
    ├── 002/
    │   ├── segment.json
    │   ├── recommended.mp4
    │   └── alternatives/
    └── 003/
        ├── segment.json
        └── recommended.png
```

### `analysis.json`

记录脚本分析结果，包括：

- 段落内容
- `segment_role`
- `visual_type`
- 搜索词
- 视觉说明

### `manifest.json`

是整个任务的总清单，适合给程序继续消费。

### `summary.md`

是给人看的摘要报告，重点说明：

- 每段为什么判成这个视觉类型
- 为什么选这个素材
- 是否用了 fallback
- 当前段落的叙事主语、上下文说明和复核优先级

### `segments/<id>/segment.json`

每段的详细结果，包含：

- 原文案
- 叙事主语与上下文说明
- 推荐素材
- 备选素材
- 选择理由
- 是否 fallback

### `alternatives/`

该段的备选素材。

---

## 6. 视觉类型说明

当前系统会把每段判成以下几类：

- `stock_video`
  - 优先搜视频素材
- `stock_image`
  - 优先搜图片素材
- `data_card`
  - 优先生成图表或数据型卡片
- `text_card`
  - 优先生成总结卡、强调卡
- `skip`
  - 跳过，通常是口播开头、主持人镜头位

一般来说：

- 具体场景更容易走 `stock_video`
- 抽象概念、数字、趋势更容易走 `data_card`
- 总结和强调更容易走 `text_card`

---

## 7. 推荐工作流

如果你是做科普、行业分析、讲解类视频，推荐这样用：

1. 先写好口播文案
2. 用 `scriptmate analyze` 看系统怎么理解段落
3. 用 `scriptmate match` 生成素材方案包
4. 打开 `summary.md` 和 `segments/`
5. 把 `recommended` 和 `alternatives` 拿去剪映里组合

这样你不会被一个黑盒成片结果锁死，而是得到一组更高质量、更可控的素材。

---

## 8. 常见问题

### Q1：为什么有些段没有视频，只有卡片？

因为系统会优先判断“这段更适合什么视觉表达”，而不是所有段都硬找视频。

例如：

- 数据
- 总结
- 抽象概念
- 趋势对比

这些内容往往用图表或卡片更准确。

### Q2：为什么某段没有下载素材？

可能有两种情况：

- 你使用了 `--no-download`
- 该段最终走的是本地生成卡片或图表 fallback

### Q3：可以只用自己的素材库吗？

可以。你可以通过：

```bash
scriptmate match --file sample.txt -o ./output --library-root ./assets --library-meta ./metadata.csv
```

让系统优先使用你自己的素材。

### Q4：这个工具会直接生成视频吗？

当前 V1 不会。  
它专注于输出“高质量素材方案包”，方便你继续在剪映等工具里完成剪辑。

---

## 9. 当前 V1 范围

当前版本已支持：

- 文案解析
- 多段分镜判断
- Pexels + Pixabay 搜索
- AI 评分
- URL 去重
- 数据图表 fallback
- 文字卡片 fallback
- 输出方案包

当前版本不做：

- 自动配音
- 自动字幕
- 自动成片
- 真人口播视频驱动
- AI 生图
- 复杂交互编辑
