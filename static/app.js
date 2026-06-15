// Minimal markdown renderer (bold, inline code, code blocks, lists, paragraphs)
function renderMarkdown(text) {
  const lines = text.split('\n');
  let html = '';
  let inCode = false;
  let codeLines = [];
  let codeLang = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('```')) {
      if (!inCode) {
        inCode = true;
        codeLang = line.slice(3).trim();
        codeLines = [];
      } else {
        inCode = false;
        const escaped = codeLines.join('\n')
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html += `<pre><code>${escaped}</code></pre>`;
        codeLines = [];
      }
      continue;
    }

    if (inCode) { codeLines.push(line); continue; }

    let processed = line
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');

    if (/^[*-] /.test(processed)) {
      html += `<li>${processed.slice(2)}</li>`;
    } else if (/^\d+\. /.test(processed)) {
      html += `<li>${processed.replace(/^\d+\. /, '')}</li>`;
    } else if (processed.trim() === '') {
      html += '';
    } else {
      html += `<p>${processed}</p>`;
    }
  }

  if (inCode) {
    const escaped = codeLines.join('\n')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    html += `<pre><code>${escaped}</code></pre>`;
  }

  return html;
}

const messagesEl = document.getElementById('messages');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const clearBtn = document.getElementById('clearBtn');
let streaming = false;

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, content, streaming = false) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'label';
  label.textContent = role === 'user' ? 'You' : 'Companion';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (streaming) {
    bubble.innerHTML = '<span class="cursor"></span>';
    msg.dataset.streaming = '1';
  } else {
    bubble.innerHTML = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);
  }

  msg.appendChild(label);
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);
  scrollToBottom();
  return bubble;
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function setDisabled(val) {
  streaming = val;
  sendBtn.disabled = val;
  input.disabled = val;
}

async function loadHistory() {
  const res = await fetch('/history');
  const messages = await res.json();
  for (const msg of messages) {
    addMessage(msg.role, msg.content);
  }
  scrollToBottom();
}

async function sendMessage(text) {
  addMessage('user', text);
  const bubble = addMessage('assistant', '', true);
  setDisabled(true);

  let accumulated = '';

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.error) {
            bubble.innerHTML = `<em style="color:#f87171">Error: ${escapeHtml(data.error)}</em>`;
            return;
          }
          if (data.text) {
            accumulated += data.text;
            bubble.innerHTML = renderMarkdown(accumulated) + '<span class="cursor"></span>';
            scrollToBottom();
          }
          if (data.done) {
            bubble.innerHTML = renderMarkdown(accumulated);
          }
        } catch (_) {}
      }
    }
  } catch (err) {
    bubble.innerHTML = `<em style="color:#f87171">Connection error</em>`;
  } finally {
    setDisabled(false);
    input.focus();
    scrollToBottom();
  }
}

// Auto-resize textarea
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 160) + 'px';
});

// Submit on Enter (Shift+Enter for newline)
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!streaming) document.getElementById('chatForm').requestSubmit();
  }
});

document.getElementById('chatForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || streaming) return;
  input.value = '';
  input.style.height = 'auto';
  sendMessage(text);
});

clearBtn.addEventListener('click', async () => {
  if (!confirm('Clear conversation history?')) return;
  await fetch('/clear', { method: 'POST' });
  messagesEl.innerHTML = '';
});

loadHistory();
