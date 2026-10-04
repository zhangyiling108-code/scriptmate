# 开放素材检索与视觉评分

## 图片来源

Pexels/Pixabay 根据素材类型选择图片或视频接口。Openverse 和 Wikimedia Commons 当前接入图片，Coverr 仅检索视频，NASA 支持图片和视频。

新生成的配置已启用开放图片来源；已有配置不会被覆盖，请在 `[sources].enabled` 中加入 `openverse`、`commons` 并保留其他来源：

```toml
[sources]
enabled = ["pexels", "pixabay", "coverr", "nasa", "openverse", "commons"]

[sources.openverse]
base_url = "https://api.openverse.org/v1"
allowed_licenses = ["cc0", "pdm", "by"]

[sources.commons]
base_url = "https://commons.wikimedia.org/w/api.php"
allowed_licenses = ["cc0", "pdm", "by"]
```

单独搜索图片不需要 planner/judge 密钥：

```bash
.venv/bin/scriptmate search "上海外滩" --source commons --media-type image --aspect 9:16 -o ./output/commons
.venv/bin/scriptmate search "solar panels" --source openverse --media-type image --aspect 16:9 -o ./output/openverse
.venv/bin/scriptmate search "city skyline" --source pexels --media-type image --aspect 16:9 -o ./output/pexels
```

`search` 默认检索视频；`match` 使用 planner 给出的类型。未启用的来源或不支持的媒体类型会显示警告。开放来源保留中文查询，英文图库继续使用英文检索词。结果仍按画幅筛选，上述具体查询不保证一定存在符合比例的素材。

Openverse 可匿名访问，匿名配额较低；需要更高额度时通过 `OPENVERSE_API_TOKEN` 注入有效 bearer token。Commons 不需要密钥。环境变量由运行环境注入或 shell 导出，项目不会自动读取 `.env`。API 与返回的原图/缩略图域名均需网络访问权限，原图可能由不同站点托管。

## 许可与署名

默认许可筛选为 CC0、公有领域标记、CC BY。未知许可不会加入开放来源候选；只有输出用途适合相应条款时才额外允许 `by-sa` 等代码。仍需核对原始来源。

清单、每段 JSON 和审阅页包含作者、许可证链接/版本、署名要求与文本。`attributions.md` 汇总主选与备选，最终作品保留实际使用素材的署名。按原始来源页和媒体地址去重，避免聚合来源重复提供同一素材。

本地文件默认许可为 `unknown`，不再因位于本地就标记为自有。CSV/JSONL 可增加 `license_type`、`license_url`、`license_version`、`creator`、`creator_url`、`attribution`、`source_page`、`attribution_required`；确实自有的素材可设置 `license_type=owned`。

## 判断模型

planner、文本预筛和最终 judge 独立配置。可选 `[prefilter_model]` 先按元数据排列候选；`[judge].prefilter_limit` 默认 12，每次评分最多将这些候选交给最终 judge，至少保留本次请求的 shortlist 数量。预筛没有相关度硬门槛，但名额有限，低排名候选可能不会送往视觉模型。聊天 judge 使用 `/chat/completions`，输出候选 ID、0–1 分数、理由及 `visible_evidence`。最终分不与预筛分相加，文本高分不能覆盖画面不匹配。其他 embedding 或非 chat 格式的 reranker 需要单独适配。

### Typesafe JEV

官方 [Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python) 0.7.2 定义默认模型 `jev-latest`、Bearer 认证和 `POST https://api.typesafe.ai/v1/systemone`。已于 2026-10-01 核对在线 [OpenAPI](https://api.typesafe.ai/openapi.json)、[Score 文档](https://docs.typesafe.ai/primitives/score/)与 [State 文档](https://docs.typesafe.ai/concepts/state/)。项目直接使用相同 HTTP 协议，无需安装 SDK。该接口按文本/JSON 状态和问题判断，不把候选 URL 当作已读取的画面。

JEV 用于文本预筛，DeepSeek 用于实际画面核验。2026-10-04 已核对 [DeepSeek 官方视觉文档](https://api-docs.deepseek.com/guides/vision/)并完成 `deepseek-flash` 的真实图片请求：

```toml
[prefilter_model]
provider = "typesafe"
model = "jev-latest"
base_url = "https://api.typesafe.ai"
supports_vision = false

[judge_model]
provider = "deepseek"
model = "deepseek-flash"
base_url = "https://api.deepseek.com"
supports_vision = true
image_transport = "inline"

[judge]
vision = true
require_visual_evidence = true
prefilter_limit = 12
concurrency = 2
cache_ttl_seconds = 604800
```

安全注入 `TYPESAFE_API_KEY` 与 `DEEPSEEK_API_KEY`；也可直接使用仓库中的配置：

```bash
.venv/bin/scriptmate doctor --config config.typesafe.example.toml
.venv/bin/scriptmate match --file /path/to/script.txt --aspect 9:16 -o ./output/materials --config config.typesafe.example.toml
```

`JUDGE_MODEL_*` 与 `PREFILTER_MODEL_*` 环境变量分别覆盖文件中的各自角色；切换时清除旧覆盖值。预筛使用 `PREFILTER_MODEL_API_KEY`，Typesafe 也接受 `TYPESAFE_API_KEY`，不会借用 planner/judge 的密钥。只设置 Typesafe 密钥不会自动启用预筛，需要 `[prefilter_model]`。不要把 Typesafe 配置给生成脚本分析 JSON 的 planner。

JEV 按五级标准返回 0–4 的期望分数，归一化为 0–1 后只用于文本预筛。清单与逐段 JSON 的 `metadata_score`、`metadata_judge_details` 保留预筛分、实际模型、概率分布和置信度；`visual_score`、`visual_observation`、`evidence_scope` 记录最终画面判断。JEV 理由是本地格式化的摘要，接口不提供自由文本解释。置信度不会提高相关度分。

JEV 不能从 URL 或文件名读取画面。旧配置把 Typesafe 放在 `[judge_model]` 时仍能返回元数据候选，但不再自动选为主选；直接对该角色启用 `--judge-vision` 仍会报错。缺失、越界或不一致的评分默认报错，不自动降级。`jev-latest` 是可变别名；立即重评可设置 `cache_ttl_seconds=0`，复现可使用账户 `GET /v1/models` 返回的固定 ID。

官方说明 JEV 的主要训练语言为英文，中文等 CJK 输入目前准确率较低。请求保留 planner 已有的英文视觉描述和关键词，同时保留原稿上下文；本适配器不额外调用翻译服务。应用于中文项目时应使用已人工标注的素材样例校准评分标准与门槛，离线协议测试本身不证明排序质量优于原 judge。

适配器通过离线协议测试。本机已经验证 JEV `jev-1.13.0` 与 DeepSeek `deepseek-flash` 的真实请求；其他账户和端点仍需各自验证。

### 聊天视觉模型

更换模型时先核对准确 ID、实际端点、图片与 JSON 支持。未经核验的模型不会预设为默认。

```toml
[judge_model]
provider = "compatible"
model = "YOUR_VERIFIED_VISION_MODEL"
base_url = "https://YOUR_MODEL_HOST/v1"
supports_vision = true

[judge]
vision = true
concurrency = 2
cache_ttl_seconds = 604800
```

占位值需替换为已核验的端点/模型。通过 `JUDGE_MODEL_API_KEY` 提供密钥，`JUDGE_MODEL_SUPPORTS_VISION` 可覆盖能力设置。明确设置 `supports_vision=false` 时要求视觉评分会报错。旧配置未提供此字段时保留原有兼容判断；填写 true 本身不证明端点已验证成功。

本地图片缩小编码后发送；在线候选使用缩略图。`image_transport="url"` 将地址交给模型；`"inline"` 先读取缩略图，校验图片并缩至最长边 1024 像素，再编码发送，可避免模型侧无法读取外部链接。在线预览读取上限为 8 MiB，不下载完整视频。单张图片读取失败只影响该候选：记录 `visual_input_error`，按元数据保留人工复核，不写入该次失败的缓存，其他候选继续核验。模型接口失败仍默认报错，显式允许 judge fallback 时才降级，降级结果不会标为视觉核验。

证据范围逐候选记录：`image` 表示模型读取了图片，`video_thumbnail` 仅表示读取视频封面，`metadata` 表示没有图片输入。视觉响应必须包含可见内容描述，不能仅凭高分判定核验通过。`require_visual_evidence=true` 要求真实图片输入才可自动选主选；所有元数据候选与视频封面仍可人工复核。报告的 `ready/usable` 建议也不用于这些待复核候选。图片经模型核验仍不等于事实鉴定，物种、精确地理位置与因果机制仍需核对可靠来源。视频多帧核验、动作判断和片段时间范围尚未实现。

本地候选也经过同一个 judge，原始本地匹配分数保留为 `local_match_score`。使用本地素材仍需要可用 planner/judge，不自动绕过模型；启发式降级仍需明确使用对应 `--allow-...-fallback` 参数。

## 缓存、并发与失败

```toml
[matching]
search_concurrency = 4
provider_concurrency = 2
search_timeout_seconds = 90
search_cache_ttl_seconds = 86400
```

搜索受总并发和逐来源并发限制。来源失败不会阻止其他来源返回，但会进入搜索 JSON、匹配清单、报告与审阅页。认证错误不反复重试；429/临时错误使用退避并参考 Retry-After。诊断不输出含凭据的请求 URL。

judge 对未缓存候选分批并发处理，单素材缓存可跨不同候选批次复用。缓存包含评分版本、端点、完整上下文、视觉模式、素材描述与本地指纹。启发式降级不写入模型缓存；模型恢复后重新评分。损坏/过期缓存重新获取，写入采用原子替换。

聊天 judge 漏评时保留已返回评分，只对缺失候选补问，额外补问次数不超过 `[judge_model].max_retries`。补问仍失败时默认报错，不填入伪造分数；显式允许 judge fallback 时仅对缺失项使用启发式评分。补问会增加模型请求和输入 token，HTTP 临时错误仍按原有策略重试。

分段缓存包含版本、供应商、端点和模型，启发式 planner 分段不会写入正常分析缓存。2026-10-04 评分缓存升级至版本 6，区分元数据与视觉输入、传输方式，旧缓存不会被当作已核验画面。旧文件保留，首次重评会产生额外 API 用量。预筛与视觉阶段各有请求和缓存成本；候选限制控制单次视觉请求规模，并非每日预算。

这些参数限制同时请求数和缓存期限，不是每日配额或 token 预算，仍应按供应商额度配置。

## 验证

离线测试覆盖响应转换、许可筛选、中文路由、失败提示、并发、缓存及视觉请求格式。具备网络权限和真实凭据后仍需在线验证，不能从 MockTransport 的通过结果声称图库/模型在线可用。

官方文档：[Openverse](https://docs.openverse.org/api/)、[MediaWiki Imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo)、[Pexels](https://www.pexels.com/api/documentation/)。
