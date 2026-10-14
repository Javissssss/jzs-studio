# 巨人之上 · 内容工作台（jzs-studio）

把「选题 → 写作 → 配图 → 排版 → 存草稿」整条双平台内容流水线封装成一个**本地 Web 产品**，脱离 AI 对话框独立运行，可跨电脑移植。

- **双平台**：一篇内容同时产出 微信公众号长文 + 小红书图文笔记
- **半自动写作**：产品不绑定任何 AI。它生成「创作简报」，你拿给任意 AI（ws / Codex / 通义 / Kimi / 豆包）出稿，把回复粘回来自动解析回填
- **密钥不出本机**：素材源（Pexels）的 key 只走环境变量，绝不写入产品文件
- **发布红线**：产品永远只到「存草稿」，正式发表按钮由你人工点

---

## 一、快速开始

### Windows
双击 `run.bat`（首次会自动装依赖 + 下载浏览器内核，约 2-3 分钟），然后浏览器打开 http://127.0.0.1:8770

### macOS / Linux
```bash
chmod +x run.sh && ./run.sh
```

### 手动启动
```bash
pip install -r requirements.txt
python -m playwright install chromium   # 首次
python app.py --port 8770
```

---

## 二、八步流水线

| 步 | 阶段 | 做什么 | 人工确认点 |
|----|------|--------|:---:|
| 1 | 选题 | 百度热搜 / 手动粘贴 / 直接指定，按账号定位（AI·财经·效率）评分排序 | ✅ |
| 2 | 创作简报 | 一键生成含文风铁律+结构模板+配图规划+输出标记的简报，复制给任意 AI | |
| 3 | 回填稿件 | 把 AI 完整回复粘进来，按标记自动解析出双平台稿件+配图数据 | |
| 4 | 配图制作 | 按正文占位符自动生成：框架图 / 氛围图(Pexels) / 数据图 + 小红书卡片 | |
| 5 | 排版渲染 | 公众号正文+配图 → 砖红米白终版 HTML | |
| 6 | 终稿确认 | 预览终版，检查排版/配图/免责声明 | ✅ |
| 7 | 存草稿 | 复制富文本+打开平台，辅助你存草稿（永不点发表） | |
| 8 | 完成归档 | 生成交付清单，产出文件在 workspace/<id>/output/ | |

---

## 三、半自动写作流（核心）

```
[产品] 生成创作简报  ──复制──▶  [任意AI] 按标记出稿  ──粘回──▶  [产品] 自动解析回填
```

AI 回复需包含这些标记块（产品据此解析）：

| 标记 | 内容 |
|------|------|
| `===WECHAT_START/END===` | 公众号正文 Markdown |
| `===XHS_START/END===` | 小红书正文 |
| `===XHS_TITLE_START/END===` | 小红书标题（每行一个） |
| `===XHS_TAGS_START/END===` | 小红书标签 |
| `===FIGURES_START/END===` | 框架图数据（JSON 数组） |
| `===CHARTS_START/END===` | 数据图数据（JSON 数组） |

正文里用占位符标注配图位置：
- `[FIGURE:f1] 图说` —— 框架图（flow/compare/checklist/timeline）
- `[MOOD:english query] 图说` —— 氛围图（Pexels 搜索，英文具象名词）
- `[CHART:c1] 图说` —— 数据图
- `[CLOSE]...[/CLOSE]` —— 结尾互动+免责声明块

没有标记也能用：整段会被当作公众号正文。

---

## 四、环境变量（可选）

| 变量 | 用途 | 必需 |
|------|------|:---:|
| `PEXELS_API_KEY` | 氛围配图素材源（内网主力） | 否* |
| `UNSPLASH_ACCESS_KEY` | 备用素材源 | 否 |

\* 不设 Pexels key 时，氛围图不可用，但框架图/数据图/小红书卡片不受影响。

设置（Windows，重开终端生效）：
```cmd
setx PEXELS_API_KEY "你的key"
```

---

## 五、发布说明（辅助式，非全自动）

产品采用**辅助发布**而非模拟点击，更可靠：

- **公众号**：把终版 HTML 渲染成富文本复制到剪贴板 → 打开公众号后台（首次扫码登录 jzs profile）→ 你在编辑器粘贴、存草稿
- **小红书**：复制文案 + 打开创作平台（首次扫码登录 jzs-xhs profile）→ 你按序上传卡片、粘贴文案、存草稿

登录态通过 agent-browser profile 复用，扫码一次后免登。**产品永不点「发表/发布」。**

---

## 六、目录结构

```
jzs-studio/
├── app.py              Flask 服务（端口 8770）
├── core/               业务逻辑
│   ├── config.py       路径/常量/设计Token
│   ├── state.py        项目状态机
│   ├── topics.py       选题（百度热搜/手动/直接）
│   ├── brief.py        创作简报生成 + AI回复解析
│   ├── media.py        配图（框架图/氛围图/数据图）
│   ├── render.py       公众号 HTML 排版
│   ├── cards.py        小红书卡片
│   └── publish.py      辅助发布（draft-only）
├── web/                前端（原生 HTML/CSS/JS）
│   ├── index.html
│   ├── style.css
│   └── app.js
├── skill/jzs-content-publisher/   内嵌 skill 包（脚本/模板/参考）
├── workspace/          运行时项目数据（每个项目一个子目录）
├── requirements.txt
├── run.bat / run.sh
└── README.md
```

---

## 七、移植到另一台电脑

1. 整个 `jzs-studio/` 目录拷过去（或解压移植包）
2. 装 Python 3.10+
3. 双击 `run.bat`（或 `./run.sh`）—— 自动装依赖
4. 如需氛围配图，`setx PEXELS_API_KEY "..."`
5. 发布功能需另装 agent-browser（`npm i -g agent-browser`）并首次扫码登录

> workspace/ 里的历史项目会一并带过去，可继续未完成的项目。

---

## 八、依赖

- Python 3.10+
- flask、playwright（`requirements.txt`）
- playwright chromium 内核（首次自动下载）
- 可选：agent-browser（仅发布环节用，扫码登录）

设计：砖红 `#C96442` / 米白 `#FAF9F5`，与公众号终版排版同源。
