# 第一版使用说明

这是本地命令行系统：作品文件、任务、停止原因、版本和反馈保存在自己的资料目录中。第一本作品的题材、书名、人物和设定仍需作者提供；以下书籍标识、任务编号和路径都是操作示意，不代表已经选定作品。

## 启动与资料目录

控制器及 EPUB/TXT 参考处理使用 Python 3.11 或更新版本的标准库。从源码仓库根目录运行，不需要 `pip install`；参考 PDF 抽取可选依赖 `pypdf`。`task-run`、参考书联网阅读流程及创建绑定参考资料的任务需要 Codex CLI 和可用的 ChatGPT 登录；不要为运行本系统配置付费 API key。

```powershell
Set-Location F:\Novel
python --version
python -m novel --help
python -m novel init
python -m novel doctor
```

`init` 创建本地 SQLite 数据库、缺少的目录和默认额度策略，并复制缺少的内置原则及写作、审核、研究方法文件，不调用模型，也不会覆盖已有策略或方法。`doctor` 检查 CLI 参数、ChatGPT 登录和可读取的模型偏好；`ready: true` 表示前置检查通过，不保证当前额度足够或一次模型任务必然成功。

默认资料根目录是当前目录。需要将私有作品与源码分开放置时，仍从源码根目录启动，并在每条命令的子命令之前加入 `--root`：

```powershell
python -m novel --root 'F:\MyNovelData' init
python -m novel --root 'F:\MyNovelData' books
```

以下示例省略 `--root`，使用仓库根目录。输入文本文件使用 UTF-8，允许 BOM；命令返回 JSON，阅读正文的 `read` 返回原文。错误写入标准错误，退出码为 `1`。

## 建立作品与作者输入

书籍 ID 使用 1–64 个小写英文字母、数字、连字符或下划线，避开 Windows 保留名。把下面的占位内容替换为作者实际确定的信息：

```powershell
$bookId = 'your-book-id'
python -m novel book-create $bookId --title '填写作者确认的书名'
python -m novel decision $bookId --text-file 'C:\path\author-decisions.txt'
python -m novel reference-import $bookId --text-file 'C:\path\reference-material.txt'
python -m novel book-show $bookId
python -m novel files $bookId
```

`decision` 保存作者原话和明确授权的决定；`reference-import` 保存作者指定、可使用的参考材料原文。二者各自生成追加记录，并创建新版本。参考材料不会自动成为新作事实。不要把 Agent 的建议用 `decision` 冒充作者决定。

整本参考书使用 [`reference-add` 自动流程](reference-library.md)，会检查整个系列、番外和附录并分析全部实有内容。`reference-use --book <作品ID>` 把来源及缺口报告绑定到作品；之后 CLI 创建任务前会检查更新。找不到全文时继续已有分析，不以节选冒充完整；`reference-status` 可只读查看覆盖和缺口。

录入决定或参考材料前，应完成或取消该书的 `running`、`submitted` 任务。导入会改变输入版本：若原任务正在等待作者决定，应先保留交接信息，录入真实决定，再取消已经过期的原任务，基于新版本创建接续任务。不要反复恢复旧版本任务。

空作品的初始版本，以及尚无正文时的资料导入版本，标为 `accepted`，用于允许启动第一章；这不是作品质量已经通过验收。

## 写作、审核和阶段通过

每次显式调用只运行一次尝试。创建任务会固定当前输入版本及 `policies/`、`methods/` 的内容哈希；准备任务包时将实际原则与方法放入 `policies_and_methods`，供执行者在运行边界内遵守。

```powershell
python -m novel task-create $bookId write --instruction-file 'C:\path\chapter-instruction.txt'
```

从返回 JSON 取出 `id`，再运行：

```powershell
$taskId = '替换为返回的任务编号'
python -m novel task-run $taskId --timeout 600
python -m novel task-show $taskId
python -m novel handoff $taskId
```

`task-run` 会领取排队任务、增加累计尝试数、导出固定任务包、调用 Codex，验证结果并提交候选。成功后任务是 `submitted`，当前正文尚未切换。检查 `result.changes`、`unresolved` 和状态记录后，执行本地发布：

```powershell
python -m novel task-publish $taskId
python -m novel book-show $bookId
python -m novel read $bookId manuscript/001.md
```

`task-publish` 只更新本地资料库，**不上传 GitHub，也不公开发布小说**。写作或返修结果会成为新的 `draft` 版本，任务变为 `completed`。

随后创建独立审核任务。它读取当前版本，只提交审稿记录，不修改正文：

```powershell
python -m novel task-create $bookId review --instruction '审核全部现有正文：连续性、人物、世界合理性和阅读体验；分别记录错误、疑点和体验判断。'
$reviewId = '替换为返回的审核任务编号'
python -m novel task-run $reviewId --timeout 600
python -m novel task-show $reviewId
python -m novel task-publish $reviewId
python -m novel assess $bookId
```

审核覆盖全部当前正文、没有阻断项，并且没有仍在执行、已提交或停止的任务时，操作员可以执行：

```powershell
python -m novel accept $bookId
```

`accept` 是版本的流程阶段通过，不是作者已经读过、喜欢或认可文学质量的证明。实际作者反馈要另行记录。审核中的已确认错误、重大合理性疑点、未决项和缺失的正文覆盖会阻止通过。发布新的审核证据会把同一版本重新置为 `draft`，需要重新评估。

当前版本通过后才能创建下一次 `write`。需要修改现有稿件时使用 `revise`；返修必须同时提交正文和 `canon/state.json`，覆盖相关章节与状态。返修生成新版本，旧版审核不会自动覆盖新版，须重新审核。

普通、可逆的剧情候选可以由 Agent 自主选择，但必须留下 `agent_selection` 理由记录，并让采用后的状态同时引用选择记录与正文。标记为作者 `undecided` 的事项仍需真实的作者决定；不能把重大、锁定或未获授权事项自行改称普通候选。具体字段见 [协议说明](protocol.md)。

## 研究与手动提交

当知识缺口阻碍推演或审核时，创建 `research` 任务，明确问题、必要前提和受影响内容：

```powershell
python -m novel task-create $bookId research --instruction-file 'C:\path\research-question.txt'
```

同样通过 `task-run`、检查结果、`task-publish` 完成一次研究。适配器仅为 `research` 启用内建 live 网页搜索；其余任务禁用搜索。研究必须保存来源、适用条件、不确定性和影响范围，不能为既定剧情寻找借口。配置支持搜索不等于某次检索已成功：以该次 JSONL、实际来源和结果回读为证。代码中的来源格式校验不能证明网页内容真实或结论成立。

研究发布也会产生新 `draft` 版本；有正文时需按当前版本重新审核。缺少外部证据时允许明确记录推断和缺口，不能将它写成已核实的外部事实。

也可以在已授权的其他执行环境准备候选，再通过相同协议提交：

```powershell
python -m novel task-claim $taskId
python -m novel task-prepare $taskId
python -m novel task-submit $taskId 'C:\path\result.json'
python -m novel task-publish $taskId
```

这条路径与 `task-run` 二选一，不要再次领取已经 `running` 的任务。`task-prepare` 只能用于已领取任务。结果协议见 [协议说明](protocol.md)，相同结果重复提交、已完成任务重复发布是幂等操作；同一任务不能换一份不同结果覆盖原提交。

## 中断、停止与接续

```powershell
python -m novel tasks --book $bookId
python -m novel handoff $taskId
```

`handoff` 验证实际输入文件和已存结果，显示输入是否仍为当前版本、规则是否一致、完成步骤、改动文件、未决项和下一步。任务次数、停止原因和结果保存在 SQLite，不因换会话清零。已经发布完成的写入任务，其输入自然可能不再是当前版本；同时核对 `result_revision`，不要把正常的版本前进误判为运行失败。

| 情况 | 操作 |
| --- | --- |
| 明确等待决定、额度不足、无进展、工具故障或授权限制 | `task-stop TASK REASON --note '具体原因'`；REASON 为 `decision`、`quota`、`no_progress`、`tool_failure`、`authorization` |
| `running` 任务因宿主中断而遗留，尚无可用结果 | 确认该次 CLI 已退出后，`task-recover TASK --note '中断与处理情况'`，将其记录为工具故障停止 |
| 停止原因已解决，输入版本和规则仍一致 | `task-resume TASK --note '如何解决'`；回到 `queued`，再显式 `task-run` |
| 输入或规则已变化、次数耗尽、任务不再需要 | `task-cancel TASK --note '原因与接续位置'`，保留历史，再按授权创建当前版本的新任务 |
| 已有完整 `result.json`，任务仍是 `running` | 先核对日志、输入和结果，再 `task-submit`，不必重复调用模型 |

`task-stop`、`task-recover`、`task-cancel` 修改队列状态，**不会终止仍存活的 CLI 进程**。适配器自己的超时会清理本次进程树；若记录为 `cleanup unconfirmed`，必须先处理那个确切进程，再接续，不能把状态恢复当成进程已经结束。

默认每个任务最多领取 `3` 次、累计记录 `2` 次 `no_progress` 后耗尽；结果限制为规范 JSON 的 `2,000,000` 个 UTF-8 字节。`exhausted` 不能直接恢复。系统不自动循环重试。

同书存在 `blocked` 或 `exhausted` 任务时，其他任务不能领取、提交或发布，也不能阶段通过或回滚；显式解决或取消后才能继续。写作、返修、研究同书同一时间只能有一个活动写入者。审核虽有单独任务身份，不能通过新建审核绕过同书停止状态。

修改 `policies/limits.json` 或 `policies/`、`methods/` 中任何文件，会使旧任务在领取、提交、发布、恢复时因规则哈希不一致而被拒绝；旧规则审核也不能直接支持新规则下的通过。它不会自动重写旧任务状态。修改后应保留原始依据并显式安排新任务，不能靠降低标准宣布原任务通过。

## 查阅、反馈与回滚

```powershell
python -m novel books
python -m novel search $bookId '关键词'
python -m novel read $bookId manuscript/001.md --revision '替换为完整版本哈希'
python -m novel feedback $bookId --text-file 'C:\path\author-feedback.txt' --source author
python -m novel feedback $bookId --text-file 'C:\path\reader-feedback.txt' --source target_reader
python -m novel audit
```

搜索是当前作品版本的逐行、不区分大小写文本检索，不是语义检索。反馈保留原文、来源和当时版本，不自动改正文，也不能把 Agent 自评录成作者或目标读者反馈。`audit` 检查 SQLite、登记快照、版本关联、结果哈希和审核证据一致性，不评判小说质量。

需要回到旧内容时，先完成或取消活动任务，再执行：

```powershell
python -m novel rollback $bookId '替换为该书历史版本哈希' --note '具体回退原因'
```

回滚以旧内容创建新的 `draft` 版本，保留当前历史链，须重新审核；不会删除后续历史或把旧版通过状态直接复制回来。

## 返修前的显式引用影响查询

```sh
python -m novel impact BOOK manuscript/001.md
python -m novel impact BOOK manuscript/001.md --revision REVISION
python -m novel search BOOK '证据原文' --revision REVISION
python -m novel search BOOK '证据原文' --page-size 50
python -m novel search BOOK '证据原文' --revision FIRST_PAGE_REVISION --page-size 50 --offset 50
python -m novel diff BOOK OLD_REVISION --to-revision NEW_REVISION
python -m novel excerpt BOOK manuscript/001.md --revision REVISION --start-line 20 --line-count 40
```

返回实际查询的版本、源文件 SHA-256，以及 `canon/state.json` 中引用该文件的记录：分区、稳定 ID、陈述、知识类别、持有者和精确原文证据。默认查询一次固定的当前快照，也可查询同一本书的历史版本；文件不存在或版本属于其他作品会报错。命令不改变任务、重试次数、审核状态或作品版本，不调用模型。

输出还包括 `research`：所选快照中 `affected_paths` 包含目标文件的研究记录（完整保留来源、条件、不确定性和声明类型）；以及 `reviews`：覆盖目标文件且绑定同一版本的已发布审核。每份审核保留完整覆盖、维度、发现和任务未决项，`controls_match` 表示是否匹配查询时的控制版本。旧控制版本审核仍可查看，但不能作为当前门禁证据；旧作品版本审核不会混入新版本。

这是返修前核对依据的入口：逐条检查证据是否仍支持原陈述，再安排必要的状态更新和审核。空列表仅表示没有相应显式记录，不能表示无需跨章复核；正文的隐含因果不在本查询范围。候选、误解和人物所知保留原类别，不会因此升级为作品事实。研究声明影响不等于结论已被采用，审核覆盖也不等于审核通过；是否可通过仍由 `assess` 和 `accept` 的完整门禁决定。

`diff` 比较同一本书的两个不可变快照；省略 `--to-revision` 时固定为查询开始时的当前版本。返回按路径排序的新增、删除和修改清单，以及前后 SHA-256；不存在的一侧为 `null`，内容相同的文件不列出。反向比较历史快照也可能产生“删除”，这不表示命令删除了文件。两端快照都经过完整性与作品归属校验。命令只比较内容，不判断正文质量、语义影响或是否通过审核，可配合两个版本的 `impact` 分别回查依据。

`excerpt` 按 1 起始的行号返回有限原文，默认从第 1 行读取最多 100 行。结果携带固定版本、完整源文件哈希、总行数、实际终止行、带行号的文本及 `has_more`。行数不足时返回到文件末尾，不补齐、不改写；范围必须为正整数，起始行超出文件时报错。输出行文本不含换行符，若需要完整原始文本仍使用 `read`。这些只读入口支持操作员按需检索；目前模型任务包仍携带完整版本，不自动截断研究依据或状态依赖。

`search --page-size` 返回固定 `revision`、原始查询、`offset`、`matches` 和 `next_offset`；结果按路径及行号排序。每页 1–1000 条，末页 `next_offset` 为 `null`。继续翻页必须沿用首个结果中的版本和同一查询，并显式提供 `--revision`，避免当前版本变化引起漏项或重复。不指定分页参数时保留原列表输出。分页限制输出条数，不限制单行长度；目前仍需读取整个快照，尚不是大型检索索引。

## 存储、备份与权限边界

| 路径 | 内容 |
| --- | --- |
| `books/<book-id>/versions/<revision>/` | 不可直接修改的完整内容快照，内含 `manifest.json` 和正文、状态、来源等文件 |
| `runtime/novel.sqlite3` | 当前版本指针、队列、累计尝试、提交结果、审核、反馈、事件；使用 SQLite WAL |
| `runtime/tasks/<task-id>/attempt-<n>/` | 固定任务包、Schema、prompt、运行标记、Codex JSONL、错误日志和模型结果 |
| `policies/`、`methods/` | 运行约束和方法文件；共同参与任务控制哈希，并导出到模型任务包 |

不要直接编辑版本快照；内容哈希会检出改动。常规修改通过任务结果或明确的作者录入命令产生新版本。SQLite 事务和先写快照后切换指针保护本地一致性，不能抵御同一用户账户故意改写控制程序或全部存储。

备份应在全部写入者停止后，成套保留 **`books/`、`runtime/`、`policies/`、`methods/` 和实际存在的 `evaluations/experiments/`**；同时保存对应源码版本。若存在 SQLite 的 `-wal`、`-shm` 文件，不要只复制主数据库后遗漏它们。恢复到独立目录后运行 `audit`，并对实际实验执行 `eval-summary`，再接续。仅备份 Git 仓库或仅复制正文都不能恢复完整工作状态。

本仓库的 `.gitignore` 忽略 `books/`、`runtime/`、本地验收目录和常见凭据文件，因此提交代码不会自动备份私有作品或模型日志。`policies/`、`methods/` 可被 Git 跟踪，勿在其中放凭据或不准备提交的私密原文。改用外部 `--root` 时，资料目录的 Git 规则由那个目录自行管理。

模型结果没有作者决定、原始参考导入、反馈录入、阶段通过或规则修改的权限字段；操作员命令承载这些动作。这个区分是可检查的控制器协议与执行流程，不是人类身份认证或完整操作系统权限隔离。使用者必须具有相应作者授权。
