# 私人逐章阅读页

页面提供章节目录、上一章/下一章、字号调节、当前版本与核对时间，以及本设备的章节和滚动位置记忆。它没有正文、决定、审核、验收或任务写入接口。作者认可与模型流程状态分别展示。

## 正式在线接入

`novel/reader_hub.py` 可在现有 Hub `authenticated` 依赖之后、前端静态挂载之前登记 `/novel/reader/`。准备工具为 `adapters/prepare_reader_hub.py`，只对明确选择的源码副本修改；匹配不到已检查的认证/挂载位置时拒绝修改。

页面及全部正文接口沿用 Hub 原有网页登录和 `hub_session`；再核对已启用的 `novel-shizhi-zhicheng` 正式工作区 owner、phase 和固定接管回执。浏览器不能指定工作区、资料根或账户。登录失效时需在现有 Hub 首页重新登录；尚未新增登录流程或凭据。

每次打开/刷新目录，以 SQLite `mode=ro` 读取当前 `current_revision`，校验清单内容哈希和作品归属，再读取该版本的章节。每章请求固定该次目录版本，因此阅读过程中后台发布新章不会混合版本；点击“刷新版本”才切换。只列出 `manuscript/` 的编号 Markdown/TXT 文件，不返回状态、作者决定、任务日志或其他路径。正文使用安全文本节点展示，不执行其 HTML。缺少章名的稿件仅显示章节编号，不以正文首句冒充作者章名。

部署前须核对实际 systemd 工作目录、运行源码、registry 与活动任务；备份将修改的源码和正式资料的哈希/任务状态。新增 reader 文件与最小 API 注册代码后，仅重启 API，验证认证拒绝、所属账户读取、全部章哈希、真实浏览器翻章、服务健康与原任务次数。恢复原 API 文件并移除本次新增文件即可回退；不修改控制规则、OAuth 授权、正文或原审核。

## 本机检查

明确选择当前正式资料根，不使用旧本机作品根作为线上进度：

```powershell
python -m novel.reader --root '实际正式资料根' --book shizhi-zhicheng --port 8767
```

已从固定正式版本逐章读取并核验的本机阅读副本可这样预览：

```powershell
python -m novel.reader --snapshot runtime/reader/current-formal.json --port 8767
```

副本模式明确展示核对时间和不会自动同步的说明，只用于预览，不能替代用户要求的在线正式源。文件留在 ignored `runtime/reader/`，不随 Git 上传。在线页面不包含这一副本。

本机服务器仅监听 `127.0.0.1`，验证 Host，拒绝跨站读取，并发送 no-store 和 CSP。线上认证由原 Hub 提供，不将本机服务器直接暴露公网。

## 本轮实施与验证（2026-10-17）

初次本地交付时，私人在线部署尚未执行，等待作者授权本次 root SSH 安全登录和临时加密凭据使用。随后作者明确授权，现已按下节完成部署。没有创建 Sites 或对外上传正文。

正式源经 MCP 回读为 `15d4a6aacc59ee64babfcde8bb81105062c9e97047b1c52500fd33cf428a4c6d`，28章固定包逐章完整读取，全部内容长度/哈希与索引一致；导出后再次核对仍为当前版本。本机 HTTP 接口又完整读回28章，全文SHA均匹配。该读取不创建写作或审核任务，不修改 Canon、作者决定或任务次数。

浏览器实际验证了桌面目录、手机展开目录、首章到第二章再返回、末章禁止继续翻页、字号、刷新和无错误控制台；真实正文检查不代替文学质量认可。9项专项测试在已有 Hub 依赖环境中通过，包含真实文件/SQLite、HTTP和认证路由的工程夹具。完整 `python -m unittest discover -s tests -v` 在同一环境执行269项，全部通过，232.405秒；日志 `.local-validation/reader-full-venv-tests.log`。先前一轮完整运行已中断，保留原日志，不把它称为完成。

部署原件与哈希、只读服务检查脚本、受控部署/回退脚本保存在 ignored `.local-validation/reader-20261017/`。真正上线前必须新读实际服务源码及状态，再填入部署计划；不得直接把旧路径或预期URL当成已验证的线上入口。

## 私人在线部署回读

实际入口：[私人逐章阅读页](https://47.178.34.133/novel/reader/)。先在现有 Hub 登录页输入网页登录密码和动态验证码，登录后打开阅读地址；不要在网页登录页使用 root SSH 密码。

作者明确授权后，线上预检确认 API 的 systemd 工作目录与进程 cwd 都是 `/opt/novel-dot-pilot-20261016/hub-source`，实际监听 `127.0.0.1:8765`；正式 root 沿用登记配置。原写作任务 `cf05e2cb13894d03acbc30056a8ef334` 为 running/attempts=1/no_progress=0，没有重领或清零。

线上 API 原文件为 CRLF；接入器最初按 LF 检查而安全拒绝，没有修改运行服务。兼容修正保留全部原始字节和原换行，仅插入注册代码；新增回归覆盖 LF/CRLF，并通过10项专项测试，日志 `deployment-targeted-tests.log`。API SHA 从 `48728995e2b7d34287bec4d7512681901589dcf2be47318e2bcac3e4b67cc64f` 变为 `c576ca130138ce1b32b69b680f3aa3a05aa82b8fa1994837cfb28b12d0196d72`。

原 API、SQLite 一致性备份、原快照文件哈希和任务计数保存在 VPS `/opt/novel-reader-20261017/rollback/`。安装前未完成请求为空，代码包/逐文件哈希匹配；服务账户实际读取正式源28章，版本 `15d4a6aa…`。安装后本机与公网 HTTPS 的匿名正文请求均401，匿名页面转到原登录页303。原2,860份快照文件SHA未变，原106个任务的输入版本和累计计数保留，Worker PID仍为1586642。API及其代理在本次 API 重启后均active；Worker未重启。随后真实 MCP 回读确认当前正式版本accepted、第二十九章原写作仍running/attempts=1/no_progress=0、uncertain_requests为空。启动错误标记为0。

作者随后完成原 Hub 网页登录。在线浏览器实际显示“正式工作区 · 当前版本”、`15d4a6aacc · 流程阶段通过`、第1/28章《墙后有人》；已实际操作到第二章并返回、通过桌面目录打开第28章《墙上的方印》并核对下一章禁用、刷新同一正式版本、展开手机目录并返回第一章。浏览器错误日志为空，临时视口已复原，真实阅读页保留打开。此轮验证读取线上正式源，区别于此前本机阅读副本。

`final-deployment-receipt.json` 已同步到 VPS 和本机，`authenticated_browser_read=verified`。Windows PowerShell 启动曾因本机脚本执行策略被拒绝；未改动策略，后以 Python GUI 收取用户输入，并用 Windows 用户级 DPAPI 临时加密。实际上线、MCP及登录后页面回读后，精确删除了本次 DPAPI 凭据及可能的临时文件，回读 DPAPI/tmp/XML 均不存在，见 `credential-cleanup.json`。完整上线回执和后验检查保存在 `.local-validation/reader-20261017/`。

## Hub 主导航入口（2026-10-17）

作者随后要求把入口加入 Hub 左侧菜单。现已在现有主导航末尾增加“逐章阅读”，使用同源普通链接 `/novel/reader/`，同一窗口沿用 Hub 登录。桌面侧边栏及手机导航共用原有样式；原有菜单、审核功能和退出逻辑保留。刷新已打开的 Hub 首页即可看到入口。

本轮读取线上实际前端源码和清单，在 `.local-validation/reader-nav-20261017/frontend/` 独立副本中修改 `src/main.tsx` 与 `src/style.css`，没有覆盖本机另一仓库中的源码。接入工具为 `adapters/prepare_reader_navigation.py`。严格按线上 lockfile 安装已有缓存中的依赖，通过 `tsc --noEmit` 和 Vite 生产构建；构建环境未提供控制面凭据。

上线前保存源码、全部旧静态文件、作品快照哈希和任务计数，回退位置为 VPS `/opt/novel-reader-nav-20261017/rollback/`。新哈希静态资源先上传，入口文件原子更新，旧资源保留；公网首页、Service Worker、JS/CSS 都逐项核对新构建哈希。API/代理/Worker PID分别仍为1612857/1612858/1586642，无服务重启；原2,860份快照文件未变，原106个任务的输入版本和累计计数保留。

已在真实登录会话中核对桌面左侧菜单并实际点击，进入显示“正式工作区 · 当前版本”的第一章，完成到第二章并返回的翻章验证；手机导航同样实际点击成功，浏览器错误日志为空，临时视口复原。`final-deployment-receipt.json` 的 `browser_click_verified=true`。本次重新收取的 DPAPI 临时 SSH 凭据已精确删除并回读不存在，见同目录 `credential-cleanup.json`。源码、构建日志、哈希计划和上线回执均保留在 `.local-validation/reader-nav-20261017/`。
