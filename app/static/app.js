const state = {
  apiKey: localStorage.getItem('ope.apiKey') || '',
  project: localStorage.getItem('ope.project') || 'ope-core',
  mode: localStorage.getItem('ope.mode') || 'auto',
  sessionTotals: JSON.parse(sessionStorage.getItem('ope.sessionTotals') || 'null') || {
    messages: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
  },
  chatMessages: JSON.parse(sessionStorage.getItem('ope.chatMessages') || '[]'),
};

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
  answer: $('answerOutput'),
  answerMetrics: $('answerMetrics'),
  messageCost: $('messageCost'),
  messageTokens: $('messageTokens'),
  sessionCost: $('sessionCost'),
  sessionTokens: $('sessionTokens'),
  health: $('healthStatus'),
  ready: $('readyStatus'),
  routes: $('routePanel'),
  models: $('modelsPanel'),
  events: $('eventsPanel'),
  memory: $('memoryPanel'),
  toolsPanel: $('toolsPanel'),
};

elements.apiKey.value = state.apiKey;
elements.project.value = state.project;
elements.mode.value = state.mode;

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

function saveChatMessages() {
  sessionStorage.setItem('ope.chatMessages', JSON.stringify(state.chatMessages));
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
    elements.answer.innerHTML = '<p class="empty chat-empty">Ask something to start.</p>';
    return;
  }
  elements.answer.innerHTML = state.chatMessages.map((message) => {
    const meta = chatMessageMeta(message);
    return `
      <article class="chat-message ${escapeHtml(message.role)} ${message.status === 'pending' ? 'pending' : ''}">
        <div class="chat-message-head">
          <strong>${message.role === 'user' ? 'You' : message.role === 'system' ? 'System' : 'O.P.E.'}</strong>
          ${meta ? `<span>${escapeHtml(meta)}</span>` : ''}
        </div>
        <div class="chat-message-body">${escapeHtml(message.content)}</div>
      </article>
    `;
  }).join('');
  elements.answer.scrollTop = elements.answer.scrollHeight;
}

function appendChatMessage(role, content, extras = {}) {
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
  sessionStorage.setItem('ope.sessionTotals', JSON.stringify(state.sessionTotals));
  renderCost(metadata);
}

function resetSessionCost() {
  state.sessionTotals = {
    messages: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
  };
  sessionStorage.setItem('ope.sessionTotals', JSON.stringify(state.sessionTotals));
  renderCost();
}

function routeLabel(value) {
  return String(value || '')
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
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

function wireTabs() {
  document.querySelectorAll('.tab-button').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.tab-button').forEach((item) => item.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      $(`${button.dataset.tab}Tab`).classList.add('active');
    });
  });
}

async function refreshAll() {
  await checkStatus();
  if (!hasApiKey()) {
    renderEmpty(elements.routes, 'Enter your OPE API key to load routes.');
    renderEmpty(elements.models, 'Enter your OPE API key to load models.');
    renderEmpty(elements.events, 'Enter your OPE API key to load events.');
    renderEmpty(elements.toolsPanel, 'Enter your OPE API key to load tools.');
    return;
  }
  await Promise.allSettled([loadRoutes(), loadModels(), loadEvents(), loadTools()]);
}

$('askForm').addEventListener('submit', submitAsk);
$('planButton').addEventListener('click', previewPlan);
$('refreshButton').addEventListener('click', refreshAll);
$('routesButton').addEventListener('click', loadRoutes);
$('modelsButton').addEventListener('click', loadModels);
$('eventsButton').addEventListener('click', loadEvents);
$('toolsButton').addEventListener('click', loadTools);
$('memorySearchForm').addEventListener('submit', searchMemory);
$('memoryWriteForm').addEventListener('submit', writeMemory);
$('resetCostButton').addEventListener('click', resetSessionCost);
$('clearChatButton').addEventListener('click', clearChatMessages);
$('forgetKeyButton').addEventListener('click', forgetApiKey);
elements.apiKey.addEventListener('input', persistApiKey);
elements.apiKey.addEventListener('change', refreshAll);
elements.mode.addEventListener('change', () => {
  localStorage.setItem('ope.mode', elements.mode.value || 'auto');
});
elements.project.addEventListener('change', () => {
  localStorage.setItem('ope.project', elements.project.value.trim() || 'ope-core');
  refreshAll();
});

wireTabs();
renderCost();
renderChat();
refreshAll();
