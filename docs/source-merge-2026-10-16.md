# 本地与云端源码分叉合并（2026-10-16）

PR #1 已合入 main；作者随后批准在原 `codex/v1-local-workflow` 分支新建[后续 Draft PR #3](https://github.com/ythyy9/Novel/pull/3)。没有强推、重置或修改 main，也没有恢复嵌套模型调用。

## 历史与本地保护

以 main `066106fcbcdc886b9cc4ca482811e096bf2eaa47` 为第一父提交、原本地 `bf8149244559a9c66290fbaf03a899dfd08bec16` 为第二父提交，生成合并 `e78b2858546598a728ce26265fcf0e461fc8c50d`。原 `e8705429b086f4a121b95e91526a832da3398649` 和 `bf81492` 的 SHA 均保留为祖先，没有用等价新提交替代。

代码和测试采用较新的 main：包含执行所有权、持久失败记录、PeerEvidenceError 门禁、NTFS 删除侧文件重新核对和有界快照 rename 重试。`novel/`、`tests/` 与 main 无差异；本地独有的两份历史验收文档保留，不重复叠加旧代码实现。

协调后的 17 个工作文件逐字节恢复；345 个 books/runtime/实验资料文件哈希保持不变。命名规则四文件随后以独立提交发布并修正协议路径，原始字节仍保存在 `0a2e35b` 和本地快照；其余 13 个工作文件保留原字节。尚未完成的 README、评估、作品与交接文档改动保持未提交，不将它们假称为干净工作区。

本地恢复材料在 `.local-validation/source-merge-20261016/`（含第一轮完整快照、current-root-snapshot、原始补丁和各轮失败日志）及 `.local-validation/main-sync-20261016T115107Z/`（含 Git bundle）。备份分支 `codex/backup-local-before-main-20261016t115107z`、stash `64b3f8b` 和 `4da865f` 均保留。没有覆盖式同步 books/runtime。

## 规则与工程验证

`2f231d51a334613628af8798f24fbe04b6beb17d` 发布准确命名规则，后续全部专名须有来源、选择理由、寓意和语境，区分事实、创作解释、Unknown 与作者采用状态。作者已确认第二版及 275 字试读中的名字没有问题，该确认不扩大为整章文学验收。

命名记录使用现有协议允许的追加式 `revisions/naming-<record-id>.md`。旧的 `research/naming.md` 与 write/revise 协议冲突，已修正方法而未放宽验证器；外部词源研究仍走独立 research 任务的结构化 JSON。已有记录不得覆盖。艾宁/避沈及宁字笔迹的剧情依赖保留。

Windows 全量 240 项通过，231.867 秒；源码与本次最终源码相同。三类工程任务包实际读取完整新方法；write/revise 实际提交并发布合法命名记录，旧 research 路径仍拒绝，review 包也读回。全过程没有模型调用。路径修正后的 [PR CI](https://github.com/ythyy9/Novel/actions/runs/38897888661) 四项 Windows/Linux、Python 3.11/3.13 job 均 success。

旧候选的一轮 Windows 失败日志实际捕获了 `F:/$Extend/$Deleted/` 删除对象解析路径；采用 main 中已经针对该竞态的有界重新核对修复，没有再以“尚无路径证据”描述它。原失败、准备脚本错误和之后成功结果都保留，未删记录制造通过。

## 真实双端复验

使用双方独立测试副本和[获准私有 Drive 文件夹](https://drive.google.com/drive/folders/1Y2TztNFidtLPGKDuIdmoTd10aRr-g3l3)，源代码及进度仍走 Git。正文、作者原话、不可变版本、任务数据库、相关运行记录和回执以固定文件 ID、清单及 SHA 保存版本；不含参考原作全文、凭据或无关实验。不用聊天摘要或 Notion 代替原件。

测试源码固定为 `2f231d51a334613628af8798f24fbe04b6beb17d`，controller hash `691cc4636902515fe27a5c9251715ab906596a0ddc3eba0ee6c59ea70477247b`，control hash `fac04df69e037eef05a4e67e06838befacb47e0ab313964dde22dddbc68ec3b9`。原 d71 控制器及已完成交接的包、回执和数据不改写。

最终测试包 [83d8bf679843 ZIP](https://drive.google.com/file/d/1OzyyCZF2jFFw5AosKMJ1i_7ZAoXBxRvS/view)，514366 bytes、146 文件，SHA `83d8bf67984313e6d3ffa8852135612f514cc2db2da3e28a17be5fa41aa95a85`；baseline `82c3b6effd1fe81f10e3119710fdba1820bee0d7cf1cdb251d9cee9ed3c86922`，任务 `d7a8327572ca4806b91b526c3bb10a0c`。

本次只复用之前真实外层云端产出的 275 字片段，验证合并后的传递、任务身份、提交发布与回执，不生成新故事，不把回放称为新的文学效果。正式第一章第二版仍是 `b31e137b…`，正文 SHA `0a6df1539c4bf4c4714c3293ae8a262f1991ede152215f67b8c0a4872e0add1e`；历史 cc 第一版不能代替它。

真实云端已接收、核对并认领新任务一次，按本次任务身份复用旧真实试读，提交并发布 draft；本地随后实际 receive/apply，云端实际 confirm，本地实际 ack。输出版本 `fffe07db1d7bfb30fc4cbcba394a0abd79bfc4bf8d0e15997f11546cb8123c9f`，返回 bundle `8aec2bd30b4df3a62fb5a375ff6eb8844676a98883916730bf9d99b8f783057f`；共同基线 agreement `83b85a7f2bb7287168edf7533a6796b503d2bfe148ce939e6b1c6cf66031cf63`。

- [云端真实返回 ZIP](https://drive.google.com/file/d/1ZQDYF_p6s41XbnYV4hV6abjiD2ERROHw/view)：101486 bytes，SHA `205303467f55080ad55911d991b49456e9e5d5ef74ec6e5684c15c14717019e1`；26 项文件清单及 manifest 均经本地独立验真。
- [本地实际应用回执](https://drive.google.com/file/d/19rutcKQd_r6MEGGdQTXjB9fEJ5XV1UVJ/view)：SHA `b808de85149d1cf8306a2138c71eac05b6d600ef541fe54aef126642111ef407`。
- [云端共同基线确认](https://drive.google.com/file/d/1LsIkYI_Cb_gUhejup-MiZikPL-JZe7_-/view)：SHA `bd5eadac4f9397bfbbe5cae34685abf06d273a86845604b892fafa54bdb99a37`；[云端确认回读](https://drive.google.com/file/d/19_z3YRgtQS7f2PchOXVV6s4fJbd0Bd3V/view)。
- [本地最终 ack 回读](https://drive.google.com/file/d/1pqpzEBMwK8aiBwLNggT9nj1_ql-YRyrK/view)：SHA `038f64afc9b9aeb372512ccc7662d8eda27316cb3d468c8ffaf5cb3c9d6f1735`。

双方共享的可执行语义状态一致：相同版本、作者五条原话反馈（含 `400487…` 命名确认）、三份作者决定、结果及累计次数、控制器和控制文件。两端都实际读到原两条反馈诊断；旧审核 `32fe3410…` 的 stop、resume 和 attempts=2 保留。各端独立审计保持原样：云端 confirm 后 10 快照/56 事件，本地 ack 后 10 快照/60 事件；没有改写数据库来追求文件相同。

重复 receive/apply、confirm、ack 均实测无重复执行或新增重复事件。使用这个真实云端返回包在可丢弃本地工程分支验证：旧包不回退更新版本，双端分叉明确 `diverged` 并拒绝 apply，缺失第一章附件时 audit 停止且新任务 attempts=0，历史失败/重试事件不丢失。工程分支用于边界测试，不能代替上述真实双端流程或文学反馈。

完整本地记录在 `.local-validation/source-merge-20261016/final-handoff/`，含 `closure-readback.json`、`boundary-real-bundle-readback.json`、两端包和回执。旧的准备包与方法路径不兼容阶段保留，不重写为最终成功。

## 接续入口与下一步

本地正式资料根仍为 `F:/Novel`，第一章仍为正式第二版 `b31e137b…`，没有把测试输出或 275 字片段合入正式正文。本次测试根是 `.local-validation/source-merge-20261016/final-handoff/handoff-data`。云端测试源码入口 `/workspace/Novel/.local-validation/source-merge-handoff-20261016`，其数据根为 `.local-validation/final-83d8/bootstrap/data`，均使用明确 `--root`；不要把测试 draft 当成新的正式章节。

云端之后新作品的标准命名规则入口是该源码目录下 `.local-validation/standard-naming/continuation-root`，control hash 为上述 `fac04df…`，当前没有作品或任务。它只证明后续入口已配置，不表示本作品自动迁移或已准备续写。历史 d71 控制器/data 仅用于复现；后续实际作品任务须选择正确资料根和当前作者决定，新任务按新控制文件创建，不能重写旧任务 hash 或清零次数。

作者已认可当前名字；新增名字选择能力和整体文学效果仍未验收。下一步是确定后续有界创作内容并继续遵守命名依据、笔迹依赖和原反馈；本轮不自动续写、不恢复嵌套模型、不建立 Notion 看板。

