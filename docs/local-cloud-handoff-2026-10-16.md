# 本地与云端真实交接验收

日期：2026-10-16。状态：真实本地→云端恢复收件→外层云端生成→本地受控接续→云端confirm→本地ack已通过。整个验收在可恢复的独立副本完成，正式第一章未覆盖；作者阅读与文学/方法效果仍待评价。工程测试与实际两端记录分开列明。

## 保护与代码基线

原主工作区为 `codex/v1-local-workflow` / `bf8149244559a9c66290fbaf03a899dfd08bec16`；远端已核对为 `d71c3f9dda7e00b972621221a41fafefbabe633c`。本地有两个既有未推送提交，远端有九个后续提交；不回退任何一端，不覆盖现有参考书功能、README、评估文档和创作资料。本次真实验收的本地控制器是由准确远端提交导出的独立目录，云端也使用该提交；正式工作区未作覆盖同步。

全量稳定快照位于 `.local-validation/local-cloud-20261016/snapshot/`，包含922文件、11,827,669字节及Git目录。拷贝前后源文件哈希稳定、副本逐项匹配，四个SQLite库完整性检查均ok；Git fsck退出0，悬空历史对象保留。原有584个非Git文件回读未变。恢复应复制到新的独立目录并验证manifest，不覆盖现有工作区。

## 第一章版本与作者反馈

| 身份 | 版本 | 正文SHA-256 |
| --- | --- | --- |
| 最初草稿；后来仅补状态引用，正文相同 | `836600af9d53ced390281403ca55dfaf3c0455355084955343b933d91b722696` / `c974f8d371cc60cbdb1a247c0fbd8550f90f61183ceb16b0b2e916c5e24be15c` | `2ed9cbaf2f0b161d4dc62b2abdaa7a98527d63133e446268112624e52d596f59` |
| 作者命名反馈对应的旧版；已修咳嗽和锁具动作 | `9483c7d94eeede01bc057d6d247b17271b475274526ead6ae3504feb4327b674` | `0fb7574679a0bcbab37a54766a1059f718bebba0a02d562225039c8991d5a1dc` |
| 艾宁命名与可理解性首轮改稿 | `f31c7c6ffb21f0f5ac0a6ed58bd18dd6ed93c7201c290bd1cf56566c3122bd51` | `03f5999500ba5b2ca029d962c4b9a98ec914ff5412339281e1652a787df42b4c` |
| 当前第二版，经局部修复和对应复核 | `b31e137b0fb8be41c0734c4b6cfdcc84512e30533d116b76448d517830fff278` | `0a6df1539c4bf4c4714c3293ae8a262f1991ede152215f67b8c0a4872e0add1e` |

SQLite、workflow.json和不可变快照共同指向当前版。runtime/writing阅读副本仅有285处CRLF/LF差异，文字相同；阅读副本字节SHA为 `1025eaaee0046282e9e3e6e71baa6da7a771fef34b701edd067806b1007e7b84`，两者均保留，不假称字节一致。云端此前cc粘贴的历史第一版独立SHA为 `f23020f6e6be336e0234f22f07431fe2848799bf8d01f7c302aea705b72eeb1d`，9534字节，未绑定正式版本；不能据其来源标签假称与任一本机快照字节相同，更不能当第二版。

作者命名原话在 `runtime/writing/shizhi-zhicheng/author-feedback-naming.txt`，已在原反馈 `d6bab85c2a0740d590e9bb5ea540aba2` 上用现有feedback-diagnose追加真实诊断。原话、四条作者反馈、三项作者决定、旧版本与旧审核不改写。逐行差异与来源索引在 `runtime/inputs/naming-case-20261016/`。

可证实原因：初次write指令已经预填沈照；任务包只带初始状态与参考创作授权，具体命名在正文生成前已由上游Agent暂拟。现有材料不能说明上游的隐藏动机、训练偏好或沈姓总体频率，也不能把后来才提出的避沈偏好当成最初已违反的指令。

本作预防措施位于下一次命名和task.instruction形成之前：回读艾宁决定及避沈要求；有新名时先核对原作词义、文学出处、命名语境与Unknown，再比较音译/音意结合/本地化，检查家庭代际称呼。返修提交前枚举字形、签名、谐音、人物name/holder及精确引文依赖。当前稿已从照字四点拖横改为宁字反向末钩，保留辨字、认签字和承认责任的剧情作用；55处状态来源实际逐项命中，当前正文无沈照残留，历史旧名和稳定ID保留。措施只针对本作品，不自动升级methods/policies或审核门禁。

## 共享位置和范围

经作者单独批准，现有Google Drive中创建私有 [Novel-Handoff](https://drive.google.com/drive/folders/1Y2TztNFidtLPGKDuIdmoTd10aRr-g3l3)，回读shared=false且只有本人owner权限。两端现有连接器均已实际查询；本机已从该位置下载并验证上传包SHA。每次包和回执使用独立文件ID及哈希命名，不覆盖旧文件；代码和工程进度继续使用既有Git分支，不创建Notion系统。

初始包 [novel-v2-bootstrap-20261016-27776922f4a6.zip](https://drive.google.com/file/d/1y_xAyqJBp1F2HJf3UVxWza71QI_5OO8w/view) 为515632字节，SHA-256 `27776922f4a6e6d69eeedd24f16895a1ba32b5457fa4989747347b016ad1fe6f`。清单含145个文件，另有manifest自身；内容为本作9个不可变版本、作者原话/诊断/差异、SQLite、相关任务包与失败日志、控制文件和命名说明。原作全文/提取、未选实验、凭据、Git及未提交源码保持本地。局部manifest不是整个工作区备份；完整保护快照另留本机。

本地独立资料位置为 `.local-validation/local-cloud-20261016/acceptance-data/`；批准的云端独立位置为 `/workspace/Novel/.local-validation/real-handoff-20261016/data/`。首次使用现有停写副本恢复加v2基线，不把单个文本假装成SQLite/版本链已迁移。基线ID `dc4c60c8ef2a3582c7d9a6545fd469f6bedbcda8fda45be41a5b5c7250630165`，选择任务 `3c25249ec7d34141b011378f8f4b6817`；本机恢复为same_selected_state，9快照/50事件，旧审核attempts=2、失败和resume均保留。

## 工程与实际状态

准确d71控制器在本机Windows执行 `python -m unittest discover -s tests -v`：185项全部通过，195.032秒，exit=0，无跳过。日志 `.local-validation/local-cloud-20261016/remote-baseline-unittest.log`。这是工程验证，不是双端或文学验收。

实际云端引用下载曾两次遇到代理CONNECT403，未计为收件；之后通过同一已授权Drive连接器明确支持的有界legacy字节返回取得ZIP，SHA及145项清单真实通过，没有改变代理、网络、认证或权限。原失败现场保留。另有一次feedback-show误传诊断ID的只读错误，随后用原反馈ID回读成功；未消耗创作尝试。

原外层云端Codex实际读固定第二版任务包，生成275汉字后续试读；现有task-submit --expected-attempt 1、task-publish成功，任务completed/attempts=1，输出仅为draft，无独立文学审核。返回包 [cloud-return ZIP](https://drive.google.com/file/d/1aKNztggmdE5bbsmnJGnliaM-keimrn82/view) 为127358字节，SHA `e1faec83be44865e263e58dc51456ccccda22b0e84069dc3be6ffc2d79d177d4`；本地实际下载、53个清单文件核验和baseline逐字节比较通过。

本地receive/check得到incoming_ahead，明确expected-base/expected-target后apply成功。试读片段SHA `8707bceb79340097a2b5cd34ba3659105ec58b1c4c19087ecfe54903d1b80730`，测试当前版本 `fafee60d7cf3f92ec3e54e01a0ae0b1610dd59a7e5f461dbec0eab647d8215a8`；第一章原字节和全部三项作者决定不变，原有稳定ID保留，61处最终状态引文实际命中。

真实[本地采用回执](https://drive.google.com/file/d/1wFBjHPxzWrVhx2jMoGiPfz3ajg5w8FvV/view) ID `503560e0832f34c4addbfcdba159399063efaefb4020378450cdfb22028f40c6`，文件SHA `eed04004cdbe64ddcb32e47133edc5ac929b9d500a0be7626cfd5d2651193d40`。云端真实读取后执行confirm；[共同基线确认](https://drive.google.com/file/d/1oz_msDECp3KCIIi9vCQbpBDM81KwGV66/view) 文件SHA `5762d76e53360f994c5345c8c8cc3a061a16d2eb9b8ba96b4b6b3956c1616132`。本地实际下载校验并ack登记，双方agreement ID同为 `4f9d4562ddeff426ccfe0526f9c8e34f66afd6cad5156e7c32e8b7795f4e6f65`。采用/登记不是作者批准。

[本地ack回读](https://drive.google.com/file/d/1Q7wh06J_d7e9zhUPQhN4I6Nqzg1pae2X/view) 文件SHA `84ddb94ed7ccd00adfc8ffa9faffa4f60794789bb9899e43909b690aa3b0c405`。双方共同语义状态包括同一作品版本、任务结果及次数、原反馈、控制器和控制文件；各端审计原样保存。云端confirm后10快照/55事件，本地ack后10快照/59事件，不能为求数据库相同改写历史。

## 幂等、旧版、冲突与失败保留

本地对真实返回包重复receive和apply、云端重复confirm、本地重复ack均实际验证，未重复任务执行或登记、未增加重复事件。以真实云端包对明确标注的本地工程派生分支验收：旧包重放不能回退更新版本，双端均从旧基线前进时check=diverged且apply拒绝，缺当前正文附件则audit停止且attempts保持0。工程派生只在可丢弃副本生成，没有模型或Mock调用，不能当成另一段文学创作或真正实时分布式锁。

历史审核任务32fe34109dd14a078bacad136269176b的原stop、resume和attempts=2在两端实际恢复、接续和确认后均保留。一次边界脚本将云端已有只追加修订记录重新提交，被控制器正确拒绝；修正脚本选择范围后通过，原失败副本及记录另留，没有改门禁或增加真实模型尝试。报告为 `.local-validation/local-cloud-20261016/boundary-real-bundle-readback.json`，失败记录为 `boundary-failures.jsonl`。

## 反馈迭代的实际结果与下一步

既有反馈诊断链已追加初次定位与真实试读结果两条记录；新记录 `0feb9ef7a3a04b3791ef8949565317b9` 的SHA为 `13e2e401b765c495cf470832d2b2a7a0d7476f969c1a9577586c88668414bd86`。原诊断保留其记录当时的pending，不倒填之后成功。追加记录是操作员有证据的观察，不是作者评价，也不自动启用通用方法。

可观察改善仅限约束沿用：本次任务包明确带入艾宁/避沈、宁字末钩依赖及不改第一章；云端实际片段保留这些约束和认签字后的责任，未泄漏旧名，未新增姓名。它未检验新名选择频率、跨作品推广或文学体验。

共同下一步：等待作者阅读当前第二版和275汉字试读片段；文学与命名方法效果待评价。不自动续写整章，不恢复程序嵌套模型调用，不建立Notion看板。

## 接续入口与边界

本次保留准确d71控制器在 `.local-validation/local-cloud-20261016/controller/`；运行现有CLI时从该目录执行，并显式 `--root ../acceptance-data`，正文、版本和回执则使用Drive中固定文件ID/清单以及两端独立目录。主工作区现有两项未推送提交及未提交参考书功能仍保持原状，尚未合并两条Git历史，不能说正式工作区源码已整体同步。该限制不混同已完成的真实测试副本闭环。
