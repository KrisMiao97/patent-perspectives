# 输出模版与数据约定

先读根目录 DESIGN.md。报告内容先按 assets/report-outline.md 组织，再填写结构化数据并生成；不要为迎合版式减少必要限定。

## 生成方法

使用 Python 3.10 或以上，无第三方运行依赖：

```text
python scripts/render_report.py research-data.json --output report.html
```

命令中的脚本路径相对 Skill 根目录；输入和输出可使用绝对路径。生成结果是可独立打开的单文件 HTML。HTML 内嵌数据、样式、交互和已提供的图，只有点击外部来源时才联网。assets/report.html 是生成器使用的页面母版，不是研究成品；不要直接交付未填内容的母版。

## 必填数据

| 字段 | 内容 |
|---|---|
| schema_version | 固定为 1；格式变更时同步生成器和本文 |
| title / cutoff | 对象与研究题名；证据截止日为 YYYY-MM-DD，不能用修订日冒充 |
| finding | 本轮已有证据支持的具体发现，包含关键范围 |
| opportunity | 由差异形成的产品变化与使用价值，未验证的收益按可能性表达 |
| judgment | 当前有条件的取舍；没有全局排序也可给局部判断 |
| boundary | 会影响理解的范围、实测或复核限制 |
| directions | 方向数组，可为零；数量不固定，D 编号唯一 |
| evidence | 证据数组，可为零；E 编号唯一 |

方向包含 id、name、benefit、tradeoff、judgment、evidence_state、decision_state。状态是两个不同字段，不共用一个综合标签。reasoning 是按材料披露、方案差异、可能能力、成立条件、尚存假设排列的五项；每项有 title、text、evidence，最后一个字段为证据编号数组。标题应写具体主张，不直接填角色名。

conditions 为条件分支数组，每项有 if 与 then，说明一种情况出现后如何改变取舍。不是默认试验已经发生，也不自动变成立项通过。可选 figure 是内嵌 PNG、JPEG 或 SVG 的 base64 数据 URL，caption 为必填图注；图中的文字同样需要实际检查，生成器不判断图文真实性。

证据包含 id、title、summary、source_role、in_sample、location、disclosure、limitation；in_sample 必须明确填 true 或 false。directions 为关联方向数组；documents 为 number 与 url 的数组，可容纳专利、论文、产品及标准。publication 可写公开日或资料日期；没有日期时省略，不编造。source_role 区分直接披露、相似机制、跨领域参照或实测等，不只是“可信”。

## 可选模块

- scope：短句数组，展示已核实的样本数量、去重口径及阅读范围。
- timeline：按公开日升序的 date、title、change、evidence 数组；change 写部件、动作及变化，不能只写文献题名。
- periods：label、conclusion、basis，逐期解释“主要在解决什么”，无可支持的跨期比较时省略。
- worklog：question、action、finding、remaining，说明关键疑问、实际完成的补证、判断变化和剩余未知。
- decision_boundary：本轮能支持的研究或立项判断；缺省沿用 boundary。
- references：补充来源与方法链接的 title、url 数组；仅允许 HTTP(S)，显示在附录。
- appendix：纯文本段落数组，保留检索式、记录口径、排除理由和方法；换行会保留。

生成器将纯文本转义，不执行输入中的 HTML。引用必须解析到实际 E 条目；外部来源限 HTTP(S)。它会拒绝编号重复、引用丢失、方向论证缺项及时间乱序，但不会证明原文正确、检索全面、数量真实或收益已验证；这些由研究核查负责。

## 最小结构示例

assets/report-data.example.json 给出无已形成方向的合法起点，内容明确处于模版准备状态。实际研究应替换全部文案，并逐项填入已经完成的分析。不能把示例空值或结构检查通过当作研究完成。

有方向时一项 reasoning 的写法如下，E1 必须在证据数组中存在：

```json
{"title":"底座可单独解扣，握持件仍采用紧固连接","text":"这里用完整句子说明原文中的部件位置和动作，并说明与简单基线的差异。","evidence":["E1"]}
```

## 接续更新

修改研究数据后重新生成 HTML，保留上一版数据和实际差异。更正材质、位置或归组时同步摘要、方向判断、图注、时间节点与证据索引。新增补充资料不自动改变主样本分母。生成失败时不覆盖原报告；成功后仍需按 DESIGN.md 做视觉与交互验收。

修改生成器后运行 `python -m unittest discover -s tests -v`，检查不同方向数量、引用完整性、文本转义和失败时保留原报告。它不代替画面验收，也不检查专利事实。
