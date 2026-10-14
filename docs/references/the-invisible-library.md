# 参考作品：The Invisible Library

状态：**作者已选定为参考作品；较高把握为完整正文，未与出版社全文逐字校对。** 登记日期：2026-10-14。

## 作者决定与使用范围

用户提供 Genevieve Cogman 的《The Invisible Library》本地 LIT 文件，并说明：

> 但是我不确定下载的是不是完整版的，拿这个当参考把

以上摘录保留用户原话；用户提供的完整来源 URL 见下面的核验记录。这项决定确定参考材料，不确定新作题材、主角、世界设定或剧情路线。

分析区分“原作发生什么”“叙事作用的分析假设”“依赖条件”“可借鉴的方法”和“尚未验证的迁移建议”。2026-10-14 已完成 23 章分段通读与关键证据复核，形成[首轮分析](the-invisible-library-analysis.md)、[证据索引](the-invisible-library-evidence.md)与[九张候选方法卡](../../lessons/candidates/the-invisible-library.md)。尚未进行新作迁移、作者/读者效果验证或系统方法启用。

原作事实保持在参考资料范围，不能自动进入新作品的 Canon。普通候选的选择仍遵循项目的自主创作和明确采纳协议。

## 版本与公开书目核对

| 项目 | 核对结果 |
| --- | --- |
| 书名 / 作者 | The Invisible Library / Genevieve Cogman |
| ISBN | 9781447256243；文件元数据与版权页一致 |
| 出版信息 | Pan Macmillan；出版社页面标 2014-12-15、400 页 |
| 公开规模 | Kobo 同 ISBN 标约 96k words；其电子阅读页数为 353，与出版社纸面页数口径不同 |
| 文件内年份 | 内部元数据日期为 2014-12-15；版权页写 2015 年 Tor 电子版，版权为 2015。分别保留，不据此推断缺章 |
| 文件处理痕迹 | 文件元数据保留 calibre 5.9.0 标记；本轮使用 calibre 9.16.0 读取，不能据此认证该 LIT 为出版社原始发行文件 |

来源：[出版社书目](https://www.panmacmillan.com/authors/genevieve-cogman/the-invisible-library/9781447256243)、[Kobo 同版书目](https://www.kobo.com/gb/en/ebook/the-invisible-library)。

## 本地完整性检查

| 检查 | 结果与含义 |
| --- | --- |
| 原始格式 | `ITOLITLS` 文件头，确为 Microsoft Reader LIT |
| 原文件大小 | 375,746 字节 |
| MD5 | `0733ab84eff443f68ada6742afec2b31`，与用户提供链接的文件编号一致；这只证明文件对应，不独自证明作品完整 |
| SHA-256 | `3aaded0b6838ad2709dc13bf04736f1e46308ce57c2793e1f5e55ad9ea1f8d58` |
| 实际解析 | LIT 解析及 EPUB 转换退出码为 0；清单资源无缺失，生成 EPUB 的 ZIP 完整性检查通过 |
| 章节 | 原始解包 NCX 与正文一致：CHAPTER ONE 至 CHAPTER TWENTY-THREE，共 23 章连续，无缺号 |
| 目录引用 | 23 章、作者介绍、致谢共 25 个目录目标及锚点均存在 |
| 文本规模 | 正文含章名约 95,472 英文词；连同前后附文约 96,156 词，符合公开约 96k 的规模 |
| 转换保持性 | 原始解包 HTML 与生成 EPUB 的每个正文节，经同一文本抽取规则处理后逐节一致 |
| 收尾 | 第 23 章有正常叙事收束和完整句末；随后保留作者介绍、致谢与版权页，未见明显截断 |

计数采用 ASCII 英文字母词元，允许词内撇号或连字符；因此不要求与零售商的取整数完全相同。本次没有独立取得官方完整目录或逐字比对底本，也不能排除极少量转录或排版差异。综合结构、结尾与字数证据，可以按完整正文开展参考分析；这不是逐字无误的认证。

用户提供的来源页面：[文件记录](https://annas-archive.gd/md5/0733ab84eff443f68ada6742afec2b31?check=1)。本轮未能读取该页面，页面本身的版本/完整性声明未核实；结论依据用户文件与上述公开书目。

## 本地资料位置

完整资料保存在 Git 忽略的 `runtime/references/the-invisible-library-2014/`：

- `source.lit`：原始文件副本，与下载目录原件哈希一致。
- `converted.epub`、`extracted-text.txt`、`chapters/01.txt` 至 `23.txt`：派生阅读与逐章分析资料。
- `conversion-debug/input/`：直接解包结果，含原有 OPF、NCX、HTML 和图片。
- `conversion.log`、`integrity-report.json`、`manifest.json`：转换、检查与来源记录。

GitHub 仅保存本页的选择、书目与核验结论。原书正文和转换副本留在本地参考库；尚未为新小说创建作品记录，也未将原作资料写入新作状态。
