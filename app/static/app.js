function defaultTotals() {
  return {
    messages: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
  };
}

function parseStorage(store, key, fallback) {
  try {
    const raw = store.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    return fallback;
  }
}

function normalizeSession(session = {}) {
  const now = new Date().toISOString();
  return {
    id: session.id || `session-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title: session.title || 'New chat',
    createdAt: session.createdAt || now,
    updatedAt: session.updatedAt || session.createdAt || now,
    messages: Array.isArray(session.messages) ? session.messages : [],
    totals: { ...defaultTotals(), ...(session.totals || {}) },
  };
}

function loadChatSessions() {
  const stored = parseStorage(localStorage, 'ope.chatSessions', []);
  if (Array.isArray(stored) && stored.length) {
    return stored.map(normalizeSession);
  }

  return [
    normalizeSession({
      title: 'New chat',
      messages: parseStorage(sessionStorage, 'ope.chatMessages', []),
      totals: parseStorage(sessionStorage, 'ope.sessionTotals', defaultTotals()),
    }),
  ];
}

const initialSessions = loadChatSessions();
const preferredSessionId = localStorage.getItem('ope.activeSessionId');
const initialActiveSession = initialSessions.find((session) => session.id === preferredSessionId) || initialSessions[0];

const state = {
  apiKey: localStorage.getItem('ope.apiKey') || '',
  project: localStorage.getItem('ope.project') || 'ope-core',
  mode: localStorage.getItem('ope.mode') || 'auto',
  activeSessionId: initialActiveSession.id,
  chatSessions: initialSessions,
  sessionTotals: initialActiveSession.totals,
  chatMessages: initialActiveSession.messages,
};

const defaultRouteOptions = [
  { route: 'quick_lookup', primary_model: 'openai-mini' },
  { route: 'technical_search', primary_model: 'gemini-main' },
  { route: 'codebase_work', primary_model: 'claude-coding' },
  { route: 'deep_reasoning', primary_model: 'claude-main' },
  { route: 'private_memory', primary_model: 'openai-main' },
  { route: 'tool_action', primary_model: 'claude-main' },
];

const $ = (id) => document.getElementById(id);

const elements = {
  apiKey: $('apiKeyInput'),
  project: $('projectInput'),
  mode: $('modeInput'),
  query: $('queryInput'),
  budget: $('budgetInput'),
  latency: $('latencyInput'),
  search: $('searchInput'),
  tools: $('toolsInput'),
  approval: $('approvalInput'),
  requestState: $('requestState'),
  requestPreview: $('requestPreview'),
  answer: $('answerOutput'),
  answerMetrics: $('answerMetrics'),
  messageCost: $('messageCost'),
  messageTokens: $('messageTokens'),
  sessionCost: $('sessionCost'),
  sessionTokens: $('sessionTokens'),
  modelSummary: $('modelSummary'),
  health: $('healthStatus'),
  ready: $('readyStatus'),
  sessions: $('sessionPanel'),
  approvalStats: $('approvalStatsPanel'),
  approvals: $('approvalsPanel'),
  routes: $('routePanel'),
  models: $('modelsPanel'),
  events: $('eventsPanel'),
  memory: $('memoryPanel'),
  uploads: $('uploadsPanel'),
  uploadForm: $('uploadForm'),
  uploadFile: $('uploadFileInput'),
  uploadCategory: $('uploadCategoryInput'),
  uploadDescription: $('uploadDescriptionInput'),
  uploadSuggestion: $('uploadSuggestionText'),
  connectors: $('connectorsPanel'),
  toolsPanel: $('toolsPanel'),
  draftJobForm: $('draftJobForm'),
  draftAction: $('draftActionInput'),
  draftTarget: $('draftTargetInput'),
  draftTargetLabel: $('draftTargetLabel'),
  draftTitle: $('draftTitleInput'),
  draftTitleLabel: $('draftTitleLabel'),
  draftRequestedBy: $('draftRequestedByInput'),
  draftBody: $('draftBodyInput'),
  draftBodyLabel: $('draftBodyLabel'),
  draftPayloadPreview: $('draftPayloadPreview'),
  draftJobStatus: $('draftJobStatus'),
};

let approvalFilter = 'pending';
let approvalJobsById = new Map();
let approvalPollTimer = null;

const draftActionSpecs = {
  'github:draft_issue': {
    connector: 'github',
    action: 'draft_issue',
    targetLabel: 'Owner / repo',
    targetPlaceholder: 'DroneWuKong/O.P.E.',
    titleLabel: 'Issue title',
    titlePlaceholder: 'Approval Inbox follow-up',
    bodyLabel: 'Issue body',
    bodyPlaceholder: 'Describe the change you want queued for review...',
    example: {
      target: 'DroneWuKong/O.P.E.',
      title: 'Tighten connector approval history',
      body: 'Add a filtered history view for approved and rejected connector jobs.',
    },
    buildPayload({ target, title, body }) {
      const [owner, repo] = target.split('/').map((part) => part.trim());
      if (!owner || !repo) throw new Error('Use owner/repo for the GitHub target.');
      return { owner, repo, title, body };
    },
  },
  'gmail:draft_reply': {
    connector: 'gmail',
    action: 'draft_reply',
    targetLabel: 'To or thread',
    targetPlaceholder: 'person@example.com or thread-id',
    titleLabel: 'Subject',
    titlePlaceholder: 'Re: O.P.E. update',
    bodyLabel: 'Reply body',
    bodyPlaceholder: 'Write the reply draft for review...',
    example: {
      target: 'operator@example.com',
      title: 'Re: O.P.E. connector approvals',
      body: 'Hey there, the local draft is ready for review in O.P.E. before anything leaves the system.',
    },
    buildPayload({ target, title, body }) {
      const payload = { subject: title, body };
      if (target.includes('@')) payload.to = target;
      else if (target) payload.thread_id = target;
      return payload;
    },
  },
  'google_drive:draft_doc_update': {
    connector: 'google_drive',
    action: 'draft_doc_update',
    targetLabel: 'File ID',
    targetPlaceholder: 'Google Doc file id',
    titleLabel: 'Draft title',
    titlePlaceholder: 'Deployment notes update',
    bodyLabel: 'Doc update',
    bodyPlaceholder: 'Write the proposed document update...',
    example: {
      target: 'doc-123',
      title: 'Connector approvals milestone',
      body: 'Add notes explaining that local draft jobs require approval and do not mutate Google Drive.',
    },
    buildPayload({ target, title, body }) {
      if (!target) throw new Error('Enter a Google Doc file id.');
      return { file_id: target, title, body };
    },
  },
};

elements.apiKey.value = state.apiKey;
elements.project.value = state.project;

function normalizedApiKey() {
  return elements.apiKey.value.trim().replace(/^Bearer\s+/i, '');
}

function hasApiKey() {
  return normalizedApiKey().length > 0;
}

function requireApiKey(target) {
  if (hasApiKey()) {
    return true;
  }
  renderEmpty(target, 'Enter your OPE API key to load this panel.');
  return false;
}

function authHeaders() {
  const key = normalizedApiKey();
  const headers = { 'Content-Type': 'application/json' };
  if (key) {
    headers.Authorization = `Bearer ${key}`;
  }
  persistApiKey();
  localStorage.setItem('ope.project', elements.project.value.trim() || 'ope-core');
  localStorage.setItem('ope.mode', elements.mode.value || 'auto');
  return headers;
}

function persistApiKey() {
  const key = normalizedApiKey();
  if (key) {
    localStorage.setItem('ope.apiKey', key);
  }
}

function forgetApiKey() {
  elements.apiKey.value = '';
  localStorage.removeItem('ope.apiKey');
  refreshAll();
}

async function api(path, options = {}) {
  if (!hasApiKey()) {
    throw new Error('Enter your OPE API key first.');
  }
  const response = await fetch(path, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail?.error || data?.detail || response.statusText;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

async function apiForm(path, formData, options = {}) {
  if (!hasApiKey()) {
    throw new Error('Enter your OPE API key first.');
  }
  const key = normalizedApiKey();
  const headers = {};
  if (key) headers.Authorization = `Bearer ${key}`;
  persistApiKey();
  localStorage.setItem('ope.project', elements.project.value.trim() || 'ope-core');
  const response = await fetch(path, {
    ...options,
    method: options.method || 'POST',
    headers: {
      ...headers,
      ...(options.headers || {}),
    },
    body: formData,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail?.error || data?.detail || response.statusText;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

function setStatus(el, label, ok, detail = '') {
  el.classList.toggle('ok', ok === true);
  el.classList.toggle('bad', ok === false);
  el.textContent = `${label}: ${ok ? 'ok' : 'down'}${detail ? ` (${detail})` : ''}`;
}

function setBusy(label) {
  elements.requestState.textContent = label;
}

function renderEmpty(target, text = 'Nothing here yet.') {
  target.innerHTML = `<p class="empty">${escapeHtml(text)}</p>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  })[char]);
}

function renderMetrics(items) {
  elements.answerMetrics.innerHTML = items
    .filter((item) => item.value !== undefined && item.value !== null && item.value !== '')
    .map((item) => `<span class="metric">${escapeHtml(item.label)}: ${escapeHtml(item.value)}</span>`)
    .join('');
}

function routeLabel(value) {
  return String(value || '')
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function populateRouteOptions(routes = defaultRouteOptions) {
  const selected = elements.mode.options.length ? elements.mode.value : state.mode || 'auto';
  const options = [
    '<option value="auto">Auto route</option>',
    ...routes.map((route) => (
      `<option value="${escapeHtml(route.route)}">${escapeHtml(routeLabel(route.route))} / ${escapeHtml(route.primary_model || 'model?')}</option>`
    )),
  ];
  elements.mode.innerHTML = options.join('');
  elements.mode.value = [...elements.mode.options].some((option) => option.value === selected) ? selected : 'auto';
  renderRequestPreview();
}

function selectedRouteText() {
  return elements.mode.selectedOptions[0]?.textContent?.trim() || 'Auto route';
}

function renderRequestPreview() {
  if (!elements.requestPreview) return;
  const chips = [
    { label: 'Route', value: selectedRouteText() },
    { label: 'Budget', value: routeLabel(elements.budget.value) },
    { label: 'Latency', value: routeLabel(elements.latency.value) },
    { label: 'Search', value: elements.search.checked ? 'on' : 'off' },
    { label: 'Tools', value: elements.tools.checked ? 'on' : 'off' },
  ];
  elements.requestPreview.innerHTML = chips.map((chip) => `
    <span><b>${escapeHtml(chip.label)}</b>${escapeHtml(chip.value)}</span>
  `).join('');
}

function activeSession() {
  return state.chatSessions.find((session) => session.id === state.activeSessionId) || state.chatSessions[0];
}

function syncActiveSession() {
  const session = activeSession();
  if (!session) return;
  session.messages = state.chatMessages;
  session.totals = state.sessionTotals;
  session.updatedAt = new Date().toISOString();
}

function persistSessions() {
  syncActiveSession();
  localStorage.setItem('ope.chatSessions', JSON.stringify(state.chatSessions));
  localStorage.setItem('ope.activeSessionId', state.activeSessionId);
  sessionStorage.setItem('ope.chatMessages', JSON.stringify(state.chatMessages));
  sessionStorage.setItem('ope.sessionTotals', JSON.stringify(state.sessionTotals));
}

function sessionTitleFromMessage(value) {
  const compact = String(value || '').replace(/\s+/g, ' ').trim();
  if (!compact) return 'New chat';
  return compact.length > 40 ? `${compact.slice(0, 37)}...` : compact;
}

function titleActiveSession(value) {
  const session = activeSession();
  if (!session || session.title !== 'New chat') return;
  session.title = sessionTitleFromMessage(value);
}

function sessionMeta(session) {
  const count = session.messages.length;
  const cost = formatUsd(session.totals?.costUsd || 0);
  return `${count} ${count === 1 ? 'message' : 'messages'} / ${cost}`;
}

function renderSessionList() {
  if (!elements.sessions) return;
  elements.sessions.innerHTML = state.chatSessions.map((session) => `
    <button class="session-item ${session.id === state.activeSessionId ? 'active' : ''}" type="button" data-session-id="${escapeHtml(session.id)}">
      <span class="session-title">${escapeHtml(session.title)}</span>
      <span class="session-meta">${escapeHtml(sessionMeta(session))}</span>
    </button>
  `).join('');
}

function switchSession(id) {
  const next = state.chatSessions.find((session) => session.id === id);
  if (!next || next.id === state.activeSessionId) return;
  syncActiveSession();
  state.activeSessionId = next.id;
  state.chatMessages = next.messages;
  state.sessionTotals = next.totals;
  persistSessions();
  renderChat();
  renderCost();
  renderMetrics([]);
  renderSessionList();
  setBusy('Ready');
}

function newChatSession() {
  syncActiveSession();
  const session = normalizeSession({ title: 'New chat' });
  state.chatSessions.unshift(session);
  state.activeSessionId = session.id;
  state.chatMessages = session.messages;
  state.sessionTotals = session.totals;
  persistSessions();
  renderChat();
  renderCost();
  renderMetrics([]);
  renderSessionList();
  setBusy('New chat');
}

function deleteCurrentSession() {
  if (state.chatSessions.length <= 1) {
    const session = activeSession();
    session.title = 'New chat';
    state.chatMessages = [];
    state.sessionTotals = defaultTotals();
    persistSessions();
    renderChat();
    renderCost();
    renderMetrics([]);
    renderSessionList();
    setBusy('Cleared');
    return;
  }

  state.chatSessions = state.chatSessions.filter((session) => session.id !== state.activeSessionId);
  const next = state.chatSessions[0];
  state.activeSessionId = next.id;
  state.chatMessages = next.messages;
  state.sessionTotals = next.totals;
  persistSessions();
  renderChat();
  renderCost();
  renderMetrics([]);
  renderSessionList();
  setBusy('Deleted');
}

function saveChatMessages() {
  persistSessions();
  renderSessionList();
}

function chatMessageMeta(message) {
  const usage = message.metadata?.usage || {};
  const details = [
    message.route ? `route ${message.route}` : '',
    message.model ? `model ${message.model}` : '',
    message.metadata?.latency_ms ? `${message.metadata.latency_ms} ms` : '',
    usage.total_tokens ? `${Number(usage.total_tokens).toLocaleString()} tokens` : '',
    message.metadata?.estimated_cost_usd !== undefined ? formatUsd(message.metadata.estimated_cost_usd) : '',
  ].filter(Boolean);
  return details.join(' / ');
}

function renderChat() {
  if (!state.chatMessages.length) {
    elements.answer.innerHTML = `
      <section class="empty-orbit" aria-label="Empty chat">
        <p class="orbit-kicker">O.P.E. / Octoputer</p>
        <h3>What's the work?</h3>
        <p>Ask plain. O.P.E. routes it.</p>
      </section>
    `;
    return;
  }
  elements.answer.innerHTML = state.chatMessages.map((message) => {
    const meta = chatMessageMeta(message);
    const copyButton = message.role !== 'user' && message.status !== 'pending'
      ? `<button class="copy-button" type="button" data-copy-message="${escapeHtml(message.id)}">Copy</button>`
      : '';
    const useButton = message.role === 'user'
      ? `<button class="copy-button" type="button" data-use-message="${escapeHtml(message.id)}">Use</button>`
      : '';
    return `
      <article class="chat-message ${escapeHtml(message.role)} ${message.status === 'pending' ? 'pending' : ''}">
        <div class="chat-message-head">
          <strong>${message.role === 'user' ? 'You' : message.role === 'system' ? 'System' : 'O.P.E.'}</strong>
          <div>
            ${meta ? `<span>${escapeHtml(meta)}</span>` : ''}
            ${copyButton}
            ${useButton}
          </div>
        </div>
        <div class="chat-message-body">${escapeHtml(message.content)}</div>
      </article>
    `;
  }).join('');
  elements.answer.scrollTop = elements.answer.scrollHeight;
}

function appendChatMessage(role, content, extras = {}) {
  if (role === 'user') {
    titleActiveSession(content);
  }
  const message = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    createdAt: new Date().toISOString(),
    ...extras,
  };
  state.chatMessages.push(message);
  saveChatMessages();
  renderChat();
  return message.id;
}

function updateChatMessage(id, updates) {
  state.chatMessages = state.chatMessages.map((message) => (
    message.id === id ? { ...message, ...updates } : message
  ));
  saveChatMessages();
  renderChat();
}

function clearChatMessages() {
  state.chatMessages = [];
  saveChatMessages();
  renderChat();
  renderMetrics([]);
  setBusy('Idle');
}

function lastUserMessage() {
  return [...state.chatMessages].reverse().find((message) => message.role === 'user');
}

function setComposerValue(value) {
  elements.query.value = value || '';
  autosizeComposer();
  elements.query.focus();
}

function sessionMarkdown() {
  const lines = [
    '# O.P.E. Session',
    '',
    `Exported: ${new Date().toISOString()}`,
    `Project: ${elements.project.value.trim() || 'ope-core'}`,
    `Messages: ${state.chatMessages.length}`,
    `Estimated session cost: ${formatUsd(state.sessionTotals.costUsd)}`,
    `Session tokens: ${state.sessionTotals.totalTokens.toLocaleString()}`,
    '',
  ];
  state.chatMessages.forEach((message) => {
    const label = message.role === 'assistant' ? 'O.P.E.' : message.role === 'user' ? 'You' : 'System';
    lines.push(`## ${label}`);
    const meta = chatMessageMeta(message);
    if (meta) lines.push(`_${meta}_`, '');
    lines.push(message.content || '', '');
  });
  return lines.join('\n');
}

function exportChat() {
  if (!state.chatMessages.length) {
    setBusy('Nothing to export');
    return;
  }
  const blob = new Blob([sessionMarkdown()], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `ope-session-${new Date().toISOString().replace(/[:.]/g, '-')}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  setBusy('Exported');
}

function formatUsd(value) {
  const amount = Number(value || 0);
  if (amount >= 0.01) return `$${amount.toFixed(4)}`;
  return `$${amount.toFixed(6)}`;
}

function renderCost(message = {}) {
  const usage = message.usage || {};
  const messageCost = Number(message.estimated_cost_usd || 0);
  const inputTokens = Number(usage.input_tokens || 0);
  const outputTokens = Number(usage.output_tokens || 0);
  const totalTokens = Number(usage.total_tokens || 0);
  elements.messageCost.textContent = formatUsd(messageCost);
  elements.messageTokens.textContent = `${totalTokens.toLocaleString()} tokens (${inputTokens.toLocaleString()} in / ${outputTokens.toLocaleString()} out)`;
  elements.sessionCost.textContent = formatUsd(state.sessionTotals.costUsd);
  elements.sessionTokens.textContent = `${state.sessionTotals.messages.toLocaleString()} messages / ${state.sessionTotals.totalTokens.toLocaleString()} tokens`;
}

function addMessageCost(metadata = {}) {
  const usage = metadata.usage || {};
  const costUsd = Number(metadata.estimated_cost_usd || 0);
  const inputTokens = Number(usage.input_tokens || 0);
  const outputTokens = Number(usage.output_tokens || 0);
  const totalTokens = Number(usage.total_tokens || inputTokens + outputTokens);
  state.sessionTotals.messages += 1;
  state.sessionTotals.inputTokens += inputTokens;
  state.sessionTotals.outputTokens += outputTokens;
  state.sessionTotals.totalTokens += totalTokens;
  state.sessionTotals.costUsd += costUsd;
  persistSessions();
  renderSessionList();
  renderCost(metadata);
}

function resetSessionCost() {
  state.sessionTotals = defaultTotals();
  persistSessions();
  renderSessionList();
  renderCost();
}

function modelStatusText(info = {}) {
  const failure = info.last_failure ? String(info.last_failure).replaceAll('_', ' ') : '';
  const cooldown = Number(info.cooldown_remaining_seconds || 0);
  if (cooldown > 0) {
    return failure ? `cooling down ${cooldown}s after ${failure}` : `cooling down ${cooldown}s`;
  }
  if (failure) {
    return `ready, previous issue: ${failure}`;
  }
  return info.available ? 'ready' : 'no recent health signal';
}

function modelStatusClass(info = {}) {
  if (Number(info.cooldown_remaining_seconds || 0) > 0 || info.available === false) {
    return 'warn';
  }
  if (info.last_failure || info.available !== true) {
    return 'watch';
  }
  return 'ok';
}

function renderModelSummary(data = {}) {
  const provider = data.provider_health || {};
  const names = data.models?.length ? data.models : Object.keys(provider);
  const counts = names.reduce((acc, name) => {
    const level = modelStatusClass(provider[name] || { available: null });
    acc[level] = (acc[level] || 0) + 1;
    return acc;
  }, { ok: 0, watch: 0, warn: 0 });
  elements.modelSummary.textContent = `Models: ${counts.ok || 0} ready / ${counts.watch || 0} watch / ${counts.warn || 0} down`;
  elements.modelSummary.className = counts.warn ? 'warn' : counts.watch ? 'watch' : 'ok';
}

function requestBody() {
  const tokens = elements.approval.checked ? ['tool_action_approved'] : [];
  return {
    query: elements.query.value.trim(),
    project: elements.project.value.trim() || 'ope-core',
    allow_search: elements.search.checked,
    allow_tools: elements.tools.checked,
    approval_tokens: tokens,
    budget: elements.budget.value,
    latency: elements.latency.value,
    mode: elements.mode.value,
  };
}

async function checkStatus() {
  try {
    const health = await fetch('/health').then((response) => response.json());
    setStatus(elements.health, 'Health', Boolean(health.ok));
  } catch (error) {
    setStatus(elements.health, 'Health', false);
  }

  try {
    const ready = await fetch('/ready').then((response) => response.json());
    setStatus(elements.ready, 'Ready', Boolean(ready.ok));
  } catch (error) {
    setStatus(elements.ready, 'Ready', false);
  }
}

async function submitAsk(event) {
  event.preventDefault();
  await sendCurrentPrompt();
}

async function sendCurrentPrompt() {
  const body = requestBody();
  if (!hasApiKey()) {
    setBusy('Need key');
    return;
  }
  if (!body.query) {
    setBusy('Need message');
    return;
  }

  setBusy('Routing...');
  renderMetrics([]);
  appendChatMessage('user', body.query);
  elements.query.value = '';
  const assistantMessageId = appendChatMessage('assistant', 'Thinking...', { status: 'pending' });

  try {
    const started = performance.now();
    const result = await api('/ask', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const elapsed = Math.round(performance.now() - started);
    renderMetrics([
      { label: 'route', value: result.route_plan?.route },
      { label: 'model', value: result.model_used },
      { label: 'latency', value: `${result.metadata?.latency_ms || elapsed} ms` },
      { label: 'tokens', value: result.metadata?.usage?.total_tokens },
      { label: 'est. cost', value: formatUsd(result.metadata?.estimated_cost_usd) },
      { label: 'memory', value: result.memory_used?.length || 0 },
    ]);
    updateChatMessage(assistantMessageId, {
      content: result.answer,
      status: 'complete',
      route: result.route_plan?.route,
      model: result.model_used,
      metadata: {
        ...(result.metadata || {}),
        latency_ms: result.metadata?.latency_ms || elapsed,
      },
    });
    addMessageCost(result.metadata || {});
    setBusy('Ready');
    loadEvents();
    loadModels();
  } catch (error) {
    updateChatMessage(assistantMessageId, {
      content: error.message,
      status: 'failed',
      role: 'system',
    });
    setBusy('Failed');
  }
}

function retryLastPrompt() {
  const message = lastUserMessage();
  if (!message) {
    setBusy('No prior prompt');
    return;
  }
  setComposerValue(message.content);
  $('askForm').requestSubmit();
}

async function previewPlan() {
  const body = requestBody();
  if (!hasApiKey()) {
    setBusy('Need key');
    return;
  }
  if (!body.query) {
    setBusy('Need message');
    return;
  }
  setBusy('Planning...');
  try {
    const plan = await api('/plan', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    appendChatMessage('system', JSON.stringify(plan, null, 2), {
      route: plan.route,
      model: plan.primary_model,
    });
    renderMetrics([
      { label: 'route', value: plan.route },
      { label: 'primary', value: plan.primary_model },
      { label: 'approval', value: plan.approval_required ? 'required' : 'not required' },
    ]);
    setBusy('Ready');
  } catch (error) {
    elements.answer.innerHTML = `<span class="error-text">${escapeHtml(error.message)}</span>`;
    setBusy('Failed');
  }
}

async function loadRoutes() {
  if (!requireApiKey(elements.routes)) return;
  try {
    const data = await api('/routes');
    populateRouteOptions(data.routes || defaultRouteOptions);
    elements.routes.innerHTML = data.routes.map((route) => `
      <details class="route-item">
        <summary>
          <strong>${escapeHtml(routeLabel(route.route))}</strong>
          <span>${escapeHtml(route.primary_model)}</span>
        </summary>
        <p>${route.search_enabled ? 'Search on' : 'Search off'} / ${route.tools_enabled ? 'tools capable' : 'no tools'}${route.verify ? ' / verify' : ''}</p>
        ${route.fallback_models.length ? `<small>Fallbacks: ${escapeHtml(route.fallback_models.join(', '))}</small>` : '<small>No fallbacks configured.</small>'}
      </details>
    `).join('');
  } catch (error) {
    renderEmpty(elements.routes, error.message);
  }
}

async function loadModels() {
  if (!requireApiKey(elements.models)) return;
  try {
    const data = await api('/models/status');
    renderModelSummary(data);
    const provider = data.provider_health || {};
    const names = data.models?.length ? data.models : Object.keys(provider);
    const rows = names.map((name) => {
      const info = provider[name] || { available: null };
      return `
      <div class="status-item ${modelStatusClass(info)}">
        <strong>${escapeHtml(name)}</strong>
        <span>${escapeHtml(modelStatusText(info))}</span>
      </div>
    `;
    });
    elements.models.innerHTML = rows.join('') || '<p class="empty">No provider health recorded yet.</p>';
  } catch (error) {
    elements.modelSummary.textContent = 'Models: check failed';
    elements.modelSummary.className = 'warn';
    renderEmpty(elements.models, error.message);
  }
}

async function loadEvents() {
  if (!requireApiKey(elements.events)) return;
  try {
    const project = encodeURIComponent(elements.project.value.trim() || 'ope-core');
    const data = await api(`/events/recent?project=${project}&limit=12`);
    const events = data.events || [];
    elements.events.innerHTML = events.map((event) => `
      <div class="row-item">
        <strong>${escapeHtml(event.query)}</strong>
        <span>${escapeHtml(event.selected_route || event.query_type || 'route?')} / ${escapeHtml(event.selected_model || 'model?')} / ${event.latency_ms || '?'} ms / ${event.success ? 'ok' : 'failed'}</span>
      </div>
    `).join('');
    if (!events.length) renderEmpty(elements.events);
  } catch (error) {
    renderEmpty(elements.events, error.message);
  }
}

async function searchMemory(event) {
  event.preventDefault();
  if (!requireApiKey(elements.memory)) return;
  const query = $('memoryQueryInput').value.trim();
  if (!query) return;
  try {
    const data = await api('/memory/search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        project: elements.project.value.trim() || 'ope-core',
        limit: 10,
      }),
    });
    const memories = data.memories || [];
    elements.memory.innerHTML = memories.map((memory) => `
      <div class="row-item">
        <strong>${escapeHtml(memory.summary)}</strong>
        <span>${escapeHtml(memory.memory_type)} / ${escapeHtml((memory.tags || []).join(', '))}</span>
      </div>
    `).join('');
    if (!memories.length) renderEmpty(elements.memory);
  } catch (error) {
    renderEmpty(elements.memory, error.message);
  }
}

async function writeMemory(event) {
  event.preventDefault();
  if (!requireApiKey(elements.memory)) return;
  const summary = $('memorySummaryInput').value.trim();
  if (!summary) return;
  try {
    const memory = await api('/memory/write', {
      method: 'POST',
      body: JSON.stringify({
        summary,
        project: elements.project.value.trim() || 'ope-core',
        memory_type: 'operator_note',
        tags: ['ui'],
        source: 'ui',
      }),
    });
    $('memorySummaryInput').value = '';
    elements.memory.innerHTML = `
      <div class="row-item">
        <strong>${escapeHtml(memory.summary)}</strong>
        <span>saved as ${escapeHtml(memory.memory_type)}</span>
      </div>
    `;
  } catch (error) {
    renderEmpty(elements.memory, error.message);
  }
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function suggestUploadCategory() {
  const file = elements.uploadFile.files?.[0];
  if (!file || !hasApiKey()) {
    elements.uploadSuggestion.textContent = 'Pick a file and O.P.E. will suggest where it belongs.';
    return;
  }
  try {
    const data = await api(
      `/uploads/suggest?filename=${encodeURIComponent(file.name)}&content_type=${encodeURIComponent(file.type || '')}`
    );
    elements.uploadSuggestion.textContent = `Suggestion: ${data.category} (${Math.round((data.confidence || 0) * 100)}%)`;
    if (!elements.uploadCategory.value && data.confidence >= 0.75) {
      elements.uploadCategory.value = data.category;
    }
  } catch (error) {
    elements.uploadSuggestion.textContent = error.message;
  }
}

async function uploadLocalFile(event) {
  event.preventDefault();
  if (!requireApiKey(elements.uploads)) return;
  const file = elements.uploadFile.files?.[0];
  if (!file) {
    elements.uploadSuggestion.textContent = 'Choose a file first.';
    return;
  }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('project', elements.project.value.trim() || 'ope-core');
  if (elements.uploadCategory.value) formData.append('category', elements.uploadCategory.value);
  if (elements.uploadDescription.value.trim()) formData.append('description', elements.uploadDescription.value.trim());
  try {
    setBusy('Uploading');
    const upload = await apiForm('/uploads', formData);
    elements.uploadSuggestion.textContent = `Saved to ${upload.relative_path}`;
    elements.uploadFile.value = '';
    elements.uploadDescription.value = '';
    elements.uploadCategory.value = '';
    await loadUploads();
    setBusy('Uploaded');
  } catch (error) {
    elements.uploadSuggestion.textContent = error.message;
    setBusy('Failed');
  }
}

async function loadUploads() {
  if (!requireApiKey(elements.uploads)) return;
  try {
    const project = encodeURIComponent(elements.project.value.trim() || 'ope-core');
    const data = await api(`/uploads?project=${project}&limit=20`);
    const uploads = data.uploads || [];
    elements.uploads.innerHTML = uploads.map((upload) => `
      <div class="row-item upload-item">
        <strong>${escapeHtml(upload.original_filename)} <span>${escapeHtml(upload.category)}</span></strong>
        <span>${escapeHtml(upload.relative_path)} / ${escapeHtml(formatBytes(upload.size_bytes))}</span>
        <small>${escapeHtml(upload.description || `suggested ${upload.suggested_category} (${Math.round((upload.confidence || 0) * 100)}%)`)}</small>
      </div>
    `).join('');
    if (!uploads.length) renderEmpty(elements.uploads, 'No uploads yet.');
  } catch (error) {
    renderEmpty(elements.uploads, error.message);
  }
}

async function loadTools() {
  if (!requireApiKey(elements.toolsPanel)) return;
  try {
    const project = encodeURIComponent(elements.project.value.trim() || 'ope-core');
    const [stats, jobs] = await Promise.all([
      api(`/tools/queue/stats?project=${project}`),
      api(`/tools/jobs?project=${project}&limit=10`),
    ]);
    const jobRows = (jobs.jobs || []).map((job) => `
      <div class="row-item">
        <strong>${escapeHtml(job.tool_name)}: ${escapeHtml(job.action)}</strong>
        <span>${escapeHtml(job.status)} / ${escapeHtml(job.id)}</span>
      </div>
    `).join('');
    elements.toolsPanel.innerHTML = `
      <div class="row-item">
        <strong>${stats.total || 0} queued jobs</strong>
        <span>${escapeHtml(JSON.stringify(stats.by_status || {}))}</span>
      </div>
      ${jobRows}
    `;
  } catch (error) {
    renderEmpty(elements.toolsPanel, error.message);
  }
}

function approvalStatuses() {
  return {
    pending: ['pending_review'],
    running: ['approved', 'running'],
    done: ['succeeded'],
    failed: ['failed', 'cancelled'],
  }[approvalFilter] || ['pending_review'];
}

function jobConnector(job = {}) {
  return String(job.tool_name || '').startsWith('connector:')
    ? job.tool_name.split(':')[1]
    : job.tool_name || 'tool';
}

function jobRisk(job = {}) {
  const result = job.result?.result || job.result || {};
  const externalSideEffect = result.external_side_effect ?? result.draft?.external_side_effect;
  if (externalSideEffect === false || String(job.action || '').startsWith('draft_')) return 'local draft';
  if (job.status === 'pending_review') return 'needs approval';
  return 'read/action';
}

function compactJson(value, max = 360) {
  const text = JSON.stringify(value || {}, null, 2);
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function jobResultText(job = {}) {
  if (job.error) return job.error;
  if (!job.result) return '';
  return compactJson(job.result, 900);
}

function draftFromJob(job = {}) {
  return job.result?.result?.draft || job.result?.draft || null;
}

function renderQueueStats(stats = {}) {
  const byStatus = stats.by_status || {};
  const cells = [
    ['Pending', byStatus.pending_review || 0],
    ['Approved', byStatus.approved || 0],
    ['Running', stats.running || byStatus.running || 0],
    ['Done', byStatus.succeeded || 0],
    ['Failed', (byStatus.failed || 0) + (byStatus.cancelled || 0)],
  ];
  elements.approvalStats.innerHTML = cells.map(([label, value]) => `
    <div>
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
    </div>
  `).join('');
}

function renderDraftResult(draft = {}) {
  const title = draft.title || draft.subject || 'Untitled draft';
  const target = compactJson(draft.target || {}, 220);
  const nextSteps = Array.isArray(draft.next_steps) ? draft.next_steps : [];
  return `
    <div class="draft-result">
      <strong>${escapeHtml(title)}</strong>
      <small>${escapeHtml(draft.connector || 'connector')} / ${escapeHtml(draft.draft_type || 'draft')} / external side effect: false</small>
      <label>Target</label>
      <pre>${escapeHtml(target)}</pre>
      <label>Body</label>
      <pre>${escapeHtml(draft.body || '')}</pre>
      ${nextSteps.length ? `<label>Next</label><ul>${nextSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join('')}</ul>` : ''}
    </div>
  `;
}

function renderApprovalActions(job = {}) {
  const buttons = [];
  if (job.status === 'pending_review') {
    buttons.push(`<button class="mini-button" type="button" data-approve-job="${escapeHtml(job.id)}">Approve</button>`);
    buttons.push(`<button class="mini-button" type="button" data-reject-job="${escapeHtml(job.id)}">Reject</button>`);
  }
  if (job.status === 'failed' || job.status === 'cancelled') {
    buttons.push(`<button class="mini-button" type="button" data-retry-job="${escapeHtml(job.id)}">Retry</button>`);
  }
  if (draftFromJob(job)) {
    buttons.push(`<button class="mini-button" type="button" data-copy-draft="${escapeHtml(job.id)}">Copy draft</button>`);
  }
  if (job.result || job.error) {
    buttons.push(`<button class="mini-button" type="button" data-copy-job="${escapeHtml(job.id)}">Copy result</button>`);
  }
  return buttons.join('');
}

function renderApprovalJobs(jobs = []) {
  approvalJobsById = new Map(jobs.map((job) => [job.id, job]));
  if (!jobs.length) {
    renderEmpty(elements.approvals, 'No jobs in this lane.');
    return;
  }
  elements.approvals.innerHTML = jobs.map((job) => {
    const resultText = jobResultText(job);
    const draft = draftFromJob(job);
    return `
      <details class="approval-item ${escapeHtml(job.status)}" data-job-row="${escapeHtml(job.id)}">
        <summary>
          <span>
            <strong>${escapeHtml(jobConnector(job))} / ${escapeHtml(job.action)}</strong>
            <small>${escapeHtml(job.status)} / ${escapeHtml(jobRisk(job))}${job.created_at ? ` / ${escapeHtml(job.created_at)}` : ''}</small>
          </span>
          <span class="approval-actions">${renderApprovalActions(job)}</span>
        </summary>
        <div class="approval-body">
          <label>Payload</label>
          <pre>${escapeHtml(compactJson(job.payload))}</pre>
          ${draft ? renderDraftResult(draft) : ''}
          ${resultText && !draft ? `<label>${job.error ? 'Error' : 'Result'}</label><pre>${escapeHtml(resultText)}</pre>` : ''}
        </div>
      </details>
    `;
  }).join('');
}

async function loadApprovals() {
  if (!requireApiKey(elements.approvals)) return;
  try {
    const project = encodeURIComponent(elements.project.value.trim() || 'ope-core');
    const connectorPrefix = encodeURIComponent('connector:');
    const [stats, responses] = await Promise.all([
      api(`/tools/queue/stats?project=${project}&tool_name_prefix=${connectorPrefix}`),
      Promise.all(approvalStatuses().map(
        (status) => api(`/tools/jobs?project=${project}&status=${status}&tool_name_prefix=${connectorPrefix}&limit=25`)
      )),
    ]);
    renderQueueStats(stats);
    const jobs = responses.flatMap((data) => data.jobs || [])
      .filter((job) => String(job.tool_name || '').startsWith('connector:'))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
    renderApprovalJobs(jobs);
  } catch (error) {
    renderEmpty(elements.approvals, error.message);
  }
}

async function patchJob(jobId, body, busyLabel) {
  setBusy(busyLabel);
  try {
    await api(`/tools/jobs/${encodeURIComponent(jobId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    await Promise.allSettled([loadApprovals(), loadTools()]);
    setBusy('Ready');
    return true;
  } catch (error) {
    setBusy('Failed');
    renderEmpty(elements.approvals, error.message);
    return false;
  }
}

function watchApprovals() {
  window.clearTimeout(approvalPollTimer);
  approvalPollTimer = window.setTimeout(() => {
    loadApprovals();
    approvalPollTimer = window.setTimeout(loadApprovals, 2500);
  }, 900);
}

function setApprovalFilter(nextFilter) {
  approvalFilter = nextFilter;
  document.querySelectorAll('[data-approval-filter]').forEach((button) => {
    button.classList.toggle('active', button.dataset.approvalFilter === approvalFilter);
  });
  loadApprovals();
}

async function copyJobResult(jobId) {
  const job = approvalJobsById.get(jobId);
  const text = job ? compactJson(job.result || { error: job.error }, 2000) : '';
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    setBusy('Copied');
  } catch (error) {
    setBusy('Copy failed');
  }
}

async function copyDraftBody(jobId) {
  const draft = draftFromJob(approvalJobsById.get(jobId));
  const text = draft ? [draft.title || draft.subject, draft.body].filter(Boolean).join('\n\n') : '';
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    setBusy('Copied');
  } catch (error) {
    setBusy('Copy failed');
  }
}

function selectedDraftSpec() {
  return draftActionSpecs[elements.draftAction.value] || draftActionSpecs['github:draft_issue'];
}

function draftFormValues() {
  return {
    target: elements.draftTarget.value.trim(),
    title: elements.draftTitle.value.trim(),
    body: elements.draftBody.value.trim(),
  };
}

function buildDraftPayload() {
  const spec = selectedDraftSpec();
  const values = draftFormValues();
  if (!values.title) throw new Error('Add a title or subject.');
  if (!values.body) throw new Error('Add draft body content.');
  return spec.buildPayload(values);
}

function updateDraftFormLabels() {
  const spec = selectedDraftSpec();
  elements.draftTargetLabel.textContent = spec.targetLabel;
  elements.draftTarget.placeholder = spec.targetPlaceholder;
  elements.draftTitleLabel.textContent = spec.titleLabel;
  elements.draftTitle.placeholder = spec.titlePlaceholder;
  elements.draftBodyLabel.textContent = spec.bodyLabel;
  elements.draftBody.placeholder = spec.bodyPlaceholder;
  updateDraftPayloadPreview();
}

function updateDraftPayloadPreview() {
  try {
    elements.draftPayloadPreview.textContent = compactJson(buildDraftPayload(), 900);
    elements.draftJobStatus.textContent = 'Ready to queue for approval.';
    elements.draftJobStatus.classList.remove('error-text');
  } catch (error) {
    elements.draftPayloadPreview.textContent = compactJson({ pending: error.message }, 900);
  }
}

function fillDraftExample() {
  const spec = selectedDraftSpec();
  elements.draftTarget.value = spec.example.target;
  elements.draftTitle.value = spec.example.title;
  elements.draftBody.value = spec.example.body;
  updateDraftPayloadPreview();
}

async function queueDraftJob(event) {
  event.preventDefault();
  if (!hasApiKey()) {
    elements.draftJobStatus.textContent = 'Enter your OPE API key first.';
    elements.draftJobStatus.classList.add('error-text');
    return;
  }
  const spec = selectedDraftSpec();
  try {
    const payload = buildDraftPayload();
    setBusy('Queueing');
    const job = await api(`/connectors/${encodeURIComponent(spec.connector)}/jobs`, {
      method: 'POST',
      body: JSON.stringify({
        project: elements.project.value.trim() || 'ope-core',
        action: spec.action,
        payload,
        requested_by: elements.draftRequestedBy.value.trim() || 'operator',
      }),
    });
    elements.draftJobStatus.textContent = `Queued ${job.id} for approval.`;
    elements.draftJobStatus.classList.remove('error-text');
    setApprovalFilter('pending');
    activateOperationsTab('approvals');
    await Promise.allSettled([loadApprovals(), loadTools()]);
    setBusy('Queued');
  } catch (error) {
    elements.draftJobStatus.textContent = error.message;
    elements.draftJobStatus.classList.add('error-text');
    setBusy('Failed');
  }
}

function connectorStatusClass(status) {
  if (status === 'configured') return 'ok';
  if (status === 'disabled') return 'warn';
  return 'watch';
}

async function loadConnectors() {
  if (!requireApiKey(elements.connectors)) return;
  try {
    const data = await api('/connectors');
    const connectors = data.connectors || [];
    elements.connectors.innerHTML = connectors.map((connector) => {
      const actions = (connector.actions || []).map((action) => (
        `${action.name} (${action.kind || (action.read_only ? 'read' : 'write')}${action.external_write ? ', external' : ''})`
      )).join(', ');
      return `
        <div class="row-item connector-item ${connectorStatusClass(connector.status)}">
          <strong>${escapeHtml(connector.name)} <span>${escapeHtml(connector.status)}</span></strong>
          <span>${escapeHtml(connector.auth_type)} / ${escapeHtml(connector.scopes.join(', '))}</span>
          <small>${escapeHtml(actions || 'No actions registered.')}</small>
          <small>${escapeHtml(connector.notes)}</small>
        </div>
      `;
    }).join('');
    if (!connectors.length) renderEmpty(elements.connectors);
  } catch (error) {
    renderEmpty(elements.connectors, error.message);
  }
}

function wireTabs() {
  document.querySelectorAll('.tab-button').forEach((button) => {
    button.addEventListener('click', () => activateOperationsTab(button.dataset.tab));
  });
}

function activateOperationsTab(tabName) {
  const targetTab = $(`${tabName}Tab`);
  const targetButton = document.querySelector(`[data-tab="${tabName}"]`);
  if (!targetTab || !targetButton) return;
  document.querySelectorAll('.tab-button').forEach((item) => item.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach((item) => item.classList.remove('active'));
  targetButton.classList.add('active');
  targetTab.classList.add('active');
}

async function refreshAll() {
  await checkStatus();
  if (!hasApiKey()) {
    populateRouteOptions();
    elements.modelSummary.textContent = 'Models: key needed';
    elements.modelSummary.className = 'watch';
    elements.approvalStats.innerHTML = '';
    renderEmpty(elements.routes, 'Enter your OPE API key to load routes.');
    renderEmpty(elements.models, 'Enter your OPE API key to load models.');
    renderEmpty(elements.events, 'Enter your OPE API key to load events.');
    renderEmpty(elements.approvals, 'Enter your OPE API key to load approvals.');
    renderEmpty(elements.uploads, 'Enter your OPE API key to load uploads.');
    renderEmpty(elements.connectors, 'Enter your OPE API key to load connectors.');
    renderEmpty(elements.toolsPanel, 'Enter your OPE API key to load tools.');
    return;
  }
  await Promise.allSettled([loadRoutes(), loadModels(), loadEvents(), loadApprovals(), loadUploads(), loadConnectors(), loadTools()]);
}

function autosizeComposer() {
  elements.query.style.height = 'auto';
  elements.query.style.height = `${Math.min(elements.query.scrollHeight, 220)}px`;
}

function fillPrompt(prompt) {
  setComposerValue(prompt);
}

async function copyMessage(id) {
  const message = state.chatMessages.find((item) => item.id === id);
  if (!message) return;
  try {
    await navigator.clipboard.writeText(message.content);
    setBusy('Copied');
  } catch (error) {
    setBusy('Copy failed');
  }
}

$('askForm').addEventListener('submit', submitAsk);
$('retryButton').addEventListener('click', retryLastPrompt);
$('planButton').addEventListener('click', previewPlan);
$('refreshButton').addEventListener('click', refreshAll);
$('routesButton').addEventListener('click', loadRoutes);
$('modelsButton').addEventListener('click', loadModels);
$('eventsButton').addEventListener('click', loadEvents);
$('approvalsButton').addEventListener('click', loadApprovals);
$('connectorsButton').addEventListener('click', loadConnectors);
$('toolsButton').addEventListener('click', loadTools);
$('memorySearchForm').addEventListener('submit', searchMemory);
$('memoryWriteForm').addEventListener('submit', writeMemory);
elements.uploadForm.addEventListener('submit', uploadLocalFile);
elements.uploadFile.addEventListener('change', suggestUploadCategory);
$('uploadsButton').addEventListener('click', loadUploads);
elements.draftJobForm.addEventListener('submit', queueDraftJob);
$('draftExampleButton').addEventListener('click', fillDraftExample);
$('resetCostButton').addEventListener('click', resetSessionCost);
$('clearChatButton').addEventListener('click', clearChatMessages);
$('exportChatButton').addEventListener('click', exportChat);
$('forgetKeyButton').addEventListener('click', forgetApiKey);
$('newChatButton').addEventListener('click', newChatSession);
$('deleteChatButton').addEventListener('click', deleteCurrentSession);
elements.sessions.addEventListener('click', (event) => {
  const sessionButton = event.target.closest('[data-session-id]');
  if (sessionButton) switchSession(sessionButton.dataset.sessionId);
});
elements.approvals.addEventListener('click', (event) => {
  const approveButton = event.target.closest('[data-approve-job]');
  const rejectButton = event.target.closest('[data-reject-job]');
  const retryButton = event.target.closest('[data-retry-job]');
  const copyDraftButton = event.target.closest('[data-copy-draft]');
  const copyButton = event.target.closest('[data-copy-job]');
  if (approveButton) {
    event.preventDefault();
    patchJob(approveButton.dataset.approveJob, { status: 'approved', approved_by: 'operator' }, 'Approved')
      .then((ok) => {
        if (!ok) return;
        setApprovalFilter('running');
        watchApprovals();
      });
  }
  if (rejectButton) {
    event.preventDefault();
    patchJob(rejectButton.dataset.rejectJob, { status: 'cancelled', approved_by: 'operator', error: 'Rejected by operator' }, 'Rejected');
  }
  if (retryButton) {
    event.preventDefault();
    patchJob(
      retryButton.dataset.retryJob,
      { status: 'approved', approved_by: 'operator', clear_result: true, clear_error: true },
      'Retrying'
    ).then((ok) => {
      if (!ok) return;
      setApprovalFilter('running');
      watchApprovals();
    });
  }
  if (copyDraftButton) {
    event.preventDefault();
    copyDraftBody(copyDraftButton.dataset.copyDraft);
  }
  if (copyButton) {
    event.preventDefault();
    copyJobResult(copyButton.dataset.copyJob);
  }
});
elements.answer.addEventListener('click', (event) => {
  const copyButton = event.target.closest('[data-copy-message]');
  if (copyButton) copyMessage(copyButton.dataset.copyMessage);
  const useButton = event.target.closest('[data-use-message]');
  if (useButton) {
    const message = state.chatMessages.find((item) => item.id === useButton.dataset.useMessage);
    if (message) setComposerValue(message.content);
  }
});
document.querySelectorAll('[data-prompt]').forEach((button) => {
  button.addEventListener('click', () => fillPrompt(button.dataset.prompt));
});
document.querySelectorAll('[data-approval-filter]').forEach((button) => {
  button.addEventListener('click', () => setApprovalFilter(button.dataset.approvalFilter));
});
elements.draftAction.addEventListener('change', updateDraftFormLabels);
[elements.draftTarget, elements.draftTitle, elements.draftBody].forEach((input) => {
  input.addEventListener('input', updateDraftPayloadPreview);
});
elements.query.addEventListener('input', autosizeComposer);
elements.query.addEventListener('keydown', (event) => {
  const desktopSend = window.matchMedia('(min-width: 700px)').matches;
  if (desktopSend && event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $('askForm').requestSubmit();
  }
});
elements.apiKey.addEventListener('input', persistApiKey);
elements.apiKey.addEventListener('change', refreshAll);
elements.mode.addEventListener('change', () => {
  state.mode = elements.mode.value || 'auto';
  localStorage.setItem('ope.mode', elements.mode.value || 'auto');
  renderRequestPreview();
});
elements.project.addEventListener('change', () => {
  localStorage.setItem('ope.project', elements.project.value.trim() || 'ope-core');
  refreshAll();
});
[elements.budget, elements.latency, elements.search, elements.tools, elements.approval].forEach((control) => {
  control.addEventListener('change', renderRequestPreview);
});

wireTabs();
populateRouteOptions();
renderRequestPreview();
autosizeComposer();
renderCost();
renderChat();
renderSessionList();
updateDraftFormLabels();
refreshAll();
