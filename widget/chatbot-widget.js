/**
 * Solutions Agency Chatbot Widget
 * Vanilla JS, dependency-free, embeddable via a single <script> tag.
 * Uses Shadow DOM to avoid CSS conflicts with the host WordPress theme.
 *
 * Usage (embed in WordPress, e.g. via a Custom HTML block or footer script):
 *   <script
 *     src="https://your-vps-domain.com/widget/chatbot-widget.js"
 *     data-api-url="https://your-vps-domain.com/api/chat"
 *     data-agency-name="Your Agency Name"
 *   ></script>
 */
(function () {
  "use strict";

  const scriptTag = document.currentScript;
  const API_URL = scriptTag?.getAttribute("data-api-url") || "http://localhost:8000/api/chat";
  const AGENCY_NAME = scriptTag?.getAttribute("data-agency-name") || "Our Team";

  const SESSION_STORAGE_KEY = "solutions_bot_session_id";

  function getOrCreateSessionId() {
    let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!sessionId) {
      sessionId = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    }
    return sessionId;
  }

  const sessionId = getOrCreateSessionId();

  // --- Host element + Shadow DOM ---
  const host = document.createElement("div");
  host.id = "solutions-bot-widget-host";
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: "open" });

  const styles = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :host {
      all: initial;
    }

    * {
      box-sizing: border-box;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .launcher {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: #14151A;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 8px 24px rgba(20, 21, 26, 0.35);
      z-index: 999999;
      transition: transform 0.2s ease;
    }
    .launcher:hover { transform: scale(1.06); }

    .launcher::before {
      content: '';
      position: absolute;
      inset: -6px;
      border-radius: 50%;
      border: 2px solid #5B5FEF;
      opacity: 0.5;
      animation: pulse-ring 2.4s ease-out infinite;
    }
    @keyframes pulse-ring {
      0% { transform: scale(0.9); opacity: 0.5; }
      80% { transform: scale(1.3); opacity: 0; }
      100% { transform: scale(1.3); opacity: 0; }
    }

    .launcher svg { width: 26px; height: 26px; z-index: 1; }

    .panel {
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 560px;
      max-height: calc(100vh - 140px);
      background: #FFFFFF;
      border-radius: 16px;
      box-shadow: 0 16px 48px rgba(20, 21, 26, 0.22);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
      border: 1px solid #E8E8ED;
    }
    .panel.open { display: flex; }

    .panel-header {
      background: #14151A;
      color: #FFFFFF;
      padding: 18px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .panel-header .title { display: flex; flex-direction: column; }
    .panel-header .name { font-weight: 600; font-size: 15px; }
    .panel-header .status { font-size: 12px; color: #9C9FE0; display: flex; align-items: center; gap: 6px; margin-top: 2px; }
    .panel-header .status::before {
      content: '';
      width: 6px; height: 6px; border-radius: 50%;
      background: #4ADE80;
      display: inline-block;
    }
    .panel-header button {
      background: none; border: none; color: #FFFFFF;
      cursor: pointer; opacity: 0.7; padding: 4px;
    }
    .panel-header button:hover { opacity: 1; }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #FAFAFC;
    }

    .msg {
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 14px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
    .msg.user {
      align-self: flex-end;
      background: #5B5FEF;
      color: #FFFFFF;
      border-bottom-right-radius: 4px;
    }
    .msg.bot {
      align-self: flex-start;
      background: #F1F1F5;
      color: #1C1E26;
      border-bottom-left-radius: 4px;
    }

    .typing-indicator {
      align-self: flex-start;
      background: #F1F1F5;
      padding: 12px 16px;
      border-radius: 14px;
      border-bottom-left-radius: 4px;
      display: flex;
      gap: 4px;
    }
    .typing-indicator span {
      width: 6px; height: 6px; border-radius: 50%;
      background: #9C9FA6;
      animation: typing-bounce 1.2s infinite ease-in-out;
    }
    .typing-indicator span:nth-child(2) { animation-delay: 0.15s; }
    .typing-indicator span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes typing-bounce {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
      30% { transform: translateY(-4px); opacity: 1; }
    }

    .quick-replies {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 4px 4px 8px;
      align-self: flex-start;
      max-width: 100%;
    }
    .quick-reply-chip {
      background: #fff;
      border: 1px solid #5B5FEF;
      color: #5B5FEF;
      font-size: 12.5px;
      font-weight: 500;
      padding: 8px 14px;
      border-radius: 16px;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
      white-space: nowrap;
    }
    .quick-reply-chip:hover {
      background: #5B5FEF;
      color: #fff;
    }

    .input-row {
      display: flex;
      align-items: flex-end;
      gap: 8px;
      padding: 14px;
      border-top: 1px solid #E8E8ED;
      background: #FFFFFF;
    }
    .input-row textarea {
      flex: 1;
      resize: none;
      border: 1px solid #E8E8ED;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 14px;
      max-height: 90px;
      outline: none;
      color: #1C1E26;
    }
    .input-row textarea:focus { border-color: #5B5FEF; }
    .input-row button {
      background: #5B5FEF;
      border: none;
      border-radius: 10px;
      width: 40px; height: 40px;
      flex-shrink: 0;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: background 0.15s ease;
    }
    .input-row button:hover { background: #4A4EDB; }
    .input-row button:disabled { background: #C7C7D6; cursor: not-allowed; }
    .input-row button svg { width: 18px; height: 18px; }

    .messages::-webkit-scrollbar { width: 6px; }
    .messages::-webkit-scrollbar-thumb { background: #D6D6E0; border-radius: 3px; }

    /* --- Mobile responsiveness --- */
    
    @media (max-width: 480px) {
      .launcher {
        bottom: 16px;
        right: 16px;
        width: 56px;
        height: 56px;
      }

      .panel {
        bottom: 0;
        right: 0;
        left: 0;
        top: 0;
        width: 100%;
        max-width: 100%;
        height: 100%;
        max-height: 100%;
        border-radius: 0;
      }

      .panel-header {
        padding-top: max(18px, env(safe-area-inset-top));
      }

      .input-row {
        padding-bottom: max(14px, env(safe-area-inset-bottom));
      }

      .input-row textarea {
        font-size: 16px; /* Prevents iOS Safari auto-zoom on focus */
      }
    }
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = styles;
  shadow.appendChild(styleEl);

  const wrapper = document.createElement("div");
  wrapper.innerHTML = `
    <button class="launcher" aria-label="Open chat">
      <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
      </svg>
    </button>

    <div class="panel" role="dialog" aria-label="Chat with ${AGENCY_NAME}">
      <div class="panel-header">
        <div class="title">
          <span class="name">${AGENCY_NAME}</span>
          <span class="status">Online</span>
        </div>
        <button class="close-btn" aria-label="Close chat">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="white" stroke-width="2" stroke-linecap="round">
            <path d="M18 6 6 18M6 6l12 12"></path>
          </svg>
        </button>
      </div>
      <div class="messages" id="messages"></div>
      <div class="input-row">
        <textarea id="chat-input" rows="1" placeholder="Type your message..."></textarea>
        <button id="send-btn" aria-label="Send message">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m22 2-7 20-4-9-9-4Z"></path>
            <path d="M22 2 11 13"></path>
          </svg>
        </button>
      </div>
    </div>
  `;
  shadow.appendChild(wrapper);

  const launcherBtn = shadow.querySelector(".launcher");
  const panel = shadow.querySelector(".panel");
  const closeBtn = shadow.querySelector(".close-btn");
  const messagesEl = shadow.querySelector("#messages");
  const inputEl = shadow.querySelector("#chat-input");
  const sendBtn = shadow.querySelector("#send-btn");

  let hasGreeted = false;

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderMarkdownLite(text) {
    // Escape HTML first to prevent injection, then apply simple markdown formatting
    let safe = escapeHtml(text);

    // **bold**
    safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // [link text](url)
    safe = safe.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    // Line breaks
    safe = safe.replace(/\n/g, "<br>");

    return safe;
  }

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.innerHTML = renderMarkdownLite(text);
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "typing-indicator";
    el.id = "typing-indicator";
    el.innerHTML = "<span></span><span></span><span></span>";
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideTyping() {
    const el = shadow.querySelector("#typing-indicator");
    if (el) el.remove();
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;

    removeQuickReplies();
    appendMessage("user", text);
    inputEl.value = "";
    inputEl.style.height = "auto";
    sendBtn.disabled = true;
    showTyping();

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!response.ok) throw new Error(`Request failed: ${response.status}`);

      const data = await response.json();
      hideTyping();
      appendMessage("bot", data.reply);
    } catch (err) {
      hideTyping();
      appendMessage(
        "bot",
        "Sorry, something went wrong connecting to our server. Please try again in a moment."
      );
      console.error("Solutions bot widget error:", err);
    } finally {
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  const QUICK_REPLIES = [
    "What services do you offer?",
    "Can I see some past work?",
    "I want to book a call",
    "What's your pricing like?",
  ];

  function showQuickReplies() {
    const el = document.createElement("div");
    el.className = "quick-replies";
    el.id = "quick-replies";
    QUICK_REPLIES.forEach((question) => {
      const chip = document.createElement("button");
      chip.className = "quick-reply-chip";
      chip.textContent = question;
      chip.addEventListener("click", () => {
        removeQuickReplies();
        inputEl.value = question;
        sendMessage();
      });
      el.appendChild(chip);
    });
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeQuickReplies() {
    const el = shadow.querySelector("#quick-replies");
    if (el) el.remove();
  }

  launcherBtn.addEventListener("click", () => {
    panel.classList.add("open");
    if (!hasGreeted) {
      appendMessage(
        "bot",
        `Hi! 👋 I'm here to help with website development, design, AI automation, or custom software. What are you looking for today?`
      );
      showQuickReplies();
      hasGreeted = true;
    }
    inputEl.focus();
  });

  closeBtn.addEventListener("click", () => panel.classList.remove("open"));

  sendBtn.addEventListener("click", sendMessage);

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 90) + "px";
  });
})();