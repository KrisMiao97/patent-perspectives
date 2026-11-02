# 原文嵌入图片的人工转写补证

`scripts/compose_image_transcription.py` 不执行 OCR、公式修正或技术语义判断。宿主必须实际查看同件原始正文中的每张图片，忠实转写，再独立核对转写和正文。原纯文本因缺公式被拒绝后，拒绝记录仍保留；本适配器生成独立、带明确人工标记的补证版本，不改变数据库中的旧正文，也不替代逐件技术分析。

## 宿主输入（schema 2）

输入为一个 JSON 对象：

```json
{
  "document_id": "对应已导入的原始未转写文档ID",
  "publication_number": "同件公开号",
  "source_version": "原始版本名",
  "source_text_hash": "数据库原文text_hash",
  "image_manifest": "run目录内图片清单相对路径",
  "image_manifest_sha256": "实际查看时冻结的清单SHA256",
  "reviewer": "实际阅图人",
  "visual_review_complete": true,
  "images": [
    {
      "image_id": "原img-id",
      "source_image_path": "/原始img src的路径，不含临时签名",
      "sha256": "实际查看的本地图片SHA256",
      "transcription": "人工忠实转写，保留符号和疑点",
      "visually_verified": true
    }
  ]
}
```

清单必须覆盖全部且仅覆盖原文实际嵌入图片；包含公开号、正文类型、原缓存相对路径及 SHA256，并对每图保留 `image_id/file/source_image_path/status/bytes/sha256`。图片都应为下载成功的原始文件，不用裁剪、重绘、同族或其他版本代替。实际查看后，不可只更新清单中的 hash 来换图；阅图声明也绑定每张已看图片的 hash 和原始路径。

适配器依次检查：原文 ID、版本与文本 hash；清单冻结 hash；原缓存 hash；实际工具、endpoint、完整批量参数、cache_key；传输、MCP 与业务成功；实际批量 record 索引及 PN；唯一原文语言；完整标记；重建的每个原文字符；原 img-id 与 src 路径；全部阅图声明与本地字节 hash/长度。PNG 另检查完整 chunk、CRC、压缩流和结束标记，JPEG/GIF/WebP仅检查容器边界。这些不证明图片数学含义或完整视觉内容，仍需实际查看原图。

正文以 `【原文图片人工转写 image_id：内容】` 明示新增字符；输出保留原缓存、record 路径、源文 hash、清单 hash、每图 hash/路径、原标签 hash和审阅者。版本含 `review-schema2`，避免旧版相同文字被数据库缓存而丢失新证明字段。权利要求数和编号序列不得因转写改变，补证文本需要再经 `document-import` 和完整语义分析验收。

## 调用

```text
python scripts/compose_image_transcription.py --db RUN/full.sqlite --input RUN/host-image-review.json --output RUN/normalized/composed.json
```

脚本通过只读方式访问原数据库，只写指定 JSON 输出。输出应进入同件新的技术文本版本，由正常导入器处理。图片无法读取、清单未齐、正文重建不一致或转写不确定时，不产生合格替代正文。

转写原图不等于修复原文：例如原图写 `cot θ` 就保留 `cot θ`，不能按工程经验改成 `cot(θ/2)`。若公式符号只在另一从属分支定义，应记录分支关系和缺失，不把该分支其他限定自动合并到公式所在项。引用公式结论的证据要包括实际公式标记，不能只引用“满足：”之前的引导文字。

## 验证

`tests/test_image_transcription.py` 使用临时合成数据，覆盖缓存/请求/PN/record/正文篡改、未读全图、换图并重算清单、换文档/版本、路径越界、图片截断和新权项注入等拒绝情形。人工转写的正确性需另行独立复核，适配器不会把声明自动当作语义正确证明。

## 离线原图展示

正式渲染通过既有全量门槛后，`scripts/document_images.py` 在创建输出目录以前重新核对当前分析范围内、实际展示的每份 schema 2 转写文档。检查同申请、同公开号、同语种的原始版本、正文哈希、每图人工标记，以及 run 目录内的本地路径、SHA-256、字节数和完整图像容器。缺失、改动或越界会阻止正式导出，不能用文字转写掩盖原图已不可核阅。

核过的同一批字节以 `document-images/<sha256>.<格式>` 写入离线包，相同图像只复制一份，各文档仍分别保留公开号、img-id 和版本关联。图片说明使用“原文嵌图（文字经人工转写）”，与 `aux-images/` 中可选代表图区分。文本版本同时展示 `normalization_notice`。原始缓存、请求、签名访问地址及私有 review 全量字段不随图片导出。

搜索记录中的 `metadata_original.images` 仍保留在数据库中，但其原始图片字典及访问地址不进入页面的 publications 或图片目录。其他著录原值继续保留。所有可展示图片只来自经过核验的本地代表图或原文嵌图路径。

仅复制当前范围内实际展示的原文图和代表图。父库的范围外文献、检索和来源记录继续保留在数据库及来源对账中，不把其图片复制到当前页面包。可选代表图丢失仍显示未知；它不承担已转写正文的原图核阅责任。

`technical_fulltext` 字段只代表结构检查通过且未被拒绝的文本候选，不代表人工核对过每个文字、公式或嵌图。页面使用“文本候选（已通过结构检查）”标签；主完成率继续仅按来源有效且逐件语义分析完成的申请计算。
