# Novel 云端嵌套 Codex 接入：最小平台支持请求

状态：待平台处理，未发送支持工单。无需作者作品或认证秘密即可调查。请保持现有认证原位置、仓库权限和沙箱边界；不是申请全网放行或复制凭据。

## 问题与环境

Novel 云端任务，Linux x86_64 / Debian 13，Codex CLI 0.159.2。仓库 `/workspace/Novel`。父层云端任务及 GitHub 连接器正常，但嵌套 `codex exec` 的 app-server 初始化无法完成。

原审核任务 `e8817187f6ef4170a03d65c39dd70e6e` 仅尝试一次，保留 `blocked / tool_failure / attempts=1`，没有模型输出。该任务不能通过另建任务或重置次数绕过。

## 最小复现（供平台侧使用，本轮未重复执行）

```sh
codex --version
codex app-server --stdio </dev/null
```

默认报无法初始化 `/run/codex-environment/codex-home` 下 SQLite。以前进一步执行以下**无模型请求**诊断，SQLite 实际成功落到工作区，但初始化仍失败：

```sh
codex --strict-config \
  -c 'sqlite_home="/workspace/Novel/.local-validation/cloud-20261014/codex-runtime-diagnostic/state"' \
  -c 'log_dir="/workspace/Novel/.local-validation/cloud-20261014/codex-runtime-diagnostic/logs"' \
  app-server --stdio </dev/null
```

退出 1，`Error: Read-only file system (os error 30)`。失败系统调用为：

```text
open("/run/codex-environment/codex-home/installation_id", O_RDWR|O_CREAT|O_LARGEFILE|O_CLOEXEC, 0644) = -1 EROFS
```

另有 tmp/arg0 chmod 的非致命 PATH alias 警告及 uid_map 写入拒绝；不保证仅处理 installation_id 就足以完成整个执行链。

[官方 0.159.2 源码](https://raw.githubusercontent.com/openai/codex/rust-v0.159.2/codex-rs/core/src/installation_id.rs) 的 resolve_installation_id 从 codex_home 拼接固定文件名，先读写创建并加锁，再读取已有 UUID。故“预置一个只读 installation_id”也不足以满足当前实现。安装二进制报告 build commit unknown；不能把源码阅读当成本地二进制字节级同一证明，但行为与此前系统调用证据一致。[官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference) 的 sqlite_home/log_dir 不是安装标识目录设置。

## 本轮新诊断：既有执行接口与网络

只读查看 `codex app-server proxy --help`、`daemon --help`、`doctor --help`。proxy 可连接已有 Unix socket，但官方 `codex doctor --json`（20秒外层上限）退出1，明确 background server is not running；未运行 start/bootstrap/restart，没有探测其他用户或项目 socket。

官方 doctor 自带脱敏报告另指出：ChatGPT HTTP 推理端点 connect failed；WebSocket 握手 `Proxy connection failed: HTTP CONNECT failed with status 403`，并有 DNS lookup failed 提示。没有生成模型回合、未改变代理或申请网络权限。仅 api.github.com 的既有授权不涵盖此推理网络需求；不要将 GitHub 连接器成功当作 Codex 推理可达。

## 请平台具体处理

1. 确认当前 Novel 云端执行环境是否支持嵌套订阅登录 Codex；若支持，提供可用的托管执行接口，或支持纯运行/安装标识状态与现有只读认证路径分离的 CLI/平台配置。不要要求用户搬认证或直接 chmod/remount。
2. 检查同一环境的 ChatGPT 推理端点 HTTP/WebSocket 连接策略。请提供官方所需的最小目的地与受支持通道；涉及新的网络安全设置先向用户说明并取得批准，不能自行放开所有互联网。
3. 平台确认修复后，先无模型初始化验收；成功后再由 Novel 控制器显式恢复原任务，保留第一次失败记录，执行一次真实结果→提交→发布→回读验证。

## 用户提交入口与附件

联系创建该云端环境的管理员/运行平台支持方；若属于 ChatGPT 托管环境且没有独立管理员，可通过 [OpenAI 官方支持入口说明](https://help.openai.com/en/articles/6614161-how-can-i-contact-support) 在 help.openai.com 右下角聊天入口提交本问题。只向支持方提供本文件和脱敏错误摘要；不要公开发布任务链接或上传认证文件。

环境内原证据：`.local-validation/cloud-20261014/appserver-configured-paths.log`、`appserver-configured.stderr`；新诊断 `.local-validation/runtime-interface-check/doctor.redacted.json` 及 `summary.json`。报告可包含环境/账户元数据，提供时只选相关脱敏检查项，不上传整个 runtime 或作品目录。用户可私下补充本云端任务定位链接，模型没有代发工单。
