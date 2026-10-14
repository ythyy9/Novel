# Codex 接入

第一版适配器使用已安装的 Codex CLI 和现有 ChatGPT 登录，每次显式运行一个任务。
`novel.adapter.prepare(engine, task_id)` 导出所选作品、固定输入版本、文件 SHA-256、任务要求和结果 Schema；`run(...)` 调用真实 `codex exec` 并返回经过记录协议验证的候选。
提交和发布由控制器单独执行，执行者不能自行将结果宣布为正式正文。

运行前使用 `doctor()` 检查 CLI 版本、必要参数和 `codex login status`。只接受能够确认的 `Logged in using ChatGPT`；不会自动登录、读取或复制认证文件，也不会改用 API key。
子进程环境剔除 API key、直接 token 及 OpenAI endpoint 覆盖，用户环境不变。
执行使用 `--ignore-user-config`，隔离用户配置中的外部 provider/MCP；仅保留可读取的顶层 `model` 与 `model_reasoning_effort`，显式使用 `openai` provider 和 `chatgpt` 登录方式。
已有模型偏好不可读取时停止，避免静默改用另一个模型。项目与用户的执行规则仍然生效，不使用忽略规则、跳过审批或扩大 sandbox 的参数。

每次尝试位于 `runtime/tasks/<任务>/attempt-<累计次数>/`：

- `packet.json`、`prompt.md`、`result.schema.json`：本次固定输入；同一次尝试的输入不能被覆盖成不同内容。
- `execution-started.json`：禁止同一次尝试重复启动的标记。
- `stdout.jsonl`、`stderr.log`、`adapter-events.jsonl`：真实 CLI 输出与适配器事件。
- `result.json`：CLI 的最后结构化结果；存在不等于已提交或已发布。

失败会保留次数与日志，并进入控制器的持久停止状态。适配器不自动重试。超时或 Ctrl+C 只终止本次创建的进程树；恢复需要显式检查并由控制器创建下一次尝试。

`read-only` sandbox 是 CLI 对工具调用的保护，**不是完整的操作系统隔离证明**。运行配置关闭 shell 和 Apps；提示词禁止其他文件工具、MCP 和连接器，并要求不查阅其他作品。这些设置不构成操作系统级完整隔离。
仅 `research` 任务配置内建网页搜索为 `live`，其余任务为 `disabled`。研究提示要求只检索必要的通用问题、不发送未公开正文，引用实际取得的来源，记录适用条件与不确定性。检索不足必须保留缺口；来源 JSON 合法不等于来源真实可靠，审计可检查 CLI 的 JSONL 事件及来源回读。

单元测试里的子进程替身只验证命令参数和错误处理，不构成实际模型、账户额度或文学质量验收。真实执行状态以本机诊断、运行日志及结果回读为准。

官方依据：[非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)、[认证](https://learn.chatgpt.com/docs/auth)、[配置基础](https://learn.chatgpt.com/docs/config-file/config-basic)、[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。CLI 参数以运行机器上的 `codex exec --help` 为准。
