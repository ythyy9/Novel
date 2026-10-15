# 云端工程接续记录

## 2026-10-14：显式引用影响查询与历史版本检索

- 实际目录 `/workspace/Novel`；沿用 `codex/v1-local-workflow`。起点及实施前远程 HEAD 均为 `4dd1919075ec647235166385ed1b63d317551a7d`，起始工作区干净，只有一个 worktree。未切换分支、未操作 main。
- 实读 AGENTS.md、README.md、architecture、roadmap、usage、validation 及相关源码测试；没有下级 AGENTS.md。阶段 1、2 已由现有代码及本轮全套测试确认，未重新实现。
- Python 3.12.14。云端没有 `books/`、`runtime/` 和实际实验数据；本机 `F:/Novel` 未提交 README/评估文档及参考原文未访问。不得据此推断本机停止状态为空或累计次数为零。
- 任务一：新增 `impact BOOK PATH [--revision REVISION]`，输出版本、源哈希、四个状态分区的显式引用记录、六类知识与原文证据。缺失路径、跨作品版本拒绝；只读，不改变审核或任务状态。不是完整依赖图，不推断正文语义因果。
- 任务二：新增 `search --revision`，支持同作品历史快照原文检索，默认行为兼容；拒绝跨作品及不存在版本。
- 所有工程夹具在临时目录运行并清理，没有正式小说、真人阅读反馈或本轮真实 Codex 调用。未修改原则、锁定项、原始反馈或限额。

### 验证命令与日志

日志根目录：`.local-validation/cloud-20261014/`（云端本地保留，按仓库规则不入 Git）。

| 实际命令 | 结果 | 日志 |
| --- | --- | --- |
| `python -m unittest discover -s tests -v`（基线） | 130 项，128 通过，2 Windows 专属跳过 | `baseline.log` |
| 同上（首项初次） | 133 项，1 error，2 跳过；夹具删除稳定知识 ID 被现有门禁拒绝 | `impact-tests.log` |
| 同上（首次返修） | 退出 1；133 项，1 error，2 跳过；夹具将候选与事实使用同一陈述被既有采用门禁拒绝 | `impact-final.log` |
| 同上（第二次返修） | 退出 0；133 项，131 通过，2 跳过 | `impact-final-2.log` |
| 同上（两项最终） | 见下方最终状态 | `final.log` |
| `git diff --check` | 退出 0 | 工具执行记录 |
| `git ls-remote --heads origin codex/v1-local-workflow` | 退出 0，实施前与提交前均为基线 SHA | 工具执行记录 |
| `gh pr view 1 --json state,isDraft,headRefName,headRefOid,url,title` | 退出 1，GraphQL Forbidden | 工具执行记录 |
| `gh api repos/ythyy9/Novel/pulls/1 --jq ...` | 退出 1，REST Forbidden | 工具执行记录 |

前两轮测试的 shell 尾命令为 tail，因此该 shell 的退出 0 不代表 unittest 成功；失败按日志保留。从首次返修起显式传递 unittest 退出码。基线成功按 unittest 输出确认。

### 累计失败与接续边界

历史验收记录中 Windows 路径并发失败与沙箱 taskkill 清理权限失败保持原记录，未清零。历史本机任务累计次数因 runtime 未同步，仍为未知。本轮工程测试失败 2 次、夹具返修 2 次，最终结果单独记录；没有模型调用重试。另有一次补丁上下文不匹配，确认未写入后修正补丁。GitHub PR 读取权限失败 2 次（不同接口），不再重试或扩大权限；没有自动审批拒绝提示。

静态复核：固定版本后读取快照，沿用跨作品检查及快照完整性检查；保留知识类别，返回源证据；不写入数据库、版本或控制文件。测试覆盖历史版本、六类知识、四个分区、空结果、非法路径、跨作品和真实 CLI 子进程。未将空结果解释为无语义影响。

下一工程任务：研究记录 `affected_paths` 与审核覆盖的版本绑定查询（独立定义输出及回归，不能把它冒充自动因果分析）。按需上下文和完整依赖图尚未实现。连续章节验收仍依赖作者明确的作品输入，不能自行选定作品或启用候选方法。

最终测试：退出 0，134 项，132 通过、2 Windows 专属跳过，11.074 秒。达到两项工程验收标准。提交 SHA 与远程推送结果在后续交接段记录。

### 提交与远程交接

功能提交 `29fbdc397d6a3fb8e01d380d402ce6b7c3742050`。
`git push origin HEAD:refs/heads/codex/v1-local-workflow` 退出 0；随后 `git ls-remote --heads origin codex/v1-local-workflow` 退出 0，回读为同一 SHA，工作区干净。
已有 PR 定位：https://github.com/ythyy9/Novel/pull/1 。分支已推送，但由于 GitHub API Forbidden，PR 当前状态及 Draft 属性未验证，未尝试修改或合并。此权限阻塞仅影响 PR 管理；本轮两个可验收工程阶段已经完成。无需重跑模型或重置既有数据即可从下一工程任务接续。最终交接记录由单独文档提交保存。

## 接续阶段：研究影响与审核覆盖查询

起点 `19e58a616e68e609969d5d3f096c26207c327335`，同分支、工作区干净；沿用上述累计记录，无重复环境验收。

父会话于 **2026-10-14T15:41Z** 通过其已授权 GitHub 连接只读核验：PR #1 open、draft=true、merged=false，head 为 `codex/v1-local-workflow`，SHA 为 `19e58a616e68e609969d5d3f096c26207c327335`，并回读本进度文档。这是父会话证据，不代表云端 gh API 权限恢复；前述两次 Forbidden 原样保留。

实现：扩展 `impact` 返回所选快照研究记录的完整声明影响及条件、不确定性、来源；查询同一版本且覆盖目标文件的已发布审核，返回控制版本匹配状态、完整报告、未决项和结果哈希。复用研究格式校验和审核完整性校验；不将声明影响解释为采用，不将覆盖解释为通过。

验收：`python -m unittest discover -s tests -p test_engine.py -v` 退出 0，64 项全部通过，日志 `.local-validation/cloud-20261014/evidence-engine.log`。增加历史版本隔离、旧控制标记、未决项保留、审核证据损坏拒绝、只读及 CLI 覆盖。全量结果见下。差异检查 `git diff --check` 退出 0。提交前远程回读仍为 `19e58a6`，没有发现并发提交。本阶段无新增失败或返修；工程累计失败保持 2 次，先前补丁上下文失败保持 1 次；模型调用 0，未知本机累计状态不清零。

下一独立工程项：同作品两个不可变快照的文件差异清单（增删改及哈希），供跨章返修逐文件核对；不自动推断因果、不修改阶段门禁、不需要未同步作品。

本阶段全量：`python -m unittest discover -s tests -v` 退出 0，136 项、134 通过、2 Windows 专属跳过，11.183 秒；日志 `.local-validation/cloud-20261014/evidence-final.log`。本阶段为真实 SQLite/文件/CLI 工程验证，没有真实模型或读者验收。

研究/审核阶段功能提交：`a45651db0f57ff01619203f9f0f7d2e8e61c1f72`。`git push origin HEAD:refs/heads/codex/v1-local-workflow` 退出 0；随后 `git ls-remote --heads origin codex/v1-local-workflow` 退出 0，回读一致。

## 接续阶段：版本文件差异清单

新增 `diff BOOK FROM_REVISION [--to-revision TO_REVISION]`，省略目标时固定当前版本。输出按路径排序的新增、删除、修改及两端内容哈希，不输出未变文件；反向比较也能定位历史已不存在的文件。只读取经校验的同作品快照，不改当前指针或审核。测试覆盖增删改、同版空差异、显式历史与默认当前版本、错误/跨作品版本、只读及真实 CLI。差异静态复核通过，`git diff --check` 退出 0。

- 首次 `python -m unittest discover -s tests -v` 退出 1：138 项中 2 个断言失败，2 Windows 跳过。夹具初始状态 JSON 与写入 JSON 的格式也有变化，测试错误地假定只有正文变化、并假定第一项是正文。日志 `.local-validation/cloud-20261014/diff-final.log` 保留。
- 修复仅调整夹具断言为按路径核对，并明确验证 JSON 空白也属于内容变化，没有放宽程序或门禁。
- 再次同命令退出 0：138 项，136 通过、2 Windows 专属跳过，12.957 秒。日志 `.local-validation/cloud-20261014/diff-final-2.log`。
- 累计：工程全量失败运行 3 次（共 4 个用例失败/错误），夹具返修 3 次；补丁上下文失败 1 次；GitHub API 失败 2 次；没有新增模型调用。此前本机历史状态仍未知。

本阶段达到验收标准。下项候选为版本绑定的有限范围原文读取，用路径、行号及源哈希支持按需恢复；默认完整任务包仍保持现状，不能在未验证依赖闭包前自动删减模型任务输入。实际文学验收、全量语义依赖及 OS 隔离继续明确未完成；不因它们需要作者输入而阻断独立工程工作。

差异阶段提交：`94d449f70584827e9c7ff0639114e257e7609f19`；推送退出 0，远程回读一致。

## 授权后的 GitHub API 脱敏诊断

用户追加授权在既有权限内诊断修复，不扩大网络或权限。检查 executor/cloud 技能目录及工作区，均未找到 `cloud-environment-runtime`，未假设存在其他凭据交付方式。`gh --version` 为 2.46.0；安全 auth 输出显示环境 GH_TOKEN 来源存在、账户 active，但登录验证失败。只确认代理配置存在，不打印任何环境值、token、完整 Git 配置或带凭据 URL。

- `gh api --include repos/ythyy9/Novel/pulls/1` 退出 1：`Get https://api.github.com/repos/ythyy9/Novel/pulls/1: Forbidden`。未获得 GitHub 响应头或响应正文。
- 无认证 `curl -I --max-time 20 https://api.github.com/` 退出 56：`HTTP/1.1 403 Forbidden`、`content-type: text/plain`、`server: envoy`，错误 `CONNECT tunnel failed, response 403`。
- 安全日志：`.local-validation/cloud-20261014/github-diagnostic.log`。没有 GH_DEBUG、Authorization 输出、绕过代理或变更环境权限。
- 证据支持代理 CONNECT 层拒绝；不能据 auth status 的 invalid 提示证明 token 无效，没有 GitHub 速率限制或仓库权限响应可供判断。最小缺口：环境管理侧核查既有代理对 `api.github.com:443` 的拒绝；若需新增域名许可或秘密，必须由聊天侧处理，本任务不自行扩大权限。此操作是网络拒绝，不是自动审批拒绝。
- PR 标题/描述更新尚未执行；父会话此前只读确认的 Draft 状态仍作为独立证据保留，不能写成本地权限恢复。Git 分支读写仍正常，工程继续。诊断新增 API 请求失败 1 次、auth 验证失败 1 次和无认证代理探针失败 1 次，均保留，不重复无信息请求。

## 接续阶段：有限范围原文读取

新增 `excerpt BOOK PATH [--revision REVISION] [--start-line N] [--line-count N]`。默认最多 100 行，返回固定版本、完整源哈希、总行数、实际行范围、逐行文本和 has_more。复用版本归属、路径及不可变快照校验；不改变模型任务包或审核门禁。范围必须为正整数，缺失文件、越界起点及跨作品版本拒绝。

实际命令 `python -m unittest discover -s tests -v` 退出 0：140 项、138 通过、2 Windows 专属跳过，19.717 秒。日志 `.local-validation/cloud-20261014/excerpt-final.log`。覆盖中文/emoji/空行、历史版本、末尾截断、默认当前版、无写入、非法参数与真实 CLI。本阶段无新增失败；工程失败运行累计仍为 3 次（4 个失败/错误用例），夹具返修 3 次，补丁上下文失败 1 次。静态审查和 `git diff --check` 通过。未运行模型或真人阅读验收。

下一工程候选：为任务恢复提供稳定分页的检索结果，明确版本与翻页边界，避免当前全量逐行输出随长篇规模增长；自动缩减模型输入和依赖闭包仍未实现，不将本阶段称为完整长篇上下文系统。远程 PR 管理等待环境代理检查，独立工程没有作者决策阻塞。

分段读取功能提交 `0e1a687cfdb15b8c57fba4b187008b03e05834c7`，推送退出 0；`git ls-remote --heads origin codex/v1-local-workflow` 退出 0，回读一致，工作区干净。本次接续三个功能阶段均已实际提交和远程验证。此段交接元数据另作文档提交，不需要重复已通过且源码未变的测试。

## 接续：稳定分页、真实接入与恢复验收

起点 `8a228f9adddecef73207c250f0dc2a9a8dfe9cfa`，工作区干净，沿用原分支。父会话确认同 SHA 的 PR #1 仍 Draft/未合并；本任务随后通过可用的 `github_get_pr_info` 连接器实际读取成功，PR 记录已含父会话补充的前轮结果。保留其内容，不重复代理探针，不把连接器成功写成 gh CLI 恢复。

分页：`search --page-size 1..1000 [--offset N]` 返回固定版本、查询、偏移、命中和下一偏移；后续页必须指定版本，避免当前指针变化造成翻页漂移；默认全量输出兼容。按路径和行号稳定排序，仅积累一页加一条命中，不建立索引、不限制单行字节数、仍读取完整快照。全量命令 `python -m unittest discover -s tests -v` 退出 0，142 项、140 通过、2 Windows 专属跳过，11.538 秒；日志 `paging-final.log`（同前日志根）。新增历史版本翻页、边界/非法参数、空结果、跨作品及 CLI 验证。

真实接入：`python -m novel doctor` 退出 0，ready=true，Codex CLI 0.159.2、ChatGPT 登录、所需 flags 可用；无模型偏好配置，未指定其他模型、未切换计费。`cloud-doctor.json` 是实际预检，但不代表执行成功。

在 `.local-validation/cloud-20261014/live-review/` 建立独立工程资料（没有正式作品），固定短夹具经控制器提交发布，再创建真实只读审核任务 **e8817187f6ef4170a03d65c39dd70e6e**。实际 `python -m novel --root <该目录> task-run e8817187f6ef4170a03d65c39dd70e6e --timeout 90` 退出 **1**，底层 Codex 退出 1；stderr 为 `Error: failed to initialize in-process app-server client: Read-only file system (os error 30)`，stdout 空，没有模型结果。

任务已真实保存 `blocked / tool_failure / attempts=1`；没有自动 resume、重跑或创建替代模型任务。摘要 `live-run-summary.json`；实际日志在 `live-review/runtime/tasks/e8817187f6ef4170a03d65c39dd70e6e/attempt-1/`。查看 CLI 帮助和本地可用说明，未找到已核实的独立运行写入目录方案；不修改 CODEX_HOME、不复制认证、不扩大文件系统权限。CLI 帮助明确 auth 仍依赖 CODEX_HOME，不能假定搬目录无影响。故真实接入以及依赖它的模型/联网研究验证停止，等待受支持运行配置或平台修复；其他工程继续。

按路线图优先补充完整停机备份恢复回归：复制 books/runtime/policies/methods/evaluations 到独立目录，真实新 CLI 进程运行 audit/handoff/eval-summary，核对停止原因、尝试/无进展计数、实验与源副本不变；删除恢复副本 books 后必须审计失败。没有使用本机私有资料，也没有把 agent 实验意见冒充人类反馈。

首次 `python -m unittest discover -s tests -p test_recovery.py -v` 退出 1（4 项，1 error）：检查恢复停止时误用 write，先触发既有“未通过不得写下一章”门禁。改用 revise 定向检验停止门禁，保留日志 `restore-drill.log`；没有改门禁。其后全量结果见下。

累计更新：工程失败运行 4 次（共 5 个失败/错误用例）、夹具返修 4 次；本轮另有一次文档补丁上下文失败，确认未修改后修正，补丁失败累计 2 次。真实 Codex 调用 1 次失败、重试 0、任务 attempts=1。此前网络诊断失败和本机未知累计状态全部保留。

剩余缺口和优先级见 `docs/remaining-acceptance.md`：区分必要可靠性/接入验证、已完成查询便利功能、缺作者输入/未同步资料的作品验收。停止无限扩展小查询；下一必要项为同一任务真实接入恢复，验收须有模型结构结果、控制器提交发布和回读，再谈审核检出/误报及研究 web 事件。

最终 `python -m unittest discover -s tests -v` 退出 0：143 项，141 通过、2 Windows 专属跳过，14.586 秒；日志 `.local-validation/cloud-20261014/reliability-final.log`。`git diff --check` 退出 0。差异审查确认未改原则、限额、原始反馈、自动重试或审核门禁；分页仅查询，恢复回归只操作隔离夹具。

功能与验收提交 `b2198a675b9e8d4be5ffe23383e924fafc22b48f`；Git 推送退出 0，远程回读一致，工作区干净。

本任务已实际使用现有 GitHub MCP 连接器：读取 PR #1 最新正文，保留父会话及既有内容，仅追加本阶段分页/恢复测试、143 项结果和真实 Codex 阻塞。`github_update_pull_request` 成功，随后独立 `github_get_pr_info` 回读正文完全一致，draft=true、state=open、merged=false、base=main、head=codex/v1-local-workflow，SHA=b2198a6，updated_at=2026-10-14T15:55:34Z。未改 base、Draft、reviewers 或发送评论。PR 管理已由既有连接器完成；gh 代理通道未恢复。

用户随后批准仅为 Novel 放行 api.github.com HTTPS443。工具发现未提供按域名修改本执行环境网络策略的接口，不能把通用网络/无沙箱权限当成窄域名授权。未申请全网、未改代理、未新加秘密、未作无信息重试。父聊天可通过环境管理入口处理；该网络问题与真实 Codex app-server 的只读文件系统阻塞分开保存。

## 初始化只读文件系统定位（未重试模型任务）

起点 `9b0a2b0cdcea53aaf3e54cd5cd1b230ab84dba72`，工作区干净。PR 管理默认使用已验收 GitHub 连接器，不再以 gh CONNECT403 停止 PR 工作；未改网络。

只读检查 CLI 0.159.2 帮助、已安装二进制的配置标识及官方[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。参考明确提供 `sqlite_home`（SQLite 运行状态）和 `log_dir`（日志）配置，同时说明它们不是托管云策略存储重定向；本次只对嵌套 CLI 进程传入配置，没有修改托管环境策略。参考未列出 installation_id 独立路径设置。没有推断未知私有 flag 的支持性。

两次**仅 app-server 初始化**诊断均使用 stdin=DEVNULL，没有 initialize/thread/turn 请求、没有模型 prompt，不执行 task-run；采用现有脱敏子进程环境。未改 CODEX_HOME、认证文件或沙箱。strace 只记录失败文件系统调用，不记录 read/write 数据、请求头或认证内容。

1. `strace -f -e trace=mkdir,mkdirat,openat -e status=failed -o <日志>/appserver-failed-paths.log codex app-server --stdio`，CLI 退出 1。stderr 明确：`failed to initialize sqlite state runtime under /run/codex-environment/codex-home`。本层跟踪未包含 open/chmod，所以不能据日志缺少 EROFS 推断文件系统可写。
2. 在授权工作区创建纯运行诊断目录，使用 `codex --strict-config -c 'sqlite_home="/workspace/Novel/.local-validation/cloud-20261014/codex-runtime-diagnostic/state"' -c 'log_dir="/workspace/Novel/.local-validation/cloud-20261014/codex-runtime-diagnostic/logs"' app-server --stdio`，配合 `strace -f -e trace=%file -e status=failed`。CLI 仍退出 1；工作区已产生 state_5、logs_2、queue_1、goals_1、memories_1 SQLite 文件，说明运行状态目录参数实际生效，但尚未完成 app-server 初始化。

第二次确切拒绝调用：

```text
chmod("/run/codex-environment/codex-home/tmp/arg0", 0700) = -1 EROFS
openat(4, "uid_map", O_RDWR|O_CLOEXEC) = -1 EROFS
open("/run/codex-environment/codex-home/installation_id", O_RDWR|O_CREAT|O_LARGEFILE|O_CLOEXEC, 0644) = -1 EROFS
```

`tmp/arg0` 对应先前非致命 PATH aliases 警告；运行状态重定向后末尾失败指向 Codex 安装标识 `installation_id` 的创建/读写打开。`uid_map` 同时表明环境内命名空间相关写操作被拒绝，未尝试调整。无法仅凭该跟踪保证修复 installation_id 后不再遇到其他限制。

日志根仍为 `.local-validation/cloud-20261014/`：`appserver-init.stderr`、`appserver-failed-paths.log`、`appserver-configured.stderr`、`appserver-configured-paths.log`。包装 Python 命令退出 0 是成功记录诊断，不是 CLI 成功；两次 CLI exit=1。纯运行目录留作诊断证据，未把局部有效的目录覆盖写入 Novel 适配器。

结论：SQLite/日志可在工作区生成，但完整初始化仍必须写当前 CODEX_HOME 下安装标识；没有找到保留当前认证原位且独立重定向该标识的官方支持配置。需平台提供符合当前只读挂载/身份边界的 CLI 初始化支持，或官方受支持的状态/安装标识分离配置。未申请提权、改挂载、重设 CODEX_HOME、搬认证、替换模型或削弱沙箱；不能宣称修复。

重新回读原审核任务：`blocked / tool_failure / attempts=1 / no_progress=0`，未恢复、未重试。audit 返回 database=ok、snapshots_verified=2、events=8。模型调用累计仍为此前 1 次失败、0 次重试；本轮新增初始化诊断失败 2 次（与模型次数分列）。源码及测试未变，不重复全套测试；工程失败/返修累计保持原值。下一必要动作由平台解决该具体运行边界，有明确修复证据后才按原任务协议恢复同一任务并单次验证。

## 独立必要修复：恢复审计的任务版本关联

起点 `18b4255dd6892ca5265e87206664986d665921c7`，同分支、工作区干净，远程一致。重新核对 AGENTS、路线图和剩余缺口；没有重跑模型或初始化诊断。分类保持：可自主修复已证实的控制器/恢复缺口；平台负责当前 Codex 初始化只读边界；作品和方法实际效果依赖作者输入及未同步原资料。

发现实际缺口：audit 原来只验证快照、审核关联与非空结果哈希，未覆盖所有任务的输入/输出版本关联。因此恢复副本中任务指向不存在或其他作品的版本时，SQLite integrity_check 和原 audit 仍可成功。此项属于路线图 1、2、6 的版本与可靠恢复要求，不是新增便利命令。

修复：所有任务必须绑定存在且同作品的输入；已存结果的 task_id/input_revision 必须匹配任务；输出必须存在、同作品且有完成结果，非审核输出的创建任务和父版本必须对应，审核输出必须为输入版本；完成任务不能缺输出。仅检测并拒绝，不自动改写或修复资料，不要求历史输入等于当前版本，不降低停止/审核门禁。

实际验证（日志 `.local-validation/task-version-audit/`）：

- 修复前 `python -m unittest discover -s tests -p test_engine.py -k audit_rejects -v` 退出 1；3 个测试中新增用例的 5 个损坏子场景按预期暴露缺口，日志 `before.log`。
- 修复后 `python -m unittest discover -s tests -v` 退出 0：145 项、143 通过、2 Windows 专属跳过，15.261 秒，日志 `after.log`。
- 随后补充完成任务输出缺失、同作品输入与结果身份错配断言，源码未再修改；同定向命令退出 0，3 项通过，日志 `final-targeted.log`。
- `git diff --check` 退出 0。复核历史任务/备份恢复测试保持通过；未改数据库 schema，未写原反馈、原则、限额或现有任务状态。
- 原真实任务 e8817187f6ef4170a03d65c39dd70e6e 回读仍 blocked/tool_failure/attempts=1；增强后的 audit 返回 ok、2 个快照、8 条事件。真实模型调用仍累计 1 次失败、0 重试；初始化诊断仍 2 次失败，没有新增探针。

累计：既有工程失败运行 4 次（5 个失败/错误用例）和夹具返修 4 次保留；本轮另加 1 次有意的修复前回归失败（5 个损坏子场景），修复后失败 0、实现返修 0。补丁上下文失败累计仍 2 次。未把环境重启或新回合当作计数清零。

下一必要项仍是平台支持的真实 Codex 初始化恢复，验收须保留同一任务累计次数并得到结构结果、提交发布及回读。当前审计缺口已经独立完成；没有证据支持再追加必要代码功能。长时间压力、自动上下文裁剪及其他客户端是后续扩展/验证，不代替真实模型与作品验收。

## 有界合成规模与恢复验证

起点 `6c2fdf739df29f9e00b3adabc3500fd4c4b47ee7`，工作区干净、远程一致。按用户追加授权独立验收路线图 1/2/6 的规模与恢复，不依赖被阻塞的模型。事前规定：100 文件×10,000 Unicode 字符、5 批提交、一次待发布返修；120 秒、512 MiB 地址空间、256 MiB 资料验收阈值。完整条件、复现及测量边界见 `docs/scale-validation.md`。

新增可复现脚本 `scripts/validate_scale.py`；两次实际执行均退出 0，首次 3.255 秒，审查加强超时进程组清理后最终脚本 4.010 秒。最终 RSS 工作进程 21,032 KiB、CLI 子进程 20,916 KiB；资料 28,421,864 字节。源/副本 7/8 快照，6 页检索无漏/重，完整备份恢复和交接一致、停止次数保留、待发布可接续、发布幂等、历史版本不变、注入损坏引用被拒绝。原始日志在 `.local-validation/scale-001/` 与 `scale-002/`。

没有产品缺陷，没有改限额/原则/沙箱或启动真实模型。新增规模运行失败 0；既有工程失败4次与夹具返修4次、修复前回归失败1次（5子场景）、补丁上下文失败2次、模型失败1次/重试0、初始化诊断失败2次均保持，不清零。原真实任务未操作。产品源码未变，本轮验证新脚本，不重复上一阶段145项单元测试。`git diff --check` 退出0。

剩余：本规模下进程死亡/断电、长期并发、丰富状态引用及版本膨胀未验证；单次合成数据测试不能等同长期或文学通过。目前未发现新的必要产品代码缺陷。下一高优先级仍是平台解除已定位的真实接入边界，并在原任务上验证结构结果、提交发布回读；不通过另建模型任务清零或新增便利功能代替。
