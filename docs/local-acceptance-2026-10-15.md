# 2026-10-15 本地接续与真实模型验收

本轮在 Windows 本机接续云端源码 `619ed202f50c3af11197df0d15d3ae27aaccdb5a`，完成本地真实审核、定向返修、版本复核和联网研究，共五次真实模型调用。云端 `installation_id` 只读目录错误及推理代理 CONNECT 403 仍未修复；本地结果不替代云端验收，云端原停止任务未被恢复或清零。

## 环境与源码

- 原工作区从 `4dd1919` 快进至 `619ed20`。先在独立工作区验证相同代码，再同步原工作区；原有 `README.md`、`docs/evaluations.md` 和未跟踪的候选回放文档内容哈希均未改变。
- Windows / Python 3.11.9；`python -m unittest discover -s tests -v`：**145 项全部通过，无跳过，98.781 秒**。日志为本地 `.local-validation/unittest-local-20261015.txt`。
- Codex CLI `0.153.4`，现有 ChatGPT 登录，实际保留本机 `gpt-6-astra / xhigh` 配置。没有复制认证文件、更换模型、切换 API key 或调整云端网络。
- 按现有适配器使用 `read-only` 子执行沙箱、结构化结果、一次性执行和累计次数。宿主正常运行所需权限经工具审批；没有关闭子执行器沙箱。CLI 日志中的 PowerShell shell snapshot 不支持警告未导致调用失败。
- [OpenAI 非交互模式说明](https://learn.chatgpt.com/docs/non-interactive-mode)支持通过 `codex exec` 复用现有登录；本次成功依据仍是实际 JSONL、结果校验及控制器回读，而非文档或 `doctor.ready`。

## 审核与返修的实际结果

使用两份短小、明确标注的合成工程材料。两者包含相同的钥匙保管规则、密信已经送达这一事实、人物仍以为信未送达的误解以及读者知识。A 有完整解封交接；B 将同一把钥匙写成九点零五分同时在口袋与封匣中。材料通过手动结果协议导入，**不是模型生成或作者作品**。

运行前固定 A 不应因人物误解而被阻断、B 应检出物品位置矛盾、返修后必须重新审核的条件，保存在本地 `fixture-manifest.json`。三次审核使用相同通用审核要求，输入包不含期望标签或评分答案。不同任务身份仅表示模型会话分开，不是独立真人评审或操作系统信息隔离。

| 步骤 | 真实任务 ID | 结果与控制器行为 |
| --- | --- | --- |
| A 正常材料审核 | `c261112eacbf4451b9ac760847397454` | 覆盖两节正文和状态；无 findings、无 unresolved；经发布、评估后阶段通过。人物误解未被误报为事实矛盾 |
| B 矛盾材料审核 | `33e1e5d578e145b2b701bba2e4178293` | 精确定位钥匙矛盾，报告一项 confirmed/error/major；实际调用 `accept` 被拒绝 |
| B 定向返修 | `04cbc591a391424e8583dff07c4eae20` | 修改第二节，补足九点十分解封、交接、开门；提交状态文件，保留四个已有知识 ID 并增加有精确正文依据的交接记录 |
| B 新版本审核 | `e156fc2ba0c141a5b44e25b10a1edf06` | 新独立任务覆盖全部正文与状态，无 findings、无 unresolved；经发布、评估后阶段通过 |

以上四项各执行一次，CLI 退出 0，真实结构化结果经过协议校验和提交后才由控制器发布，没有失败重试或手工替换模型结果。

返修从 `9a4f5a8ff7156cbe3d9a5aff573a23d14ceb7809707753d0f0b3a7936c25bb99` 生成 `4d68ddcb364e50adfffc8deaa5947dab93a90e982cb509aafc0afae317cc7e43`。发布后、重新审核前，`assessment.review_tasks` 为空且实际 `accept` 再次被拒绝。新审核只绑定新版本，旧版 `R1` 仍为 open、原结果哈希不变。

控制器结果 SHA-256（规范 JSON）：

| 结果 | SHA-256 |
| --- | --- |
| A 审核 | `89e5414fddc9e66170ce3f3015c0bda92731d1f10db0652363913382d11914c0` |
| B 审核 | `6e9358fbfc4c285d3f240a96021529d9f061ca28b7347a7a6ed38314490af7b5` |
| B 返修 | `19cdd780f0eb8c3e1672668b6605170299330d5c66a2511110319c011769e6e8` |
| B 新版审核 | `ff62474da6c6c9bd893e4af29b72865e0e7fb44f395842265d1e0006f57849be` |

## 真实联网研究与来源复核

研究任务 `fe276bfafcb9484d93cef51c6459e5bc` 在独立工程资料库核实“所有现实港口每天恰好两次高潮且严格相隔 12 小时”这一通用命题。只提供公开问题，没有传送正式作品。任务执行一次、退出 0，研究记录通过校验、提交、本地发布和回读；只新增 `research/tides.json`，Canon 内容逐字未变。

原始 JSONL 确认 **4 个已完成的 web_search 事件**：两次搜索、一次分潮页面访问、一次 FAQ 页内检索。模型结果自述打开了五项来源，但日志的事件粒度不足以逐页确认这一说法，因此不把该自述列为独立证据。主 Agent 另行打开五项原页面，核对核心论点：

- [NOAA 月球日](https://oceanservice.noaa.gov/education/tutorial_tides/tides05_lunarday.html)与[潮汐类型](https://oceanservice.noaa.gov/education/tutorial_tides/tides07_cycles.html)：月球日不同于 24 小时民用日，全日潮构成全球统一“两次高潮”规则的反例。
- [NOAA 分潮说明](https://tidesandcurrents.noaa.gov/about_harmonic_constituents)：当地预测叠加多个分潮；太阳半日分潮周期不能直接替代当地实际高潮间隔。
- [NOAA 预测使用说明](https://tidesandcurrents.noaa.gov/noaatidepredictionshelp.html)与[预测精度 FAQ](https://tidesandcurrents.noaa.gov/faq.html)：具体预测需要站点、日期和时间标准，短期天气和径流会影响实际水位。

缺少具体港口与日期时，记录保留当地潮型和高潮时刻的 Unknown，没有捏造数值或创建作品规则。这不妨碍通用命题研究完成；研究资料未标成作品阶段通过。研究结果规范 JSON SHA-256 为 `6e513a0eeb7125f8e694253ed396380707598a5e7e605cd6a9b9db4f4c39e0d0`。

五次执行耗时依次为 **74.939、74.037、85.582、56.904、129.324 秒**；每次均为 attempts=1。最终新进程回读确认五个任务 completed、对应 JSONL 存在 turn.completed、原始 result.json 与数据库结果一致；`audit` 为 SQLite ok、7 个快照、33 条事件。原始产物哈希及汇总见本地 `evidence.json`。

## 原始证据与限制

本地证据目录：`.local-validation/local-20261015/`。`data/` 包含 SQLite、不可变快照、方法和每次尝试的 packet/prompt/schema、JSONL、stderr、原始结果与适配器事件。`rejection-receipt.json`、`revision-receipt.json`、`revised-acceptance-receipt.json` 保存实际拒绝、差异和新版通过回读。`python .local-validation/local-20261015/verify.py` 可只读复核任务与产物并重新生成汇总，不调用模型。上述私有运行资料默认不进 Git。

本次是一个明显矛盾和一个正常写法的对照，证实这对材料上的实际检出/误报情况、返修及版本门禁；不能推算总体准确率，也未证明微妙因果、长篇依赖、文学质量或作者认可。没有修改审核标准或启用参考作品候选方法，没有创建正式作品。正式创作仍依赖作者给出题材、人物/世界起点和锁定项；电脑休眠后的云端执行能力仍受原平台问题阻塞。
