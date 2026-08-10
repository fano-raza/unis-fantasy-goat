const $ = (id) => document.getElementById(id);

let chart;
let meta = null;

function selectedFromCheckboxes(containerId) {
  const root = $(containerId);
  if (!root) return null;
  const vals = [...root.querySelectorAll('input[type="checkbox"]:checked')].map((x) => x.value);
  return vals.length ? vals : null;
}

function selectedInts(containerId) {
  const vals = selectedFromCheckboxes(containerId);
  if (!vals) return null;
  const out = vals.map((x) => Number(x)).filter((x) => !Number.isNaN(x));
  return out.length ? out : null;
}

function updateSummary(summaryId, selected, noun) {
  const el = $(summaryId);
  if (!el) return;
  if (!selected || !selected.length) {
    el.textContent = `Select ${noun}`;
    return;
  }
  if (selected.length <= 3) {
    el.textContent = selected.join(', ');
  } else {
    el.textContent = `${selected.length} selected`;
  }
}

function renderMulti(containerId, summaryId, values, noun) {
  const root = $(containerId);
  if (!root) return;
  root.innerHTML = values
    .map(
      (v) =>
        `<label><input type="checkbox" value="${String(v)}" /> <span>${String(v)}</span></label>`
    )
    .join('');

  root.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener('change', () => {
      updateSummary(summaryId, selectedFromCheckboxes(containerId), noun);
    });
  });

  updateSummary(summaryId, null, noun);
}

function setAllInMulti(containerId, summaryId, noun, checked) {
  const root = $(containerId);
  if (!root) return;
  root.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = checked;
  });
  updateSummary(summaryId, selectedFromCheckboxes(containerId), noun);
}

function populateMetricSelect(metrics) {
  const select = $('metric');
  const entries = Object.entries(metrics || {});
  select.innerHTML = entries
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, label]) => `<option value="${key}">${label} (${key})</option>`)
    .join('');

  if (metrics.PTS) {
    select.value = 'PTS';
  }
}

async function loadMeta() {
  const res = await fetch('/meta');
  if (!res.ok) {
    throw new Error(`Failed loading /meta (${res.status})`);
  }
  meta = await res.json();

  populateMetricSelect(meta.metrics);
  renderMulti('groupByOptions', 'groupBySummary', ['Team', 'Opp', 'Year', 'Week', 'Season'], 'group by');
  const defaultGroupBy = $('groupByOptions')?.querySelector('input[type="checkbox"][value="Team"]');
  if (defaultGroupBy) {
    defaultGroupBy.checked = true;
    updateSummary('groupBySummary', ['Team'], 'group by');
  }
  renderMulti('yearsOptions', 'yearsSummary', meta.years || [], 'years');
  renderMulti('weeksOptions', 'weeksSummary', meta.weeks || [], 'weeks');
  renderMulti('teamsOptions', 'teamsSummary', meta.teams || [], 'teams');
  renderMulti('oppsOptions', 'oppsSummary', meta.opponents || [], 'opponents');
}

function buildPayload() {
  const seasons = $('seasons').value;
  const groupBy = selectedFromCheckboxes('groupByOptions') || ['Team'];
  return {
    metric: $('metric').value.trim(),
    aggregation: $('aggregation').value,
    group_by: groupBy,
    years: selectedInts('yearsOptions'),
    weeks: selectedInts('weeksOptions'),
    teams: selectedFromCheckboxes('teamsOptions'),
    opponents: selectedFromCheckboxes('oppsOptions'),
    seasons: seasons ? [seasons] : null,
    count_only: true,
    sort_desc: true,
    limit: Number($('limit').value || 25),
  };
}

function renderTable(rows) {
  if (!rows || !rows.length) {
    $('tableWrap').textContent = 'No rows returned.';
    return;
  }

  const cols = Object.keys(rows[0]);
  const head = `<tr>${cols.map((c) => `<th>${c}</th>`).join('')}</tr>`;
  const body = rows
    .map((r) => `<tr>${cols.map((c) => `<td>${r[c]}</td>`).join('')}</tr>`)
    .join('');
  $('tableWrap').innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

$('runQuery').addEventListener('click', async () => {
  $('status').textContent = 'Running table query...';
  try {
    const payload = buildPayload();
    const data = await postJson('/query', payload);
    renderTable(data.rows);
    $('status').textContent = `Returned ${data.row_count} rows.`;
    $('status').className = 'ok';
  } catch (e) {
    $('status').textContent = e.message;
    $('status').className = 'err';
  }
});

$('runTs').addEventListener('click', async () => {
  $('status').textContent = 'Running time series query...';
  try {
    const base = buildPayload();
    const payload = {
      metric: base.metric,
      aggregation: ['avg', 'sum'].includes(base.aggregation) ? base.aggregation : 'sum',
      group_by: 'Week',
      years: base.years,
      weeks: base.weeks,
      teams: base.teams,
      opponents: base.opponents,
      seasons: base.seasons,
      count_only: true,
    };
    const data = await postJson('/timeseries', payload);
    const labels = data.rows.map((r) => r.Week ?? r.Year);
    const values = data.rows.map((r) => r.value);

    if (chart) chart.destroy();
    chart = new Chart($('trend'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: `${payload.metric} (${payload.aggregation})`,
            data: values,
            borderColor: '#0f6fff',
            tension: 0.2,
          },
        ],
      },
      options: { responsive: true, maintainAspectRatio: true },
    });
    $('status').textContent = `Trend points: ${data.row_count}.`;
    $('status').className = 'ok';
  } catch (e) {
    $('status').textContent = e.message;
    $('status').className = 'err';
  }
});

$('runSwap').addEventListener('click', async () => {
  $('status').textContent = 'Running schedule-swap query...';
  try {
    const base = buildPayload();
    const payload = {
      years: base.years,
      weeks: base.weeks,
      teams: base.teams,
      seasons: base.seasons,
      limit: base.limit,
    };
    const data = await postJson('/schedule_swap', payload);
    renderTable(data.rows);
    $('status').textContent = `Schedule swap rows: ${data.row_count}.`;
    $('status').className = 'ok';
  } catch (e) {
    $('status').textContent = e.message;
    $('status').className = 'err';
  }
});

(async function init() {
  $('status').textContent = 'Loading metadata...';
  try {
    await loadMeta();
    // Years actions
    $('yearsSelectAll')?.addEventListener('click', () =>
      setAllInMulti('yearsOptions', 'yearsSummary', 'years', true)
    );
    $('yearsClear')?.addEventListener('click', () =>
      setAllInMulti('yearsOptions', 'yearsSummary', 'years', false)
    );

    // Teams actions
    $('teamsSelectAll')?.addEventListener('click', () =>
      setAllInMulti('teamsOptions', 'teamsSummary', 'teams', true)
    );
    $('teamsClear')?.addEventListener('click', () =>
      setAllInMulti('teamsOptions', 'teamsSummary', 'teams', false)
    );

    $('status').textContent = 'Ready.';
    $('status').className = 'ok';
  } catch (e) {
    $('status').textContent = `Failed to load metadata: ${e.message}`;
    $('status').className = 'err';
  }
})();
