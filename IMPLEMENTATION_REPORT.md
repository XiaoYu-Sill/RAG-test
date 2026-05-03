# 实现报告 — 高铁应急文档RAG问答系统

## 系统概述

本系统是一个基于检索增强生成（RAG）技术的高铁事故应急处置文档智能问答平台。用户上传专业文档后，系统将文档语义向量化存储，并在用户提问时精准检索相关片段，结合大语言模型生成带来源引用的专业回答。

---

## 架构设计

```
用户输入问题
    │
    ▼
[FastAPI /chat 端点]
    │
    ├─► [Retriever] → [VectorStore (FAISS)] → ZhipuAI embedding-3 → 相关文档片段
    │
    └─► [LLMClient] → ZhipuAI glm-4-flash (流式) → SSE 事件流
                                                         │
                                    ┌────────────────────┤
                                    │  data: {type:"sources",...}
                                    │  data: {type:"chunk",...}   ×N
                                    │  data: {type:"done"}
                                    └────────────────────►  前端渲染
```

---

## 核心模块实现

### 1. 文档处理（document_processor.py）

- **PDF**：PyMuPDF（fitz）逐页提取文本，保留页码
- **DOCX**：python-docx 提取所有段落文本
- **XLSX**：openpyxl 按 Sheet 读取，Sheet名作为"页码"
- **PPTX**：python-pptx 按幻灯片读取，幻灯片编号作为页码
- **CSV**：pandas 转为字符串表格
- **TXT/MD**：直接读取

所有格式均使用 `RecursiveCharacterTextSplitter`（chunk_size=500, overlap=50）进行分块，每个 chunk 携带：
```json
{"source": "文件名", "page": 页码, "chunk_id": "uuid"}
```

### 2. 向量存储（vector_store.py）

- 使用 FAISS `IndexFlatIP`（内积 = 归一化后的余弦相似度）
- 向量归一化后存储，检索结果即为余弦相似度分数
- 持久化：`faiss.write_index()` 保存索引，`metadata.json` 保存文本和元数据
- 支持按来源文件删除（重建索引）

### 3. ZhipuAI 集成（llm.py）

- 嵌入：`client.embeddings.create(model="embedding-3", input=text)`
- 生成：`client.chat.completions.create(model="glm-4-flash", stream=True)`
- Prompt 模板包含检索到的上下文，要求模型引用 `[来源X]` 格式

### 4. FastAPI 后端（main.py）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 服务前端 HTML |
| `/frontend/{filename}` | GET | 服务 CSS/JS |
| `/upload` | POST | 文件上传 + 索引 |
| `/documents` | GET | 文档列表 |
| `/documents/{filename}` | DELETE | 删除文档 |
| `/chat` | POST | SSE 流式问答 |
| `/health` | GET | 健康检查 |

### 5. 前端（index.html / styles.css / app.js）

- **布局**：左侧栏（文档管理）+ 主聊天区 + 底部输入框
- **流式渲染**：`fetch` + `ReadableStream`，逐字追加并实时 Markdown 渲染
- **来源引用**：`[来源X]` 渲染为可悬停 `<span>`，hover 显示 tooltip（文档名、页码、内容预览）
- **Markdown**：marked.js 渲染，highlight.js 代码高亮
- **打字机效果**：通过 CSS `streaming-cursor::after` 实现光标闪烁

---

## SSE 事件协议

```
data: {"type":"sources","sources":[{"source":"file.pdf","page":3,"content":"...","score":0.95},...]}
data: {"type":"chunk","content":"回答内容片段..."}
data: {"type":"chunk","content":"..."}   (N次)
data: {"type":"done"}
```

---

## 数据持久化

```
data/vector_store/
├── faiss.index      # FAISS 二进制索引
├── metadata.json    # 文本内容 + 来源元数据
└── documents.json   # 文档注册表（文件名、大小、片段数、上传时间）
```

---

## 性能考量

1. **嵌入批处理**：当前逐条调用 ZhipuAI API，生产环境可改为批次调用
2. **向量搜索**：FAISS IndexFlatIP 为精确搜索，文档量大时可切换为 IVF 索引
3. **文本截断**：单条嵌入最长 2048 字符，避免 API 限制
4. **流式输出**：SSE 协议零缓冲传输，`X-Accel-Buffering: no` 穿透 Nginx 代理

---

## 已知限制与后续优化方向

1. 嵌入调用串行化，批量上传大文档时较慢 → 可改为并发/批量 API 调用
2. 删除文档需重建整个索引 → 可切换为 FAISS with IDs 或 Milvus
3. 无用户认证 → 生产环境需加 JWT/API Key 鉴权
4. 无会话记忆 → 可接入 LangChain ConversationMemory 实现多轮对话
