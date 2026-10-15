# 劳动法律语料

法规原件位于 `source/`，`manifest.json` 记录导入文件、法规元数据、国家法律法规数据库来源链接及 SHA-256。

本次语料于 2026-10-15 从国家法律法规数据库获取，含 14 部当前标记为有效的全国性劳动法律法规。清单中的 14 份官方 DOCX 是知识库导入来源；同目录另有 12 份官方 PDF 参考文件，不会重复导入。该首批文件集用于 MVP，不代表已收齐全部劳动领域法规。

## 同步及导入

从 `backend/` 目录执行：

```powershell
python -m agents.labor_law_agent.sync_official_corpus
python -m agents.labor_law_agent.ingest_corpus
```

首次导入前，在 `backend/.env` 配置数据库连接及 `TENCENT_TOKENHUB_API_KEY`，并确认该 Key 已开通所用向量模型。默认使用 `kinfra-text-embedding-0.6b`，接口地址为 `https://tokenhub.tencentmaas.com/v1`，向量维度固定为 1024。法规更新后重新同步并导入；数据库会保留旧版本，仅把新版本设为当前检索版本。若法规不再被官方标记为现行有效，下一次成功同步和导入会停用其当前标记。
