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

planner 与 judge 独立配置。聊天模型使用 OpenAI 兼容的 `/chat/completions`，要求输出候选 ID、0–1 分数与理由。Typesafe JEV 使用下述专用适配器。其他 embedding 或非 chat 格式的 reranker 需要单独适配，不能直接当作聊天模型填写。

### Typesafe JEV

官方 [Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python) 0.7.2 定义默认模型 `jev-latest`、Bearer 认证和 `POST https://api.typesafe.ai/v1/systemone`。已于 2026-10-01 核对在线 [OpenAPI](https://api.typesafe.ai/openapi.json)、[Score 文档](https://docs.typesafe.ai/primitives/score/)与 [State 文档](https://docs.typesafe.ai/concepts/state/)。项目直接使用相同 HTTP 协议，无需安装 SDK。该接口按文本/JSON 状态和问题判断，不把候选 URL 当作已读取的画面。

在现有配置中替换 `[judge_model]` 并保持 `[judge].vision=false`：

```toml
[judge_model]
provider = "typesafe"
model = "jev-latest"
base_url = "https://api.typesafe.ai"
supports_vision = false

[judge]
vision = false
concurrency = 2
cache_ttl_seconds = 604800
```

安全注入 `TYPESAFE_API_KEY`；planner 继续使用自身的密钥。也可直接使用仓库中的配置：

```bash
.venv/bin/scriptmate doctor --config config.typesafe.example.toml
.venv/bin/scriptmate match --file /path/to/script.txt --aspect 9:16 -o ./output/materials --config config.typesafe.example.toml
```

`JUDGE_MODEL_*` 环境变量优先于文件；切换时清除旧供应商的覆盖值。JEV 不会从 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 借用密钥。仅设置 `TYPESAFE_API_KEY` 不会自动切换供应商；需选择 `provider="typesafe"`。不要把 Typesafe 配置给生成脚本分析 JSON 的 planner。

每个候选按五级标准评估，返回 0–4 的期望分数，再除以 4 转成现有排序所需的 0–1；随后仍应用既有编辑调整。清单与逐段 JSON 的 `judge_details` 保留实际模型 ID、原始分数、标准、概率分布及置信度，审阅页显示模型与置信度。理由是本地格式化的评分摘要，接口没有提供自由文本解释。置信度不等同于相关度，不因置信度高就提高分数。

图片或视频的实际画面仍需人工或视觉模型核对，JEV 仅评分已有标题、描述、标签及规格；不能从本地文件名推断未记录的画面。开启 `--judge-vision` 会明确报错。缺失、越界或不一致的评分会报错，默认不会自动降级。`jev-latest` 是可变别名，缓存可能在 TTL 内保留旧结果；要立即重评设置 `cache_ttl_seconds=0`，要复现结果则使用账户 `GET /v1/models` 返回的固定模型 ID。

官方说明 JEV 的主要训练语言为英文，中文等 CJK 输入目前准确率较低。请求保留 planner 已有的英文视觉描述和关键词，同时保留原稿上下文；本适配器不额外调用翻译服务。应用于中文项目时应使用已人工标注的素材样例校准评分标准与门槛，离线协议测试本身不证明排序质量优于原 judge。

适配器通过模拟官方协议的离线测试；真实账户调用仍需要已应用的网络权限和环境凭据。

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

本地图片缩小并编码后发送；在线候选使用缩略图。视频目前使用封面/缩略图，不能证明整段视频或推断片段时间范围。本次未加入视频镜头索引、多帧视频推理或本地 embedding 服务。

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

这些参数限制同时请求数和缓存期限，不是每日配额或 token 预算，仍应按供应商额度配置。

## 验证

离线测试覆盖响应转换、许可筛选、中文路由、失败提示、并发、缓存及视觉请求格式。具备网络权限和真实凭据后仍需在线验证，不能从 MockTransport 的通过结果声称图库/模型在线可用。

官方文档：[Openverse](https://docs.openverse.org/api/)、[MediaWiki Imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo)、[Pexels](https://www.pexels.com/api/documentation/)。
