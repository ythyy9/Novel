# 当前运行与恢复

创作执行在已登记的 Dot 工作区，工程维护独立进行。`task-run`、联网参考分析及 CLI 创建任务时的自动参考刷新保持暂停。本文不授予新的模型、作者决定、权限或数据库结构变更授权。

## 状态与阅读

`novel_work_status` 保留旧的仅传 `workspace` 调用方式。返回全部活动任务及最近10项历史，`task_count` 是登记任务总数，`tasks_complete` 表示是否列全。可传 `history_limit`（1–100）、`before`（上次的 `next_before`）分页；活动任务在每页仍可见。不要将某项未出现在历史页理解为它已被删除。

默认任务摘要不重复长指令。完整指令通过已有 `novel_work_read` 读取指定任务的 `task-info.json`，或在状态请求中显式使用 `include_instructions=true`。`packet-index.json`、原始文件、结果、候选历史和所有 checkpoint 的读法保持。

仍缓存旧工具参数的会话可使用原有 `novel_work_read`，传入本工作区已有任务 ID，并读取状态返回的 `next_history_document`；沿返回偏移读完整页，再取下一页路径。无需重建任务或重新授权。

上下文计划按完整包哈希在进程内缓存，最多8项、约32 MiB。每次仍读取并验证原包，缓存不改变计划、批次或 checkpoint 哈希；进程重启后重新构建。状态和进度从数据库读取，不缓存为旧状态。缓存不减少完整阅读覆盖，也不将传输成功视为理解证明。

## 任务打开失败

`open_task` 先保存请求和预分配的任务身份，再创建、领取原任务并原子保存固定包。失败回执和原任务都保留；正常重放失败请求不会自动重做操作。`recoverable_open_requests` 提供需核对的请求和任务身份。

核对原请求、任务、版本、尝试、上下文及错误后，可信操作员可在相应资料根调用：

```python
from novel.dot import DotWorkspace
workspace = DotWorkspace(verified_root, verified_book_id)
receipt = workspace.recover_open_task(
    request_id=new_recovery_request_id,
    failed_request_id=original_request_id,
    task_id=original_task_id,
    expected_attempt=verified_attempt,
    expected_revision=verified_revision,
    context_ref=original_context_ref,
    note="已核对原始故障与恢复条件",
)
```

这个入口不暴露为创作 MCP 工具，不取消、重建、恢复 blocked/exhausted 任务或清零计数。尚未领取且 attempts=0 的原任务只领取一次；running 任务保持原尝试。已有完整包复用原字节；包缺失但已有上传/阅读证据时拒绝重建，须恢复原备份。原失败或 pending 回执不改写，新请求追加恢复回执。旧部署缺少请求意图时，只允许已登记且签名匹配的原任务恢复。

## 恢复审计

在一致备份的独立副本上执行 `python -m novel --root <恢复副本> audit`。它验证作品 SQLite、不可变快照、版本和审核关联；存在 `runtime/dot` 时，还验证 gateway 数据库、固定包与输入快照、任务身份、上传片段与已确认回执、checkpoint 哈希及送达范围。缺少数据库或包时失败，不自动创建替代资料。

未完成上传及历史错误是可恢复进度，不能删除以使检查通过。审计不证明文学质量，也不解除独立审核、停止条件或作者决定边界。备份须包含完整 runtime、books、controls 和实际实验资料；线上取得一致数据库副本时保留正在执行的任务，不调用 resume/reclaim。

## 源码与发布

发布前先从运行服务的 cwd、PYTHONPATH 和源码清单核对实际基线，再与 Git 比较，保留线上独有修复。私有正文、作者原话、上传、checkpoint、凭据和部署配置不能进入公开 Git；历史精确修复以哈希绑定保留，原文留在私有历史中。

受版本控制的工程范围为 `novel/`、`tests/`、所需 schemas、adapters、ops、CI 与公开操作文档。`policies/`、`methods/` 仍绑定活动任务；本轮优化不改它们。分支测试通过后，经既有 CI 门禁合入，再将确定的候选部署并记录 Git 提交、生产基线哈希、候选哈希、验证结果及实际运行回读。

云端维护 API 只接受已授权的源码白名单，不因文件可上传就允许改变审核标准、作者决定、权限或数据库结构。部署使用现有双实例切换与排空；保留旧代码供回退。切换前后核对原任务身份、累计次数、旧文件及历史表的已有行，允许正常创作追加新进度。代码回退不回退作品或数据库。
