# 巨人之上 · 内容工作台

[![CI](https://github.com/Javissssss/jzs-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Javissssss/jzs-studio/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-C96442)
![License](https://img.shields.io/badge/license-MIT-87867F)

**一篇内容，两个平台。** 本地运行的 Web 工作台：从热榜选题，到公众号长文和小红书图文的配图、排版、存草稿，全程 4 步完成。

- **不绑定 AI**：工作台生成「创作简报」，你可以交给任意 AI（Codex / Kimi / 通义 / 豆包…）写稿，再把回复粘回来
- **配图全自动**：框架图、氛围图、数据图和小红书卡片一键生成。AI 漏写配图位时自动补位
- **人守红线**：只做到「存草稿」，正式发表由你亲手点。财经题自动加免责声明
- **密钥不出本机**：API Key 只从环境变量读取，不写入任何文件

## 快速开始

| 系统 | 命令 |
|---|---|
| Windows | 双击 `run.bat` |
| macOS / Linux | `chmod +x run.sh && ./run.sh` |
| 手动 | `pip install -r requirements.txt && python -m playwright install chromium && python app.py` |

首次运行会自动安装依赖并下载浏览器内核（约 2–3 分钟）。完成后会自动打开 <http://127.0.0.1:8770>。

## 四步流程

| 步 | 你做什么 | 工作台做什么 |
|---|---|---|
| 1 选题 | 选择来源（微博 / 头条 / 百度 / 手动 / 指定），点「选定」 | 抓取热榜，按「AI · 财经 · 效率」定位评分排序 |
| 2 简报 & 回填 | 把简报粘给 AI，再把回复粘回来（Ctrl+Enter） | 生成简报并复制，解析双平台稿件，自动补配图位 |
| 3 一键生产 | 点一个按钮 | 配图 → 小红书卡片 → 砖红米白排版，右侧实时预览 |
| 4 确认 & 存草稿 | 看自检清单，复制粘贴到平台 | 复制富文本和文案，打开平台后台，打包 zip 下载 |

稿件可以随时点「编辑稿件」修改，保存后会自动重新排版。

## AI 回复格式

简报末尾已经写好了格式要求，AI 照着输出即可。工作台按以下标记解析：

```text
===WECHAT_START===      公众号正文 Markdown（## 小节）
===XHS_START===         小红书正文
===XHS_TITLE_START===   小红书标题，每行一个
===XHS_TAGS_START===    #标签
===FIGURES_START===     框架图 JSON 数组
===CHARTS_START===      数据图 JSON 数组
（每块以对应的 _END=== 结尾）
```

正文占位符：`[FIGURE:f1] 图说`、`[MOOD:english query] 图说`、`[CHART:c1] 图说`、`[CLOSE]…[/CLOSE]`。

没有标记也能用，整段回复会被当作公众号正文。

## 配置

复制 `.env.example` 查看全部变量，均为可选：

| 变量 | 作用 |
|---|---|
| `PEXELS_API_KEY` | 氛围图素材源（[免费申请](https://www.pexels.com/api/)）。不设置时只影响氛围图 |
| `UNSPLASH_ACCESS_KEY` | 备用素材源 |
| `JZS_WORKSPACE` | 草稿目录，默认 `./workspace`（不入库） |

发布辅助（复制富文本、打开后台）需要 `npm i -g agent-browser`（Node 18+）。首次使用需扫码登录。

> 服务默认只监听 `127.0.0.1`，且没有登录鉴权。不要用 `--host 0.0.0.0` 暴露到公网。

## 项目结构

```text
app.py              Flask 服务 + REST API
core/               流水线：topics 选题 · brief 简报/解析 · enrich 配图补位
                    media 配图 · cards 小红书卡片 · render 排版 · publish 发布辅助
web/                单页工作台（原生 JS，无构建）
skill/              可独立复用的内容技能包（脚本 / 模板 / 文风规范）
tests/              离线单测 + API 测试
```

## 开发

```bash
python -m unittest discover -s tests -v    # 离线测试，不需要网络和浏览器
python app.py --debug
```

每次 push 和 PR 都会触发 GitHub Actions，在 Ubuntu 和 Windows 上分别跑测试。

## License

[MIT](LICENSE)
