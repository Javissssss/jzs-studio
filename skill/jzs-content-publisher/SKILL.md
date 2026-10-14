---
name: jzs-content-publisher
description: >
  「巨人之上」双平台内容全流程工作流：选题→公众号文章→小红书笔记→配图→人工润色→双平台存草稿。
  可移植设计：零硬编码路径、零密钥进包，ws/Codex/OpenClaw 通吃。
  触发词：发公众号和小红书、双平台发布、内容全流程、写一篇发两边、jzs发布。
version: 1
updated: 2026-10-13
---

# 双平台内容发布全流程 Skill

## 定位

一次创作，双平台分发：**微信公众号「巨人之上」**（深度长文）+ **小红书**（降维卡片笔记）。
两个人工确认点：**选题** 和 **终稿润色**。发布只到草稿箱，正式发布按钮永远由人按。

## 可移植铁律（任何执行环境必须遵守）

1. **零硬编码路径**：所有输出走 `JZS_OUTPUT_DIR` 环境变量；未设置时默认 `<当前工作目录>/output/YYYY-MM-DD/`。临时文件走系统 temp（Windows: `$env:TEMP`，Unix: `/tmp`）。
2. **零密钥进包**：平台登录态只存本机 agent-browser profile；素材源 key 只走环境变量（`PEXELS_API_KEY` / `UNSPLASH_ACCESS_KEY`）。任何凭证不得写入本 skill 包文件。
3. **能力探测降级**：每个依赖外部能力的环节都有降级链（见 references/images.md、references/setup.md），探测失败不中断流程，降级执行并告知用户。
4. **人工确认点不可跳过**：阶段1选题、阶段4润色必须等用户明确确认；阶段5发布前必须用户说"定稿"。

## 工作流（6阶段）

### 阶段0：环境自检（每台机器首次执行）

按 `references/setup.md` 检查：python3、playwright、agent-browser、双平台登录态。
缺失项引导安装，登录态缺失引导扫码（绝不索要密码）。

### 阶段1：选题 🙋人工确认点

**输入二选一**：
- 用户直接指定题目 → 跳过打分，直接出选题卡
- 用户给方向/关键词 → 用可用的搜索工具（ws: bocha MCP；Codex: web搜索）抓 5-10 条热点 → 写入 `<temp>/topics.json`（格式 `{"items":[{"title","summary","source","link","rank"}]}`）→ 跑 `scripts/filter_topics.py` 10分制打分 → 取 ≥7 分前5条

**输出选题卡**（每个候选一张）：
- 一句话核心主张（主角是谁、发现了什么、为什么反直觉）
- 目标读者的痛点/疑惑
- 文章结构草稿（3-5个H2标题）
- 预计字数区间 + 配图规划概要（几张、什么类型）

**用可点击选项框**（ws: question工具；Codex: 编号列表）让用户选定/否决/修改。未确认前不得进入阶段2。

### 阶段2：公众号文章创作

严格按 `references/wechat-style.md` 执行：
1. 正文 MD（2500-4000字，文风铁律）
2. HTML 排版（基于 `templates/wechat_template.html`，砖红米白设计Token）
3. 交付到输出目录 + 给 `file:///` 预览链接

### 阶段3：配图制作

按 `references/images.md` 的探测链执行：
1. 先出**配图规划表**（每张：位置/类型/引擎/内容描述），随文章预览一起给用户过目
2. 知识框架图 → `scripts/figure_cards.py`（HTML卡片截图，4款模板）
3. 概念/封面信息图 → baoyu-infographic 或运行时原生AI生图（ws: 即梦/flux MCP；Codex: imagegen）
4. 氛围配图 → `scripts/search_images.py`（引擎链 unsplash→pexels→openverse，Pexels 为内网主力源）
5. 公众号封面 2.35:1（1080×459），插入HTML对应位置

### 阶段4：小红书笔记创作

严格按 `references/xhs-style.md` 执行：
1. 公众号文降维：≤1000字文案 + 标题×2（20字内）+ 标签6-8个
2. 卡片图 4-5 张（1080×1440，`scripts/xhs_screenshot.py` 截图，截前检测 scrollHeight）

### 阶段5：终稿润色 🙋人工确认点

一次性呈上全部成品：
- 公众号 HTML `file:///` 预览链接 + 配图缩略清单
- 小红书文案全文 + 卡片PNG路径清单

用选项框收集修改意见（可多轮循环）。用户明确说"定稿"前不得发布。

### 阶段6：发布（只到草稿）+ 归档

1. **公众号**：按 `references/publish-wechat.md`，agent-browser 操控 mp.weixin.qq.com 存草稿
2. **小红书**：按 `references/publish-xhs.md`，agent-browser 操控 creator.xiaohongshu.com 存草稿
3. 两平台各截图回执，附草稿箱入口链接，提醒用户人工点发布
4. 归档：产出物清单写入 `<输出目录>/manifest.md`；按各风格文档末尾规则回填参考作品表

## 目录结构

```
jzs-content-publisher/
├── SKILL.md                    # 本文件
├── references/
│   ├── setup.md                # 环境初始化与能力探测
│   ├── wechat-style.md         # 公众号文风+排版规范
│   ├── xhs-style.md            # 小红书文案+卡片图规范
│   ├── images.md               # 配图策略与降级链
│   ├── publish-wechat.md       # 公众号存草稿手册
│   └── publish-xhs.md          # 小红书存草稿手册
├── scripts/
│   ├── filter_topics.py        # 10分制选题打分（纯标准库）
│   ├── search_images.py        # 素材抓取（Pexels/Unsplash/Openverse 自动降级）
│   ├── xhs_screenshot.py       # 小红书卡片截图（playwright）
│   └── figure_cards.py         # 框架图卡片→PNG（playwright）
└── templates/
    ├── wechat_template.html    # 公众号排版模板
    └── figure/                 # 框架图模板：flow/compare/checklist/timeline
```

## 安全红线

- 密码/cookie/token 永不进对话、脚本、skill文件；登录只走扫码或 agent-browser auth vault
- 发布动作永远停在草稿；正式发布由人工完成
- 财经类内容必须带免责声明："行情为已发生的客观描述，不构成任何买卖推荐"
- 小红书同一账号不允许多网页端同时登录，发布前提醒用户避免踢登录态
