# 四项专利 Skill 的证据交接

适用于 patent-batch-reader、专利棱镜、研发罗盘和 patent-draft-review 之间复用证据。保留各自原有台账和报告。交接另存一份小型 JSON，接收方以稳定证据 ID 对应本地权项、卡片或意见。文件应由实际阅读者从同件原件和当前记录填制，不得用报告倒推没有核查的事实。

交接件顶层 `schema_version` 为 1，包含 `sources` 与 `evidence`：

```json
{
  "schema_version": 1,
  "sources": [{
    "id": "orig-a",
    "publication": "CN123456789A",
    "version": "A 公开原中文",
    "path": "originals/CN123456789A.pdf",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }],
  "evidence": [{
    "id": "CN123456789A-claim2-e1",
    "source_id": "orig-a",
    "locations": ["PDF第2页 权2", "PDF第5页 [0024]"],
    "kind": "disclosure",
    "statement": "腔压超过阈值才打开阀",
    "conditions": {"state": "stated", "values": ["压差超过 10 kPa", "阀处于初始关闭状态"]}
  }]
}
```

示例文献号、内容和指纹仅示意格式。实际使用按以下约定：

- `publication` 保存带种类代码的准确公开号。未公开草稿填 `null`，另填 `publication_note`。`version` 保留实际 A、B、U 或来稿版次。不同语言、公开/授权文本分别标明，严禁用同族或另一个版本代替。原件 ID 在同一交接链内稳定，独立并列的版本各有自己的 ID。
- `path` 是相对于 `--source-root` 的原件路径。`sha256` 对原件的实际字节计算，不能填从 PDF 提取的文本或换行转换后的文本指纹。提取件或复用包另记录派生关系。打开新的原件时还应核查封面身份；哈希校验不识别文件内公开号或版别。
- `locations` 记录对应原件的 PDF 物理页、段号、权项、图号或图中区域。不同位置分条。若下游需要可机器定位的直接引文，省略或拼接引用拆成连续短段，分别核对，不将组合摘录当成一条连续原句。
- `kind` 区分 `disclosure` 明确披露、`claimed_effect` 申请人声称效果、`inference` 推断、`test` 测试和 `unknown` 未知。`conditions.state` 为 `stated` 时逐条保留 `values`。仍有未知的可在 `unknown` 下保留已知条件并在 `reason` 写缺口。`not_applicable` 也须写理由。区分未取得、未检查和回源未发现，不根据空白升级结论。复核状态沿用实际来源台账，不由交接通过补写。

首次接收同时以待采纳文件作两个输入，校对当前原件字节。回看所用位置、成立条件和结论后，另保存一份已采纳快照，记录与各本地意见或卡片的 ID 对应。接续时，在更新分析及出报告前比较已采纳快照与当前交接件：

```text
python scripts/evidence_handoff.py 先前已采纳.json 本次.json --source-root 原件所在目录
```

返回码 0 表示所传字段和当前指纹一致，1 表示有新增、丢失或变化，2 表示格式无效、路径非法或输入不可读。首轮以同一件校对只建立当前基线。其后按输出的 `evidence_to_recheck` 及本地 ID 映射，回查受影响的权项、卡片、意见与专题；不把旧复核复制为新复核。原件缺失、指纹不匹配、证据键更换或条件缩减均需处理。待核时保持旧快照和相应结论的旧版本标记，回查后才另存新的采纳快照。

工具比较交接文件、检查当前原件字节并提示回查。它不替代逐字定位、解释条件或审核结论强度。发送端和接收端都以实际本地使用的内容核对交接记录；正文若删去必要条件，即使交接文件没改，也须人工指出。
