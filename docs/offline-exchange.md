# 离线双向交接（第一阶段）

目的：两端开工前能核对另一端已做的任务、产物、版本、验证声明及未决项，避免重复劳动。当前实现本地生成、验证、接收独立副本和开工预检，**没有网络传输、实时同步、数据库合并或自动开工门禁**。操作员必须在开工前调用预检并处理结果；task-claim 尚不自动查询收件箱。单端看不到离线对端的新工作，所以始终返回 peer_latest_known=false。

## 已有资料与本阶段范围

代码和工程文档走 Git；books 保存不可变版本，runtime/novel.sqlite3 保存任务/当前指针/原反馈/停止计数，runtime/feedback 保存原因与预防诊断，evaluations/experiments 保存对照。此前停写完整备份和 handoff 能恢复单份资料，但无法比较两端分叉。

本包按显式选择包含：

- 实际 handoff 任务记录：任务ID、输入/输出与当前版本、步骤、结果、停止及累计次数。相关作品的反馈原话一并保存。
- 显式指定的 UTF-8 文本产物及SHA-256、控制器源码摘要（统一换行）、控制规则摘要。
- 来源端、操作ID、共同基线包ID/状态、操作员填写的验证声明、未决项、下一步与排除项。

任务元数据由控制器读取；verification 是操作员声明，不能等同本次执行验证。单独的任意文本输入没有正式任务关联时，只选 artifacts，不伪造 book/task id。需将修改依据、诊断和实验文件逐项列入 artifacts；缺省不递归扫目录、不推定依赖齐全。包中的任务元数据和反馈也可能含私密内容，外传前必须授权整个选定范围。

本阶段不是完整备份：任务包、错误日志、认证、数据库和未选文件不打包。被允许的路径只限 books/、runtime/inputs/、runtime/feedback/、evaluations/experiments/ 下显式选定的 .json/.txt/.md；首版为跨平台采用ASCII相对路径，不允许符号链接、设备名、路径逃逸或大小写冲突。包最大16MiB，不压缩、不解压为活动目录。大规模数据继续使用已有停写备份协议。

## 本地操作

先停止资料写入者。双次捕获能检测观察到的变化，不是操作系统文件锁，也不能保障并发任意编辑的一致性。以下ID/路径仅作格式示意：

```json
{
  "origin": "local",
  "operation_id": "handoff-001",
  "task_ids": ["实际任务ID"],
  "artifacts": ["runtime/inputs/example.txt"],
  "verification": "未运行验证，待补证据",
  "unresolved": ["第二版修改依据尚未提供"],
  "next_step": "先核对对端任务与版本，再安排工作",
  "excluded": ["未选择的正文、完整原作、日志、认证与数据库"]
}
```

```text
python -m novel --root DATA bundle-create SPEC.json NEW-PACKAGE.json
python -m novel --root DATA bundle-create NEXT-SPEC.json NEXT-PACKAGE.json --baseline BASE-PACKAGE.json
python -m novel --root PEER-DATA bundle-check NEXT-PACKAGE.json --baseline BASE-PACKAGE.json
python -m novel --root PEER-DATA bundle-receive NEXT-PACKAGE.json --baseline BASE-PACKAGE.json
```

每次新的交接用新 operation_id；重复接收同一个包幂等。同来源/操作ID对应不同包内容则拒绝。输出文件独占创建，已有包不会被覆盖。先通过当前获准渠道交换包及共同基线；**上述命令不执行交换动作**。没有选定目的地和传输授权时只生成合成测试包。

返回方向使用完全相同的命令，只更换 origin/operation_id；收件箱记录在 `runtime/exchange/inbox/ORIGIN/OPERATION.json`，断网仍可读取并预检。receive 返回收到副本的回执，不表示活动状态已采用或对端已收到回执；如需对端确认，仍须经授权渠道交付该回执。保存的包携带创建时间，文件哈希只检测完整性，不认证发送者身份。

## 预检与不覆盖约束

| status | 含义与下一步 |
| --- | --- |
| same_selected_state | 所选状态一致，仍须检查已完成任务和排除项，不代表全项目已同步 |
| unknown_baseline | 无可核验共同基线；不得猜测哪端更新 |
| incoming_ahead | 接收端仍是基线、来包已变化；先核对和接续，不重做旧任务 |
| local_ahead | 来包仍是基线、接收端已变化；保留本端工作，向对端交接 |
| diverged | 双端状态不相同且均非基线，或本端缺必要状态；停止覆盖，先人工核对 |

必须显式提供可信基线包才能判断前进/分叉；不能只信来包自述的基线。后续包的任务/产物选择集须保持一致，否则拒绝建立继承关系，要求重新明确基线。首版按整个选定状态保守判冲突，不自动合并不同文件的并发修改。

work_blockers 提示版本需核对、已完成任务不得重做、停止条件必须保留。incoming_completed_tasks/incoming_stopped_tasks 便于执行者识别。即使发生分叉，receive也只保留独立证据副本；它不会改本端任务、作品、反馈、规则或“当前版本”指针。核对一次后本地状态可能再变化，所以每次开工都重新 check；不能把旧预检作为持久许可。

## 验收与待接通部分

合成的两个独立资料目录验证：双向预检、共同基线、落后/分叉识别、已完成任务提示、反馈和停止记录保留、重复包幂等、同操作异内容拒绝、损坏/错误基线/路径拒绝、源变化拒绝、断开来源后读取副本、CLI输入输出。不将这些测试称为真实电脑与云端同步打通。

下一阶段才考虑经过授权的传输目的地、回执交付以及活动资料接续策略。用户电脑当前离线，未访问。第一版章节仅是历史输入，第二版和本地修改依据未到；没有自动把这些资料加入 Git 或交接包。
