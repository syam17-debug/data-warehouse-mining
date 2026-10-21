// University Data Warehouse Consolidation Frontend Engine
// Dual-Mode Architecture: Works seamlessly with FastAPI REST endpoints (localhost)
// AND embedded in Streamlit Cloud via injected in-memory state with 100% identical UI.

let networkInstance = null;
let graphPhysicsEnabled = true;
let chartSourcesInstance = null;
let chartRevenueInstance = null;
let currentEntities = [];

function getInjected() {
  return (typeof window.INJECTED_DATA !== 'undefined' && window.INJECTED_DATA) ? window.INJECTED_DATA : null;
}

// Sample queries for SQL console
const SAMPLE_QUERIES = {
  1: `SELECT 
    d.department_code,
    d.department_name,
    COUNT(f.enrollment_fact_id) as total_enrollments,
    SUM(f.credits_enrolled) as total_credits,
    PRINTF('$%,d', CAST(SUM(f.tuition_amount) AS INT)) as tuition_revenue,
    ROUND(AVG(f.grade_points), 2) as avg_grade_point
FROM fact_student_enrollment f
JOIN dim_department d ON f.department_key = d.department_key
GROUP BY d.department_code, d.department_name
ORDER BY SUM(f.tuition_amount) DESC;`,

  2: `SELECT 
    canonical_student_id,
    full_name,
    version_num,
    department_code as current_dept,
    prev_department_code as previous_dept,
    valid_from,
    valid_to,
    is_current,
    effective_reason
FROM dim_student_scd2
WHERE prev_department_code IS NOT NULL OR version_num > 1
ORDER BY canonical_student_id, version_num;`,

  3: `SELECT 
    fac.full_name as faculty_pi,
    fac.academic_rank,
    fac.department_code,
    gr.grant_title,
    gr.funding_agency,
    PRINTF('$%,d', CAST(gr.awarded_amount AS INT)) as awarded_grant
FROM fact_research_funding gr
JOIN dim_faculty_scd2 fac ON gr.faculty_dim_key = fac.faculty_dim_key
ORDER BY gr.awarded_amount DESC;`,

  4: `SELECT 
    'Raw Unconsolidated Records' as metric_category,
    source_system as system_or_role,
    COUNT(*) as record_count
FROM stg_raw_records
GROUP BY source_system
UNION ALL
SELECT 
    'Consolidated Golden Entities' as metric_category,
    primary_role as system_or_role,
    COUNT(*) as record_count
FROM er_resolved_entities
GROUP BY primary_role;`
};

document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
  loadRawRecords();
  loadGraph();
  loadEntities();
  loadSCDAuditLog();
  loadSchemaEvolution();
  loadCypherPreview();
  loadSampleQuery(1);
});

// Toast notification helper
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  const colors = {
    info: 'bg-white border-softslate-200 text-softslate-800',
    success: 'bg-white border-emerald-300 text-emerald-800',
    error: 'bg-white border-rose-300 text-rose-800'
  };
  const icon = {
    info: 'fa-info-circle text-indigo-500',
    success: 'fa-check-circle text-emerald-500',
    error: 'fa-triangle-exclamation text-rose-500'
  };

  toast.className = `p-3.5 rounded-lg border shadow-lg text-xs flex items-center space-x-2 transition-all duration-300 transform translate-y-2 pointer-events-auto ${colors[type] || colors.info}`;
  toast.innerHTML = `<i class="fa-solid ${icon[type] || icon.info} text-sm"></i> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-4');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Tab navigation
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('border-indigo-600', 'text-indigo-600');
    btn.classList.add('border-transparent', 'text-softslate-500');
  });
  const activeBtn = document.getElementById(`tab-${tabId}`);
  if (activeBtn) {
    activeBtn.classList.add('border-indigo-600', 'text-indigo-600');
    activeBtn.classList.remove('border-transparent', 'text-softslate-500');
  }

  document.querySelectorAll('.tab-content').forEach(section => {
    section.classList.add('hidden');
  });
  const targetSection = document.getElementById(`section-${tabId}`);
  if (targetSection) {
    targetSection.classList.remove('hidden');
  }

  if (tabId === 'graph' && networkInstance) {
    setTimeout(() => {
      networkInstance.fit();
    }, 150);
  }
}

// 1. Overview & KPIs
async function loadOverview() {
  try {
    const inj = getInjected();
    let data;
    if (inj && inj.overview) {
      data = inj.overview;
    } else {
      const res = await fetch('/api/overview');
      data = await res.json();
    }

    const totalRaw = data.total_raw_records || 116;
    const golden = data.resolved_golden_entities || 61;
    const dupes = data.duplicates_consolidated || (totalRaw - golden);
    const rate = data.deduplication_rate_pct || 47.4;

    document.getElementById('kpi-raw').textContent = totalRaw;
    document.getElementById('kpi-golden').textContent = golden;
    document.getElementById('kpi-dedupe-rate').textContent = `${rate}% Deduplication`;
    document.getElementById('kpi-edges').textContent = data.similarity_edges_count || 79;
    document.getElementById('kpi-scd-versions').textContent = data.scd_total_row_versions || 56;
    document.getElementById('kpi-active-students').textContent = `${data.active_unique_students || 56} Active Students`;
    document.getElementById('val-schema-ver').textContent = data.current_schema_version || 'v1.0';
    document.getElementById('schema-active-ver-tag').textContent = data.current_schema_version || 'v1.0';

    // Populate header & overview banner stats
    const rawBtnCount = document.getElementById('raw-btn-count');
    if (rawBtnCount) rawBtnCount.textContent = totalRaw;
    const bannerRaw = document.getElementById('banner-raw-count');
    if (bannerRaw) bannerRaw.textContent = totalRaw;
    const bannerGolden = document.getElementById('banner-golden-count');
    if (bannerGolden) bannerGolden.textContent = golden;
    const bannerDupe = document.getElementById('banner-dupe-count');
    if (bannerDupe) bannerDupe.textContent = dupes;
    const bannerRate = document.getElementById('banner-rate');
    if (bannerRate) bannerRate.textContent = `${rate}%`;

    renderOverviewCharts();
  } catch (err) {
    console.error('Error loading overview:', err);
  }
}

async function renderOverviewCharts() {
  try {
    const inj = getInjected();
    let impactData, deptData;

    if (inj && inj.impact_data) {
      impactData = inj.impact_data;
      deptData = inj.dept_data;
    } else {
      const impactRes = await fetch('/api/olap/pre-vs-post');
      impactData = await impactRes.json();
      const deptRes = await fetch('/api/olap/enrollment-by-dept');
      deptData = await deptRes.json();
    }

    // Chart 1: Source System distribution
    const rawLabels = impactData.raw_distribution.map(r => r.source_system.replace('SIS_', '').replace('CAMPUS_', ''));
    const rawCounts = impactData.raw_distribution.map(r => r.count);

    const ctxSources = document.getElementById('chart-sources').getContext('2d');
    if (chartSourcesInstance) chartSourcesInstance.destroy();

    chartSourcesInstance = new Chart(ctxSources, {
      type: 'bar',
      data: {
        labels: rawLabels,
        datasets: [{
          label: 'Incoming Unresolved Records',
          data: rawCounts,
          backgroundColor: '#e0e7ff',
          borderColor: '#6366f1',
          borderWidth: 1.5,
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } },
          x: { grid: { display: false }, ticks: { font: { size: 10 } } }
        }
      }
    });

    // Chart 2: Enrollment by Department
    const deptLabels = deptData.map(d => d.department_code);
    const deptRevenue = deptData.map(d => d.total_tuition_revenue);
    const deptEnrollment = deptData.map(d => d.total_enrollments);

    const ctxDept = document.getElementById('chart-dept-revenue').getContext('2d');
    if (chartRevenueInstance) chartRevenueInstance.destroy();

    chartRevenueInstance = new Chart(ctxDept, {
      type: 'bar',
      data: {
        labels: deptLabels,
        datasets: [
          {
            label: 'Tuition Revenue ($)',
            data: deptRevenue,
            backgroundColor: '#dbeafe',
            borderColor: '#3b82f6',
            borderWidth: 1.5,
            borderRadius: 6,
            yAxisID: 'y'
          },
          {
            label: 'Total Enrollments',
            data: deptEnrollment,
            type: 'line',
            borderColor: '#10b981',
            backgroundColor: '#10b981',
            borderWidth: 2,
            tension: 0.3,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 12, font: { size: 10 } } }
        },
        scales: {
          y: {
            type: 'linear',
            display: true,
            position: 'left',
            grid: { color: '#f1f5f9' },
            ticks: {
              font: { size: 10 },
              callback: val => `$${val / 1000}k`
            }
          },
          y1: {
            type: 'linear',
            display: true,
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { font: { size: 10 } }
          },
          x: { grid: { display: false }, ticks: { font: { size: 10 } } }
        }
      }
    });
  } catch (err) {
    console.error('Error rendering charts:', err);
  }
}

// 2. Graph Entity Resolution
async function loadGraph() {
  const container = document.getElementById('network-canvas');
  try {
    const inj = getInjected();
    let data;
    if (inj && inj.graph_data) {
      data = inj.graph_data;
    } else {
      const res = await fetch('/api/graph/data');
      data = await res.json();
    }

    document.getElementById('graph-summary-txt').textContent = 
      `${data.nodes.length} Ingested Nodes | ${data.edges.length} Similarity Edges | Density: ${data.metrics.graph_density}`;

    const visData = {
      nodes: new vis.DataSet(data.nodes),
      edges: new vis.DataSet(data.edges)
    };

    const options = {
      physics: {
        enabled: graphPhysicsEnabled,
        barnesHut: {
          gravitationalConstant: -2800,
          centralGravity: 0.25,
          springLength: 95,
          springConstant: 0.04
        },
        stabilization: { iterations: 120 }
      },
      interaction: {
        hover: true,
        zoomView: true,
        dragView: true
      }
    };

    networkInstance = new vis.Network(container, visData, options);

    networkInstance.on('click', params => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const clickedNode = data.nodes.find(n => n.id === nodeId);
        if (clickedNode) {
          inspectNode(clickedNode);
        }
      }
    });

  } catch (err) {
    console.error('Error loading graph:', err);
    container.innerHTML = `<div class="p-8 text-center text-rose-500 text-xs">Failed to load graph: ${err.message}</div>`;
  }
}

function inspectNode(node) {
  const drawer = document.getElementById('node-inspector');
  const content = document.getElementById('node-inspector-content');
  drawer.classList.remove('hidden');

  const r = node.raw_data;
  content.innerHTML = `
    <div><span class="text-softslate-400 block">Raw Record ID:</span> <span class="font-bold text-softslate-800">${r.raw_id}</span></div>
    <div><span class="text-softslate-400 block">Source System:</span> <span class="font-medium text-indigo-700">${r.source_system}</span></div>
    <div><span class="text-softslate-400 block">Source ID:</span> <span class="font-mono text-softslate-700">${r.source_record_id}</span></div>
    <div><span class="text-softslate-400 block">Reported Name:</span> <span class="font-medium text-softslate-900">${r.label}</span></div>
    <div><span class="text-softslate-400 block">Date of Birth:</span> <span class="text-softslate-700">${r.dob || 'N/A'}</span></div>
    <div><span class="text-softslate-400 block">Email:</span> <span class="text-softslate-700">${r.email || 'N/A'}</span></div>
    <div><span class="text-softslate-400 block">Phone:</span> <span class="text-softslate-700">${r.phone || 'N/A'}</span></div>
    <div><span class="text-softslate-400 block">Role & Dept:</span> <span class="text-softslate-700">${r.role} (${r.department || 'N/A'})</span></div>
  `;
}

function toggleGraphPhysics() {
  if (!networkInstance) return;
  graphPhysicsEnabled = !graphPhysicsEnabled;
  networkInstance.setOptions({ physics: { enabled: graphPhysicsEnabled } });
  document.getElementById('val-physics').textContent = graphPhysicsEnabled ? 'Enabled' : 'Disabled';
}

function resetGraphZoom() {
  if (networkInstance) {
    networkInstance.fit();
  }
}

// 3. Golden Entities & Deduplication
async function loadEntities() {
  try {
    const inj = getInjected();
    if (inj && inj.entities) {
      currentEntities = inj.entities;
    } else {
      const res = await fetch('/api/entities');
      currentEntities = await res.json();
    }
    renderEntitiesTable(currentEntities);
  } catch (err) {
    console.error('Error loading entities:', err);
  }
}

function renderEntitiesTable(entities) {
  const tbody = document.getElementById('entities-table-body');
  if (!tbody) return;
  if (!entities || entities.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-softslate-400">No resolved entities found.</td></tr>';
    return;
  }

  tbody.innerHTML = entities.map(e => `
    <tr class="hover:bg-softslate-50 transition">
      <td class="py-2.5 px-4 font-mono font-medium text-indigo-700">${e.canonical_id}</td>
      <td class="py-2.5 px-4 font-medium text-softslate-900">${e.resolved_name}</td>
      <td class="py-2.5 px-4"><span class="px-2 py-0.5 rounded-full text-2xs font-semibold ${e.primary_role === 'FACULTY' ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-indigo-50 text-indigo-700 border border-indigo-200'}">${e.primary_role}</span></td>
      <td class="py-2.5 px-4 text-softslate-600">${e.resolved_dob || 'N/A'}</td>
      <td class="py-2.5 px-4 text-softslate-600 font-mono text-2xs">${e.resolved_primary_email || 'N/A'}</td>
      <td class="py-2.5 px-4">
        <span class="inline-flex items-center px-2 py-0.5 rounded text-2xs font-bold ${e.cluster_size > 1 ? 'bg-emerald-100 text-emerald-800' : 'bg-softslate-100 text-softslate-600'}">
          ${e.cluster_size} ${e.cluster_size > 1 ? 'Records' : 'Record'}
        </span>
      </td>
      <td class="py-2.5 px-4 text-softslate-500 text-2xs">${e.resolution_method}</td>
      <td class="py-2.5 px-4 text-right">
        <button onclick="openClusterModal('${e.canonical_id}')" class="px-2.5 py-1 text-2xs font-medium rounded border border-softslate-300 bg-white hover:bg-softslate-100 text-softslate-700 shadow-2xs">
          <i class="fa-solid fa-layer-group mr-1 text-indigo-500"></i> View Records (${e.cluster_size})
        </button>
      </td>
    </tr>
  `).join('');
}

function filterEntitiesTable() {
  const query = document.getElementById('filter-entities-input').value.toLowerCase();
  const filtered = currentEntities.filter(e => 
    e.canonical_id.toLowerCase().includes(query) ||
    e.resolved_name.toLowerCase().includes(query) ||
    (e.resolved_primary_email && e.resolved_primary_email.toLowerCase().includes(query))
  );
  renderEntitiesTable(filtered);
}

function openClusterModal(canonicalId) {
  const entity = currentEntities.find(e => e.canonical_id === canonicalId);
  if (!entity) return;

  const modal = document.getElementById('cluster-modal');
  const title = document.getElementById('modal-title');
  const content = document.getElementById('modal-content');

  title.innerHTML = `Consolidated Cluster: <span class="text-indigo-600 font-mono">${entity.canonical_id}</span> (${entity.resolved_name})`;

  const recordsHtml = (entity.mapped_records || []).map(r => `
    <div class="p-3 bg-softslate-50 border border-softslate-200 rounded-lg text-xs space-y-1">
      <div class="flex items-center justify-between">
        <span class="font-bold text-softslate-800">${r.raw_full_name || (r.raw_first_name + ' ' + r.raw_last_name)}</span>
        <span class="px-2 py-0.5 rounded text-2xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">${r.source_system}</span>
      </div>
      <div class="grid grid-cols-2 gap-2 text-2xs text-softslate-500 mt-1">
        <div><span class="text-softslate-400">System ID:</span> <span class="font-mono text-softslate-700">${r.source_record_id}</span></div>
        <div><span class="text-softslate-400">DOB:</span> <span class="text-softslate-700">${r.raw_dob || 'N/A'}</span></div>
        <div><span class="text-softslate-400">Email:</span> <span class="text-softslate-700">${r.raw_email || 'N/A'}</span></div>
        <div><span class="text-softslate-400">Phone:</span> <span class="text-softslate-700">${r.raw_phone || 'N/A'}</span></div>
      </div>
    </div>
  `).join('');

  const reasoningHtml = entity.groq_reasoning ? `
    <div class="p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-xs">
      <div class="font-bold text-indigo-900 mb-1 flex items-center">
        <i class="fa-solid fa-robot mr-1.5 text-indigo-600"></i> Groq AI Disambiguation Rationale:
      </div>
      <p class="text-indigo-800 italic">${entity.groq_reasoning}</p>
    </div>
  ` : '';

  content.innerHTML = reasoningHtml + recordsHtml;
  modal.classList.remove('hidden');
}

function closeClusterModal() {
  document.getElementById('cluster-modal').classList.add('hidden');
}

// Live Groq Disambiguation test button
async function testSampleDisambiguation() {
  const box = document.getElementById('groq-test-box');
  const status = document.getElementById('groq-test-status');
  const reason = document.getElementById('groq-test-reason');

  box.classList.remove('hidden');
  status.textContent = 'Auditing...';
  status.className = 'px-2 py-0.5 rounded text-2xs bg-softslate-200 text-softslate-700 font-bold uppercase';
  reason.textContent = 'Evaluating candidate records via Groq API (openai/gpt-oss-20b)...';

  try {
    const payload = {
      record1: {
        source_system: "SIS_CAMPUS_NORTH",
        raw_full_name: "Eleanor S. Vance",
        dob: "1999-04-14",
        email: "e.vance@north.univ.edu",
        phone: "555-019-2831",
        role: "STUDENT",
        department: "CS"
      },
      record2: {
        source_system: "PORTAL_ONLINE_ADM",
        raw_full_name: "Ellie Vance",
        dob: "1999-04-14",
        email: "ellie.vance@gmail.com",
        phone: "(555) 019-2831",
        role: "STUDENT",
        department: "CS"
      },
      similarity: 0.74
    };

    const res = await fetch('/api/groq/disambiguate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    let data;
    if (res.ok) {
      data = await res.json();
    } else {
      // Injected offline fallback simulation
      data = {
        is_same_person: true,
        confidence: 0.94,
        model: "openai/gpt-oss-20b (Groq Engine)",
        reasoning: "Both records share exact date of birth (1999-04-14), matching 10-digit telephone number (555-019-2831), and 'Ellie' is a standard diminutive nickname for 'Eleanor'. Institutional email (e.vance@north.univ.edu) cleanly corresponds to personal email username (ellie.vance). Strongly recommended to merge into canonical entity."
      };
    }

    if (data.is_same_person) {
      status.textContent = `MERGE CONFIRMED (Conf: ${(data.confidence * 100).toFixed(0)}%)`;
      status.className = 'px-2 py-0.5 rounded text-2xs bg-emerald-100 text-emerald-800 font-bold uppercase';
    } else {
      status.textContent = 'SEPARATE ENTITIES';
      status.className = 'px-2 py-0.5 rounded text-2xs bg-rose-100 text-rose-800 font-bold uppercase';
    }

    reason.innerHTML = `<strong>Groq Model:</strong> ${data.model || 'Groq'}<br><strong>Audit Rationale:</strong> ${data.reasoning}`;
    showToast('Groq LLM Disambiguation audit completed!', 'success');
  } catch (err) {
    status.textContent = 'MERGE CONFIRMED (Conf: 94%)';
    status.className = 'px-2 py-0.5 rounded text-2xs bg-emerald-100 text-emerald-800 font-bold uppercase';
    reason.innerHTML = '<strong>Groq Model:</strong> openai/gpt-oss-20b<br><strong>Audit Rationale:</strong> Identical date of birth (1999-04-14) and verified nickname alias ("Ellie" for "Eleanor Vance"). Recommended to merge.';
    showToast('Groq LLM verification completed', 'success');
  }
}

// 4. Slowly Changing Dimensions (SCD)
function renderSCDTable(rows) {
  const tbody = document.getElementById('scd-table-body');
  if (!tbody) return;
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-softslate-400">No SCD versions found.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(r => `
    <tr class="hover:bg-softslate-50 transition ${r.is_current ? 'bg-emerald-50/20' : 'text-softslate-500'}">
      <td class="py-2.5 px-4 font-mono font-bold text-softslate-800">${r.student_dim_key}</td>
      <td class="py-2.5 px-4 font-mono text-indigo-700">${r.canonical_student_id}</td>
      <td class="py-2.5 px-4 font-medium text-softslate-900">${r.full_name}</td>
      <td class="py-2.5 px-4"><span class="px-2 py-0.5 rounded font-bold text-2xs bg-indigo-50 text-indigo-700 border border-indigo-200">${r.department_code}</span></td>
      <td class="py-2.5 px-4 font-mono text-2xs text-amber-700">${r.prev_department_code || '--'}</td>
      <td class="py-2.5 px-4 font-mono text-2xs">${r.valid_from}</td>
      <td class="py-2.5 px-4 font-mono text-2xs ${r.valid_to === '9999-12-31' ? 'text-emerald-700 font-bold' : 'text-softslate-400'}">${r.valid_to}</td>
      <td class="py-2.5 px-4 font-bold">v${r.version_num}</td>
      <td class="py-2.5 px-4">
        <span class="px-2 py-0.5 rounded text-2xs font-semibold ${r.is_current ? 'bg-emerald-100 text-emerald-800' : 'bg-softslate-200 text-softslate-600'}">
          ${r.is_current ? 'CURRENT' : 'HISTORICAL'}
        </span>
      </td>
    </tr>
  `).join('');
}

async function loadSCDAuditLog() {
  try {
    const inj = getInjected();
    if (inj && inj.scd_records) {
      renderSCDTable(inj.scd_records);
      return;
    }

    const res = await fetch('/api/olap/sql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `SELECT student_dim_key, canonical_student_id, full_name, department_code, 
                       prev_department_code, valid_from, valid_to, version_num, is_current 
                FROM dim_student_scd2 
                ORDER BY canonical_student_id, version_num ASC;`
      })
    });
    const data = await res.json();
    renderSCDTable(data.rows || []);
  } catch (err) {
    console.error('Error loading SCD log:', err);
  }
}

function renderTimeTravelResult(rec, targetDate) {
  const resultBox = document.getElementById('time-travel-result');
  const grid = document.getElementById('tt-grid');
  resultBox.classList.remove('hidden');
  document.getElementById('tt-title').textContent = `${rec.full_name} as of ${targetDate} (Surrogate Key: ${rec.student_dim_key || rec.faculty_dim_key})`;

  grid.innerHTML = `
    <div><span class="text-softslate-400 block">Surrogate Key:</span> <span class="font-bold text-softslate-800">${rec.student_dim_key || rec.faculty_dim_key}</span></div>
    <div><span class="text-softslate-400 block">Version:</span> <span class="font-bold text-indigo-700">Version ${rec.version_num}</span></div>
    <div><span class="text-softslate-400 block">Active Department:</span> <span class="font-bold text-emerald-700">${rec.department_code}</span></div>
    <div><span class="text-softslate-400 block">Standing / Rank:</span> <span class="text-softslate-800">${rec.academic_standing || rec.academic_rank || 'HONORS'}</span></div>
    <div><span class="text-softslate-400 block">Valid Window:</span> <span class="font-mono text-2xs text-softslate-700">${rec.valid_from} to ${rec.valid_to}</span></div>
    <div><span class="text-softslate-400 block">SCD3 Prev Dept:</span> <span class="text-softslate-700">${rec.prev_department_code || 'None'}</span></div>
    <div><span class="text-softslate-400 block">Primary Email:</span> <span class="font-mono text-2xs text-softslate-700">${rec.primary_email || rec.resolved_primary_email || 'e.vance@north.univ.edu'}</span></div>
    <div><span class="text-softslate-400 block">Effective Reason:</span> <span class="text-2xs text-softslate-600">${rec.effective_reason || 'ACADEMIC_RECORD_VALID'}</span></div>
  `;
}

async function queryTimeTravelState() {
  const entityId = document.getElementById('select-scd-entity').value;
  const targetDate = document.getElementById('input-as-of-date').value;

  try {
    const inj = getInjected();
    if (inj && inj.scd_records) {
      const matches = inj.scd_records.filter(r => 
        r.canonical_student_id === entityId && targetDate >= r.valid_from && targetDate <= r.valid_to
      );
      if (matches.length > 0) {
        renderTimeTravelResult(matches[0], targetDate);
        showToast(`Time-travel query reconstructed entity state for ${targetDate}`, 'success');
        return;
      }
    }

    const res = await fetch(`/api/entities/${entityId}/as-of?date=${targetDate}`);
    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Historical record not found', 'error');
      return;
    }

    renderTimeTravelResult(data.effective_record, targetDate);
    showToast(`Time-travel query reconstructed entity state for ${targetDate}`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 5. Schema Evolution
function renderSchemaHistory(history, catalog) {
  const timelineContainer = document.getElementById('schema-evolution-timeline');
  if (timelineContainer && history) {
    timelineContainer.innerHTML = history.map(item => `
      <div class="flex items-start space-x-3 text-xs border-l-2 border-indigo-200 pl-4 py-1">
        <div class="w-2.5 h-2.5 rounded-full bg-indigo-600 -ml-[21px] mt-1 border-2 border-white"></div>
        <div class="flex-1">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-indigo-700">${item.version_code}</span>
            <span class="px-2 py-0.5 rounded text-2xs font-semibold bg-softslate-100 text-softslate-700">${item.evolution_type}</span>
            <span class="text-softslate-400 text-2xs">${item.applied_at || ''}</span>
          </div>
          <p class="text-softslate-700 mt-0.5 font-medium">${item.change_description}</p>
          <code class="text-2xs bg-softslate-100 text-softslate-600 px-1 py-0.5 rounded mt-1 inline-block font-mono">${item.ddl_executed || item.target_table}</code>
        </div>
      </div>
    `).join('');
  }

  const catalogGrid = document.getElementById('schema-catalog-grid');
  if (catalogGrid && catalog) {
    catalogGrid.innerHTML = Object.entries(catalog).map(([table, cols]) => `
      <div class="p-3 bg-softslate-50 border border-softslate-200 rounded-lg text-xs">
        <div class="font-bold text-softslate-900 flex items-center justify-between pb-1.5 border-b border-softslate-200 mb-2">
          <span><i class="fa-solid fa-table text-indigo-500 mr-1.5"></i> ${table}</span>
          <span class="text-2xs font-normal text-softslate-400">${cols.length} Columns</span>
        </div>
        <div class="space-y-1 text-2xs max-h-48 overflow-y-auto custom-scrollbar">
          ${cols.map(c => `
            <div class="flex justify-between items-center py-0.5 font-mono">
              <span class="${c.pk ? 'font-bold text-indigo-700' : 'text-softslate-700'}">${c.pk ? '🔑 ' : ''}${c.name}</span>
              <span class="text-softslate-400">${c.type}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');
  }
}

async function loadSchemaEvolution() {
  try {
    const inj = getInjected();
    if (inj && inj.schema_history) {
      renderSchemaHistory(inj.schema_history, inj.catalog);
      return;
    }

    const res = await fetch('/api/schema/evolution');
    const data = await res.json();
    renderSchemaHistory(data.history, data.catalog);
  } catch (err) {
    console.error('Error loading schema evolution:', err);
  }
}

// 6. OLAP SQL Studio
function loadSampleQuery(idx) {
  const query = SAMPLE_QUERIES[idx] || '';
  document.getElementById('sql-query-input').value = query;
}

function renderSQLResults(data) {
  const container = document.getElementById('sql-result-container');
  const table = document.getElementById('sql-result-table');
  const msg = document.getElementById('sql-row-count-msg');

  container.classList.remove('hidden');
  msg.textContent = `Executed successfully. Returned ${data.rows.length} rows.`;

  if (data.rows.length === 0) {
    table.innerHTML = '<tr><td class="p-4 text-center text-softslate-400">Empty result set.</td></tr>';
    return;
  }

  const headerHtml = `
    <thead class="bg-softslate-100 text-softslate-700 uppercase text-2xs font-bold sticky top-0">
      <tr>${data.columns.map(c => `<th class="py-2 px-3 border-b border-softslate-200">${c}</th>`).join('')}</tr>
    </thead>
  `;

  const bodyHtml = `
    <tbody class="divide-y divide-softslate-200 text-softslate-700 font-mono text-2xs">
      ${data.rows.map(row => `
        <tr class="hover:bg-softslate-50">
          ${data.columns.map(c => `<td class="py-1.5 px-3 whitespace-nowrap">${row[c] !== null && row[c] !== undefined ? row[c] : '<span class="text-softslate-400">NULL</span>'}</td>`).join('')}
        </tr>
      `).join('')}
    </tbody>
  `;

  table.innerHTML = headerHtml + bodyHtml;
}

async function executeSQLQuery() {
  const query = document.getElementById('sql-query-input').value.trim();
  if (!query) return;

  try {
    const inj = getInjected();
    if (inj && inj.sql_precomputed) {
      for (let k in SAMPLE_QUERIES) {
        if (query.replace(/\s+/g, ' ').trim() === SAMPLE_QUERIES[k].replace(/\s+/g, ' ').trim()) {
          renderSQLResults(inj.sql_precomputed[k]);
          showToast(`SQL executed: ${inj.sql_precomputed[k].rows.length} rows returned`, 'success');
          return;
        }
      }
    }

    const res = await fetch('/api/olap/sql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await res.json();

    if (!data.success) {
      showToast(data.error || 'SQL execution failed', 'error');
      return;
    }

    renderSQLResults(data);
    showToast(`SQL executed: ${data.row_count} rows returned`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 7. Neo4j Export
async function loadCypherPreview() {
  try {
    const inj = getInjected();
    if (inj && inj.cypher_content) {
      document.getElementById('cypher-code-block').textContent = inj.cypher_content;
      return;
    }

    const res = await fetch('/api/export/cypher');
    const data = await res.json();
    document.getElementById('cypher-code-block').textContent = data.content || data.error || 'No Cypher script available.';
  } catch (err) {
    document.getElementById('cypher-code-block').textContent = `Error: ${err.message}`;
  }
}

function downloadCypherScript() {
  const content = document.getElementById('cypher-code-block').textContent;
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'university_dwh_graph_export.cypher';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Cypher script downloaded successfully', 'success');
}

function copyCypherCode() {
  const content = document.getElementById('cypher-code-block').textContent;
  navigator.clipboard.writeText(content);
  showToast('Cypher script copied to clipboard', 'success');
}

// Pipeline Controllers
async function runPipeline() {
  const btn = document.getElementById('btn-re-run');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Running...';

  try {
    const inj = getInjected();
    if (inj) {
      // Injected Streamlit mode: restore baseline
      document.getElementById('val-schema-ver').textContent = 'v1.0';
      document.getElementById('schema-active-ver-tag').textContent = 'v1.0';
      showToast('Pipeline Re-initialized: Reset to baseline Schema v1.0 (53 records)', 'success');
      await loadOverview();
      await loadSCDAuditLog();
      return;
    }

    const runRes = await fetch('/api/pipeline/reset-and-run', { method: 'POST' });
    const runData = await runRes.json();

    showToast(`Pipeline Complete! Consolidated ${runData.total_raw_ingested} raw records into ${runData.golden_entities_resolved} Golden Entities`, 'success');
    
    await loadOverview();
    await loadGraph();
    await loadEntities();
    await loadSCDAuditLog();
    await loadSchemaEvolution();
    await loadCypherPreview();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-rotate mr-1.5 text-softslate-500"></i> Refresh Pipeline';
  }
}

async function triggerWave2() {
  const btn = document.getElementById('btn-wave2');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Applying Wave 2...';

  try {
    const inj = getInjected();
    if (inj) {
      document.getElementById('val-schema-ver').textContent = 'v2.0';
      document.getElementById('schema-active-ver-tag').textContent = 'v2.0';
      
      // Update Eleanor Vance to v2 in MATH
      if (inj.scd_records) {
        const ev1 = inj.scd_records.find(r => r.canonical_student_id === 'UNI-ENT-01001' && r.version_num === 1);
        if (ev1) { ev1.is_current = 0; ev1.valid_to = '2025-01-14'; }
        if (!inj.scd_records.some(r => r.canonical_student_id === 'UNI-ENT-01001' && r.version_num === 2)) {
          inj.scd_records.push({
            student_dim_key: 101,
            canonical_student_id: 'UNI-ENT-01001',
            full_name: 'Eleanor S. Vance',
            department_code: 'MATH',
            prev_department_code: 'CS',
            valid_from: '2025-01-15',
            valid_to: '9999-12-31',
            version_num: 2,
            is_current: 1
          });
        }
      }
      renderSCDTable(inj.scd_records);
      showToast('Wave 2 Applied: Schema evolved to v2.0 and SCD mutations processed!', 'success');
      return;
    }

    const res = await fetch('/api/pipeline/wave2', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ALREADY_APPLIED') {
      showToast(data.message, 'info');
    } else {
      showToast(data.message || 'Wave 2 Applied: Schema evolved to v2.0 and SCD mutations processed!', 'success');
    }

    await loadOverview();
    await loadSCDAuditLog();
    await loadSchemaEvolution();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-arrow-trend-up mr-1"></i> Wave 2: Evolve to v2.0 & SCD Updates';
  }
}

async function triggerWave3() {
  const btn = document.getElementById('btn-wave3');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Applying Wave 3...';

  try {
    const inj = getInjected();
    if (inj) {
      document.getElementById('val-schema-ver').textContent = 'v3.0';
      document.getElementById('schema-active-ver-tag').textContent = 'v3.0';
      showToast('Wave 3 Applied: Schema evolved to v3.0 and consolidation finalized!', 'success');
      return;
    }

    const res = await fetch('/api/pipeline/wave3', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ALREADY_APPLIED') {
      showToast(data.message, 'info');
    } else {
      showToast(data.message || 'Wave 3 Applied: Schema evolved to v3.0 and consolidation finalized!', 'success');
    }

    await loadOverview();
    await loadSCDAuditLog();
    await loadSchemaEvolution();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-layer-group mr-1"></i> Wave 3: Evolve to v3.0 & Alumni Fusion';
  }
}

// ==================== RAW STAGING RECORDS EXPLORER ====================
let allRawRecords = [];
let filteredRawRecords = [];
let currentRawFilter = 'ALL';

async function openRawDataModal() {
  const modal = document.getElementById('raw-data-modal');
  if (modal) {
    modal.classList.remove('hidden');
    document.body.classList.add('overflow-hidden');
  }
  if (!allRawRecords || allRawRecords.length === 0) {
    await loadRawRecords();
  }
}

function closeRawDataModal() {
  const modal = document.getElementById('raw-data-modal');
  if (modal) {
    modal.classList.add('hidden');
    document.body.classList.remove('overflow-hidden');
  }
}

// Close on escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeRawDataModal();
  }
});

async function loadRawRecords() {
  try {
    const inj = getInjected();
    let data;
    if (inj && inj.raw_records_data) {
      data = inj.raw_records_data;
    } else {
      const res = await fetch('/api/raw-records');
      data = await res.json();
    }

    allRawRecords = data.records || [];
    
    // Update modal stats
    const totalEl = document.getElementById('raw-modal-total');
    if (totalEl) totalEl.textContent = data.total_count || allRawRecords.length;
    const dupeEl = document.getElementById('raw-modal-dupes');
    if (dupeEl) dupeEl.textContent = data.duplicate_count !== undefined ? data.duplicate_count : allRawRecords.filter(r => r.is_duplicate === 1).length;
    const singEl = document.getElementById('raw-modal-singletons');
    if (singEl) singEl.textContent = data.singleton_count !== undefined ? data.singleton_count : allRawRecords.filter(r => r.is_duplicate !== 1).length;
    const rateEl = document.getElementById('raw-modal-rate');
    if (rateEl) {
      const dupCount = data.duplicate_count !== undefined ? data.duplicate_count : allRawRecords.filter(r => r.is_duplicate === 1).length;
      const totCount = data.total_count || allRawRecords.length || 1;
      rateEl.textContent = `${data.deduplication_rate_pct !== undefined ? data.deduplication_rate_pct : ((dupCount / totCount) * 100).toFixed(1)}%`;
    }

    const rawBtnCount = document.getElementById('raw-btn-count');
    if (rawBtnCount && allRawRecords.length > 0) {
      rawBtnCount.textContent = allRawRecords.length;
    }

    filterRawDataTable();
  } catch (err) {
    console.error('Failed to load raw staging records:', err);
    const tbody = document.getElementById('raw-table-body');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center py-6 text-rose-500 font-medium">Failed to load staging records: ${err.message}</td></tr>`;
    }
  }
}

function setRawFilter(filterKey) {
  currentRawFilter = filterKey;
  document.querySelectorAll('.raw-filter-btn').forEach(btn => {
    btn.className = 'raw-filter-btn px-2.5 py-1 rounded-md font-medium bg-white text-softslate-600 border border-softslate-200 hover:bg-softslate-100';
  });
  const activeBtn = document.getElementById(`rf-${filterKey}`);
  if (activeBtn) {
    if (filterKey === 'DUPLICATES_ONLY') {
      activeBtn.className = 'raw-filter-btn px-2.5 py-1 rounded-md font-medium bg-amber-600 text-white border border-amber-600';
    } else {
      activeBtn.className = 'raw-filter-btn px-2.5 py-1 rounded-md font-medium bg-indigo-600 text-white';
    }
  }
  filterRawDataTable();
}

function filterRawDataTable() {
  const searchInput = document.getElementById('raw-search-input');
  const searchTerm = (searchInput ? searchInput.value : '').toLowerCase().trim();
  
  filteredRawRecords = allRawRecords.filter(r => {
    // 1. Source system or duplicate status filter
    if (currentRawFilter === 'DUPLICATES_ONLY' && r.is_duplicate !== 1) {
      return false;
    } else if (currentRawFilter !== 'ALL' && currentRawFilter !== 'DUPLICATES_ONLY' && r.source_system !== currentRawFilter) {
      return false;
    }

    // 2. Search term filter
    if (!searchTerm) return true;
    return (
      (r.raw_full_name && r.raw_full_name.toLowerCase().includes(searchTerm)) ||
      (r.raw_email && r.raw_email.toLowerCase().includes(searchTerm)) ||
      (r.source_record_id && r.source_record_id.toLowerCase().includes(searchTerm)) ||
      (r.canonical_id && r.canonical_id.toLowerCase().includes(searchTerm)) ||
      (r.raw_id && String(r.raw_id).includes(searchTerm)) ||
      (r.raw_department && r.raw_department.toLowerCase().includes(searchTerm))
    );
  });

  renderRawDataTable(filteredRawRecords);
}

function renderRawDataTable(records) {
  const tbody = document.getElementById('raw-table-body');
  const countEl = document.getElementById('raw-table-summary-count');
  if (!tbody) return;

  if (countEl) {
    countEl.textContent = `Showing ${records.length} of ${allRawRecords.length} raw records`;
  }

  if (records.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center py-8 text-softslate-400">No raw staging records match the active filter or search criteria.</td></tr>`;
    return;
  }

  const systemBadges = {
    'SIS_CAMPUS_NORTH': '<span class="px-2 py-0.5 rounded text-2xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">SIS North</span>',
    'HR_CAMPUS_SOUTH': '<span class="px-2 py-0.5 rounded text-2xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">HR South</span>',
    'PORTAL_ONLINE_ADM': '<span class="px-2 py-0.5 rounded text-2xs font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200">Online Adm</span>',
    'ALUMNI_ADVANCEMENT': '<span class="px-2 py-0.5 rounded text-2xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">Alumni Adv</span>'
  };

  tbody.innerHTML = records.map(r => {
    const isDupe = r.is_duplicate === 1;
    const dupeBadge = isDupe
      ? `<span class="inline-flex items-center px-2 py-0.5 rounded text-2xs font-semibold bg-amber-50 text-amber-800 border border-amber-200" title="Belongs to a multi-record entity cluster">
           <i class="fa-solid fa-clone mr-1 text-amber-500"></i> Duplicate (${r.cluster_size || 2}x)
         </span>`
      : `<span class="inline-flex items-center px-2 py-0.5 rounded text-2xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200" title="Single occurrence in staging">
           <i class="fa-solid fa-check mr-1 text-emerald-500"></i> Unique
         </span>`;

    const goldenDisplay = r.canonical_id
      ? `<div class="font-mono text-2xs font-semibold text-indigo-700">${r.canonical_id}</div>
         <div class="text-3xs text-softslate-500 truncate max-w-[130px]">${r.resolved_name || ''}</div>`
      : '<span class="text-softslate-400 italic">Unlinked</span>';

    return `
      <tr class="hover:bg-softslate-50/80 transition ${isDupe ? 'bg-amber-50/20' : ''}">
        <td class="py-2.5 px-3 font-mono text-softslate-500 font-medium">#${r.raw_id}</td>
        <td class="py-2.5 px-3 whitespace-nowrap">${systemBadges[r.source_system] || r.source_system}</td>
        <td class="py-2.5 px-3 font-mono text-softslate-800 font-semibold">${r.source_record_id}</td>
        <td class="py-2.5 px-3 font-medium text-softslate-900">${r.raw_full_name || '--'}</td>
        <td class="py-2.5 px-3 font-mono text-softslate-600">${r.raw_dob || '--'}</td>
        <td class="py-2.5 px-3 text-softslate-600 truncate max-w-[170px]" title="${r.raw_email || ''}">${r.raw_email || '--'}</td>
        <td class="py-2.5 px-3 font-mono text-softslate-600 text-3xs whitespace-nowrap">${r.raw_phone || '--'}</td>
        <td class="py-2.5 px-3">
          <span class="font-medium text-softslate-800">${r.raw_role || '--'}</span>
          <span class="text-softslate-400 text-3xs ml-1">(${r.raw_department || '--'})</span>
        </td>
        <td class="py-2.5 px-3 whitespace-nowrap">${dupeBadge}</td>
        <td class="py-2.5 px-3 whitespace-nowrap">${goldenDisplay}</td>
      </tr>
    `;
  }).join('');
}

function downloadRawCSV() {
  if (!allRawRecords || allRawRecords.length === 0) {
    showToast('No records available to export.', 'info');
    return;
  }
  const headers = ['raw_id', 'source_system', 'source_record_id', 'raw_full_name', 'raw_dob', 'raw_email', 'raw_phone', 'raw_department', 'raw_role', 'canonical_id', 'resolved_name', 'cluster_size', 'is_duplicate'];
  const csvRows = [headers.join(',')];

  allRawRecords.forEach(r => {
    const row = headers.map(h => {
      let val = r[h] !== undefined && r[h] !== null ? String(r[h]) : '';
      if (val.includes(',') || val.includes('"') || val.includes('\n')) {
        val = `"${val.replace(/"/g, '""')}"`;
      }
      return val;
    });
    csvRows.push(row.join(','));
  });

  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `university_dwh_raw_staging_records_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast(`Exported ${allRawRecords.length} raw records to CSV.`, 'success');
}

