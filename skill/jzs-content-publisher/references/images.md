# 配图策略与降级链

## 总原则

1. 先出**配图规划表**给用户过目，再动手生成（位置/类型/引擎/内容描述）
2. 知识类文章：框架图必须文字精准 → HTML卡片截图；概念/封面追求高档艺术感 → AI信息图
3. 时事/评论类文章：以真实素材图为主，AI生图为辅
4. 所有引擎不可用时兜底：HTML+CSS卡片截图（零API依赖，风格与砖红米白模板统一）

## 引擎探测链（按运行时自动选择）

| 优先级 | 引擎 | 可用条件 | 适用 |
|--------|------|---------|------|
| 1 | 运行时原生AI生图 | ws: `image_mcp_generate_image_by_jimeng`/`_by_flux`；Codex: `imagegen` skill | 封面、概念信息图 |
| 2 | baoyu-infographic skill | 已安装该skill且优先级1可用（它自己会解析后端） | 高档信息图（21版式×22风格） |
| 3 | antv MCP 图表 | ws: `antv_generate_*` | 数据图表（柱/线/饼/思维导图/流程） |
| 4 | HTML卡片截图 | playwright 可用（**必备兜底**） | 框架图、流程图、对比图、清单图、时间线 |
| 5 | 素材抓取 | Pexels（env `PEXELS_API_KEY`，内网主力）；Unsplash（env `UNSPLASH_ACCESS_KEY`）；Openverse（免key，内网常超时） | 氛围/场景配图 |

## 各图片类型规范

### 公众号封面（2.35:1，1080×459）
- 优先AI生图：prompt = 文章主题关键词 + 风格后缀（"editorial illustration, warm beige and terracotta palette, minimal, premium magazine cover style, no text"）
- **AI生图一律要求无文字**（中文必乱码），标题信息由公众号后台封面文案承载
- 降级：templates/figure/ 风格横版卡片截图

### 正文框架图（知识类核心）
- 用 `scripts/figure_cards.py`，4款模板：
  - `flow` 流程图（步骤/机制拆解）
  - `compare` 对比图（两栏对照）
  - `checklist` 清单图（可执行建议）
  - `timeline` 时间线（事件演进）
- 宽度 1080px，高度自适应，砖红米白Token，可直接嵌入公众号HTML
- 每张图配 `<figcaption>` 说明

### 正文氛围配图（3-5张）
- `scripts/search_images.py --query "关键词" --count N`（引擎链：unsplash→pexels→openverse，自动降级）
- 关键词策略：中文主题 → 翻译成英文具象名词搜（如"美债收益率"→"bond market finance"）
- 来源标注：figcaption 写"图源：Pexels/Unsplash/Openverse"，只用免版权（CC0/CC-BY/Pexels License）图
- CC-BY 图需署名的，在页脚数据来源区统一署名
- **内网实测（2026-10-13）**：Openverse/Wikimedia 在本机网络不可达（超时），**Pexels 可达且 key 有效**
  （返回字段 `photos`，图在 `src.large`，图床 `images.pexels.com`）→ Pexels 为内网主力素材源。
  素材源全部失败时**不中断**：氛围图改用AI生图 photorealistic 风格 prompt
  （"photorealistic editorial photo, [主题场景], natural light, no text"），
  或降级 figure_cards.py 视觉卡片；并在交付回执中注明"素材源不可达，已降级"

### 数据图表（财经类）
- ws环境：antv MCP 生成（line/column/pie/dual-axes），下载PNG嵌入
- Codex/兜底：figure_cards.py 手写HTML表格+CSS条形图截图

### 小红书卡片图
- 见 xhs-style.md，用 `scripts/xhs_screenshot.py`，不走AI生图（文字密度高，AI必乱码）

## AI生图 prompt 模板

```
[主题具象描述], [情绪/氛围], editorial illustration style,
warm beige (#FAF9F5) and terracotta (#C96442) accent palette,
clean minimal composition, premium magazine quality,
no text, no watermark, no letters
--ar 21:9 (封面) / 3:4 (小红书备用)
```

生成后必检：①无乱码文字 ②无水印 ③色调与模板协调。不合格重生成或降级素材图。
