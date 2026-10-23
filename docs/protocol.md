# 第一版任务与记录协议

协议由 [结果 Schema](../schemas/result.schema.json)、`novel/records.py` 和 `novel/engine.py` 共同实现。Schema 约束输出形状；Python 校验器还检查路径、精确引用、输入版本、任务状态、来源边界和发布条件。模型声称完成不等于提交或发布成功。

大资料包可经 Dot 的[有界读取与状态增量传输](context-protocol.md)分批处理：固定包原件不变，逐批全文阅读、保存进度，再展开成本文的完整九字段结果执行原校验。传输 checkpoint 不是作品提交，增量不是跳过完整状态或审核的许可。

以下 JSON 是结构示例，人物、正文和编号均为示意，不能当作首部作品的作者决定。实际结果必须使用对应任务的真实编号和版本。

## 任务和版本

任务种类为 `write`、`revise`、`correct_records`、`research`、`review`。创建时固定 `id`、`book_id`、`kind`、`instruction`、`input_revision`、`control_hash`，并记录创建时间。执行状态、`attempts`、`no_progress`、`stop_reason`、`detail`、结果与哈希由控制器维护，模型不能自行更新。

正常转换为 `queued → running → submitted → completed`。领取时累计 `attempts`；停止为 `blocked`，达到次数限制后为 `exhausted`；有说明的显式取消为 `cancelled`。`blocked` 解决后可以回到 `queued`，不清零次数。当前版本或规则变化会使旧任务失效，须保留记录并显式接续。

版本是包含父版本、任务身份和文件 SHA-256 的 manifest 的内容哈希。模型拿到固定输入包，包含所选作品文件、文件哈希及 `policies_and_methods` 下的实际原则与方法；控制器在提交与发布时重新确认输入仍为当前版本，并校验真实文件。方法约束不能授予额外工具权限。模型结果不会直接覆盖有效正文。

## 通用结果

顶层必须且只能有以下九个字段。JSON 不允许重复键、NaN 或 Infinity。

| 字段 | 类型及要求 |
| --- | --- |
| `task_id` | 非空字符串，严格匹配任务编号 |
| `input_revision` | 非空字符串，严格匹配该任务输入版本 |
| `completed_steps` | 非空字符串数组，至少一项；描述实际完成步骤 |
| `next_step` | 非空字符串 |
| `unresolved` | 非空字符串构成的数组，可为空；不能隐藏待决定或证据缺口 |
| `changes` | `{ "path": string, "content": string }` 数组；content 是非空完整文件文本，不是补丁 |
| `review` | `review` 任务为审核对象，其余任务必须为 `null` |
| `affected_paths` | 去重路径数组，每个路径须存在于输入或合并后的结果中 |
| `state_notes` | 字符串；`write`/`revise` 必须非空 |

完整审核结果的最小示例，假设输入中存在 `manuscript/001.md`：

```json
{
  "task_id": "task-example",
  "input_revision": "revision-example",
  "completed_steps": ["逐项检查所覆盖正文的四个审核维度"],
  "next_step": "由操作员检查审核依据并执行 assess",
  "unresolved": [],
  "changes": [],
  "review": {
    "coverage": ["manuscript/001.md"],
    "dimensions": ["continuity", "character", "world", "reading"],
    "findings": []
  },
  "affected_paths": [],
  "state_notes": ""
}
```

空 `findings` 仅表示该次审核未报告问题，不能证明不存在问题或作者已经认可。

### 各任务的写入范围

| 种类 | 结果要求 |
| --- | --- |
| `write` / `revise` | 同时提交至少一个 `manuscript/*.md` 和 `canon/state.json`；所有改动正文都须列入 `affected_paths`；不得改 `research/` 或另建其他 `canon/` 状态文件 |
| `correct_records` | 新增一份 `revisions/correction-*.json`，记录有原文证据的已有记录更正或旧修订说明的追加注释；有状态更正时同时提交精确对应的 `canon/state.json`，不要求改正文 |
| `research` | 只新增一个或多个 `research/*.json`；不能覆盖已有研究记录，也不能改正文或状态 |
| `review` | `changes` 必须为空，只提交审核记录 |

所有任务都不能借结果写入 `decisions/` 或 `reference/`；这些内容只经明确授权的操作员导入。结果没有删除文件操作。`write`/`revise` 可在允许路径内补充候选或返修说明，但不能删掉 `knowledge`、`characters`、`world`、`offstage` 中的既有 `id`；需要纠正时保留身份并修改记录，历史版本保存旧内容。完整状态和增量提交遵守同一身份保留约束。

`correct_records` 的固定包另带 `record-correction-guide.md`。更正说明格式为
`{"format":"novel-record-correction-v1","reason":"原因","records":[],"annotations":[]}`，
至少包含一项更正。`records` 每项含 `section`、`id`、完整 `before`/`after`、`reason`、`evidence`；
只允许改变已有记录的 `statement` 与 `sources`，保留原来源、顺序、身份、信息类别、持有人及名称。
`annotations` 每项含原有修订文件的 `path`、原文 `quote`、追加的 `correction` 和 `evidence`；
原说明不被覆盖。所有 evidence 必须精确引用固定输入，不得用本次新说明给自身作证。
变化文件及被注释的原文件均须列入 `affected_paths`。状态可用既有 `state_delta` 传输，
展开后必须与说明中逐项登记的更正完全一致。发布生成待审核新版本，独立复核和验收门禁保持；
既有任务不改种类、不重建，历史单任务恢复补丁继续保留。

路径使用 `/`，相对于作品根目录，允许的首层目录是 `manuscript`、`canon`、`possibilities`、`research`、`reference`、`decisions`、`revisions`，扩展名为 `.md` 或 `.json`。拒绝绝对路径、反斜线、`.`/`..`、隐藏路径组件、Windows 保留名、非法字符、大小写冲突与文件/目录冲突。`reviews/` 不作为模型写入目录，审核记录存入数据库。

## `canon/state.json`

顶层必须且只能有四个数组：`knowledge`、`characters`、`world`、`offstage`。下面例子的输入或结果正文 `manuscript/001.md` 必须包含这两句原文：`来信已经送达。守门人以为来信还未送达。`

```json
{
  "knowledge": [
    {
      "id": "letter-arrived",
      "kind": "world_fact",
      "statement": "来信已经送达。",
      "holder": null,
      "sources": [{"path": "manuscript/001.md", "quote": "来信已经送达。"}]
    },
    {
      "id": "keeper-mistake",
      "kind": "character_belief",
      "statement": "守门人以为来信还未送达。",
      "holder": "守门人",
      "sources": [{"path": "manuscript/001.md", "quote": "守门人以为来信还未送达。"}]
    }
  ],
  "characters": [],
  "world": [],
  "offstage": []
}
```

`knowledge` 每项必须且只能包含 `id`、`kind`、`statement`、`holder`、`sources`。

| `kind` | 含义 |
| --- | --- |
| `world_fact` | 作品采用的事实 |
| `character_knowledge` | 指定人物掌握的信息 |
| `character_belief` | 指定人物的错误认识或信念 |
| `reader_knowledge` | 读者已经获得的信息 |
| `undecided` | 作者尚未决定的内容 |
| `candidate` | 尚未采用的候选 |

人物知识与信念必须给出非空 `holder`；其他类型可为 `null`，非空时也须是字符串。每个数组内部 `id` 唯一；所有 `id`、`statement` 均为非空字符串。

`characters`、`world`、`offstage` 每项必须包含 `id`、`statement`、`sources`，其中 `characters` 可额外包含非空 `name`，其余额外字段拒绝。这三个索引不自动将其中内容提升为作品事实；六类信息以 `knowledge` 为准。

`sources` 必须是非空数组，每项严格为 `{ "path": "相对路径", "quote": "精确原文" }`。路径必须存在，quote 必须是最终合并文件的精确非空子串，不能引用 `canon/state.json` 自身。`world_fact` 不能只由 `reference/` 或 `possibilities/` 支持。

原有 `undecided` 转成 `world_fact`，或用新 ID 采用同一作者未决原句，都须引用输入版本中已存在的 `decisions/` 记录。模型不能在同一结果内制造作者决定来满足这个条件。

普通、可逆的 `candidate` 除引用已有作者决定外，也可通过明确的 Agent 选择记录采用。在 `revisions/*.json` 中新增以下精确结构，candidate_ids 填入原有候选 ID：

```json
{
  "kind": "agent_selection",
  "candidate_ids": ["candidate-example"],
  "reason": "选择能保留人物既有动机且后果可以返修的方案。",
  "scope": "ordinary_reversible"
}
```

采用后的 `world_fact.sources` 必须同时引用这份选择记录与正文，精确 quote 校验同样适用。选择理由非空，标记为 Agent 自主选择，不能冒充作者决定；`undecided` 不能走这条路径。原有知识 ID 仍需保留。

控制器识别稳定 ID 及完全相同的 statement，不能识别所有换词改写、伪装成新命题的语义关系，也不能自动判断某选择是否真的属于普通可逆事项。引用存在只证明出处可追溯，不证明那段话逻辑上足以支持结论；授权范围和因果合理性仍需审核。

## `research/*.json`

每个研究文件必须且只能包含 `question`、`sources`、`conclusion`、`conditions`、`uncertainties`、`affected_paths`、`claims`。

没有取得外部来源时，可以明确提交一个有限推断，不能伪造外部事实：

```json
{
  "question": "当前正文是否说明守门人已经知道来信送达？",
  "sources": [],
  "conclusion": "仅依当前正文，守门人的认识与事实不同。",
  "conditions": ["只适用于当前章节中的这两句描写"],
  "uncertainties": ["尚未检查其他章节，也没有取得外部证据"],
  "affected_paths": ["manuscript/001.md"],
  "claims": [
    {
      "kind": "inference",
      "text": "应继续区分来信已送达这一事实与守门人的错误认识。",
      "source_indexes": []
    }
  ]
}
```

- `question`、`conclusion`：非空字符串。
- `conditions`、`uncertainties`：各至少一条非空字符串；不能省略适用条件和未知事项。
- `affected_paths`：去重数组，路径必须存在于合并结果中；记录内声明的影响范围必须被通用结果的 `affected_paths` 包含。
- `sources`：可为空；每项必须且只能含 `url`、`title`、`accessed`。URL 为有效的绝对 HTTP(S) 地址，不得含用户名、密码、空白或反斜线；title 为非空标题，accessed 为真实访问日期 `YYYY-MM-DD`。
- `claims`：至少一项；每项必须且只能含 `kind`、`text`、`source_indexes`。text 非空；kind 为 `external_fact`、`inference` 或 `fiction_rule`；source_indexes 为指向 sources 的不重复、从零起算整数下标，`external_fact` 至少引用一项。

`external_fact` 表示资料事实，`inference` 表示系统推断，`fiction_rule` 表示作品规则。结构校验不自动证明 `fiction_rule` 已获作者采用，也不能检验网站是否真的被访问。真实检索能力和某次检索成功应分别由执行日志、来源阅读及结果回读确认。

## 审核对象与发现

`review` 必须且只能含 `coverage`、`dimensions`、`findings`。coverage 至少包含一个实际输入文件，不得重复；dimensions 必须将 `continuity`、`character`、`world`、`reading` 各列一次。

`findings` 可为空；每项必须且只能有以下字段：

```json
{
  "id": "finding-example",
  "category": "concern",
  "confirmed": false,
  "severity": "major",
  "path": "manuscript/001.md",
  "quote": "守门人以为来信还未送达。",
  "explanation": "需要核对前文是否已经让守门人读到这封信。",
  "suggestion": "检查人物知识变化的时点，并同步涉及章节。",
  "affected_paths": ["manuscript/001.md"],
  "status": "open"
}
```

`id` 在此次审核中唯一；`category` 是 `error`、`concern`、`experience`；`confirmed` 是布尔值；`severity` 是 `major` 或 `minor`；新发现的 `status` 必须为 `open`。path 必须属于 coverage，quote 必须精确命中那个输入文件；解释和建议均非空，影响路径必须存在。

阶段通过要求当前版本有已发布的独立审核任务，且覆盖全部当前正文。以下内容阻断通过：已确认的 `error`（不论严重度）、`major` 的 `concern`、审核的 `unresolved`、产生当前版本的写入任务的 `unresolved`，以及过期规则审核和缺失覆盖。普通体验意见或轻微未确认疑点可保留，但不能删除原始发现来制造通过。

当前没有“模型把发现改为 closed”的操作。通常通过 `revise` 生成新版本并重新审核，保留旧版发现。新审核的 findings 为空，也不会抹掉同一版本旧审核中仍然存在的阻断项。

## 操作员权限与证据范围

模型只交付上述结果对象。`decision`、`reference-import`、`feedback`、`accept`、停止恢复、取消、回滚以及规则调整属于控制器操作，必须基于对应作者授权或已授权的运行职责；协议中不存在让模型自行声明“作者同意”的字段。

本地 CLI 没有身份认证，因此不能把调用某条命令当作人类确实亲自操作的证明。SQLite 事件记录动作、任务与版本，作者原文和实际来源提供内容依据；流程验收、模型运行成功、来源核实和作者文学评价应分别报告。

外部 CLI 提交必须提供 `task-submit TASK RESULT --expected-attempt N`，N 来自生成结果时的任务包 `task.attempts`。它不是结果 JSON 新字段；控制器在同一提交事务中拒绝不匹配的尝试。受信任 Python 调用仍可直接调用 Engine.submit；外部执行应显式传入 expected_attempt。此机制防止误接收旧尝试结果，不证明调用者没有谎报次数。

反馈诊断不属于模型交付结果字段，由控制器外部操作员用 `feedback-diagnose` 追加到 runtime/feedback。保留原反馈哈希、同作品精确版本引用、原因假设、预防范围、验证计划和实际观察，必要时绑定已有实验清单及当时汇总。详见 [反馈闭环](feedback-loop.md)；不允许借诊断自动改写原则或宣称知道模型内部动机。
