# Novel 云端工程维护

2026-10-20 作者授权：补充正式记录更正和云端部署入口，使 Dot 可委派云端 Codex
修复、测试和部署日常工程问题；保留原任务、作品、尝试、上传、checkpoint 与全部历史，
不中断正在进行的创作。创作执行仍由 Dot 完成，程序内模型调用保持暂停。

## 实现

- `novel/corrections.py`：独立的 `correct_records` 任务校验，见 `docs/protocol.md`。
- `ops/maintenance.py`：独立 HTTPS 后端，提供源码、版本状态、候选提交、隔离测试、
  双实例服务切换和代码回退。入口为 `https://47-178-34-133.sslip.io/novel-ops/v1`。
- `ops/api_runner.py`：受操作员管理的 API 启动器，响应携带实际 release hash。
- `ops/OPS-CONTRACT.md`：云端执行者操作合同；源码下载包中包含同一份说明。

部署入口只接受 `novel/*.py` 和 `tests/test_*.py` 的完整文件，不接受任意命令、
删除操作、作品目录、数据库、控制文件或运维服务自身修改。测试在单独 Linux 用户及
systemd 隔离环境中运行，无网络、不能访问正式作品和服务凭据。
验证过的待部署源码由 root 持有，测试用可写副本与它分离，部署时再次校验原件。

运行代码仍使用既有 API 的业务账户与权限；文件白名单和工程检查不能证明任意代码
语义上不会触及业务数据。云端维护者须审查差异，不能用工程修复改变作者决定、
审核标准、权限范围或数据结构。此类变更需要单独的操作员方案。

正常部署先启动另一 API 实例，核对本机健康、匿名鉴权与运行版本，然后用 Caddy
平滑重载切换上游。原请求由旧实例完成，确认连接排空后再停止旧实例；Worker 不切换。
切换失败恢复旧路由。代码回退不恢复数据库或作品旧版本。

## 云端连接

使用 Private / Only me 的 `Novel Maintenance` 云端环境，为目标主机配置专用
`NOVEL_OPS_TOKEN` network secret。凭据只用于该 HTTPS 目标，不包含 root SSH 权限，
不得写入聊天、源码、工具输出、URL 或作品任务包。服务端只保留令牌哈希。
令牌应经受支持的私人配置界面保存，并在新云端任务中实际验证；本地请求成功
不能代替云端接入验收。

实际建立独立 `Novel Maintenance` 环境，配置标识
`cecfg_6ad74a81876c8195837dc7605869b7b4`，保留旧 Novel 环境与旧任务。
原 IP 地址经云端代理出现证书主机名不匹配，已有内部 MCP 隧道亦被 CONNECT 403 拒绝。
作者随后明确同意使用 `47-178-34-133.sslip.io`，并将专用令牌唯一接收主机限定为它；
该名称由第三方 DNS 映射到同一 VPS，服务器自行持有有效 TLS 证书。
正常 TLS 校验和云端代理均保持启用。

Dot 发现工程问题后携带错误、任务身份和版本交办云端 Codex。云端先读取部署源码，
完成修复与隔离测试，再部署和回读真实状态。作品侧超时先查询原请求；失败 request ID
保持历史，不盲重放、不重置尝试或以新任务替代。工程维护不自动创建定时监控。

## 本次执行证据

本地保留在 `.local-validation/novel-self-repair-20261020-01a158dd/`。
独立入口与 `correct_records` 已实际部署，源码树 SHA256：
`1a4279009e1fc753b9a660368eb24b1eb320a00e9809e128595db337e45c4751`。
运行 API 为 `novel-api-blue.service`，cwd 保持原 Hub 路径，PYTHONPATH 指向
`/opt/novel-ops/releases/records-general-20261020-a2/source`；Worker PID 未变。
服务端隔离检查 290 项中 285 通过、5 项平台跳过；独立维护入口专项 8 项通过。
正式插件元数据已刷新，实际工具参数包含 `correct_records`。

首次切换后，旧 API 退出曾连带停止代理。已恢复代理，修正完整 systemd unit 的
依赖关系，并增加停止前检查；再次停止旧 API 后代理 PID 保持、健康检查通过。
这次中断保留在执行记录中，不声称首次切换全程无中断。
131 个原任务、4365 个既有文件及部署前的 1539 份 checkpoint、2757 个上传片段、
572 条事件和 73 份审核记录经回读确认保留。原第34章复核仍沿 attempt 1 继续。

真实云端 `/status` 与 `/source.zip` 均为 HTTP 200，59 个源码文件逐项匹配；
ZIP 哈希与源码树哈希分别核验，未输出令牌。环境已实际显示 `Environment published`，
Only me 保持。原 Dot 已创建并完成
[验证 Novel 云端维护通道](https://chatgpt.com/local/01a15913-741a-7147-8615-59dbbb3400d0)，
真实运行于 durable 云端 `/workspace`。一次已部署版本的幂等 POST 返回200，
完整回执、deployed_at、API PID 与完整状态均保持一致；这是接口重放验收，不是新的换版。
顶层合同补充幂等语义后 ZIP 哈希变为
`9fc3585c3991500c13a076417fe76b28353f3347aee7e97aafe8e873b37c8ff1`；
仅该说明变化，59 个版本文件及源码树哈希不变。旧包和旧失败记录保留。

最终回执为
`.local-validation/novel-self-repair-20261020-01a158dd/DEPLOYMENT-RECEIPT.md`。
临时 DPAPI 凭据、状态文件、本地部署令牌副本和临时剪贴板已清理；
Only me 云端的持久秘密绑定及服务器令牌哈希保留。未创建定时监控、提交 Git 或推送源码。
