# 一稿 · 内容工作台

[![CI](https://github.com/Javissssss/jzs-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Javissssss/jzs-studio/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-4F46E5)
![License](https://img.shields.io/badge/license-MIT-87867F)

**一次创作，双平台分发。** 本地运行的 Web 工作台：选题 → 写稿 → 配图排版 → 发布，公众号长文和小红书图文一条线做完。

## 三种写稿方式 × 三种配图方式

| | API 调用 | Codex 自动执行 | 手动 |
|---|---|---|---|
| **写稿** | 任意 OpenAI 兼容模型（DeepSeek / 通义 / Kimi / OpenAI）直接写全文 | 后台跑 `codex exec`，用你的 Codex 登录写稿，实时看日志 | 复制简报给任意 AI，把回复粘回来 |
| **配图** | 生图 API（gpt-image / 豆包 Seedream / SiliconFlow）按图说生成；或 Pexels 图库搜图 | Codex 设计框架图数据 + 用 SVG 画插画，自动截图入稿 | 每个配图位单独「替换」上传或 Ctrl+V 粘贴截图 |

框架图、数据图、小红书卡片始终由模板自动生成；AI 漏写配图位会自动补位。

## 快速开始

| 系统 | 命令 |
|---|---|
| Windows | 双击 `run.bat` |
| macOS / Linux | `chmod +x run.sh && ./run.sh` |
| 手动 | `pip install -r requirements.txt && python -m playwright install chromium && python app.py` |

打开 <http://127.0.0.1:8770>，点右上角 **⚙ 设置** 填模型地址和 Key（保存在本地 `.env`，不入库，页面不回显）。

## 配置项

全部可选，在设置页填或写进 `.env`（见 `.env.example`）：

| 变量 | 作用 |
|---|---|
| `JZS_LLM_BASE_URL` / `_API_KEY` / `_MODEL` | 写作模型 |
| `JZS_IMAGE_BASE_URL` / `_API_KEY` / `_MODEL` / `_SIZE` | 生图模型 |
| `JZS_CODEX_CMD` | Codex 命令，默认找 PATH 里的 `codex`；没装可填 `npx -y @openai/codex` |
| `JZS_CODEX_TIMEOUT` | Codex 单次超时秒数，默认 600 |
| `JZS_BRAND` | 栏目名，印在文章眉题和卡片页脚 |
| `PEXELS_API_KEY` | 图库搜图 |
| `JZS_WORKSPACE` | 草稿目录，默认 `./workspace` |

Codex 需先装好并登录一次：`npm i -g @openai/codex && codex login`。工作台以 `--sandbox workspace-write` 在每个项目的独立目录里运行它。

> 服务只监听 `127.0.0.1`，没有登录鉴权，不要用 `--host 0.0.0.0` 暴露到公网。

## 项目结构

```text
app.py        Flask 服务 + REST API；写稿/配图走后台任务，前端轮询日志
core/         topics 选题 · brief 简报/解析 · llm 写作 API · codex Codex CLI
              imagegen 生图 API · media 配图 · cards 卡片 · render 排版
              jobs 后台任务 · settings 设置页 · publish 发布辅助
web/          单页工作台（原生 JS，无构建）
skill/        可独立复用的内容技能包
tests/        离线测试（mock 模型服务 + 假 Codex，不需要网络）
```

## 开发

```bash
python -m unittest discover -s tests -v
python app.py --debug
```

push 和 PR 会在 Ubuntu / Windows 上跑 CI。

## License

[MIT](LICENSE)

## 可选：复杂系统专家视角

框架包已内置在 `perspectives/complexity/`，内容原创整理自公开的复杂系统研究（反馈回路、存量流量、非线性、相变、反脆弱）。

- 写稿页的「调用复杂系统专家视角」开关默认关闭。打开后可选两档：「只用于解释概念」可以设最多几处；「全文使用」则整篇套用
- 编辑正文时，输入或选中一个概念，点「用复杂系统视角解释并插入」，生成 1-2 段解释，插在光标所在段落之后
- 实时宏观数据是可选项：在「设置」里填写 `ATTRACTOR_API_KEY`。不填也能用，只是不拉实时读数
- 想换成自己的框架：在 `perspectives/` 下新建目录放 `SKILL.md`，再在 `core/perspective.py` 的 `PERSPECTIVES` 里登记

## 换电脑

1. `git clone` 后双击 `run.bat`（Windows），或运行 `./run.sh`（macOS/Linux）。脚本会自动安装 requirements.txt 和 Chromium
2. 把旧电脑上的 `.env` 拷过来，或者在页面「设置」里重新填写
3. 成品分两个文件：`…_终版.html` 给工作台预览用；`…_终版_单文件.html` 把图片直接嵌在文件里，可以直接转发，在任何电脑上打开都能看到图
