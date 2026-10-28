# 第37章验收后的三项待关注处置（2026-10-28）

审核 `99d45c4f2c1843898de2606b229b6265`；accepted 版本 `3c526a62d9ae76afb30c1465116a23568a1f78244485f7984cbb78044f373726`；result SHA-256 `eee677c7e8494916a0b59c45483fe3fff55a541e0e4f278cc2d7bace6d5af5d1`；plan SHA-256 `0c073595288ebe98c86afeacc44b53cfe6d7f8c7cfe490bc892aea1a58cb4b92`。提交 `2026-10-27T18:36:00.703450+00:00`，发布 `2026-10-27T18:36:25.218343+00:00`，验收事件 `2026-10-27T18:37:23.535682+00:00`（均为 UTC）。初始 context_ref `/root/continue_ch37_first_review/independent_reference_successor_review`，最终综合 `/root/continue_ch37_first_review/independent_final_synthesis`。

回读结果 `mismatch=0 unknown=4`；当前accepted、活动任务0。全部原始发现保持open，以下是作者本轮指定的处置路径，不是线上finding状态更改，也不是对旧审或旧章的文学认可。原结果4行含阅读体验的checkpoint前缀副本，实质主题3项，副本身份完整保留于FINAL-RECEIPT。

## 1. 第2–3章说明密度

证据：`CH37-REVIEW-READ-0035-001`，`experience / minor / confirmed=false / open`，来源 `manuscript/003.md`，原文摘录（≤60字）：

> 她其实不知道会问到哪一步。她只知道陆桂枝还要从剩下的钱里数明天的铺费，而眼前这本簿子一合上，七户便还是齐的。

审核指出程序边界说明集中造成暂缓感，不是制度矛盾或确证错误；不以此概括全书。

| 合法路径 | 版本及审核代价 |
| --- | --- |
| 保留意见，仅在本机处置单交作者裁决（默认） | 不产生作品版本、不触发审核；旧章不返修，意见不被清除。 |
| 作者日后要求有范围返修，再走revise | 产生新版本；同步相关正文/状态/精确来源及后章影响，须新版完整独立审核及原门禁验收，不能只改两句即沿用旧审。 |
| 以后38章在新情境改善说明与行动分配 | 随正常write产生版本并整轮审核；不证明旧2–3章体验项已消失，不偷改旧章。 |

默认处置：本轮不返修。需作者裁决：未来是否要对第2–3章安排有范围的说明密度返修？

## 2. 第一章标题《墙后有人》记录缺项

证据：`CH37-FINAL-NAMING-001`，`concern / minor / confirmed=false / open`，来源 `manuscript/001.md`，原文：

> # 第一章　墙后有人

现有暂名补记不覆盖这个章题，七旧名决定也不含它；原始动机Unknown，不能为了补齐而倒写“最初就是如此”。

| 合法路径 | 版本及审核代价 |
| --- | --- |
| 在未来38章写作instruction要求补查，新增命名记录随章提交（默认） | 本轮不产生版本；未来正常write形成新版本，其整轮独立审核同时核查记录。旧章不变，原始动机无来源就继续Unknown。 |
| 经另行明确授权单独reference/decision导入资料 | 有manuscript时生成draft新版本，写作须等accepted，故先跑整轮独立审核再accept；仅补资料会多一整轮，本轮明确不采用。 |
| 保持现题，暂不补查只保留缺项 | 无新版本、无审核成本，但历史记录缺项继续存在；不等于来源齐备或作者确认。 |

默认处置：采用随38章补查，不单独导入、不改旧标题。需作者裁决：若原始动机仍不可考，是否认可“保留Unknown并仅登记当前沿用理由”的长期处理？本轮准备不以此等待启动。

## 3. 许小满命名所引handoff核验

证据：`CH37-FINAL-NAMING-002`，`concern / minor / confirmed=false / open`，来源 `revisions/naming-chapter4-20261016.md`，原文摘录（≤60字；全文在固定命名记录）：

> 先回查handoff/chapter4-naming-before-draft.md全文及revisions/namin

在本机 `.local-validation/` 与 `runtime/` 做了文件名和引用全文搜索，找到移交保留副本：

- 路径：`.local-validation/dot-pilot-20261016/takeover-preparation/formal-restore-inspection/sidecars/runtime/writing/creation-20261016/chapter4-naming-before-draft.md`。
- sha256：`cfff1ee8c5f8b5ac3647e553ec3cf1e6ded246006985b4fdfbd35c42e8550b0c`；1751字节、671字符。`formal-restore-inspection/evidence/sidecars-index.json` 记录同一原相对路径、长度和哈希。
- 旧正式任务包索引 `.local-validation/dot-pilot-20261016/evidence/formal-packet-index.json` 与 `formal-adoption-receipt.json` 均把 `handoff/chapter4-naming-before-draft.md` 记为671字符、同一哈希；历史 `activate_formal.py:76` 将上述runtime副本映射至该handoff别名（本轮只读，未运行）。因此不是仅凭同名猜测引用关系。
- 当前固定包的 `revisions/naming-chapter4-20261016.md` 全文1095字符，sha256 `8172c64c57565b0345e0e4c534806206c4f93ee3076cfdee33618459b0862f10`，与本机旧固定包记录同哈希。它引用handoff并采用“普通可逆候选”；副本的原创词面理由、成年职员语境与该记录一致，不借民俗或原作人物强加背景。
- 这证明保留副本与旧任务包别名的内容身份，不证明当前新审固定包已经补入。原始创建时间、原稿前实际传递时间仍Unknown，不用文件mtime或“写前”标题冒充时序证明；Dot采用不等于作者定名，家庭取名人等Unknown不补造。

| 合法路径 | 版本及审核代价 |
| --- | --- |
| 将副本全文、哈希和归档关系放入未来38章instruction，并在新命名记录保存供审核（默认） | 本轮只准备，不生成版本；38章正常write及整轮审核一并核查，不另造资料版本，不改第4章旧记录。 |
| 单独经授权导入原件为reference | 生成draft新版本，须整轮独立审核accept后才可write；本轮明确不采用。 |
| 暂只登记本机找到、保留线上来源限制 | 无作品版本及审核成本；当前新审的缺件历史保留，不能宣布finding已closed。 |

默认处置：本机核对完成，随38章携带核查，线上finding保持原样。需作者裁决：若原始时间链仍不可独立核验，是否长期保留该Unknown并接受已核的内容身份链？本轮不以补造时间链换取关闭。

## 第38章命名补查指令（416字）

命名补查（随第38章提交并审核）：先全文回读methods/writing.md、当前命名与作者决定，不改第1–37章。《墙后有人》查原采用依据；找不到则原始动机写Unknown，另记本次沿用理由及非作者定名状态，不虚构最初动机。许小满核对第4章命名记录所引handoff，使用启动指令所附经归档哈希核验的671字符原文，注明移交sidecar、旧任务包索引及固定包缺件历史；原始创建/写前传递时间仍Unknown。按revisions/naming-<record-id>.md追加两项来源位置、理由、寓意、语境、事实/解释/Unknown和采用状态，原件必要全文及哈希随新记录保存供新审回查，不覆盖旧记录、不冒称本轮已正式关闭旧finding。新增名字先说明再入稿，核name/holder、笔迹、谐音和精确引文依赖；引用失败写unresolved。不得单独reference/decision导入换版或把七旧名豁免扩至这两项。

## 本轮边界、待裁决及交付

第38章启动包仅保存在 `.local-validation/ch37-closure-followup-20261028/ch38-start-package.md`，expected_revision为上列accepted版本。未open_task、未改计划、未给Dot发消息。此处不附作品库导入回执，因为本轮没有导入。

与本机BLOCKED.md同步的当前待裁决清单：无工程阻塞；上列三项未来作者选择保留；原生创建时间、turnID、首章标题原始动机、handoff原始创建/写前传递时间Unknown。首次沙箱全量失败保留；宿主原测试331项、skipped1、OK，未改测试或源码。忽略目录内的BLOCKED.md随本机交付，Git只提交本白名单文档中的同步清单。

交付止于单个分支 `codex/ch37-closure-20261028` 的一个PR，不合并。线上任务/checkpoint总数与受保护目录开工快照在最终回执继续核对；系统门禁通过≠文学认可。
