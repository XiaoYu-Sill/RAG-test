/* ===== Configuration ===== */
const API_BASE = '';

/* ===== Marked.js setup ===== */
marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

/* ===== State ===== */
let isStreaming = false;
let currentSources = [];
let documents = [];

/* ===== DOM refs ===== */
const questionInput = document.getElementById('questionInput');
const sendBtn = document.getElementById('sendBtn');
const messages = document.getElementById('messages');
const welcomeScreen = document.getElementById('welcomeScreen');
const chatContainer = document.getElementById('chatContainer');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const documentList = document.getElementById('documentList');
const docCount = document.getElementById('docCount');
const charCount = document.getElementById('charCount');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');
const newChatBtn = document.getElementById('newChatBtn');
const systemStatus = document.getElementById('systemStatus');
const sourceTooltip = document.getElementById('sourceTooltip');
const topKSelect = document.getElementById('topKSelect');

/* ===== Sidebar toggle ===== */
sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
});

/* ===== New Chat ===== */
newChatBtn.addEventListener('click', () => {
  messages.innerHTML = '';
  welcomeScreen.classList.remove('hidden');
  currentSources = [];
});

/* ===== Input handling ===== */
questionInput.addEventListener('input', () => {
  const len = questionInput.value.length;
  charCount.textContent = `${len}/2000`;
  sendBtn.disabled = len === 0 || isStreaming;
  // Auto-resize textarea
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
});

questionInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) handleSend();
  }
});

sendBtn.addEventListener('click', handleSend);

function sendSuggestion(el) {
  questionInput.value = el.textContent.trim();
  questionInput.dispatchEvent(new Event('input'));
  handleSend();
}

/* ===== Send message ===== */
async function handleSend() {
  const question = questionInput.value.trim();
  if (!question || isStreaming) return;

  welcomeScreen.classList.add('hidden');
  appendUserMessage(question);

  questionInput.value = '';
  questionInput.style.height = 'auto';
  charCount.textContent = '0/2000';
  sendBtn.disabled = true;
  isStreaming = true;

  const botMsg = appendBotMessage();
  await streamAnswer(question, botMsg);

  isStreaming = false;
  sendBtn.disabled = questionInput.value.trim().length === 0;
}

/* ===== Append messages ===== */
function appendUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message user';
  div.innerHTML = `
    <div class="avatar">👤</div>
    <div class="bubble">${escapeHtml(text)}</div>
  `;
  messages.appendChild(div);
  scrollToBottom();
}

function appendBotMessage() {
  const div = document.createElement('div');
  div.className = 'message bot';
  div.innerHTML = `
    <div class="avatar">🤖</div>
    <div class="bubble streaming-cursor" id="botBubble_${Date.now()}"></div>
  `;
  messages.appendChild(div);
  scrollToBottom();
  return div.querySelector('.bubble');
}

/* ===== SSE Streaming ===== */
async function streamAnswer(question, bubbleEl) {
  const topK = parseInt(topKSelect.value, 10);
  let rawText = '';
  let sourcesData = [];
  bubbleEl.textContent = '';

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, top_k: topK }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || 'Request failed');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        let event;
        try { event = JSON.parse(jsonStr); } catch { continue; }

        if (event.type === 'chunk') {
          rawText += event.content;
          renderMarkdownInBubble(bubbleEl, rawText, true);
          scrollToBottom();
        } else if (event.type === 'sources') {
          sourcesData = event.sources || [];
        } else if (event.type === 'error') {
          rawText += `\n\n> ⚠️ 错误：${event.message}`;
          renderMarkdownInBubble(bubbleEl, rawText, false);
        } else if (event.type === 'done') {
          renderMarkdownInBubble(bubbleEl, rawText, false);
          bubbleEl.classList.remove('streaming-cursor');
          if (sourcesData.length > 0) {
            renderSources(bubbleEl, sourcesData);
          }
        }
      }
    }
  } catch (err) {
    bubbleEl.classList.remove('streaming-cursor');
    bubbleEl.innerHTML = `<span style="color:#ef4444">⚠️ 请求失败：${escapeHtml(err.message)}</span>`;
    console.error('Stream error:', err);
  }
}

function renderMarkdownInBubble(el, rawText, streaming) {
  // Parse markdown, then replace [来源X] with hoverable citation spans (data-attr only, no inline handlers)
  const html = marked.parse(rawText);
  const withCites = html.replace(/\[来源(\d+)\]/g, (match, num) => {
    const idx = parseInt(num, 10) - 1;
    return `<span class="cite-link" data-src-idx="${idx}">${match}</span>`;
  });

  if (streaming) {
    el.innerHTML = withCites + '<span class="streaming-cursor"></span>';
  } else {
    el.innerHTML = withCites;
  }
  // Attach cite-link handlers via event delegation (avoids inline handler risks)
  el.querySelectorAll('.cite-link[data-src-idx]').forEach(span => {
    const idx = parseInt(span.dataset.srcIdx, 10);
    span.addEventListener('mouseenter', (e) => showTooltip(e, idx));
    span.addEventListener('mouseleave', hideTooltip);
    span.addEventListener('click', () => scrollToSource(idx));
  });
  hljs.highlightAll();
}

/* ===== Render source cards ===== */
function renderSources(bubbleEl, sources) {
  currentSources = sources;
  const section = document.createElement('div');
  section.className = 'sources-section';
  section.id = 'sourcesSection_' + Date.now();

  const title = document.createElement('div');
  title.className = 'sources-title';
  title.innerHTML = `📚 参考来源（${sources.length} 条）`;
  section.appendChild(title);

  const cards = document.createElement('div');
  cards.className = 'source-cards';

  sources.forEach((src, i) => {
    const card = document.createElement('div');
    card.className = 'source-card';
    card.id = `src-card-${i}`;
    card.innerHTML = `
      <div class="source-card-header">
        <span class="source-num">来源${i + 1}</span>
        <span class="source-name">${escapeHtml(src.source)}</span>
        <span class="source-page">第 ${escapeHtml(String(src.page))} 页</span>
      </div>
      <div class="source-preview">${escapeHtml(src.content)}</div>
    `;
    cards.appendChild(card);
  });

  section.appendChild(cards);
  bubbleEl.appendChild(section);
  scrollToBottom();
}

function scrollToSource(idx) {
  const card = document.getElementById(`src-card-${idx}`);
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    card.style.borderColor = 'var(--accent)';
    setTimeout(() => { card.style.borderColor = ''; }, 1500);
  }
}

/* ===== Tooltip ===== */
function showTooltip(event, idx) {
  const src = currentSources[idx];
  if (!src) return;
  sourceTooltip.innerHTML = `
    <div class="tooltip-title">📄 ${escapeHtml(src.source)}</div>
    <div class="tooltip-page">第 ${escapeHtml(String(src.page))} 页 · 相关度 ${(src.score * 100).toFixed(1)}%</div>
    <div class="tooltip-content">${escapeHtml(src.content.slice(0, 200))}${src.content.length > 200 ? '...' : ''}</div>
  `;
  positionTooltip(event);
  sourceTooltip.classList.add('visible');
}

function hideTooltip() {
  sourceTooltip.classList.remove('visible');
}

function positionTooltip(event) {
  const x = event.clientX;
  const y = event.clientY;
  const tw = 320;
  const th = 120;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let left = x + 12;
  let top = y - th / 2;
  if (left + tw > vw - 12) left = x - tw - 12;
  if (top < 8) top = 8;
  if (top + th > vh - 8) top = vh - th - 8;
  sourceTooltip.style.left = left + 'px';
  sourceTooltip.style.top = top + 'px';
}

/* ===== File Upload ===== */
uploadBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
  const files = Array.from(fileInput.files);
  if (!files.length) return;
  for (const file of files) {
    await uploadFile(file);
  }
  fileInput.value = '';
  await loadDocuments();
});

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  uploadProgress.classList.remove('hidden');
  progressFill.style.width = '20%';
  progressText.textContent = `上传中：${file.name}`;

  // Simulate progress during upload
  let prog = 20;
  const interval = setInterval(() => {
    prog = Math.min(prog + 10, 85);
    progressFill.style.width = prog + '%';
  }, 400);

  try {
    const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    clearInterval(interval);
    progressFill.style.width = '100%';

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      progressText.textContent = `❌ 失败：${err.detail}`;
      setTimeout(() => { uploadProgress.classList.add('hidden'); }, 3000);
      return;
    }
    const data = await res.json();
    progressText.textContent = `✅ ${file.name} 已索引 ${data.chunks} 个片段`;
  } catch (e) {
    clearInterval(interval);
    progressText.textContent = `❌ 上传失败：${e.message}`;
  }

  setTimeout(() => {
    uploadProgress.classList.add('hidden');
    progressFill.style.width = '0%';
  }, 2500);
}

/* ===== Document list ===== */
async function loadDocuments() {
  try {
    const res = await fetch(`${API_BASE}/documents`);
    if (!res.ok) return;
    const data = await res.json();
    documents = data.documents || [];
    renderDocumentList();
  } catch (e) {
    console.error('Failed to load documents:', e);
  }
}

function renderDocumentList() {
  docCount.textContent = documents.length;
  if (documents.length === 0) {
    documentList.innerHTML = '<li class="doc-empty">暂无文档，请上传</li>';
    return;
  }
  documentList.innerHTML = documents.map((doc, idx) => `
    <li class="doc-item">
      <span class="doc-icon">${fileIcon(doc.ext)}</span>
      <div class="doc-info">
        <div class="doc-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</div>
        <div class="doc-meta">${escapeHtml(String(doc.chunks))} 片段 · ${formatSize(doc.size)}</div>
      </div>
      <button class="doc-delete" title="删除文档" data-doc-idx="${idx}">🗑</button>
    </li>
  `).join('');

  // Attach delete handlers via data attribute (avoids inline handler XSS risk)
  documentList.querySelectorAll('.doc-delete').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.docIdx, 10);
      if (!isNaN(idx) && documents[idx]) deleteDocument(documents[idx].filename);
    });
  });
}

async function deleteDocument(filename) {
  if (!confirm(`确定删除文档 "${filename}" 及其所有索引数据？`)) return;
  try {
    const res = await fetch(`${API_BASE}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || '删除失败');
      return;
    }
    await loadDocuments();
  } catch (e) {
    alert('删除失败：' + e.message);
  }
}

/* ===== Health check ===== */
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      systemStatus.textContent = '系统正常';
      systemStatus.className = 'status-badge status-ok';
    } else {
      throw new Error();
    }
  } catch {
    systemStatus.textContent = '连接异常';
    systemStatus.className = 'status-badge status-error';
  }
}

/* ===== Helpers ===== */
function scrollToBottom() {
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fileIcon(ext) {
  const icons = { '.pdf': '📕', '.docx': '📘', '.doc': '📘', '.xlsx': '📗', '.csv': '📊', '.pptx': '📙', '.txt': '📄', '.md': '📝' };
  return icons[ext] || '📄';
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/* ===== Init ===== */
(async () => {
  await checkHealth();
  await loadDocuments();
  setInterval(checkHealth, 30000);
})();
