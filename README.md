# 高铁事故应急处置 RAG 问答系统

## 说明文档

本项目提供一个基于检索增强生成（RAG）的高铁事故应急处置文档问答系统，支持默认文档索引与用户上传文档的即时索引，具备溯源引用展示与流式输出效果。

### 功能概览
- 默认对 `data/高铁事故应急预案.pdf` 建立 RAG 索引
- 支持上传 pdf/doc/docx/csv/xlsx/pptx 文件并即时索引
- 问答时展示引用来源，鼠标悬浮可查看溯源信息与文本预览
- 支持 Markdown 渲染与打字机流式输出
- 一键启动脚本

### 目录结构
```
.
├── app.py                 # FastAPI 服务入口
├── rag/                   # RAG 处理逻辑
├── static/                # 前端页面
├── data/                  # 默认数据与索引目录
├── requirements.txt
├── start.sh               # 一键启动脚本
└── IMPLEMENTATION_REPORT.md
```

### 快速启动
1. 将 `高铁事故应急预案.pdf` 放入 `data/` 目录
2. 一键启动：
```bash
chmod +x start.sh
./start.sh
```
3. 浏览器访问：`http://localhost:8000`

### 手动启动（可选）
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### 模型配置
系统使用智谱大模型（GLM-4 Plus）进行回答生成。请在环境中设置：
```
export ZHIPUAI_API_KEY=你的密钥
```
若未配置，将返回基于检索上下文的摘要提示。

### 上传与索引
在页面右上角上传文件即可自动索引。上传后的文件保存在 `data/uploads/`，向量索引保存在 `data/vector_store/`。

### 相关说明
- PDF 引用支持页码跳转（点击引用）
- 其他格式使用行号、段落或幻灯片号进行溯源展示

