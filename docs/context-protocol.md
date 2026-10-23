# 固定包分批读取协议

通过 `novel_work_read` 先读 `context-guide.md`、`context-plan.json`、`context-progress.json`，再沿真实 `next_offset` 全文读取计划批次。计划绑定原 task、attempt、input_revision、control_hash 和固定包哈希；缓存不改变这些身份或已有批次哈希。

每批最多12,000字符，传输分页每页最多6,000字符。非状态文件全文覆盖；状态通过记录及去重来源表示，恢复时保留全部字段、顺序与重复来源。`context/state-current.jsonl` 和单条来源用于导航回查，不代替完整批次阅读。

每批阅读后，通过既有 `chunk/finish` 保存包含以下字段的 `novel-context-checkpoint-v1`：`format`、`task_id`、`attempt`、`plan_sha256`、`batch_id`、`context_ref`、`notes`、`evidence`、`unresolved`、`review`。`evidence` 中每项为该批真实 `document` 和精确 `quote`。服务端检查全文送达范围；记录不能覆盖，只能追加。

审核 checkpoint 必须包括四维审核及该批作品路径覆盖。全部 checkpoint 的发现和未决项会保留到最终结果；综合阶段的空 findings 不能清空历史问题。不同 context_ref 字符串不证明真实独立审核，仍需要执行平台的独立证据。

完成全部批次后，提交 `novel-context-result-v1`，字段为 `format`、`task_id`、`attempt`、`plan_sha256`、`result`、`state_delta`。`result` 使用[原九字段结果协议](protocol.md)；`state_delta` 为 null，或包含 `base_sha256` 与 `operations`。

每项状态操作包含 `section`、`id`、`before_sha256`、`set`、`append_sources`。现有记录的 before 哈希须匹配，新增记录用 null；不得改记录 ID，不得在一项操作中同时替换与追加 sources。展开后的完整状态仍须通过全部来源、路径和身份保留校验。

已提交但尚未发布的 write/revise 候选可读取 `candidate-amend-guide.json` 后，用新上传提交 `novel-candidate-amend-v1`。它绑定原 task、attempt、input_revision、旧 result_hash 和原因，携带完整 context result；旧候选、上传、checkpoint 和失败回执保留。更正不发布作品，也不替代后续独立审核。
