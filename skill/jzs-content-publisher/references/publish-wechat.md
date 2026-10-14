# 公众号存草稿手册（agent-browser，未认证个人号适用）

> 未认证个人号无 draft/add API 权限，只能浏览器自动化。目标：**存草稿**，不点发布。

## 前置

- profile：`$HOME/.agent-browser/profiles/jzs`（登录态见 setup.md，首次扫码）
- 入口：`https://mp.weixin.qq.com`

## 步骤

1. **打开后台并验证登录**
   ```powershell
   agent-browser --profile "$HOME/.agent-browser/profiles/jzs" --headed open https://mp.weixin.qq.com
   agent-browser get url   # 仍在 mp.weixin.qq.com 且非登录页 = 已登录；否则提示用户扫码
   ```

2. **进入图文新建页**：点左侧「内容与互动 → 草稿箱」→「新的创作 → 写新图文」，
   或直接 open `https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77`（若跳转失败则走UI点击）。

3. **填标题**：真实点击标题输入框 → `agent-browser keyboard type "<标题>"`（≤64字）。

4. **灌正文（关键坑）**：公众号编辑器是富文本，直接 type HTML 会变成纯文本。正确做法：
   - 用浏览器打开本地终版HTML（`file:///` 预览页）→ `Ctrl+A` 全选 → `Ctrl+C` 复制（保留富文本格式）
   - 回到公众号编辑器正文区 → 真实点击 → `Ctrl+V` 粘贴
   - agent-browser 操作：`open file:///...html` → `press Control+a` → `press Control+c` → 切回 mp 标签页 → 点正文 → `press Control+v`
   - 粘贴后截图检查：配色/字体/图片是否保留

5. **图片检查**：外链图会被公众号转存或屏蔽。粘贴时本地 `file://` 图片不会自动上传——
   **正文图片必须先上传到公众号素材**：编辑器工具栏「图片」→ 选择本地文件（agent-browser `upload` 命令或 `set-input-files`）→ 逐张插入对应位置。
   图多时降级方案：正文只保留文字+框架图（figure卡片PNG逐张上传），氛围图酌情删减。

6. **填摘要**：导语框填 lead 副标题（≤120字）。

7. **存草稿**：点「保存为草稿」按钮 → 截图确认出现"已保存"提示 → 记录 appmsgid（URL中可见）。

8. **回执**：给用户草稿箱入口 `https://mp.weixin.qq.com`（提醒：草稿箱→预览→人工点发表）。

## 降级方案（编辑器自动化失败时）

1. 终版HTML已在浏览器打开 → 全选复制进剪贴板
2. 告知用户："HTML已复制到剪贴板，请在公众号后台新建图文后直接 Ctrl+V"
3. 封面图与框架图PNG路径一并给出，用户手动上传

## 红线

- 只点「保存为草稿」，**永不点击「发表」/「群发」**
- 遇到"微信验证"弹窗：截图推给用户扫码，不代填任何验证码
- 操作全程 `--headed` 有头模式，用户可随时接管
