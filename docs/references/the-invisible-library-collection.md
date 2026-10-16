# The Invisible Library：系列与版本补充核验

日期：2026-10-15。范围按作者本轮要求扩大到整个系列、番外和附录。此页保留书目与获取证据，不以书目记录冒充全文阅读，也不改写原第一卷分析。

## 已取得与仍缺失的材料

| 材料 | 书目依据 | 本地取得状态 |
| --- | --- | --- |
| The Invisible Library，第 1 卷 | 作者提供的 LIT / ISBN 9781447256243；[原核验](the-invisible-library.md) | 原 LIT 和转换 EPUB 均保留；正文较高把握完整，未逐字校对官方底本 |
| The Masked City，第 2 卷 | [出版社系列介绍](https://www.panmacmillan.com/blogs/science-fiction-and-fantasy/the-invisible-library-series-introduction) | 缺全文 |
| The Burning Page，第 3 卷 | 同上 | 缺全文 |
| The Lost Plot，第 4 卷 | 同上 | 缺全文 |
| The Mortal Word，第 5 卷 | 同上 | 缺全文 |
| The Secret Chapter，第 6 卷 | 同上 | 缺全文 |
| The Dark Archive，第 7 卷 | 同上 | 缺全文 |
| The Untold Story，第 8 卷 | 同上 | 缺全文 |
| A Library Christmas Carol，公开短篇 | [作者发布页](https://www.grcogman.com/2019/12/a-library-christmas-carol/) | 已从作者官网实际下载并回读，单独保存 HTML 原页及抽取文本 |
| 第一卷美版附加材料 | [出版社页面](https://penguinrandomhouselibrary.com/book/?isbn=9781101988640)明确提到访谈、图书馆传说和其他附加内容 | 未取得；全部正式标题与英美版差异仍未核实 |
| Secrets from the Library；An Interview with the Author（第二卷卷末材料） | [第二卷公开预览目录线索](https://www.everand.com/book/768014414/The-Masked-City) | 未取得正文；与第一卷附加内容是否重合仍未知 |

出版社书目支持第 1–8 卷的顺序；本轮未找到第九卷的正式出版信息，不将其写成“确认永远没有续作”。同作者的其他小说或短篇没有明确系列归属依据时，不自动列作本系列番外。

“正文完整”和“收齐跨版本附录”是不同结论。本地第一卷的 23 章、字数与收尾检查仍有效，但不能据此宣称英美各版附加材料或全系列都齐全。出版社零售页面提供的预览也不能替代完整小说。

## 公开番外的实际获取

作者网页发布时间为 2019-12-23。本轮实际通过 HTTPS 获取该精确页面；取得前已核对作者公开发布身份并登记来源，未扩大为整个网站的任意下载授权。

- HTML 原页 SHA-256：`fa037d42039ac39cb73cb86a32457a0bc0549289f5ddf094b9202a9032f80017`。
- 派生文本为 21,756 字符，包含网页文本；这不是纯短篇正文词数。HTML 范围检查保留导航/页面附文的不确定性，未将页面大小作为故事完整认证。
- 获取记录保留在 `runtime/references/library/invisible-library/state.json`，实际下载回执在本地 `.local-validation/reference-library-20261015/public-extra-receipt.json`。

原第一卷、番外和未来取得的其他卷各自绑定源文件及抽取文本哈希，不拼接进一个不明来源的“完整版”。内容分析不会自动写入新作 Canon 或启用候选方法。

## 阅读与使用

新资料库 ID 为 `invisible-library`，入口见[自动流程说明](../reference-library.md)。`python -m novel reference-status invisible-library` 给出各版本的真实阅读覆盖、系列综合是否为当前结果及全部缺口；原始执行日志和可读报告留在同一资料库下。

本次实际运行已完成第一卷和公开番外的全部文本单元分析及作品/系列综合。回读确认第一卷 6 段、番外网页 1 段均连续覆盖对应保存文本，全部原件哈希和接受结果一致，`stop=null`。这只覆盖已取得的两份材料；上表缺失的卷册和附加材料没有被计为已读。详细调用与检查记录见[验收记录](../reference-library-validation.md)。

作者已明确允许将其提供的第一卷全文分段发送到现有 ChatGPT 登录下的 Codex `gpt-6-astra` 完成阅读分析；不传送新作正文或凭据。书目查询只发送公开元数据，正文分析禁用网页工具。首次宿主权限错误、自动批准审核要求补充传输授权的记录及后续真实结果分别保留，不冒称此前已完成全文分析。
