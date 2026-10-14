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
