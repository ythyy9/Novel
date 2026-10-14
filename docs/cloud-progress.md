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
