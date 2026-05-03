# 高铁事故应急处置文档智能问答系统

基于 **RAG（检索增强生成）** 技术的专业问答系统，专为高铁事故应急处置文档检索与智能问答设计。

## 功能特性

- 📄 **多格式文档支持**：PDF、Word（docx/doc）、Excel（xlsx）、PowerPoint（pptx）、CSV、TXT、Markdown
- 🔍 **语义检索**：基于 ZhipuAI `embedding-3` 模型的向量语义搜索
- 🤖 **智能问答**：ZhipuAI `glm-4-flash` 大语言模型流式生成回答
- 📚 **来源引用**：每条回答附带可点击的文档来源、页码和内容预览
- 💾 **持久化向量库**：FAISS 本地持久化，重启后无需重新索引
- 🎨 **现代化界面**：ChatGPT 风格，支持 Markdown 渲染、代码高亮、流式输出

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 向量数据库 | FAISS（本地持久化） |
| 嵌入模型 | ZhipuAI embedding-3 |
| 语言模型 | ZhipuAI glm-4-flash |
| 文档处理 | LangChain + PyMuPDF + python-docx + openpyxl + python-pptx |
| 前端 | 纯 HTML/CSS/JS + marked.js + highlight.js |

## 快速启动

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 ZhipuAI API Key
echo "ZHIPU_API_KEY=your_key_here" > .env
```

### 2. 一键启动

```bash
bash start.sh
```

### 3. 访问系统

打开浏览器访问：http://localhost:8000

## 项目结构

```
RAG-test/
├── backend/
│   ├── main.py              # FastAPI 应用主文件
│   ├── config.py            # 配置项
│   ├── rag/
│   │   ├── document_processor.py  # 文档加载与分块
│   │   ├── vector_store.py        # FAISS 向量存储
│   │   ├── retriever.py           # RAG 检索器
│   │   └── llm.py                 # ZhipuAI 集成
│   └── uploads/             # 上传文件目录
├── frontend/
│   ├── index.html           # 主界面
│   ├── styles.css           # 样式
│   └── app.js               # 前端逻辑
├── data/
│   └── vector_store/        # FAISS 索引持久化
├── requirements.txt
├── .env.example
└── start.sh
```

## API 接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/` | 前端界面 |
| GET | `/health` | 健康检查 |
| POST | `/upload` | 上传并索引文档 |
| GET | `/documents` | 获取文档列表 |
| DELETE | `/documents/{filename}` | 删除文档 |
| POST | `/chat` | RAG 问答（SSE 流式） |

## 手动安装

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
