# 第37章两条旧原件缺口的补证与关闭

2026-10-27 作者要求完成两条旧阻断的补证与合法关闭，保留旧审核和失败历史，不降低门槛。本记录区分已完成的资料补充、待完成的独立复核和最终验收。

## 已核实的问题

第37章首审 `7c32c0b07e4447f08c3d5dbbde234b83` 已完成，attempt=1、no_progress=0，原结果哈希为 `9ada160f40ea8aed6c703517cf3a09a581128375f22ae2cb69568b21d162bba8`。其两条 unresolved 是第2、3章原审核未在 Dot 注册，直接读取 result.json 失败。后来通过操作员限定的 continuation-evidence 取得了全文，但历史 checkpoint 中的失败被原提交规则合并保留；不能通过覆盖结果、删除 checkpoint 或空 findings 关闭。

原审核身份：

| 章节 | 原任务 | 原结果 SHA-256 |
|---|---|---|
| 2 | `0fd6f50ab82549ac98605bc640df4d28` | `b16ffbeeec745358391e721e33d2e3acfc19b25510a132538e3176d40ee6e0eb` |
| 3 | `ba59e71c4fd644c88f0b85fbf3c1b424` | `7bc428fd2d7cdcf0ce78a6d5ee9ec68ba9a1aeacd727c4ee5d165a1271d5e5a3` |

## 采用的合法路径

1. 操作员核验原件身份、原输入版本及结果哈希。原直接读取失败仍是历史事实；补入原件不等于原文学问题自动解决。
2. 经已有 `Engine.reference` 追加原审核全文、来源说明、两条问题的逐项核查要求及旧首审全文。该入口生成有真实资料增加的后继版本；不修改正文、Canon、作者决定、审核标准或数据库结构。
3. 由真正独立的 Dot 审核上下文领取新版本 `review`，按现有完整阅读、全部正文覆盖及四维合同执行。特别核对第3章旧确证错误 CH03-IND-001、相关稳定状态 ID、历史返修和现行正文。体验分歧及命名 Unknown 保持各自状态。
4. 新审核逐条说明旧失败、现有原件、实质问题的当前证据及剩余未知，提交并发布新版本审核。只有新版本 `assessment.can_accept=true` 且 `accept` 实际成功，才可称资料缺口在后继版本闭环。旧版两条 unresolved 和原发现保留原样。

同版本的另一份空审核不能覆盖旧阻断；`correct_records` 也不是修改 completed review 的入口。本次没有新增关闭接口或修改门禁。

## 已完成的追加

- 补证前版本：`f8e3bcd2a58ecdd1e55db606494f9b22b7e9647574a38411f3def1211f4d82db`。
- 后继资料版本：`3c526a62d9ae76afb30c1465116a23568a1f78244485f7984cbb78044f373726`。
- 唯一新增作品文件：`reference/f995aa13119a4e8ea8c12d29a027934e.md`，23855字符，SHA-256 `968c734f2a91b455e522e49103e02575221845889e3f4c3567002af139e0244c`。
- 5381个旧文件逐项哈希相同；原当前148份作品文件逐字相同。原数据库旧行除作品当前版本指针外保持；旧首审、69份checkpoint、上传与失败历史保留。
- 控制哈希仍为 `fac04df69e037eef05a4e67e06838befacb47e0ab313964dde22dddbc68ec3b9`，运行源码树仍为 `75b83eb95031d47ee64a9bd2f34cd0ee241fd3de8a32554f0fbb412e1d53f332`。
- 追加后服务端仍拒绝验收，原因是后继版本缺少独立审核及全部正文覆盖。已将该版本交给 Dot 完整复核；此处尚不是通过回执。

补证包同时标记首审摘要“002已区分衣物溅湿与干鞋”与现行正文、010返修说明不一致。正文是鞋袜留在干砖、抹去脚上水砂再穿；新审须亲读并纠正引用，不覆盖旧首审，也不据旧摘要改写正文。

## 实际运行端与失败保留

Hub/Novel 已于10月26日迁到搬瓦工，当前正式入口为 `https://192.243.115.205:8443/`。本次先按旧项目文档只读检查了 AaITR，发现旧业务服务停用，随后核对迁移记录和实时插件来源，在搬瓦工正式 API active 的资料根完成导入。AaITR旧副本未写入；其暂停不等于当前 Novel 工作区不可用。

作者在迁移会话已取消 Novel 云端工程自动维护的恢复，本次未恢复该环境或旧 OAuth 兼容桥接。原维护文档是历史来源，不能据其旧地址执行作品写入。

第一次导入的 Python 脚本在读取编码阶段被拒，任何语句都未执行；保留失败后使用 ASCII 无损转义传输同一内容，导入成功。本次没有删除原失败，也未将尝试记录当作成功。

本机证据：`.local-validation/ch37-evidence-closure-20261027/` 内的 `prepared-evidence.json`、`evidence-addendum.md`、`import-receipt.json`、`import-failure-1.txt`、目标运行回读与凭据清理回执。服务器导入前数据库备份及保留性清单位于 `/root/ch37-evidence-closure-20261027/`，仅用于事故诊断/恢复，不得直接覆盖后续新数据。

本轮限第37章补证复核与验收，不推进第38章。

## 独立复核进行中

新审核 `99d45c4f2c1843898de2606b229b6265` 于 `2026-10-27T11:33:23.254791Z` 实际领取，attempt=1、no_progress=0。原生上下文为 `/root/continue_ch37_first_review/independent_reference_successor_review`，Dot回报以 `fork_turns=none` 新建、未覆盖模型；业务侧 context_ref 一致，实际计划70批，plan hash为 `0c073595288ebe98c86afeacc44b53cfe6d7f8c7cfe490bc892aea1a58cb4b92`。第一批已实际保存，不能把执行者自述或交付字节数等同于理解证明。

新增reference通过正式连接器分4段回读，23855字符与本地导入稿逐字相同。后续关闭仍须新审核完成、结果及正式验收成功回读。

本轮最后回读进度为6/70批、6份checkpoint，已按每上下文1至2批接续至 `independent_batches_0005_0006`，同一task/attempt/plan；无新增unresolved，无uncertain请求。仍为running，未提交最终结果、未验收，不能称两条旧缺口已正式闭环。

原小时计划 `6ad240b839b48191816a75880f5be705` 已追加本次后继版本、新审核身份及停止条件。已通过计划页面独立读到追加全文，原计划仍启用、每小时；活动时不重复派发，同任务保留checkpoint接续，完成原审核与门禁验收后停止在第37章，等待作者后续指令。不存在待作者补密码或待操作员导入的步骤；剩余工作在Dot原协调链中继续。实际状态快照见 `RUNNING-RECEIPT.json`，它不是最终验收回执。

## 最终验收回读（2026-10-28）

本节是只读业务 API 与当前搬瓦工运行端 SQLite `mode=ro` / `query_only` 的独立回读。上面的“独立复核进行中”和6/70是当时快照，原样保留。完整回执及原文片段见本机 `.local-validation/ch37-closure-followup-20261028/FINAL-RECEIPT.json`，校验 `mismatch=0`，`unknown=4`。

审核 `99d45c4f2c1843898de2606b229b6265`；accepted 版本 `3c526a62d9ae76afb30c1465116a23568a1f78244485f7984cbb78044f373726`；result SHA-256 `eee677c7e8494916a0b59c45483fe3fff55a541e0e4f278cc2d7bace6d5af5d1`；plan SHA-256 `0c073595288ebe98c86afeacc44b53cfe6d7f8c7cfe490bc892aea1a58cb4b92`。提交 `2026-10-27T18:36:00.703450+00:00`，发布 `2026-10-27T18:36:25.218343+00:00`，验收事件 `2026-10-27T18:37:23.535682+00:00`（均为 UTC）。初始 context_ref `/root/continue_ch37_first_review/independent_reference_successor_review`，最终综合 `/root/continue_ch37_first_review/independent_final_synthesis`。

新审核已完成70/70批、70份checkpoint，attempt=1、no_progress=0；`task.submitted`、`task.published`、`revision.accepted` 分别为事件648、649、650，审核登记与版本一致。当前 `status=accepted`、`can_accept=true`、`blockers=[]`、活动任务0。回读前后全库任务148→148、checkpoint2757→2757；Dot网关登记任务130→130，不能将这130当成全库任务总数。运行源码树仍为 `75b83eb95031d47ee64a9bd2f34cd0ee241fd3de8a32554f0fbb412e1d53f332`，三个部署文件与开工本机和release清单逐字哈希一致。

独立性记录来自业务 context_ref、70份串行checkpoint及最终结果的声明；它们能证明这些记录实际保存，不能独立证明平台身份、原文理解或协调者绝未参与。原生spawn创建时间与turnID仍为 **Unknown**，业务task创建时间不冒充原生spawn时间。最终结果明确区分串行reader的覆盖并集与综合者亲读，保留失败、更正和旧分歧。

新审记录逐条核了两份旧原件及八项旧问题，并结论CH03-IND-001所指具体错误在当前记录中不成立；这验证的是新审核实际给出的结论，不是本轮再做一次文学审核。旧首审两条读取失败、69份checkpoint和旧结果仍保留。新结果原始findings有4行，其中带checkpoint哈希前缀的一行重复同一阅读体验；三类实质待关注均保持open/minor，详见[处置单](chapter37-followups-2026-10-28.md)。

`runtime/dot/continuation-fence-shizhi-zhicheng.json` 仍在，绑定旧首审 `7c32c0b07e4447f08c3d5dbbde234b83`；本轮未改或退役。原小时计划 `6ad240b839b48191816a75880f5be705` 从实时编辑页核实启用、每1小时，保存按钮一直禁用，仍保留完成37章后只读等待的停止条件。没有给Dot发消息、没有启动38、没有修改计划、作品、数据库、审核规则或维护环境。

**系统门禁通过≠文学认可。** 作者本轮决定：第2–3章说明密度不返修、交作者裁决；标题及许小满不单独导入资料，补查要求随未来第38章写作和整轮审核一并落实；第38章仅准备启动包。首章标题原始动机及handoff原始创建/写前传递时间仍Unknown。找到本机handoff副本不改写本轮新审当时固定包缺件的历史。
