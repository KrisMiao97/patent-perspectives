# 专利局原始公报镜像的身份补证

当已连接bibliography没有名址，但同件专利的专利局原始公报首页包含名址时，可将公报的第三方托管副本作为身份补证。不得把Google网页上的自动归属、翻译、法律状态或整个Google域名视作官方证据。

`identity_source.source_class = original_patent_document_mirror` 仅支持HTTPS `patentimages.storage.googleapis.com/xx/xx/xx/xxxxxxxxxxxxxx/PN.pdf` 固定公报路径。PN必须已保留在同一独立申请的公开/授权版本清单，URL不允许查询参数或片段。`OFFICIAL` 与常规官方来源判断保持不变。

运行目录必须保留原PDF的实际字节及SHA256、逐页原文抽取JSON及SHA256、人工或宿主视觉核阅记录JSON及SHA256。引用用一基页码、原始申请人/权利人姓名行、同一party地址行及包含两者的连续原文，禁止用发明人地址替代权利人地址。标注“专利局原始公报的第三方托管副本”。

抽取JSON保存 `pdf_sha256`、`publication_number`、`extraction_tool`、`page_count`、`pages[{page_number,text}]`。核心仅使用标准库核验文件、哈希、页码和精确引文，不宣称自行解析PDF。宿主应先渲染核对首页。

核阅JSON必须保存 `kind=manual_original_patent_identity_review`、`result=identity_confirmed`、`reviewer`、`reviewed_at`、`publication_number`、`pdf_sha256`、`page_number`、`name_quote`、`address_quote`、`determination`、`patent_office` 和 `visual_review_performed=true`。公报办公室与候选文献国家代码相同。宿主应记录它确认的是同名的不同自然人/法人还是目标法人的具体名称，不把此项身份核验扩大为法律状态或当前权属结论。

导入时调用 `verify_identity_source`，它按来源类别验证；镜像不能绕过常规官方URL白名单。原文件、抽取或核阅任一哈希变化、引文不在所选页、姓名地址缺一、跨申请PN、越界路径均拒绝。缓存可随运行包迁移，凭证不进入证据文件。
