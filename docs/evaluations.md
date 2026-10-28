# 方法对照与经验保留

这一模块保存已经生成的新旧方法输出和真实评价，不自动训练模型、改写方法或生成“读者反馈”。原始输出、评语和决定都是新文件追加；哈希用于检测损坏，不是身份签名。

先准备实验 JSON：

```json
{
  "id": "character-attention-v1",
  "hypothesis": "写作前列出关注点与取舍，能否改善人物区分？",
  "baseline_method": "旧方法的版本或完整描述",
  "candidate_method": "候选方法的版本或完整描述",
  "cases": [
    {"id": "development-1", "split": "development", "input": "用于提出方法的实际案例", "baseline_output": "实际旧方法输出", "candidate_output": "实际候选输出"},
    {"id": "holdout-1", "split": "holdout", "input": "未用于修改方法的实际案例", "baseline_output": "实际旧方法输出", "candidate_output": "实际候选输出"}
  ]
}
```

以上仅展示格式，使用时必须填入实际内容，不能当作评价证据。

```powershell
python -m novel eval-create experiment.json
python -m novel eval-blind character-attention-v1
python -m novel eval-judge character-attention-v1 holdout-1 A --reviewer author --rationale-file feedback.txt
python -m novel eval-summary character-attention-v1
python -m novel eval-decide character-attention-v1 trial --note "目前证据不足，暂用并继续观察"
```

每个案例随机交换 A/B，排列保存后不会重新洗牌。`eval-blind` 隐藏方法映射，评价可以是 `A`、`B`、`tie` 或 `inconclusive`；`eval-summary` 会揭示映射，因此应在盲评完成后查看。文件系统中的映射并未加密，对具有本机访问权的评审者不构成隔离。

`reviewer` 是录入者对来源的声明，不是账户认证。只有实际作者/目标读者的原话才能标记为 `author`/`target_reader`；模型评语必须用 `agent`，并在汇总中单列。

`retain` 需所有案例都有评价、每个 holdout 有作者或目标读者评价、人类 holdout 至少一次候选胜，且所有 holdout 评价没有候选输。`trial` 或 `rollback` 需要明确理由。决定绑定当时的证据，新反馈不会改写过去的决定。此门禁是保守的最小证据要求，并不证明方法普遍有效。

若决定采用方法，由单独的系统改进任务更新 `methods/`，再建立新创作任务；旧任务会因控制版本变化而拒绝继续。不要让当前章节同时修改自己的审核标准。跨题材可复用经验须注明范围与验证状态，再按实际需要整理到 `lessons/`。

## 现有材料的探索性回放

没有独立保留案例时，可以先做明确标注的历史基线回放，但不能冒充上述正式 A/B 实验或把提炼来源改标为 holdout。2026-10-14 的 [C06/C07/C09 首轮记录](evaluations/reference-methods-replay-2026-10-14.md)保留了六组参考对照和一个工程边界样本：候选展开了复核细节，没有发现纠正基线明确错误的案例。记录保存在本地 `runtime/evaluations/`，没有改变运行方法或模块门禁。
