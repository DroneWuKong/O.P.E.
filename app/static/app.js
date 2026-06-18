const state = {
  apiKey: localStorage.getItem('ope.apiKey') || '',
  project: localStorage.getItem('ope.project') || 'ope-core',
  sessionTotals: JSON.parse(sessionStorage.getItem('ope.sessionTotals') || 'null') || {
    messages: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
  },
};

const $ = (id) => document.getElementById(id);

const elements = {
  apiKey: $('apiKeyInput'),
  project: $('projectInput'),
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
    elements.answer.textContent = 'Enter your OPE API key first.';
    return;
  }
  if (!body.query) {
    elements.answer.textContent = 'Give O.P.E. a prompt first.';
    return;
  }

  setBusy('Routing...');
  elements.answer.textContent = 'Thinking...';
  renderMetrics([]);

  try {
    const started = performance.now();
    const result = await api('/ask', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const elapsed = Math.round(performance.now() - started);
    elements.answer.textContent = result.answer;
    renderMetrics([
      { label: 'route', value: result.route_plan?.route },
      { label: 'model', value: result.model_used },
      { label: 'latency', value: `${result.metadata?.latency_ms || elapsed} ms` },
      { label: 'tokens', value: result.metadata?.usage?.total_tokens },
      { label: 'est. cost', value: formatUsd(result.metadata?.estimated_cost_usd) },
      { label: 'memory', value: result.memory_used?.length || 0 },
    ]);
    addMessageCost(result.metadata || {});
    setBusy('Ready');
    loadEvents();
    loadModels();
  } catch (error) {
    elements.answer.innerHTML = `<span class="error-text">${escapeHtml(error.message)}</span>`;
    setBusy('Failed');
  }
}

async function previewPlan() {
  const body = requestBody();
  if (!hasApiKey()) {
    elements.answer.textContent = 'Enter your OPE API key first.';
    return;
  }
  if (!body.query) {
    elements.answer.textContent = 'Give O.P.E. a prompt first.';
    return;
  }
  setBusy('Planning...');
  try {
    const plan = await api('/plan', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    elements.answer.textContent = JSON.stringify(plan, null, 2);
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
      <div class="route-item">
        <strong>${escapeHtml(route.route)}</strong>
        <span>${escapeHtml(route.primary_model)}${route.fallback_models.length ? ` / ${escapeHtml(route.fallback_models.join(', '))}` : ''}</span>
      </div>
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
    const rows = Object.entries(provider).map(([name, info]) => `
      <div class="status-item">
        <strong>${escapeHtml(name)}</strong>
        <span>${info.available ? 'available' : `cooldown ${info.cooldown_remaining_seconds || 0}s`} ${info.last_failure ? `- ${escapeHtml(info.last_failure)}` : ''}</span>
      </div>
    `);
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
$('forgetKeyButton').addEventListener('click', forgetApiKey);
elements.apiKey.addEventListener('input', persistApiKey);
elements.apiKey.addEventListener('change', refreshAll);

wireTabs();
renderCost();
refreshAll();
