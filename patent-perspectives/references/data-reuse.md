# 数据复用交付

交付时读取。除互动报告外，交付实际取得的专利信息、市场与产品资料、分析及证据，使后续工作能够按稳定ID接续。问题、跳过事项和增量分析基线集中写入一份独立的《分析记录与后续补充说明》，按[运行记录规则](run-status-and-issues.md)维护；不要把这些工作过程重新做成互动报告的板块。

## 内容与边界

- **专利数据：**完整候选目录、主体、申请与公开号、文献版本及实际取得的正文、法律状态和同族观察、原文来源及必要图像。保留未知、排除、待核和被拒绝文本的真实标记，不能只留下报告中展示的记录。
- **市场和产品：**本次实际收集的公司披露、市场资料、产品线/型号、场景、市场/时期、来源日期、取得时间和来源属性。没有取得的销量、市场规模等仍然未知；产品与专利的线索关系不升级为已证实采用。
- **分析：**逐件技术字段、分类与理由、三角色结论、关系、要素对照、引用和适用范围。明确申请、文献和证据ID，原始事实与解释分别保存。
- **问题驱动研究：**启用时保留共享问题ID、问题集、维度、术语、逐项比较、关系与发现的当前及历史身份、内容绑定和真实质量审阅记录。通过 `research-export` 输出机器可读副本并列入材料清单；数据库仍保留 meta.research_workflow 及原关系、结论，页面 data/research.js 不能代替研究数据或审阅记录。
- **接续记录：**机器可读问题ID、研究范围、快照时间、文件版本与校验值。一个数据时点只能作为基线，不能声称已有法律状态变化。

原母库和私有来源保留在工作目录。分发版使用一致性复制并脱敏，文件采用包内相对路径；随包给出表字段、ID关联、资产清单和遗漏说明。互动报告是阅读视图，不作为唯一数据源。

## 通用导出工具

`scripts/export_reuse.py` 仅调用 Python 标准库，不检索网络、不调用模型、不写原数据库。它使用 SQLite 的只读连接和 backup API，包含已提交到 WAL 的记录；不使用忽略 WAL 的 immutable 读取方式。输出目录必须不存在，失败不留下半成品，成功后整体提交新目录。

```text
python scripts/export_reuse.py --db RUN.sqlite --output NEW_REUSE_DIR --materials materials.json
```

省略 `--materials` 只导出数据库，不能据此宣称已经交付市场资料或原文资产。脚本输出：

- `patent.sqlite`：全部实际用户表及记录的脱敏副本。
- `tables/*.jsonl`：逐表开放格式；对象/数组类型的JSON字符串展开为JSON，其他值保留其数据类型。
- `csv/`：申请、文献著录、主体、候选审核、原文拒绝、分析、角色结论及关系等常用表；为防止表格软件执行公式，危险开头加单引号，JSONL与SQLite保留数据值。
- `materials/`：显式列入清单且通过文件检查的材料。
- `schema.json`、`field-dictionary.md`、`reuse-guide.md`：字段、主键/外键、JSON软引用及读取说明。
- `export-manifest.json`、`transformation-log.jsonl`：数据版本、全部文件校验值、材料省略项及脱敏位置。

当前接受普通SQLite表，不处理触发器或虚拟表；遇到不支持的结构、会因脱敏改变主键的情况会停止导出，不能默默破坏关联。数据库中的不透明BLOB内容置空并记录，行和ID保留；如有需要保留的原文件，单独作为实际检查过的资产列入清单。

## 显式材料清单

清单不自动扫描整个工作区。`root` 相对于清单所在目录解析，也可为明确允许的绝对目录；每个 `path` 必须是 root 内使用 `/` 的相对文件路径，不接受 `..` 或越界链接。以下仅为结构示例，ID与文件须替换为真实资料：

```json
{
  "root": "research-materials",
  "items": [
    {
      "id": "market-source-01",
      "category": "market",
      "path": "market/source-01.json",
      "description": "已取得的公司产品披露",
      "source_ids": ["actual-source-id"],
      "acquired_at": "实际取得时间"
    },
    {
      "id": "claim-comparisons",
      "category": "analysis",
      "path": "analysis/claim-comparisons.json"
    },
    {
      "id": "analysis-records",
      "category": "records",
      "path": "records/analysis-records.json"
    },
    {
      "id": "original-document-01",
      "category": "patent",
      "path": "originals/document-01.pdf",
      "binary_reviewed": true,
      "aliases": ["曾记录在原库中的相对资料路径"]
    }
  ]
}
```

`category` 为 patent、market、analysis 或 records；`id` 为不重复的ASCII字母、数字、下划线或短横线。可补 `source_url`、`description`、`source_ids`、`acquired_at`。工具不推断材料的事实真实性，来源仍需宿主核验。

`required` 默认 true：缺失或不支持的必需材料使本次导出失败；只有明确可省略材料才设为 false，省略原因进入清单。所有纳入材料都会记录原获取文件SHA256与导出文件SHA256；`aliases` 用于将原库/JSON中的准确相对引用重定位到实际导出文件。不要用近似名称替换另一文献。未打包的明确本地引用会标为 `[UNPACKAGED_LOCAL_REFERENCE]` 并留下位置，不能把该标记说成已经附有来源文件。

Markdown采用文件自身的位置作为链接基准：工具按原Markdown目录解析单行内联链接、图片和引用式链接定义，只将显式纳入且成功打包的目标改成相对导出Markdown的路径。普通URL、查询参数和锚点保留，敏感查询参数仍会脱敏；代码示例不作为资料链接处理。未纳入或越界的目标不会被隐式读取，失效内联链接改成“关联材料未打包”的文字，引用定义附未打包说明，计入 `markdown_local_reference_unavailable`。多行链接或HTML形式的内嵌引用不在此重写范围，宿主应另行检查并在统一说明记录限制。JSON和SQLite中的资料引用继续以数据包根目录为基准。

支持UTF-8的JSON、JSONL、CSV、TXT、Markdown、HTML、XML、SVG。HTML、XML、SVG以附加 `.txt` 后缀的静态源文本交付，不执行其中脚本或外链；来源中的指令仅作材料内容。PDF、PNG、JPEG、GIF、WebP要求宿主实际检查文件身份及适宜交付的内容后填写 `binary_reviewed:true`，工具还会核对文件签名；它不会自动清除二进制内部的个人信息或元数据。压缩包、程序及未知二进制不会被自动复制。大型来源目录可由宿主先生成逐文件清单，仍须明确哪些文件确实属于本次资料。

## 脱敏与原始字节验收

导出副本会处理凭证/账号字段、Bearer值、常见签名URL参数、敏感内联赋值与无关机器路径，包括嵌套JSON。原数据库及原来源文件不变。宿主仍需检查输入材料的适宜性，特别是图片、PDF和没有结构的第三方回执；程序不能凭关键词证明任意文件不含敏感内容。

**脱敏快照可用于读取、关联和后续分析，但不能冒充原始取证库。** 原有 text_hash、artifact_sha256 等字段保留的是原获取版本声明。若正文、引文或回执发生脱敏，原字节哈希及字符位置可能不能直接用于导出件；不要修改历史哈希以伪装原验收通过。使用 manifest 的当前文件SHA256核验导出完整性，并查看转换日志。重新进行原始来源/字节验收时，回到原母库与保留的私有来源，或重新取得同件资料并重新核验。

## 后续使用与验收

补充专利时按申请/公开号和版本定位已有记录，增加市场来源时保持 source_id 与产品/分析引用一致；增量比较保持两次范围、观察日期和统计单位可比，分别记录新增公开、新发现旧记录、状态变化与纠错。详细接续任务、影响和恢复条件写入统一说明，不另外生成多份互相矛盾的问题文档。

交付前核对全部用户表行数和ID关系、报告与数据分母、机器问题ID与统一说明，检查导出清单中每个实际文件的哈希及省略项。整体移动目录后检查相对资料路径。不得将一次导出成功说成全部来源已经核验、原库已经完整或研究结论已经更新。

## 行业研究补充材料

启用行业研究时，将render实际生成的industry-research.json、industry-research.md、industry-sources.csv、industry-matrix.csv连同实际取得的外部资料加入materials清单。通过稳定source_id、route_id、company_id及专利application_id/document_id/evidence_ids与原库对应；保留作用范围、观察日期和合成标记。它们是补充材料，不修改原库的专利研究完成状态。

存在独立参考语料时另输出industry-reference-corpora.json，保留实际取得的完整文献和证据，不只保留页面中的片段。此文件加入数据复用材料清单，保留原公司、范围及原始复核边界。
