/* ══════════════════════════════════════════════════════════════
   EduTrack Pro — Features v9.6
   feature_departments.js  +  feature_faculty.js (combined)

   FEATURE 1 — Department Drill-Down Analytics
     initDeptDrill()             → entry point (Institution view)
     renderDeptCards()           → dept card grid
     drillToCourse(deptKey)      → course-level view
     drillToSection(course,…)    → section-level view
     drillToSectionDetail(…)     → student list view
     updateBreadcrumb(crumbs)    → breadcrumb trail renderer

   FEATURE 2 — Faculty Management
     renderFacultyPage()         → full page render
     openMarkFacultyModal()      → show mark-attendance modal
     editFacAtt(facId,logId)     → open modal pre-filled for edit
     saveFacultyAttendance()     → POST/PUT to API
     viewFacDetail(facId)        → open detail modal

   Both features fetch live data from:
     GET  /api/departments
     GET  /api/departments/{dept}/courses
     GET  /api/departments/{dept}/courses/{course}/sections
     GET  /api/departments/{dept}/courses/{course}/sections/{sec}/students
     GET  /api/faculty
     GET  /api/faculty/analytics/summary
     GET  /api/faculty/{fac_id}
     POST /api/faculty/attendance
     PUT  /api/faculty/{fac_id}/attendance/{log_id}
   ══════════════════════════════════════════════════════════════ */

'use strict';

// ── Extended API methods ─────────────────────────────────────
Object.assign(api, {
  // Departments
  departments:       ()             => apiFetch('/api/departments'),
  deptCourses:       (dk)          => apiFetch(`/api/departments/${dk}/courses`),
  courseSections:    (dk, ck)      => apiFetch(`/api/departments/${dk}/courses/${ck}/sections`),
  sectionStudents:   (dk, ck, sec) => apiFetch(`/api/departments/${dk}/courses/${ck}/sections/${sec}/students`),

  // Faculty
  faculty:           (dept, search, date) => {
    const p = new URLSearchParams();
    if (dept)   p.set('dept', dept);
    if (search) p.set('search', search);
    if (date)   p.set('att_date', date);
    return apiFetch('/api/faculty' + (p.toString() ? '?' + p : ''));
  },
  facultyAnalytics:  ()              => apiFetch('/api/faculty/analytics/summary'),
  facultyDetail:     (id)            => apiFetch(`/api/faculty/${id}?days=30`),
  markFacAtt:        (data)          => apiFetch('/api/faculty/attendance', { method:'POST', body:JSON.stringify(data) }),
  editFacAttApi:     (id, lid, data) => apiFetch(`/api/faculty/${id}/attendance/${lid}`, { method:'PUT', body:JSON.stringify(data) }),
  exportFacultyCSV:  (dept)          => apiFetch('/api/faculty/export/csv' + (dept ? '?dept=' + dept : '')),
});

// ══════════════════════════════════════════════════════════════
// ██████████  FEATURE 1: DEPARTMENT DRILL-DOWN  ██████████████
// ══════════════════════════════════════════════════════════════

/* Drill state — tracks where the user is in the hierarchy */
const DRILL = {
  level:   'institution', // institution | dept | course | section | students
  dept:    null,          // e.g. "CS"
  course:  null,          // e.g. "DS"
  section: null,          // e.g. "A"
  color:   '#4ecba8',
  _cache:  {},            // simple in-memory cache keyed by URL
};

/**
 * updateBreadcrumb — renders the interactive breadcrumb trail.
 * @param {Array<{label:string, action:function}>} crumbs
 */
function updateBreadcrumb(crumbs) {
  const el = document.getElementById('breadTrail');
  if (!el) return;
  el.innerHTML = crumbs.map((c, i) => {
    const isLast = i === crumbs.length - 1;
    const cls = isLast ? 'bc-item active' : 'bc-item';
    const btn = isLast
      ? `<span class="${cls}">${c.label}</span>`
      : `<button class="${cls}" onclick="(${c.action.toString()})()">${c.label}</button>`;
    return btn + (isLast ? '' : '<span class="bc-sep"><i class="fa fa-chevron-right"></i></span>');
  }).join('');
}

/**
 * initDeptDrill — entry point called when the Departments page is shown.
 * Renders the Institution Overview (level 0).
 */
async function initDeptDrill() {
  DRILL.level = 'institution';
  DRILL.dept = DRILL.course = DRILL.section = null;

  updateBreadcrumb([{ label: '🏫 Institution', action: () => {} }]);

  const drill = document.getElementById('drillContent');
  if (!drill) return;
  drill.innerHTML = _drillLoading('Loading departments...');

  try {
    const data = await api.departments();
    window._deptTaxonomy = data.taxonomy || {};
    renderDeptCards(data.departments || []);
  } catch (e) {
    drill.innerHTML = _drillError(e.message, 'initDeptDrill()');
  }
}

/**
 * renderDeptCards — renders the institution-level department grid.
 * @param {Array} depts - array from GET /api/departments
 */
function renderDeptCards(depts) {
  const drill = document.getElementById('drillContent');
  if (!drill) return;

  // KPI row across all depts
  const totalStudents = depts.reduce((s, d) => s + d.total_students, 0);
  const avgAtt        = depts.length
    ? Math.round(depts.reduce((s, d) => s + d.avg_att, 0) / depts.length)
    : 0;
  const critical      = depts.reduce((s, d) => s + d.poor, 0);

  drill.innerHTML = `
    <!-- Institution KPI strip -->
    <div class="kpi-strip" style="margin-bottom:24px">
      ${kpiMini('Total Departments', depts.length,          '#4ecba8')}
      ${kpiMini('Total Students',    totalStudents,          '#4da6f5')}
      ${kpiMini('Avg Attendance',    avgAtt + '%',           '#ffb347')}
      ${kpiMini('Critical Students', critical,               '#ff7070')}
    </div>

    <!-- Dept cards grid -->
    <div class="dept-card-grid">
      ${depts.map(d => _deptCard(d)).join('')}
    </div>

    <!-- Institution bar chart -->
    <div class="card" style="margin-top:24px">
      <div class="card-head">
        <h4><i class="fa fa-chart-bar"></i> Department Attendance Overview</h4>
      </div>
      <div class="chart-pad"><canvas id="deptOverviewChart" height="160"></canvas></div>
    </div>`;

  // Render bar chart after DOM settles
  setTimeout(() => {
    mkBar(
      'deptOverviewChart',
      depts.map(d => d.name),
      depts.map(d => d.avg_att),
      depts.map(d => d.color),
      '%'
    );
  }, 80);
}

/**
 * _deptCard — builds one department card HTML string.
 */
function _deptCard(d) {
  const att = d.avg_att || 0;
  const st  = getStatus(att);
  return `
    <div class="d-card" style="--dc:${d.color}" onclick="drillToCourse('${d.key}')">
      <div class="dc-emoji">${d.emoji}</div>
      <div class="dc-name">${d.name}</div>
      <div class="dc-meta">
        <span><i class="fa fa-book"></i> ${d.course_count} courses</span>
        <span><i class="fa fa-users"></i> ${d.total_students} students</span>
      </div>
      <div class="dc-att-row">
        ${attBar(att)}
      </div>
      <div class="dc-stats-row">
        <span class="dc-stat good">✓ ${d.good}</span>
        <span class="dc-stat warn">⚠ ${d.warn}</span>
        <span class="dc-stat poor">✗ ${d.poor}</span>
      </div>
      <div class="dc-action">View Courses <i class="fa fa-arrow-right"></i></div>
    </div>`;
}

/**
 * drillToCourse — Level 2: Course list for a department.
 * @param {string} deptKey - e.g. "CS"
 */
async function drillToCourse(deptKey) {
  DRILL.level = 'dept';
  DRILL.dept  = deptKey;

  updateBreadcrumb([
    { label: '🏫 Institution', action: initDeptDrill },
    { label: '🏢 ' + (window._deptTaxonomy?.[deptKey]?.name || deptKey), action: () => {} },
  ]);

  const drill = document.getElementById('drillContent');
  drill.innerHTML = _drillLoading('Loading courses...');

  try {
    const data = await api.deptCourses(deptKey);
    const courses  = data.courses || [];
    const deptName = data.dept_name || deptKey;
    const color    = data.dept_color || '#4ecba8';
    DRILL.color    = color;

    // Summary KPIs
    const totalStu = courses.reduce((s, c) => s + c.total, 0);
    const avgAtt   = courses.length
      ? Math.round(courses.reduce((s, c) => s + c.avg_att, 0) / courses.length)
      : 0;
    const crit     = courses.reduce((s, c) => s + c.poor, 0);

    drill.innerHTML = `
      <div class="kpi-strip" style="margin-bottom:24px">
        ${kpiMini('Courses', courses.length, color)}
        ${kpiMini('Students', totalStu,       '#4da6f5')}
        ${kpiMini('Avg Att', avgAtt + '%',   '#ffb347')}
        ${kpiMini('Critical', crit,           '#ff7070')}
      </div>

      <div class="dept-card-grid">
        ${courses.map(c => _courseCard(c, deptKey, color)).join('')}
      </div>

      <div class="card" style="margin-top:24px">
        <div class="card-head">
          <h4><i class="fa fa-chart-bar"></i> Course-wise Attendance — ${deptName}</h4>
        </div>
        <div class="chart-pad"><canvas id="courseBarChart" height="160"></canvas></div>
      </div>`;

    setTimeout(() => {
      mkBar(
        'courseBarChart',
        courses.map(c => c.name),
        courses.map(c => c.avg_att),
        color, '%'
      );
    }, 80);
  } catch (e) {
    drill.innerHTML = _drillError(e.message, `drillToCourse('${deptKey}')`);
  }
}

function _courseCard(c, deptKey, color) {
  const att = c.avg_att || 0;
  return `
    <div class="d-card" style="--dc:${color}" onclick="drillToSection('${c.key}','${color}','${deptKey}')">
      <div class="dc-emoji">📚</div>
      <div class="dc-name">${c.name}</div>
      <div class="dc-meta">
        <span><i class="fa fa-layer-group"></i> ${c.secs?.join(', ') || '—'}</span>
        <span><i class="fa fa-users"></i> ${c.total} students</span>
      </div>
      <div class="dc-att-row">${attBar(att)}</div>
      <div class="dc-stats-row">
        <span class="dc-stat good">✓ ${c.good}</span>
        <span class="dc-stat warn">⚠ ${c.warn}</span>
        <span class="dc-stat poor">✗ ${c.poor}</span>
      </div>
      <div class="dc-action">View Sections <i class="fa fa-arrow-right"></i></div>
    </div>`;
}

/**
 * drillToSection — Level 3: Sections for a dept/course.
 */
async function drillToSection(courseKey, color, deptKey) {
  DRILL.level  = 'course';
  DRILL.course = courseKey;
  DRILL.color  = color;

  const deptName   = window._deptTaxonomy?.[deptKey]?.name   || deptKey;
  const courseName = window._deptTaxonomy?.[deptKey]?.courses?.[courseKey]?.name || courseKey;

  updateBreadcrumb([
    { label: '🏫 Institution',    action: initDeptDrill },
    { label: '🏢 ' + deptName,   action: () => drillToCourse(deptKey) },
    { label: '📚 ' + courseName, action: () => {} },
  ]);

  const drill = document.getElementById('drillContent');
  drill.innerHTML = _drillLoading('Loading sections...');

  try {
    const data     = data2 = await api.courseSections(deptKey, courseKey);
    const sections = data.sections || [];
    const cName    = data.course_name || courseKey;

    const totalStu = sections.reduce((s, c) => s + c.total, 0);
    const avgAtt   = sections.length
      ? Math.round(sections.reduce((s, c) => s + c.avg_att, 0) / sections.length)
      : 0;

    drill.innerHTML = `
      <div class="kpi-strip" style="margin-bottom:24px">
        ${kpiMini('Sections',   sections.length,  color)}
        ${kpiMini('Students',   totalStu,          '#4da6f5')}
        ${kpiMini('Avg Att',    avgAtt + '%',      '#ffb347')}
        ${kpiMini('Critical',   sections.reduce((s, c) => s + c.poor, 0), '#ff7070')}
      </div>
      <div class="dept-card-grid dept-card-grid--sections">
        ${sections.map(sec => _secCard(sec, deptKey, courseKey, cName, color)).join('')}
      </div>
      <div class="two-col" style="margin-top:24px">
        <div class="card">
          <div class="card-head"><h4><i class="fa fa-chart-bar"></i> Section Attendance</h4></div>
          <div class="chart-pad"><canvas id="sectionBarChart" height="180"></canvas></div>
        </div>
        <div class="card">
          <div class="card-head"><h4><i class="fa fa-chart-pie"></i> Attendance Status</h4></div>
          <div class="chart-pad"><canvas id="sectionDonut" height="180"></canvas></div>
        </div>
      </div>`;

    setTimeout(() => {
      mkBar('sectionBarChart',
        sections.map(s => 'Section ' + s.section),
        sections.map(s => s.avg_att), color, '%');

      const good  = sections.reduce((s, c) => s + c.good, 0);
      const warn  = sections.reduce((s, c) => s + c.warn, 0);
      const poor  = sections.reduce((s, c) => s + c.poor, 0);
      mkDonut('sectionDonut',
        ['Good (≥75%)', 'Warning (65-75%)', 'Critical (<65%)'],
        [good, warn, poor],
        ['#4ecba8', '#ffb347', '#ff7070']);
    }, 80);
  } catch (e) {
    drill.innerHTML = _drillError(e.message, `drillToSection('${courseKey}',...)`);
  }
}

function _secCard(sec, deptKey, courseKey, courseName, color) {
  const att = sec.avg_att || 0;
  return `
    <div class="d-card" style="--dc:${color}"
         onclick="drillToSectionDetail('${courseKey}','${sec.section}','${color}','${deptKey}')">
      <div class="dc-emoji">🏛️</div>
      <div class="dc-name">Section ${sec.section}</div>
      <div class="dc-meta">
        <span><i class="fa fa-users"></i> ${sec.total} students</span>
      </div>
      <div class="dc-att-row">${attBar(att)}</div>
      <div class="dc-stats-row">
        <span class="dc-stat good">✓ ${sec.good}</span>
        <span class="dc-stat warn">⚠ ${sec.warn}</span>
        <span class="dc-stat poor">✗ ${sec.poor}</span>
      </div>
      <div class="dc-action">View Students <i class="fa fa-arrow-right"></i></div>
    </div>`;
}

/**
 * drillToSectionDetail — Level 4/5: Student list for a section.
 */
async function drillToSectionDetail(courseKey, section, color, deptKey) {
  DRILL.level   = 'students';
  DRILL.section = section;

  const deptName   = window._deptTaxonomy?.[deptKey]?.name   || deptKey;
  const courseName = window._deptTaxonomy?.[deptKey]?.courses?.[courseKey]?.name || courseKey;

  updateBreadcrumb([
    { label: '🏫 Institution',         action: initDeptDrill },
    { label: '🏢 ' + deptName,         action: () => drillToCourse(deptKey) },
    { label: '📚 ' + courseName,        action: () => drillToSection(courseKey, color, deptKey) },
    { label: '🏛️ Section ' + section,  action: () => {} },
  ]);

  const drill = document.getElementById('drillContent');
  drill.innerHTML = _drillLoading('Loading student list...');

  try {
    const data     = await api.sectionStudents(deptKey, courseKey, section);
    const students = data.students || [];
    const stats    = data.stats    || {};

    drill.innerHTML = `
      <div class="kpi-strip" style="margin-bottom:24px">
        ${kpiMini('Students',   stats.total || students.length, color)}
        ${kpiMini('Avg Att',    (stats.avg_att || 0) + '%',     '#4da6f5')}
        ${kpiMini('Good (≥75%)', stats.good || 0,               '#4ecba8')}
        ${kpiMini('Warning',    stats.warn  || 0,               '#ffb347')}
        ${kpiMini('Critical',   stats.poor  || 0,               '#ff7070')}
      </div>

      <div class="two-col" style="margin-bottom:24px">
        <div class="card">
          <div class="card-head"><h4><i class="fa fa-chart-pie"></i> Attendance Distribution</h4></div>
          <div class="chart-pad"><canvas id="stuDistDonut" height="190"></canvas></div>
        </div>
        <div class="card">
          <div class="card-head"><h4><i class="fa fa-chart-bar"></i> Top/Bottom Students</h4></div>
          <div class="chart-pad"><canvas id="stuBarChart" height="190"></canvas></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h4><i class="fa fa-users"></i> Student List — ${courseName || courseKey} · Section ${section}</h4>
          <div class="ch-actions">
            <div class="search-box">
              <i class="fa fa-search"></i>
              <input id="stuDrillSearch" placeholder="Search student..."
                     oninput="filterDrillStudents()"/>
            </div>
            <select class="sel-sm" id="stuDrillFilter" onchange="filterDrillStudents()">
              <option value="">All</option>
              <option value="good">✓ Good</option>
              <option value="warn">⚠ Warning</option>
              <option value="poor">✗ Critical</option>
            </select>
          </div>
        </div>
        <div class="table-scroll">
          <table class="data-tbl" id="stuDrillTable">
            <thead>
              <tr>
                <th>#</th><th>Name</th><th>Roll No</th>
                <th>Present</th><th>Attendance</th><th>Last Seen</th><th>Status</th>
              </tr>
            </thead>
            <tbody id="stuDrillTbody">
              ${_stuRows(students)}
            </tbody>
          </table>
        </div>
      </div>`;

    // Cache students for filtering
    window._drillStudents = students;

    setTimeout(() => {
      mkDonut('stuDistDonut',
        ['Good (≥75%)', 'Warning (65-75%)', 'Critical (<65%)'],
        [stats.good || 0, stats.warn || 0, stats.poor || 0],
        ['#4ecba8', '#ffb347', '#ff7070']);

      // Top 6 + Bottom 6 bar
      const sorted  = [...students].sort((a, b) => b.att_pct - a.att_pct);
      const topBot  = [...sorted.slice(0, 6), ...sorted.slice(-6)].filter((v, i, a) =>
        a.findIndex(x => x.student_id === v.student_id) === i
      ).slice(0, 10);
      mkBar('stuBarChart',
        topBot.map(s => s.name.split(' ')[0]),
        topBot.map(s => s.att_pct),
        topBot.map(s => s.att_pct >= 75 ? '#4ecba8' : s.att_pct >= 65 ? '#ffb347' : '#ff7070'),
        '%');
    }, 80);
  } catch (e) {
    drill.innerHTML = _drillError(e.message, `drillToSectionDetail(...)`);
  }
}

/** Render table rows for the student list */
function _stuRows(students) {
  if (!students.length) {
    return `<tr><td colspan="7" style="text-align:center;padding:28px;color:var(--text3)">
              No students found in this section.<br>
              <small>Students must be enrolled via <code>python main.py → [1] Enrol</code>
              and their <code>section</code> field set.</small>
            </td></tr>`;
  }
  return students.map((s, i) => {
    const st = getStatus(s.att_pct);
    return `<tr>
      <td style="font-family:var(--mono);color:var(--text3)">${i + 1}</td>
      <td><strong>${s.name}</strong></td>
      <td><code>${s.roll_number}</code></td>
      <td style="font-family:var(--mono)">${s.present}/${s.total}</td>
      <td>${attBar(s.att_pct)}</td>
      <td style="font-size:.75rem;color:var(--text3)">${s.last_seen || '—'}</td>
      <td>${statusBadge(st)}</td>
    </tr>`;
  }).join('');
}

/** Filter the student table in real time */
function filterDrillStudents() {
  const q   = (document.getElementById('stuDrillSearch')?.value || '').toLowerCase();
  const flt = document.getElementById('stuDrillFilter')?.value || '';
  const all = window._drillStudents || [];
  const filtered = all.filter(s => {
    const nameMatch = (s.name || '').toLowerCase().includes(q) ||
                      (s.roll_number || '').toLowerCase().includes(q);
    const statusMatch = !flt || s.status === flt;
    return nameMatch && statusMatch;
  });
  const tbody = document.getElementById('stuDrillTbody');
  if (tbody) tbody.innerHTML = _stuRows(filtered);
}

// ── Drill UI helpers ─────────────────────────────────────────

/**
 * kpiMini — compact KPI card (used inside the drill area).
 */
function kpiMini(title, value, color) {
  return `<div class="kpi-card" style="--kc:${color}">
    <div class="kpi-val">${value}</div>
    <div class="kpi-lbl">${title}</div>
  </div>`;
}

/**
 * statusBadge — color-coded badge from a getStatus() result.
 */
function statusBadge(st) {
  return `<span class="badge ${st.bc}">${st.label}</span>`;
}

function _drillLoading(msg) {
  return `<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>${msg}</p></div>`;
}

function _drillError(msg, retry) {
  return `<div class="empty-msg" style="color:var(--coral-d)">
    <i class="fa fa-triangle-exclamation"></i>
    <p>${msg}</p>
    <button class="btn-primary" onclick="${retry}">
      <i class="fa fa-rotate-right"></i> Retry
    </button>
  </div>`;
}


// ══════════════════════════════════════════════════════════════
// ██████████  FEATURE 2: FACULTY MANAGEMENT  ████████████████
// ══════════════════════════════════════════════════════════════

/* Runtime state for faculty feature */
const FAC_STATE = {
  editLogId:  null,   // null = new mark, number = edit existing
  editFacId:  null,
  allFaculty: [],
};

/**
 * renderFacultyPage — full page render.
 * Called whenever the Faculty Management page is shown.
 */
async function renderFacultyPage() {
  // Populate dept filter
  const deptSel = document.getElementById('facMgmtDept');
  if (deptSel && deptSel.options.length <= 1) {
    const depts = ['CS', 'ECE', 'MECH', 'CIVIL', 'IT'];
    depts.forEach(d => deptSel.innerHTML += `<option value="${d}">${d}</option>`);
  }

  // Set today's date on the date picker if empty
  const datePicker = document.getElementById('facMgmtDate');
  if (datePicker && !datePicker.value)
    datePicker.value = new Date().toISOString().slice(0, 10);

  await Promise.all([
    _renderFacKpis(),
    _renderFacCharts(),
    _renderFacTable(),
  ]);
}

/* ── KPI strip ────────────────────────────────────────────── */
async function _renderFacKpis() {
  const strip = document.getElementById('facKpiStrip');
  if (!strip) return;
  strip.innerHTML = `<div class="kpi-card" style="--kc:#4ecba8">
    <div class="kpi-icon"><i class="fa fa-spinner fa-spin"></i></div>
    <div class="kpi-val">—</div><div class="kpi-lbl">Loading...</div>
  </div>`.repeat(4);
  try {
    const s = await api.facultyAnalytics();
    strip.innerHTML = `
      ${kpi('Total Faculty',   s.total_faculty,                'fa-chalkboard-teacher','#4ecba8')}
      ${kpi('Present Today',   s.present_today,                'fa-circle-check',       '#4da6f5')}
      ${kpi('Absent Today',    s.absent_today,                 'fa-circle-xmark',       '#ff7070')}
      ${kpi('Avg Att (30d)',   (s.avg_att_30d || 0) + '%',     'fa-chart-line',         '#ffb347')}`;
    window._facAnalytics = s;
  } catch (e) {
    strip.innerHTML = `<div style="color:var(--coral-d);padding:12px">${e.message}</div>`;
  }
}

/* ── Charts ──────────────────────────────────────────────── */
async function _renderFacCharts() {
  try {
    const s = window._facAnalytics || await api.facultyAnalytics();
    window._facAnalytics = s;

    // Dept bar chart
    setTimeout(() => {
      if (s.dept_chart?.length) {
        mkBar('facDeptBarChart',
          s.dept_chart.map(d => d.dept),
          s.dept_chart.map(d => d.att_pct),
          '#4ecba8', '%');
      }

      // Status donut
      const do_data = s.status_donut || {};
      mkDonut('facStatusDonut',
        ['Present', 'Absent', 'Late', 'On Duty', 'Not Marked'],
        [do_data.present || 0, do_data.absent || 0, do_data.late || 0,
         do_data.od || 0, do_data.not_marked || 0],
        ['#4ecba8', '#ff7070', '#ffb347', '#4da6f5', '#c8d6e8']);

      // Faculty comparison bar (top/bottom by att%)
      if (s.comparison?.length) {
        const slice = s.comparison.slice(0, 10);
        mkBar('facSubjectChart',
          slice.map(f => f.name.split(' ').pop()),
          slice.map(f => f.att_pct),
          slice.map(f => f.att_pct >= 75 ? '#4ecba8' : f.att_pct >= 65 ? '#ffb347' : '#ff7070'),
          '%');
      }
    }, 80);
  } catch (e) {
    log.error && console.warn('_renderFacCharts:', e.message);
  }
}

/* ── Faculty table ───────────────────────────────────────── */
async function _renderFacTable() {
  const tbody = document.getElementById('facTbody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px">
    <i class="fa fa-spinner fa-spin"></i></td></tr>`;

  const dept   = document.getElementById('facMgmtDept')?.value  || '';
  const search = document.getElementById('facSearch')?.value.trim() || '';
  const date   = document.getElementById('facMgmtDate')?.value  || '';

  try {
    const rows = await api.faculty(dept || null, search || null, date || null);
    FAC_STATE.allFaculty = rows;

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;
        color:var(--text3)">No faculty found.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(f => _facRow(f)).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:20px;
      color:var(--coral-d)">${e.message}</td></tr>`;
  }
}

/** Build one table row for a faculty member */
function _facRow(f) {
  const att  = f.att_pct || 0;
  const st   = getStatus(att);
  const subs = _parseSubs(f.subjects);
  const today = f.today_status || 'not_marked';
  const todayBadge = _todayBadge(today);
  const initls = f.name.split(' ').filter(w => w).map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return `<tr>
    <td>
      <div style="display:flex;align-items:center;gap:10px">
        <div class="fac-av" style="background:var(--mint-l);color:var(--mint-d)">${initls}</div>
        <div>
          <div style="font-weight:700">${f.name}</div>
          <div style="font-size:.72rem;color:var(--text3)">${f.email || '—'}</div>
        </div>
      </div>
    </td>
    <td><code>${f.fac_id}</code></td>
    <td><span class="badge b-lav">${f.dept}</span></td>
    <td style="font-size:.78rem;max-width:140px">${subs.join(', ') || '—'}</td>
    <td style="font-size:.78rem;color:var(--text2)">${f.designation || '—'}</td>
    <td>${todayBadge}</td>
    <td>${attBar(att)}</td>
    <td>
      <div style="display:flex;gap:6px">
        <button class="btn-sm" title="Mark/Edit Attendance"
                onclick="editFacAtt('${f.fac_id}', null)">
          <i class="fa fa-calendar-check"></i>
        </button>
        <button class="btn-sm" title="View Profile"
                onclick="viewFacDetail('${f.fac_id}')">
          <i class="fa fa-eye"></i>
        </button>
      </div>
    </td>
  </tr>`;
}

function _todayBadge(status) {
  const map = {
    present:    ['b-g',   '✓ Present'],
    absent:     ['b-c',   '✗ Absent'],
    late:       ['b-amber','⏰ Late'],
    halfday:    ['b-w',   '½ Half Day'],
    od:         ['b-lav', '📋 On Duty'],
    leave:      ['b-d',   '🌿 Leave'],
    not_marked: ['b-d',   '— Not Marked'],
  };
  const [cls, lbl] = map[status] || map.not_marked;
  return `<span class="badge ${cls}">${lbl}</span>`;
}

function _parseSubs(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw); } catch { return [raw]; }
}

/* ── Mark Faculty Attendance Modal ──────────────────────── */

/**
 * openMarkFacultyModal — opens the modal for marking attendance.
 * Called from the page-header "+ Mark Attendance" button.
 */
function openMarkFacultyModal() {
  FAC_STATE.editLogId = null;
  FAC_STATE.editFacId = null;
  _openFacModal(null, null);
}

/**
 * editFacAtt — open modal pre-filled for a faculty/log.
 * @param {string} facId  - e.g. "FAC001"
 * @param {number|null} logId - null = new entry for today
 */
function editFacAtt(facId, logId = null) {
  FAC_STATE.editFacId = facId;
  FAC_STATE.editLogId = logId;
  _openFacModal(facId, logId);
}

async function _openFacModal(prefacId, logId) {
  // Populate faculty dropdown
  const facSel = document.getElementById('fam_faculty');
  if (facSel) {
    facSel.innerHTML = '<option value="">Select faculty...</option>';
    const rows = FAC_STATE.allFaculty.length
      ? FAC_STATE.allFaculty
      : await api.faculty().catch(() => []);
    rows.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.fac_id;
      opt.textContent = `${f.name} (${f.fac_id})`;
      if (f.fac_id === prefacId) opt.selected = true;
      facSel.appendChild(opt);
    });
  }

  // Set date to today
  const dateFld = document.getElementById('fam_date');
  if (dateFld && !dateFld.value)
    dateFld.value = new Date().toISOString().slice(0, 10);

  // Reset other fields
  const statusFld = document.getElementById('fam_status');
  if (statusFld) statusFld.value = 'present';
  const timeFld = document.getElementById('fam_time');
  if (timeFld) timeFld.value = '09:00';
  const reasonFld = document.getElementById('fam_reason');
  if (reasonFld) reasonFld.value = '';
  const updFld = document.getElementById('fam_updater');
  if (updFld) updFld.value = '';

  // If logId provided, fetch and pre-fill
  if (logId && prefacId) {
    try {
      const detail = await api.facultyDetail(prefacId);
      const log = (detail.attendance_log || []).find(l => l.id === logId);
      if (log) {
        if (statusFld) statusFld.value = log.status || 'present';
        if (dateFld)   dateFld.value   = log.att_date || dateFld.value;
        if (timeFld && log.arrival_time) timeFld.value = log.arrival_time;
        if (reasonFld) reasonFld.value = log.reason || '';
        if (updFld)    updFld.value    = log.updated_by || '';
      }
    } catch {}
  }

  // Update modal title
  const header = document.querySelector('#facAttModal .modal-header h3');
  if (header) {
    header.innerHTML = logId
      ? '<i class="fa fa-pen-to-square"></i> Edit Faculty Attendance'
      : '<i class="fa fa-user-clock"></i> Mark Faculty Attendance';
  }

  document.getElementById('facAttModal')?.classList.remove('dn');
}

/**
 * saveFacultyAttendance — called by the modal Save button.
 * POST for new entries, PUT for edits.
 */
async function saveFacultyAttendance() {
  const facId   = document.getElementById('fam_faculty')?.value?.trim();
  const attDate = document.getElementById('fam_date')?.value;
  const status  = document.getElementById('fam_status')?.value;
  const time    = document.getElementById('fam_time')?.value;
  const reason  = document.getElementById('fam_reason')?.value.trim();
  const updater = document.getElementById('fam_updater')?.value.trim();

  if (!facId)   { toast('Select a faculty member', 'warn'); return; }
  if (!attDate) { toast('Date is required', 'warn'); return; }
  if (!updater) { toast('Updated By field is required', 'warn'); return; }

  const payload = {
    fac_id:       facId,
    att_date:     attDate,
    status:       status,
    arrival_time: time || null,
    reason:       reason,
    updated_by:   updater,
  };

  const saveBtn = document.querySelector('#facAttModal .btn-primary');
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Saving...';
  }

  try {
    if (FAC_STATE.editLogId) {
      // Edit existing log
      await api.editFacAttApi(FAC_STATE.editFacId, FAC_STATE.editLogId, payload);
      toast('Attendance record updated!', 'success');
    } else {
      // New entry
      await api.markFacAtt(payload);
      toast('Faculty attendance marked!', 'success');
    }
    closeModal('facAttModal');
    await renderFacultyPage(); // Refresh
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<i class="fa fa-save"></i> Save';
    }
  }
}

/**
 * viewFacDetail — open the info modal with a faculty's full profile.
 * @param {string} facId
 */
async function viewFacDetail(facId) {
  const titleEl = document.getElementById('infoModalTitle');
  const bodyEl  = document.getElementById('infoModalBody');
  if (!titleEl || !bodyEl) return;

  titleEl.innerHTML = '<i class="fa fa-user-tie"></i> Faculty Profile';
  bodyEl.innerHTML  = '<div style="text-align:center;padding:24px"><i class="fa fa-spinner fa-spin fa-2x"></i></div>';
  document.getElementById('infoModal')?.classList.remove('dn');

  try {
    const f   = await api.facultyDetail(facId);
    const subs = _parseSubs(f.subjects);
    const st  = getStatus(f.att_pct || 0);
    const initls = f.name.split(' ').filter(w => w).map(w => w[0]).join('').slice(0, 2).toUpperCase();

    // Monthly sparkline data
    const monthly = f.monthly || [];
    const canvasId = 'facDetailChart_' + facId;

    bodyEl.innerHTML = `
      <!-- Profile header -->
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
        <div class="fac-av fac-av--lg"
             style="background:var(--lav-l);color:var(--lav-d);font-size:1.6rem">
          ${initls}
        </div>
        <div>
          <div style="font-size:1.15rem;font-weight:800">${f.name}</div>
          <div style="font-size:.8rem;color:var(--text2)">${f.designation || '—'} · ${f.dept}</div>
          <div style="font-size:.75rem;color:var(--text3);margin-top:3px">
            <i class="fa fa-envelope"></i> ${f.email || '—'}
            &nbsp;·&nbsp;
            <i class="fa fa-phone"></i> ${f.mobile || '—'}
          </div>
        </div>
      </div>

      <!-- KPI row -->
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px">
        ${_miniStatBox('Att %',     f.att_pct + '%',  st.color)}
        ${_miniStatBox('Present',   f.present_days,   'var(--mint-d)')}
        ${_miniStatBox('Absent',    f.absent_days,    'var(--coral-d)')}
        ${_miniStatBox('Total',     f.total_days,     'var(--text2)')}
      </div>

      <!-- Subjects -->
      <div style="margin-bottom:14px">
        <div style="font-size:.72rem;font-weight:700;color:var(--text3);
                    text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">
          Subjects
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          ${subs.map(s => `<span class="badge b-lav">${s}</span>`).join('') || '<em style="color:var(--text3)">—</em>'}
        </div>
      </div>

      <!-- Monthly chart -->
      ${monthly.length ? `
        <div style="margin-bottom:14px">
          <div style="font-size:.72rem;font-weight:700;color:var(--text3);
                      text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">
            Monthly Attendance %
          </div>
          <canvas id="${canvasId}" height="90"></canvas>
        </div>` : ''}

      <!-- Recent log (last 7 entries) -->
      <div>
        <div style="font-size:.72rem;font-weight:700;color:var(--text3);
                    text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">
          Recent Attendance Log
        </div>
        <div class="table-scroll" style="max-height:200px">
          <table class="data-tbl">
            <thead>
              <tr><th>Date</th><th>Status</th><th>Time</th><th>Reason</th><th>By</th></tr>
            </thead>
            <tbody>
              ${(f.attendance_log || []).slice(0, 10).map(l => `
                <tr>
                  <td style="font-family:var(--mono)">${l.att_date}</td>
                  <td>${_todayBadge(l.status)}</td>
                  <td style="font-family:var(--mono)">${l.arrival_time || '—'}</td>
                  <td style="font-size:.75rem;color:var(--text2)">${l.reason || '—'}</td>
                  <td style="font-size:.72rem;color:var(--text3)">${l.updated_by || '—'}</td>
                </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;padding:16px;color:var(--text3)">No log yet</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>`;

    // Render monthly chart
    if (monthly.length) {
      setTimeout(() => {
        mkBar(canvasId,
          monthly.map(m => m.month),
          monthly.map(m => m.pct),
          monthly.map(m => m.pct >= 75 ? '#4ecba8' : m.pct >= 65 ? '#ffb347' : '#ff7070'),
          '%');
      }, 80);
    }

    // Override footer button
    const footer = document.querySelector('#infoModal .modal-footer');
    if (footer) {
      footer.innerHTML = `
        <button class="btn-secondary" onclick="closeModal('infoModal')">Close</button>
        <button class="btn-primary" onclick="editFacAtt('${facId}', null); closeModal('infoModal')">
          <i class="fa fa-calendar-check"></i> Mark Attendance
        </button>`;
    }
  } catch (e) {
    bodyEl.innerHTML = `<div style="color:var(--coral-d);padding:20px">${e.message}</div>`;
  }
}

function _miniStatBox(label, value, color) {
  return `<div style="background:var(--bg);border-radius:var(--r-sm);
                      padding:10px 12px;text-align:center">
    <div style="font-size:1.1rem;font-weight:800;color:${color}">${value}</div>
    <div style="font-size:.7rem;color:var(--text3);margin-top:2px">${label}</div>
  </div>`;
}

/* ── Faculty CSV export ───────────────────────────────────── */
async function exportFacultyCSV() {
  const dept = document.getElementById('facMgmtDept')?.value || '';
  try {
    const res  = await api.exportFacultyCSV(dept || null);
    const blob = await res.blob();
    const a = Object.assign(document.createElement('a'), {
      href:     URL.createObjectURL(blob),
      download: 'faculty_attendance_' + new Date().toISOString().slice(0, 10) + '.csv',
    });
    a.click();
    toast('CSV exported!', 'success');
  } catch (e) {
    toast('Export failed: ' + e.message, 'error');
  }
}

// ── Override stubs replaced by real implementations ──────────
// The original app.js had empty stub functions for these.
// They are now fully implemented above.
// No redeclaration needed — JavaScript hoists function declarations,
// but because this file is loaded after app.js, the real functions
// defined here will shadow the stubs only if we use `window.` assignment
// or the stubs were declared as `function` (which can be overridden).
//
// Wrapping in a DOMContentLoaded handler ensures app.js has run:
document.addEventListener('DOMContentLoaded', () => {
  // Patch stub functions with real implementations
  window.initDeptDrill           = initDeptDrill;
  window.updateBreadcrumb        = updateBreadcrumb;
  window.renderDeptCards         = renderDeptCards;
  window.drillToCourse           = drillToCourse;
  window.drillToSection          = drillToSection;
  window.drillToSectionDetail    = drillToSectionDetail;
  window.filterDrillStudents     = filterDrillStudents;
  window.kpiMini                 = kpiMini;
  window.statusBadge             = statusBadge;

  window.renderFacultyPage       = renderFacultyPage;
  window.openMarkFacultyModal    = openMarkFacultyModal;
  window.editFacAtt              = editFacAtt;
  window.saveFacultyAttendance   = saveFacultyAttendance;
  window.viewFacDetail           = viewFacDetail;
  window.exportFacultyCSV        = exportFacultyCSV;

  // Patch showPage to call initDeptDrill for the departments page
  const _orig = window.showPage;
  window.showPage = function(pid) {
    _orig(pid);
    if (pid === 'departments') initDeptDrill();
    if (pid === 'faculty')     renderFacultyPage();
  };
});