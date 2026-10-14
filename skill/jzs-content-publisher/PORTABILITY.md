# Codex / 其他运行时挂载方法

本 skill 包零硬编码路径、零密钥，可整体拷贝到任何电脑使用。

## Codex 挂载

把 skill 包目录拷到目标机器（如 `~/skills/jzs-content-publisher/`），
然后在项目的 `AGENTS.md`（或全局 `~/.codex/AGENTS.md`）加入：

```markdown
## 双平台内容发布

当用户要求"发公众号和小红书 / 双平台发布 / 写一篇发两边"时，
完整阅读并严格执行 <skill包路径>/SKILL.md 的6阶段工作流：
- 选题和终稿润色两处必须停下来等用户确认（编号列表方式提问）
- 配图引擎按 references/images.md 探测链选择：
  Codex 环境优先用原生 imagegen skill 生成封面/信息图，
  框架图一律用 scripts/figure_cards.py（playwright HTML截图）
- 发布环节按 references/publish-*.md 用 agent-browser 存草稿，永不点发布
- 输出目录：环境变量 JZS_OUTPUT_DIR，默认 ./output/YYYY-MM-DD/
```

## 目标机器一次性初始化

按 `references/setup.md` 执行：
1. `npm i -g agent-browser && agent-browser install`
2. `pip install playwright && playwright install chromium`
3. 双平台扫码建 profile（公众号 `jzs`、小红书 `jzs-xhs`）
4. 设置素材源环境变量（**key 不随包迁移，需在新机器自行设置**）：
   - `PEXELS_API_KEY`（内网主力素材源，必填）
   - `UNSPLASH_ACCESS_KEY`（可选增强）
   - Windows 持久化：`[Environment]::SetEnvironmentVariable("PEXELS_API_KEY","<你的key>","User")`
   - Unix 持久化：写入 `~/.bashrc` / `~/.zshrc`：`export PEXELS_API_KEY=<你的key>`
   - 验证：`python scripts/search_images.py --query mountain --count 1 --out <temp>` 能下载即成功

## 环境差异说明

| 环节 | ws 环境 | Codex 环境 |
|------|---------|-----------|
| 热点搜索 | bocha MCP | web 搜索工具 |
| AI生图 | 即梦/flux MCP | 原生 imagegen |
| 素材抓图 | search_images.py（相同，Pexels主力） | search_images.py（相同，Pexels主力） |
| 数据图表 | antv MCP | figure_cards.py 兜底 |
| 人工确认 | question 选项框 | 编号列表提问 |
| 框架图/卡片图 | playwright（相同） | playwright（相同） |
| 发布 | agent-browser（相同） | agent-browser（相同） |
