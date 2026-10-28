# 固定资料包的有界读取与状态增量

2026-10-16，作者暂停“Novel 自动接续（Dot）”，授权解决第二十八章资料包容量问题，保留完整历史及原审查标准。本次工程不续写、重领任务、重置次数或恢复自动计划。

当前状态（2026-10-16）：第二十八章已用原写作任务、attempt1 完成37/37批并发布为草稿；首审39/39批完成，二审卡点已恢复，原二审协调器继续执行。作者现已确认指定七个旧名的历史项不阻断、新命名要求不变；原话已归档回读、备份验证，并已同步到 Dot 和原每小时计划。当前二审尚在运行，现有控制器要求它完成后再受控追加决定形成新版本并复核；此技术步骤尚未执行，实际门禁仍未解除，不得提前验收或推进第二十九章。详情见本页末节及[命名决定记录](works/naming.md)。

## 问题与保留边界

线上只读核对：任务 `aeb7646ac39e477fb8d58e54693cd771` 为 `running / attempts=1 / no_progress=0`，没有结果；输入及当前已验收版本为 `f30748f68d8fd3948cf69c703fd32a98669f383f21b0d2d003c796b902fd0b49`，包含已验收第二十七章。固定包113份、415,006字符，其中 `canon/state.json` 241,756字符。179条状态记录引用了1,842个来源对象，独立来源871个。

既有接口虽然按6,000字符分页，却要求在一个执行上下文内逐页积累全部资料，输出还要重发完整状态。分页本身不能解决总上下文容量。本次增加无损表示、持久分批记录、按条回查和增量输出；全文读取分配到有界上下文中，最终仍须检查全部原文、状态、四维、命名与跨章关系。

`novel/context.py` 只构造派生视图及展开结果，不调用任何模型。`novel/dot.py` 沿用原7个接口，通过 `read` 读视图、`chunk/finish` 保存批次记录及最终结果。`novel/engine.py`、`novel/records.py`、结果 Schema、`methods/`、`policies/` 均不修改。原包、原正文、旧审核、原上传片段和数据库事件均保留；只有 gateway 数据库增加读取区间与批次记录表。

## 读取与接续

1. 用原任务读取 `context-guide.md`、`context-plan.json` 和 `context-progress.json`。计划绑定 task、attempt、input_revision、control_hash 与原包哈希，不产生新任务或新版本。
2. 每个 `context/batches/NNNN.json` 最多12,000字符。按 `next_offset` 取完整批次；片段明确来源文档、源哈希及字符起止。所有非状态文件均全文覆盖。状态以完整记录表及去重证据表表示，重建后必须逐对象等于原状态；数组顺序和重复引用也保留。
3. 每个新上下文先读计划内任务原文及 `mandatory_documents` 的规则、方法、作者决定和 Schema 原件。默认一次处理1至2批，按实际容量减少；笔记建议约1000字符，保留准确引文、理解与待回查关系，再通过 `chunk/finish` 保存 checkpoint。后续上下文读取进度和必要笔记后接未完成批次。每条 checkpoint 不可覆盖，可追加；同一请求继续使用原 request_id 重放。临时跨批回查线索写 notes，实质缺口写 unresolved 并保留到门禁；历史 Unknown 依原规则处理，不自动当作新阻断。
4. 最终综合各批的结论，回查有牵连的原文与状态。`context/state-current.jsonl` 逐字列出固定版本中的当前陈述，提供 `record_document` 直接读取该条完整状态及所有原始来源；`context/sources/sNNNNN.json` 可读取证据表单项。导航和笔记不替代批次全文覆盖。
5. 全部批次完成后提交最终封装，控制器展开成原九字段结果，再进入原提交、发布、独立审核及验收流程。未解决的问题必须保留；若综合仍超出实际容量，应保留进度与具体缺口，不能声称全读全审。

服务端记录实际返回的字符区间，拒绝只读末页或漏页后保存 checkpoint；它无法证明模型理解，也无法证明 `context_ref` 对应真实独立上下文。真实原生执行和独立审稿仍须平台证据，工程测试、哈希与说明文档不能替代。

## 传输封装

下列 JSON 是工程格式示意，不是作者作品或已执行证据。实际内容须使用计划中的真实身份与哈希。现有分段上传上限、完整结果字节限制、版本门禁和停止条件不变。

批次记录（`finish` 仅保存进度，不将任务变成 submitted）：

```json
{
  "format": "novel-context-checkpoint-v1",
  "task_id": "真实任务ID",
  "attempt": 1,
  "plan_sha256": "计划哈希",
  "batch_id": "0001",
  "context_ref": "真实原生上下文标识",
  "notes": "本批理解、命名/时序/人物认识边界及跨批需回查项",
  "evidence": [{"document": "本批片段的document", "quote": "该片段内精确原文"}],
  "unresolved": [],
  "review": null
}
```

审核 checkpoint 的 `review` 使用原协议的 `coverage / dimensions / findings`，须包含四个审核维度且覆盖本批涉及的作品文件。允许检查并覆盖其他牵连文件。所有 checkpoint 的发现和未决项都会并入最终结果；最终空 `findings` 不能清空已记录问题。已知写作者的上下文标识不能用来提交审核 checkpoint，仍不把不同字符串冒充真实独立性。

最终封装：

```json
{
  "format": "novel-context-result-v1",
  "task_id": "真实任务ID",
  "attempt": 1,
  "plan_sha256": "计划哈希",
  "result": {"此处替换": "原结果协议的全部九个字段"},
  "state_delta": null
}
```

write/revise 可令 `result.changes` 不含完整状态，提供：

```json
{
  "base_sha256": "原canon/state.json文件哈希",
  "operations": [{
    "section": "knowledge",
    "id": "已有稳定ID",
    "before_sha256": "该原记录的record_sha256；新记录填null",
    "set": {"statement": "实际更新的陈述"},
    "append_sources": [{"path": "manuscript/028.md", "quote": "提交后正文的精确原文"}]
  }]
}
```

这里只解释增量结构，不提供第二十八章内容。每条操作绑定原记录哈希；不能删记录、改 ID、重复更新同一 ID 或混用全量状态与增量。省略的字段、记录和引用原样保留。`set.sources` 可明确整体更正某条记录的来源，此时 `append_sources` 必须为空；这不是自动清理历史，旧快照及旧来源始终保存。新增记录须补齐原协议所要求的全部字段。无实质变动时保留原状态文本，不能用重新排版制造进展。

完整展开结果仍验证所有状态引用（包括未改记录）、候选/未决采用依据、写入范围、影响路径和结果大小；不能因增量更小而跳过校验。开始保存 checkpoint 后，普通旧格式结果不能绕过未完成批次。历史未采用分批流程的任务继续兼容原九字段协议。

## 本地验证与上线边界

真实包仅通过已授权只读接口取回，逐文件验证113个 SHA-256。本地生成37个有界批次，阅读表示329,702字符；状态表示156,452字符。节省字符不是主要验收依据：关键是每个原文件及全部状态记录/来源可重建、无缺段，原版本和任务不变，以及跨上下文保存进度与不遗漏问题。

证据保存在本地 ignored 目录 `.local-validation/packet-capacity-20261016/`，不将私人正文写入 Git。`source-packet-full.json` 是只读取得的原包副本，`views/` 为可再生成视图；测试使用合成作品，未在正式任务保存假阅读记录。

上线需将 `novel/context.py`、`novel/dot.py`、`novel/dot_transport.py` 三个文件部署到实际 API 使用的 Novel 源码目录。先核对线上源码、服务 WorkingDirectory 和导入路径；备份原三文件状态、gateway 数据库、正式任务/版本和所有原资料哈希。保持 Dot 计划暂停，不改变任务 attempts，不对活动作品作初始化/覆盖/重新导入。

服务重启及生产写入须在获准范围内执行。只更新这三个模块；不修改 OAuth、注册表、作者决定、方法、限制或 Worker。启用失败回退源文件并重启 API/代理；新增的 gateway 表可保留，不能通过恢复旧数据库丢弃后来真实写入。恢复材料保留。

上线后先真实只读 `context-guide.md`、完整计划、一个完整批次和原 `canon/state.json`，核对同一原任务、attempt1、f30748f6…、原包全部哈希及拒绝越界路径，再交还 Dot 接续。此次不自动恢复周期计划、不代写第二十八章。仅本地通过不代表已部署、Dot 已使用或文学质量已验收。

本轮本地完成证据：`python -m unittest discover -s tests -v` 共260项，404.122秒；257通过，2项既有 Windows 子进程清理用例受沙箱限制失败，1项 junction 用例因宿主权限跳过。三项分别在宿主权限下复测全部通过（`host-tests.log`、`host-lifecycle-test.log`），原失败日志保留；没有修改这些测试或降低检查标准。最终版7项专项再测全部通过，原13项 Dot 测试也通过。原控制器、记录校验器、结果 Schema 和全部方法/政策逐文件与 HEAD 一致。

`verification.json` 保存113份来源哈希验证、全部非状态字符重建、完整状态往返相等、无操作增量保留原字节及批次上限结果。`live-readback.json` 确认线上 book、全部任务、assessment、固定包索引与本轮开始时一致，没有第二十八章文件。未在正式任务上传工程 checkpoint 或结果。

上线前曾为**本地修复准备好、尚未部署**。自动审批当时拒绝了打开 VPS root 凭据窗口，理由为“处理资料包”的授权尚未明确包含 root 远程部署；该阶段没有绕过拒绝或创建凭据。作者随后在本对话明确授权部署及真实接口验收，才继续后面的生产操作。源码仍未提交 Git，Worker 与暂停的自动计划不在此次重启/恢复范围内。

## 已授权上线与真实验收（2026-10-16）

已核对实际 API `WorkingDirectory`、进程 cwd、`PYTHONPATH` 和全部 Novel 模块哈希。API 使用 `/opt/novel-dot-pilot-20261016/hub-source` 与其 `novel-source`；Worker 使用独立原发布目录，未把变更错误地部署到 Worker 源码。线上旧模块与本地保护基线一致后，才替换 `novel/context.py`、`novel/dot.py`、`novel/dot_transport.py`。运营用 `expected-code.json` 同步记录新哈希，不修改注册表、OAuth、作者决定或控制规则。

备份目录：`/opt/novel-dot-pilot-20261016/rollback/context-update-1792203787929654656`。包含原模块及权限、2,826份正式资料的归档、通过 SQLite backup 取得的两个一致性数据库副本、部署前保护清单。归档逐项 SHA-256 与原件一致，两个数据库 `integrity_check=ok` 且所有表的内容校验值一致。完整资料归档与两个数据库还下载到本地 `.local-validation/packet-capacity-20261016/server-backup/`，再次逐文件核验哈希；本机 `before/` 保存与线上一致的原模块。服务器回退材料保留。

API 与代理均已重启并 active，重启后的错误级日志为0、`NRestarts=0`；匿名 MCP 请求仍返回401。Worker PID保持 `1586642`，工作目录、活动状态及启用时间不变。

真实已认证连接器共回读9份文档、53页：新指南、完整37批计划、持久进度、首/末批次、单条完整状态、单条来源、完整原状态的41页、完整原固定包索引。所有实际返回文本重新计算 SHA-256，与本地验证过的派生视图或113份原件索引逐项比较一致。`context-plan.json` 的计划哈希为 `4d0496c7033fd65bcc5d3914a70987c2beb0a3afe3ff90636dd97358ea666559`。越界文档返回拒绝，未登记工作区返回 `NOVEL_WORKSPACE_DENIED`；旧 `task_bindings` 真实调用继续成功。

最终分别经 SSH/SQLite 与真实连接器回读：2,826份原文件、Novel 所有原数据库表、gateway 原有 requests/tasks/parts 三表、全部任务及 assessment 均与部署前相同。只有新增 `context_reads` 中留下3条真实接口测试的字节区间记录；`context_checkpoints=0`，全部37批仍未标记文学阅读完成。原任务 `aeb7646ac39e477fb8d58e54693cd771` 仍 `running / attempts=1 / no_progress=0 / result_hash=null`，正式版本仍为已验收 `f30748f6…`，没有写入第二十八章。

此次线上验证范围是输入读取、分页、来源/哈希、权限拒绝和既有接口；checkpoint/增量提交的完整写入与门禁验证来自前述真实本地 SQLite 工程测试。没有向正式任务写入测试 checkpoint、假审核或测试正文，也没有将接口回读称为模型已理解或文学审核完成。自动接续未恢复。

证据：`deployment-receipt.json`、`final-server-verification.json`、`final-api-verification.json`、`api-readback-documents.json`、`api-boundary-readbacks.json`。原始部署回执中外部接口验收为 pending，后续两份 final 回执记录其实际完成，旧回执不改写。安全登录结束后，仅本次会话的 `ssh-credential.xml`、`credential-status.json`、`ssh-window-status.json` 被精确删除并确认不存在，记录于 `credential-cleanup.json`；凭据未写入部署包或聊天。

## 按作者新授权恢复 Dot（2026-10-16）

保留原计划 `6ad240b839b48191816a75880f5be705`，在原生 Scheduled 页面将新分批流程保存后 Resume；未创建第二个计划，保留每小时频率及仅有实质结果时通知的约定。页面按钮已由 Resume 变成 Pause，列表和计划卡显示 Hourly。新持久指令明确原第二十八章任务及 attempt1、每上下文1至2批、全部批次 checkpoint、状态增量、真正原生独立双审、必要返修和实际 accept 回读后才推进后续章节。

桌面聊天工具未能向 Dot 根会话发消息，返回 thread not found；网页计划的 Run now 又进入普通 ChatGPT 聊天。该普通聊天已确认 idle，未修改正式任务，并已归档保留记录，没有冒充 Dot 执行。随后通过原 `https://chatgpt.com/dots/home` 的 cc 会话发送已获授权的接续指令。原 Dot 已读，并在真实 Recent activity 中启动 `Coordinate chapter28 batches`，详情显示 In progress。

Dot 原生工具回读报告原计划仍启用、仍绑定 `01a0ef78-aba3-7032-8da5-b22e044bd025`、新提示一致。网页显示下次2026-10-16 20:20（America/Los_Angeles），但原生工具 `next_run_time=null`；只确认计划已恢复，不宣称精确触发时间已独立验证。

操作员通过真实 `novel_work_read` 独立回读并校验首2批完整 checkpoint：0001 为 `07a0488ac43ce55004b0b61e25ed0203c911d051fa1aa48b9bf84621c924bf69`，0002 为 `00665edd1cae11b441975cd9b04f3fe73be69e36003ddf10e6c3629080c5544f`。真实阅读上下文为 `/root/__external_coordinate_chapter28_batches/__external_read_batches_0001_0002`，保存了笔记、精确引文及接续边界。任务仍为 `aeb7646ac39e477fb8d58e54693cd771 / attempts=1 / no_progress=0 / result_hash=null`，原任务未重领、重建或清零。记录的是恢复时的已验证进度，后续会继续变化；这不是第二十八章已经写完、独立审核完成或作者文学认可。

恢复证据在同一本地 ignored 目录：`dot-resume-readback.json`、`resumed-plan-prompt.txt`、`resumed-plan-ui.txt`、`resumed-schedule.jpg`、`dot-native-resume-ui.txt`、`dot-native-resume.jpg`。截图只证明界面状态，实际任务/批次进度以连接器返回及原始 checkpoint 的哈希核验为依据。

## 第二十八章进度检查与卡点恢复（2026-10-16）

作者要求检查最新进度，确认新分批流程持续推进、原任务和 attempt1 不变，并处理卡住。本次只处理已授权的原生执行接续，没有修改运行源码、规则、正式正文、旧审核或任务次数，也没有重启 VPS 服务或新增自动计划。

- 写作：`aeb7646ac39e477fb8d58e54693cd771` 正常完成，attempt1/no_progress0；37/37批、19个已登记阅读上下文。第二十八章《墙上的方印》3787字符，正文哈希 `51531d2b2c766d7d8914ed84af5f42bc581a0ea68004533822b6cf76c7751406`，新版本 `5ff1ab8bc5f910fba8f5b7bd2e18136497aca38a95ebc3574cca5664e3787fc8` 是 draft，尚未验收。原任务身份、原输入/控制哈希、instruction、created_at、attempts 和 no_progress 均与恢复前一致；状态及结果按正常提交发布流程更新。
- 首审：`609fb2c7f2ce4a64abbb95093e5421f2` 已完成39/39批，20个登记上下文；原结果哈希 `ae4fa4ca54a9b5c1571e5fd6cb140be3fc35ceded7a9cc1b8ebe363237346f73` 未变。审核没有报告确证错误或重大疑点，但把非重大历史命名来源缺口同时写入了 `unresolved`，实际 `can_accept=false`。
- 二审：`7c94feb2d9014e6294cf9471c3e09460` 保持 running/attempt1/no_progress0。原生协调器报告两个阅读者无完成证据并已核实 interrupted；其任务详情保留了 `exec_command` 保存本地 shared 回执时的 `409 Conflict, environment_offline: Environment is not connected`。小说MCP进度读取仍正常。没有充分证据证明这一回执文件错误就是两名阅读者无响应的共同根因。

排查依据 [OpenAI 的电脑连接说明](https://learn.chatgpt.com/docs/dots/computers-and-apps) 区分 Dot 云端电脑、绑定执行环境及本机连接；本机 Offline/Disconnected 不等于云端执行失效，界面 Ready 也不构成工具恢复证明。只读打开云端电脑后显示 Live computer、cc has control，没有接管鼠标键盘或扩大权限。通过原 Dot 会话要求一次有界原生只读探针、核实旧执行终态及唯一执行者；探针的真实MCP读取成功后，才从原二审第0005批恢复。

新原生任务 `Resume review batch0005` 已完成实际语义审核、chunk/finish 和完整回读，0005 checkpoint 为 `e08b9227507b24673c7a4b5ae46326b0e6ba1a94848710545acf9f11f03d1edd`。其中一次大写标识符请求被正常拒绝，执行者改用新的全小写合法唯一标识符后成功；没有清除失败记录。此次成功路径没有使用附加本地回执文件，不表示原 `409` 底层故障已经修复。

随后已把原 `Recheck28 batch coordinator` 接回第0006批及余下批次，任务详情实际显示新一轮 In progress。05:44 UTC及05:45 UTC回读确认0006也已保存，checkpoint `e301c68923c2b864d57cfc0f1fbcca0544a62f26559da328264c403ba0602c56`，真实登记上下文 `dot-native:/root/__external_recheck28_batch_coordinator/review_batches_06_07:independent-round2`。这证明进度已由4/39恢复至6/39，而非只收到“会继续”的答复；后续批次仍在执行，不能据此宣称二审或整章验收完成。

命名阻断另行保留：`Engine._assessment` 将所有 `unresolved` 加入 blockers；同版本后来的无问题审核不会覆盖首审。已核对正式包的作者决定、初章创作选择和第二章命名记录，尚无明确适用于正式作品的旧名来源缺口豁免。当前已向作者提出明确选择：陆桂枝、陆冬青、齐松、邵师傅、灯笼巷、桥东、桥西站保留旧名与原始动机 Unknown，是否作为非阻断历史项，同时维持今后新增/改名的完整依据要求。尚未收到该新决定；没有把提问、旧名字没问题的反馈或试验副本政策当成新授权，没有改旧结果或制造无意义版本。

本轮证据：`chapter28-progress-check.json` 保存检查前进度、首审原结果、正文及初步恢复回读；`chapter28-recovery-final.json` 保存6/39的最终核对、完整0006 checkpoint、原任务和首审哈希；所有文本重新计算 SHA-256。`chapter28-recovery-native.txt/.jpg` 记录原生协调器界面，仅作为界面证据，不能替代连接器回读。

## 作者已确认旧名历史项（2026-10-16）

作者回答此前明确列出七个旧名及适用范围的问题，原话为“确认旧名历史项不阻断，新命名要求不变”。这是已经作出的作者决定，不应再报告为“等待作者选择”。陆桂枝、陆冬青、齐松、邵师傅、灯笼巷、桥东、桥西站保留旧名、原始命名动机 Unknown 和全部历史，作为非阻断历史项；今后新增/改名仍须事先有完整依据，其他实质问题仍按原标准处理。

通过小说协作档案创建有界记录 `session-6d2ac61b10c35604ab6244ab959fd509`，作者原话及完整问题保存在 `turn-69a791f3644659a38b16f6ad7518c4b5`，已完整回读并核对原话和助手上下文哈希。备份状态 verified，commit `37ad0caf92f06dbc6d89426c0fcfdd44bf5c7d0d`。这份讨论记录明确标为非 Canon、待控制器导入；不把 archive 保存等同于作品版本已更新。

Dot 已回读该档案并确认范围，原每小时计划 `6ad240b839b48191816a75880f5be705` 也已保存后续衔接。操作员刷新 Scheduled 页面，独立确认其仍为同一启用的 Hourly 计划，包含作者原话、七名范围、档案 ID，以及“先完成原二审，再受控导入、新版本复核和真实验收”的步骤。没有创建重复计划，没有改变原任务 attempt1。

当前技术边界：`Engine._operator_append` 在存在 running/submitted 任务时拒绝 `decision`，以免使正在执行的固定输入失效；现有 Dot 公开工具也没有可信操作员 decision 入口。因此不取消当前二审、不改旧审核或清空 unresolved。二审完成并发布后，需由可信操作员把本地 `author-old-names-confirmation.md` 已确认原件通过现有 `Engine.decision` 追加为作品决定，核对实际路径和新 revision，再完成对应独立复核和门禁回读。决定本身无需再次询问作者；技术待导入与作者待决定是不同状态。

本地证据：`author-old-names-confirmation.md`、`author-old-names-archive-readback.json`、`author-old-names-plan-ui.txt`、`author-old-names-plan.jpg`。正文、原版本、旧首审与现有二审的结果/次数均未为本次确认而改写。

## 二审完成后的实际导入（2026-10-17）

后续二审已完成39/39批并正式发布，原任务仍attempt1。作者本轮授权操作员受控导入，随后明确授权本次root SSH安全登录及临时凭据使用；已通过现有 `Engine.decision` 将确认原件追加为 `decisions/6b22de3da2e840da8d2b23e3b2ce11ca.md`，产生新版本 `15d4a6aacc59ee64babfcde8bb81105062c9e97047b1c52500fd33cf428a4c6d`。原110份作品文件和全部历史、任务、审核及checkpoint均未改。上述“技术待导入”是此前历史状态，当前导入回执及后续独立复核/实际验收记录见 [第二十八章作者决定导入](chapter28-author-decision-2026-10-17.md)。
