# 环境初始化与能力探测（每台机器一次性）

## 1. 基础依赖检查

```powershell
python --version          # 需 3.9+
node --version            # 需 18+（agent-browser 用）
npm ls -g agent-browser   # 未装则: npm i -g agent-browser && agent-browser install
python -c "import playwright"  # 未装则: pip install playwright && playwright install chromium
```

Unix 环境同理（`python3` / `npm i -g agent-browser`）。

## 2. 平台登录态（扫码，绝不索要密码）

登录态存 agent-browser 持久化 profile，不进 skill 包、不进 git。

```powershell
# 公众号（首次会出二维码，用手机微信扫码；之后 profile 复用免登录）
agent-browser --profile "$HOME/.agent-browser/profiles/jzs" --headed open https://mp.weixin.qq.com

# 小红书创作者平台（首次扫码登录）
agent-browser --profile "$HOME/.agent-browser/profiles/jzs-xhs" --headed open https://creator.xiaohongshu.com
```

验证登录：`agent-browser get url` 未跳转到登录页即成功。
两个平台用**独立 profile**，避免 cookie 互相干扰。

## 3. 运行时能力探测（每次任务开始时执行，结果决定配图引擎）

按顺序探测，记录可用项：

| 能力 | 探测方法 | 用途 |
|------|---------|------|
| ws 生图 MCP | 工具列表含 `image_mcp_generate_image_by_jimeng` / `_by_flux` | AI信息图/封面 |
| ws 图表 MCP | 工具列表含 `antv_generate_*` | 数据图表 |
| Codex 原生 imagegen | 可用 skill 列表含 `imagegen` | AI信息图/封面 |
| bocha 搜索 MCP | 工具列表含 `bocha_bocha_web_search` | 热点采集 |
| OPENAI_API_KEY | 环境变量非空 | 通用生图（当前未配置） |
| UNSPLASH_ACCESS_KEY | 环境变量非空 | 素材搜索增强 |
| PEXELS_API_KEY | 环境变量非空 | 素材搜索（**内网主力源**，已配置） |
| playwright | `python -c "import playwright"` | 卡片/框架图截图（**必备兜底**） |

**兜底原则**：playwright + HTML卡片截图在所有环境可用，AI生图全部不可用时，
封面/信息图降级为 HTML 卡片风格（templates/figure/），流程不中断。

## 4. 输出目录

```powershell
# 默认: <cwd>/output/YYYY-MM-DD/ ；可用环境变量覆盖:
$env:JZS_OUTPUT_DIR = "D:\path\to\output"   # Windows
export JZS_OUTPUT_DIR=/path/to/output        # Unix
```

## 常见问题

- **agent-browser 命令找不到**：`$env:PATH = "$env:APPDATA\npm;$env:PATH"`（Windows npm 全局目录）
- **playwright 截图黑屏/字体缺失**：`playwright install chromium` 重装；Linux 需 `playwright install-deps`
- **公众号 profile 登录态过期**：重新 `--headed open` 扫码一次即可
- **小红书被踢登录**：同账号勿在其他网页端登录；手机 App 查看不受影响
