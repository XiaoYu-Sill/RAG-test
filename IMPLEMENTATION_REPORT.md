# 项目实现报告

## 1. 总体架构
- FastAPI 作为后端服务入口，提供文档上传、检索问答与静态页面服务。
- RAG 处理逻辑独立在 `rag/` 模块中，完成文档解析、分块、向量化与检索。
- 前端页面位于 `static/`，采用 ChatGPT 风格布局，支持 Markdown 渲染与流式输出。

## 2. 数据预处理与分块
- 对 `data/` 与 `data/uploads/` 目录中的文档进行扫描。
- 使用 LangChain 的 `RecursiveCharacterTextSplitter` 进行文本分块，默认 `chunk_size=800`，`chunk_overlap=120`。
- 不同文件类型提取方式：
  - PDF：逐页解析并保留页码元数据
  - DOCX：逐段落解析并记录段落编号
  - DOC：使用 textract 提取全文
  - CSV/XLSX：按行解析，并记录行号与工作表
  - PPTX：按幻灯片解析并记录页码

## 3. 向量化与向量数据库
- 使用 `sentence-transformers/all-MiniLM-L6-v2` 生成向量。
- 本地向量库实现于 `LocalVectorStore`：
  - 向量存储为 `data/vector_store/embeddings.npy`
  - 文本与元数据存储为 `data/vector_store/records.json`
- 支持重新构建与增量追加，上传文件后自动更新索引。

## 4. RAG 检索与溯源
- 基于余弦相似度检索 Top-K 文本块。
- 每条检索结果带有 `source_name` 与 `location` 元数据。
- 构建上下文提示时，按编号标记来源，要求模型在回答中输出 `[[编号]]` 引用。

## 5. 大模型回答
- 集成智谱大模型 GLM-4 Plus，支持流式输出。
- 若未配置 `ZHIPUAI_API_KEY`，则提供基于检索文本的摘要提示。
- 后端通过 SSE（Server-Sent Events）向前端持续推送 token。

## 6. 前端交互与展示
- Markdown 渲染：`marked` + `DOMPurify`，防止 XSS。
- 打字机效果：实时接收 token 并刷新渲染。
- 溯源交互：
  - 引用标记 `[[1]]` 会被渲染为可点击引用
  - 鼠标悬浮显示来源文档、位置与文本预览
  - 点击跳转至对应原文档（PDF 支持页码定位）

## 7. 一键启动
- `start.sh` 提供一键安装依赖并启动服务的能力。
- 启动后访问 `http://localhost:8000` 使用系统。

