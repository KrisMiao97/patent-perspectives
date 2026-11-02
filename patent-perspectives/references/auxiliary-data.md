# 同件辅助数据：法律状态、同族、摘要图

`auxiliary-import` 与 `scripts/import_auxiliary_cache.py` 接入已取得的 `legal_status`、`family`、`abstract_image` 原始缓存。只读校验是默认模式，不发起网络请求。辅助记录进入独立 auxiliary_records 表，不覆盖搜索著录、原始申请人、权属、文本或统计分母。

## 精确来源契约

每条指针包含 kind、publication_number、source_artifact、source_request、response_path、record_index。源文件必须在运行数据库目录内；脚本读取原始字节并保存 artifact_sha256、实际记录 record_sha256 和精确 record_path。publication_number 必须已在搜索文献中保留。

`source_request` 必须等于原缓存请求，工具名等于 kind，patent_number 保留实际逗号分隔的完整批量字符串。按每个号码分别匹配，不能把批量串归一成一个号码，也不能为方便而捏造单件请求。目标 PN 必须属于真实批请求，并且返回数组指定 index 必须唯一地返回同一 PN。外层传输、MCP 工具或业务错误均拒绝；空或缺件不会被补造记录。

Collector 顶层缓存示例：

```json
{
  "kind": "legal_status",
  "publication_number": "实际已保留的文献号",
  "source_artifact": "collector/raw/实际源文件.json",
  "source_request": {"tool": "legal_status", "arguments": {"patent_number": "实际完整批量号码串"}},
  "request_tool_path": ["tool"],
  "request_arguments_path": ["arguments"],
  "response_path": ["response", "result", "structuredContent"],
  "record_index": 0
}
```

连接工具原生包装可将 response_path 改为 `["result","structuredContent"]`。旧格式也可用 request_path 指向缓存中的 source_request 对象；两种请求路径不能混用。以上是位置结构示意，实际请求、路径及 index 均从现存缓存取值。

取得时点只能来自源 envelope 的 acquired_at 或 acquired_date。日期级证据保留 date 精度，不能虚构时分秒。调用者补充 acquired_at 或 artifact_sha256 时必须与源完全相同。提供者响应 timestamp 另外保留，不能代替实际取得时间。

## 法律状态

保留每个文献的原始 simple_legal_status 数组及每次观察。认可当前工具声明的“有效、审中、失效、未确认、PCT指定期内、PCT指定期满”；其中“未确认”原值保留，但文献及申请派生汇总为 unknown。空数组、未识别值和同条多状态记录也保留为 unknown。它们仍是来源记录，不升级为法律有效性结论。

同一文献有多个观察时，以实际取得时点选择最近观察，旧记录继续保留。日期级观察不能被假定为午夜：与同日精确时点的先后不明时同时保留，冲突显示unknown。同一时点的冲突也不强行排序。申请汇总检查各保留文献的状态；不同状态冲突时显示 unknown，逐文献原值和日期仍可查看。未取得辅助记录的文献保持未知；已有搜索标签作为原始来源另存，不冒充独立核验。

这些状态表示取得时的观察。即使法律状态在检索截止日之后一天取得，也必须标明真实采集日，不能倒填为截止日状态。辅助覆盖不等于历史法律状态重建。

## 同族

simple_family、inpadoc_family、patsnap_family 分别保留 family_id、成员和原始位置，不将三种定义合并成一种同族数。成员号只由明确的 country、doc_number 和 kind 组成，缺字段时不能按名称或语义补造。

详情保留所有返回成员；图谱事实边只连接当前纳入组合中能精确匹配的申请，注明同族定义、源记录、取得时间和成员原始位置。组外成员不会自动增加组合分母。不从同族关系推断共同权属、转让、法律范围或文本可替代性，同族文本不能替代同件全文。

## 摘要图与离线图像

摘要图记录不代表外观设计的全部视图。原始下载 URL 可以作为私有源记录保存，签名 URL、原始响应和完整 URL 不进入交付页或 sources-and-coverage.json；公共记录仅保留 URL 哈希、图片号、可得性和来源哈希。只有远端路径时，离线可展示图片仍为未知。

已有本地文件时，可在输入加 local_image：relative_path、sha256、source_image_url、source_image_number。URL和图片号必须等于原始该条摘要图；本地文件必须位于运行目录内，字节哈希必须正确且是可识别的 PNG、JPEG、GIF 或 WebP。不能将另一件图片挂到本件。

正式 render 再核对哈希并将文件复制到 aux-images/哈希.扩展名。缺失或变更文件不展示，辅助图片缺失不阻断已合格技术全文的完成。页面不自动下载图片，也不依赖私有签名链接。

## 使用

```text
python scripts/import_auxiliary_cache.py --db RUN.sqlite --ledger collector/ledger.sqlite --tool legal_status --limit 100 --dry-run --output legal-probe-input.json
python scripts/import_auxiliary_cache.py --db RUN.sqlite --ledger collector/ledger.sqlite --tool legal_status --dry-run
python scripts/import_auxiliary_cache.py --db RUN.sqlite --ledger collector/ledger.sqlite --tool legal_status --apply
```

family、abstract_image 仅替换 --tool。dry-run 只读两个数据库；--output 写可复查的源指针输入，不含签名图片 URL。--apply 在所有选中记录通过源核验后才以事务导入；失败保留清单并退出码3，不部分提交，也不修改采集 ledger。原始缓存继续保存。缺件由采集报告解释，不造空数据。

对于自定义包装或已绑定本地图片的输入，也可直接调用：

```text
python scripts/patent_perspectives.py --db RUN.sqlite auxiliary-import --input auxiliary-input.json
```

新增辅助来源会改变角色结论的数据指纹，已有角色结论需重审。它不撤销有效的技术全文分析。覆盖率分别报告法律状态已取得的文献、状态冲突的申请、同族来源及摘要图来源/本地图片；不能把辅助记录数量合计为技术全文完成数。
