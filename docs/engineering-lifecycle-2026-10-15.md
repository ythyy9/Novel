# 2026-10-15 执行生命周期工程修复

本轮不依赖正式作品设定。从本地 `e870542` 开始，复核准备、启动、提交、停止和接续的边界；未改创作方法、结果 Schema、审核标准、默认限额或数据库版本。原有未提交文档保持原样。

## 已复现和修复

| 缺口 | 修复前证据 | 修复后的行为 |
| --- | --- | --- |
| 重复启动误停原执行 | 已有尝试标记时，第二次调用没有启动进程，却把任务改为 blocked 并增加 no_progress | 准备和预检前独占预约同一尝试；重复调用只报错，原任务、日志和计数不变 |
| 控制器拒绝候选后卡在 running | 无实际改动的合法结构结果被 submit 拒绝，CLI 退出但任务仍为 running | task-run 经 run_and_submit 交回控制器；无实际改动记 no_progress，其他提交失败记 tool_failure；保留原始结果，显式恢复后累计次数继续 |
| 过期输入仍可准备或启动 | 领取后改变 methods，prepare 仍成功且 controls_match=false | 准备及预检完成后核对规则、输入版本、停止状态与尝试身份；过期时不启动模型。领取、提交和停止均绑定尝试，旧调用不能接管或误停新尝试 |
| 启动后本地 I/O 失败遗漏清理 | started 日志写入在清理保护范围外；真实进程故障测试进一步出现未关闭 stdin 的 ResourceWarning | 日志和输入读写失败进入已有进程树清理路径；关闭输入管道。无法确认清理时仍明确报 cleanup unconfirmed |

`run(...)` 保留只返回候选的职责，新增 `run_and_submit(...)` 供 CLI 使用；成功后仍是 submitted，不自动发布或通过。手动 `task-submit` 的可纠正输入错误不自动停止或重新领取。无实际改动使用 `NoProgressError` 分类，不依赖错误字符串猜测。

这些是控制器与适配器的一致性保护，不是 OS 权限隔离。手动取消或恢复仍不会终止外部进程；必须先核对原进程状态。启动前检查也不承诺操作员在进程启动后取消时会自动终止它。

## 工程验证

最终命令：`python -m unittest discover -s tests -v`，Windows / Python 3.11.9，**158 项全部通过，无跳过，109.720 秒**。最终日志没有 ResourceWarning。新增 13 项真实 SQLite/线程回归，并增强已有重复执行测试，覆盖：

- 并发重复调用不修改原尝试文件、日志、状态或计数，原调用仍可完成提交。
- 规则在领取后或预检期间改变、输入版本更新时拒绝启动。
- 调用在读取任务与领取之间、预检期间、结果提交边界被新尝试取代时，不误领或误停新任务。
- 无实际改动停止、原始结果保留、跨实例计数接续，第二次 no_progress 达到原有耗尽门禁。
- 超尺寸结果由控制器拒绝后持久停止；已提交或已取消任务不会被迟到失败改写。
- 真实自有 Python 子进程启动后注入日志失败，确认进程退出且 stdin 已关闭。

确定性返回值的子进程替身只用于错误注入，不能证明模型成功。首轮新增真实清理测试曾因夹具同时替代 taskkill 而失败，修正夹具后通过；随后发现的真实 stdin 资源警告已修复。失败记录保留，没有删除案例或降低断言。管道修复后重新完成上述全量检查。

## 真实 Codex 复验

任务 `1301187a5de24691b81e2e21876c4e45` 使用独立空状态工程资料，不是正式作品。CLI `0.153.4`，现有 ChatGPT 登录，保留 `gpt-6-astra / xhigh` 与 read-only 子执行边界，未换模型、复制认证或调整云端网络。

模型执行期间实际发起第二次调用：被拒绝，原任务仍 running、attempts=1、no_progress=0，原适配器日志未改变。最终仅有一个 started 事件，原模型调用 **29.669 秒、退出 0**；JSONL 有 turn.completed，原始 result.json 与控制器候选一致，随后完成提交、发布、阶段通过与新进程回读。

结果规范 JSON SHA-256：`938f0436d8fff127a56109dd46feb8f0dadfbb4f039d6e92e82083f592dfe89c`。审计：SQLite ok、1 个快照、6 条事件，作品文件内容未变。空状态复验只验证改动后的执行链，不新增文学质量结论。

## 证据与剩余范围

本地保留 `.local-validation/engineering-20261015/`：

- `initial-reproduction.json`：修复前三项缺口的实际状态。
- `lifecycle-tests.txt`、`lifecycle-tests-final.txt`、`lifecycle-tests-cleanup.txt`：初始夹具错误、资源警告及修复后的回归记录。
- `unittest-final.txt`：最后管道修复前的全量运行；最终验收以 `unittest-final-closed-pipes.txt` 为准。
- `live-task.json`、`live-duplicate.json`、`live-receipt.json`：源码文件哈希、真实重复调用拒绝及成功回读。
- `live/`：SQLite、快照、任务包、真实 JSONL、结果和适配器日志。

运行资料不进入 Git。本轮未扩大为全文自动裁剪或长期压力试验；已有百万字符存储验收不能证明模型上下文容量或持续长篇运行。云端只读目录/CONNECT 403 以及完整 OS 隔离仍是独立平台边界。本轮限定为工程修复，不建立或修改正式作品；其他聊天的作品及说明更新保留。共享的 docs/usage.md、docs/remaining-acceptance.md 正有并发编辑，本轮不覆盖它们，执行行为以本验收和 adapters/README.md 的新增说明为准。
