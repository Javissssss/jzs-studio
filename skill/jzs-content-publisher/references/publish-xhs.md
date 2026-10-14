# 小红书存草稿手册（agent-browser）

> 目标：图文笔记填完**存草稿**，发布按钮由人按。

## 前置

- profile：`$HOME/.agent-browser/profiles/jzs-xhs`（独立profile，首次扫码，见 setup.md）
- 入口：`https://creator.xiaohongshu.com`（创作者平台）
- 提醒用户：发布期间同账号勿在其他网页端登录（会互踢）

## 步骤

1. **打开并验证登录**
   ```powershell
   agent-browser --profile "$HOME/.agent-browser/profiles/jzs-xhs" --headed open https://creator.xiaohongshu.com
   agent-browser get url   # 跳到登录页 = 未登录，提示用户扫码后重试
   ```

2. **进入发布页**：点「发布笔记」或 open `https://creator.xiaohongshu.com/publish/publish?source=official`，选「上传图文」tab。

3. **上传卡片图**（按配图清单顺序）：
   - 找到 `input[type=file]` → agent-browser 上传命令设置文件列表（多文件一次传入，顺序=清单顺序）
   - 等待全部上传完成（缩略图数量=卡片数），截图确认

4. **填标题**：真实点击标题框 → type 标题（≤20字，从标题×2中用户选定的那个）。

5. **填正文**：点击正文区 → 粘贴文案（长文本用剪贴板方式：写入temp文件→读入→type，或 `press Control+v`）。
   检查：📷图X指引、URL每行一个、末尾标签是否完整。

6. **填标签话题**：正文末尾 `#标签` 逐个输入，输入后等下拉候选出现→点选精确匹配项（否则话题不生效）。

7. **存草稿**：点「保存草稿」按钮 → 截图确认 → 记录草稿状态。
   （若界面只有"发布"无"存草稿"：停在填写完成状态，截图告知用户手动点发布，**agent绝不点发布**）

8. **回执**：告知用户草稿已存，入口 `https://creator.xiaohongshu.com/new/note-manager`（笔记管理→草稿箱）。

## 降级方案（自动化失败时）

交付包已含一切：`小红书文案.md`（发布版正文可直接全选复制）+ 按序编号的卡片PNG。
告知用户手动发布三步：传图（按01-0N顺序）→ 粘标题正文 → 补话题标签。

## 红线

- 永不点「发布」按钮；只到草稿
- 遇手机验证/实名提示：截图推给用户处理
- 每天发帖量控制（账号安全），批量任务提醒用户分批
