const chat = document.getElementById("chat");
const questionInput = document.getElementById("questionInput");
const sendButton = document.getElementById("sendButton");
const fileInput = document.getElementById("fileInput");
const uploadStatus = document.getElementById("uploadStatus");
const tooltip = document.getElementById("tooltip");

let currentSources = {};

function addMessage(role, content, isHtml = false) {
  const message = document.createElement("div");
  message.className = `message ${role}`;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = role === "user" ? "你" : "助手";
  const body = document.createElement("div");
  body.className = "body";
  if (content) {
    if (isHtml) {
      body.innerHTML = content;
    } else {
      body.textContent = content;
    }
  }
  message.appendChild(meta);
  message.appendChild(body);
  chat.appendChild(message);
  chat.scrollTop = chat.scrollHeight;
  return body;
}

function renderMarkdown(text) {
  const html = marked.parse(text, { breaks: true });
  const safe = DOMPurify.sanitize(html);
  return safe.replace(/\[\[(\d+)\]\]/g, '<span class="citation" data-source-id="$1">[$1]</span>');
}

function bindCitationEvents(container) {
  const citations = container.querySelectorAll(".citation");
  citations.forEach((citation) => {
    const sourceId = citation.dataset.sourceId;
    const source = currentSources[sourceId];
    if (!source) {
      return;
    }
    citation.addEventListener("mouseenter", (event) => {
      showTooltip(event, source);
    });
    citation.addEventListener("mouseleave", hideTooltip);
    citation.addEventListener("click", () => {
      if (source.link) {
        window.open(source.link, "_blank");
      }
    });
  });
}

function showTooltip(event, source) {
  const label = `${source.metadata.source_name || "未知文档"} · ${source.metadata.location || "未知位置"}`;
  tooltip.innerHTML = `<h3>${label}</h3><p>${source.preview}</p>`;
  tooltip.classList.remove("hidden");
  tooltip.style.left = `${event.clientX + 12}px`;
  tooltip.style.top = `${event.clientY + 12}px`;
}

function hideTooltip() {
  tooltip.classList.add("hidden");
}

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }
  questionInput.value = "";
  addMessage("user", renderMarkdown(question), true);
  const assistantBody = addMessage("assistant", "正在检索与生成回答...");

  let response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch (error) {
    assistantBody.textContent = "网络异常，无法连接服务器。";
    return;
  }

  if (!response.ok) {
    assistantBody.textContent = `请求失败（${response.status}）`;
    return;
  }

  if (!response.body) {
    assistantBody.textContent = "无法建立流式连接。";
    return;
  }

  currentSources = {};
  let answerText = "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSse(buffer);
    buffer = parsed.remaining;
    parsed.events.forEach((event) => {
      if (event.event === "sources") {
        const sources = JSON.parse(event.data);
        sources.forEach((source) => {
          currentSources[String(source.id)] = source;
        });
      }
      if (event.event === "token") {
        const payload = JSON.parse(event.data);
        answerText += payload.token;
        assistantBody.innerHTML = renderMarkdown(answerText);
      }
      if (event.event === "done") {
        assistantBody.innerHTML = renderMarkdown(answerText);
        bindCitationEvents(assistantBody);
      }
    });
  }
}

function parseSse(buffer) {
  const events = [];
  const chunks = buffer.split("\n\n");
  const remaining = chunks.pop();
  chunks.forEach((chunk) => {
    let event = "message";
    let data = "";
    chunk.split("\n").forEach((line) => {
      if (line.startsWith("event:")) {
        event = line.replace("event:", "").trim();
      } else if (line.startsWith("data:")) {
        data += line.replace("data:", "").trim();
      }
    });
    if (data) {
      events.push({ event, data });
    }
  });
  return { events, remaining };
}

async function handleUpload(event) {
  const file = event.target.files[0];
  if (!file) {
    return;
  }
  uploadStatus.textContent = "上传中...";
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/upload", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) {
      uploadStatus.textContent = payload.detail || "上传失败";
    } else {
      uploadStatus.textContent = `已索引：${payload.filename}（${payload.indexed_chunks} 段）`;
    }
  } catch (error) {
    uploadStatus.textContent = "网络异常，上传失败";
  }
  fileInput.value = "";
}

sendButton.addEventListener("click", sendQuestion);
questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendQuestion();
  }
});
fileInput.addEventListener("change", handleUpload);
