# 参考书的自动检查、补充与全部阅读分析

2026-10-15 作者明确选择：以后所有参考书自动检查；查找整个系列、番外、短篇和附录；找不到就标明缺口并继续分析实有内容；取得新增材料后全部阅读分析，保留旧结论及修订依据。默认原语言未删节版，不拼接不同译本或修订版，不购买、自动登录或创建定时任务。

## 日常入口

参考书使用 `reference-add`。现有 `reference-import` 仍用于把作者给定的短材料原样追加进作品，它不把任意便笺自动识别为整本书，也不执行书目研究。

```powershell
python -m novel reference-add invisible-library --file 'C:\Books\book.epub' --title 'The Invisible Library' --author 'Genevieve Cogman' --work-id the-invisible-library --language en
python -m novel reference-status invisible-library
python -m novel reference-use invisible-library
```

`reference-add` 先保存原件、抽取全文和检查结构，然后自动联网检索系列书目、获取可用材料、分段阅读全文、综合各版本及系列。`reference-use` 重新检查书目变化，并复用哈希绑定且已验证的阅读结果；未读部分会继续处理。`reference-status` 完全只读。没有常驻进程或定时监控。

同一轮因调用预算暂停时，接续复用该轮已经完成的书目查询；该轮完成后的再次使用才开始新一轮查询。命令成功返回状态 JSON 不等于全部材料已齐全或全部分析完成，应检查 `stop`、`all_acquired_content_analyzed`、`series_analysis_current` 和 `gaps`。

添加同系列另一卷，继续使用同一资料库 ID，指定不同 `--work-id`、书名和文件。番外可用 `--kind extra`，附录可用 `--kind appendix`；相同作品的不同版本使用相同 work ID，按文件哈希分别保存和分析。原件是 LIT、提供的是转换 EPUB 时，可同时传入 `--original-file 'C:\Books\original.lit'` 保存两份文件；工具不自动声称转换逐字无损。

`--offline` 只保存、抽取及做结构检查，将联网核验和阅读保留为待完成。它用于没有网络或尚无可用模型的环境，不代表完整分析成功。TXT/Markdown 需 UTF-8；EPUB 使用 Python 标准库；HTML 保留页面范围不确定性。文本 PDF 需要可选的 `pypdf`，扫描 PDF 缺少 OCR 时逐页标记缺口。LIT、加密或不支持的格式保存原件并报告所需的可读副本，不执行附件程序、不移除 DRM。

## 用于正式创作

```powershell
python -m novel reference-use invisible-library --book your-book-id
python -m novel task-create your-book-id research --reference invisible-library --instruction '按参考报告中已经明确的知识缺口开展研究'
```

`--book` 将带来源、缺口及版本哈希的报告追加到作品 `reference/`，不导入 Canon。书籍正文保留在本地参考库；创作任务接收分析报告而非整套原书。之后经 CLI 创建该作品的任务时，会自动刷新已经绑定的资料库，再固定任务输入版本；无绑定的旧工作流不变。底层 `Engine.enqueue` 保持本地队列 API，不隐式联网；直接使用 Python API 的调用者须先调用 `refresh_bound`。

更新参考报告会生成新作品快照，原有审核不会转用于新版本。有正在运行或待提交的任务时，控制器照旧拒绝修改输入；完成/取消旧任务后再绑定。新资料改变已经通过的章节输入时，先复核该版本，再写下一章，不能绕过现有接受门禁。

自动刷新只识别报告首行的绑定标记，并核对报告哈希与资料库中登记的作品绑定；普通参考文本或报告正文中的标记不会新增绑定。这是资料完整性检查，不是同账户用户之间的权限隔离。只读状态查询和绑定报告也会回读原件与阅读证据哈希；发现损坏时，当前综合失效，已有结论按历史分析保留并附具体缺口，不覆盖旧报告。

## 完整性与阅读证据

检查保留源文件 SHA-256、抽取文本 SHA-256、EPUB ZIP/清单/阅读顺序/目录锚点、正文规模、可识别的章号及读取错误。章名检测是启发式：目录可能重复章名，分部也可能重新编号；不能用章数或页数独自认证完整。书目给出明确章数、词数时才作比较，未知就保留未知。文件更大不等于更完整，字数差异也可能来自版次或附文。

当前词数采用 ASCII 英文词元规则，只在确认英文口径时比较外部词数；中文字符数及其他语言的计数口径保留为待核实，避免把单位不一致误报成正文缺失。

正文按连续字符范围拆成不重叠单元，覆盖前后附文及附录，不静默截断。每段分析必须绑定输入哈希和单元 ID，至少提供真实存在的精确短引文；全书与系列综合须引用实际分析记录 ID。新证据改变结论时，综合记录列出旧结论、新结论和依据，历史原件、阅读结果及报告保持可回查。

`all_units_analyzed` 表示全部文本单元已交付执行器并返回通过引文检查的分析；它不能证明模型理解了每一句、每个文学结论正确或真人读者认可。`series_analysis_available` 也不代表系列全文已齐全；应同时查看当前综合状态、逐版本覆盖率和 `gaps`。出版社完整底本尚未逐字比对时，完整性保持 `not_certified`。

## 获取来源与缺口

书目检索通过现有 ChatGPT 登录下的 Codex 内建网页工具完成，只发送书名、作者等公开书目元数据；不把原书或未公开作品发送给网页。阅读与综合使用同一登录和本机配置模型，禁用网页、shell、MCP 和连接器，不切换付费 API。

控制器默认仅自动下载 Project Gutenberg、Standard Ebooks 的公开内容。其他合法来源可以由操作员在核验后登记精确 HTTPS URL；模型书目结果里的“可以下载”声明不能自行扩大授权范围。例如作者自己公开的番外，需要保存可核验的作者发布页面及登记说明：

```powershell
python -m novel reference-allow-source invisible-library 'https://author.example/story.html' --basis author_publication --evidence-url 'https://author.example/stories' --note '填写已经实际核实的发布与使用依据'
```

该示例域名是占位符，不是已核验来源。登记只允许获取该精确地址，重定向目标也需符合允许范围；不使用浏览器 Cookie、不自动购买或处理登录。缺少授权、付费、登录、网络错误、格式不支持或未找到全文时，保存具体入口和缺口，不把零售页面、节选或目录算作完整正文。默认不从未经授权的下载站补全文。

下载有 HTTPS、公网地址、重定向、大小和格式检查。它们是应用检查，不是操作系统网络隔离；DNS、系统代理和同账户文件权限仍属宿主边界。附件中的脚本和命令不执行。

## 额度、失败与接续

每次命令默认最多 24 次模型调用，每次最多 600 秒；可使用 `--max-calls`、`--timeout` 调整本次运行预算。达到调用上限会保存进度，不假称全读完。书目搜索故障可与已有正文分析分开；额度、认证失败则停止模型调用，后续不会自动绕过停止状态。

```powershell
python -m novel reference-use invisible-library --resume-note '说明先前故障如何解决' --max-calls 24
```

同一输入最多累计三次尝试，显式接续也不清零。普通下载失败保留入口，显式接续才重试，最多三次。崩溃留下的运行中任务会被报告为中断，需明确接续；每次执行的 prompt、schema、原始日志和结果均保留。调用预算耗尽后正常再次 `reference-use` 可继续未完成部分，无须伪造故障恢复说明。

## 本地资料

数据位于 Git 忽略的 `runtime/references/library/<reference-id>/`：

- `sources/` 和 `texts/`：按哈希保存原件与派生文本。
- `state.json`：书目、来源许可、版本、阅读与获取状态、累计尝试和缺口。
- `jobs/<input-hash>/attempt-N/`：真实调用输入、stdout、stderr、原始输出；`accepted.json` 为校验后的结果。
- `reports/<hash>.md`：可阅读且不可覆盖的综合报告。

写入使用每库互斥锁及原子状态替换；模型不直接编辑资料库。旧有 `runtime/references/the-invisible-library-2014/`、历史分析和候选方法卡保留。备份仍应包含整个 `runtime/`；参考分析不自动启用为 `methods/`，也不上传云端或 Git。
