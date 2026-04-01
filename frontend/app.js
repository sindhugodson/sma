// 'use strict';
// /* ═══════════════════════════════════════════════════════════
//    EduTrack Pro — Frontend v9.6
//    Connects to the Smart Attendance System backend REST API.
//    Base URL: same origin (served by FastAPI at /app)
//    All data comes from the SQLite database via /api/* endpoints.
//    ═══════════════════════════════════════════════════════════ */

// const API_BASE = '';
// let _token = null, _role = null, _user = {};

// async function apiFetch(path, opts = {}) {
//   const headers = { 'Content-Type': 'application/json' };
//   if (_token) headers['Authorization'] = 'Bearer ' + _token;
//   const res = await fetch(API_BASE + path, { ...opts, headers: { ...headers, ...(opts.headers||{}) } });
//   if (!res.ok) {
//     let detail = 'HTTP ' + res.status;
//     try { detail = (await res.json()).detail || detail; } catch(e) {}
//     throw new Error(detail);
//   }
//   const ct = res.headers.get('content-type') || '';
//   return ct.includes('application/json') ? res.json() : res;
// }

// const api = {
//   login:         (email, pass, role, facId) => apiFetch('/api/login', { method:'POST', body:JSON.stringify({email, password:pass, role, fac_id:facId||''}) }),
//   students:      ()          => apiFetch('/api/students'),
//   addStudent:    (data)      => apiFetch('/api/students', { method:'POST', body:JSON.stringify(data) }),
//   deleteStudent: (id)        => apiFetch('/api/students/'+id, { method:'DELETE' }),
//   todayAtt:      (period)    => apiFetch('/api/attendance/today'+(period?'?period='+encodeURIComponent(period):'')),
//   attSummary:    (days)      => apiFetch('/api/attendance/summary?days='+(days||30)),
//   override:      (data)      => apiFetch('/api/attendance/override', { method:'POST', body:JSON.stringify(data) }),
//   sessionStart:  (period)    => apiFetch('/api/session/start', { method:'POST', body:JSON.stringify({period}) }),
//   sessionStop:   ()          => apiFetch('/api/session/stop', { method:'POST' }),
//   sessionStatus: ()          => apiFetch('/api/session/status'),
//   trainStart:    ()          => apiFetch('/api/train', { method:'POST' }),
//   trainStatus:   ()          => apiFetch('/api/train/status'),
//   analytics:     ()          => apiFetch('/api/analytics/summary'),
//   timetable:     ()          => apiFetch('/api/timetable'),
//   settings:      ()          => apiFetch('/api/settings'),
//   saveSettings:  (data)      => apiFetch('/api/settings', { method:'POST', body:JSON.stringify(data) }),
//   periodStats:   ()          => apiFetch('/api/analytics/period'),
//   exportCsv:     ()          => apiFetch('/api/export/csv'),
// };

// const APP = { role:'admin', currentPage:'dashboard', attPollTimer:null, trainPollTimer:null, charts:{}, alertFilter:'all', localAlerts:[] };

// // ── LOGIN ──────────────────────────────────────────────────────
// let _pickedAdminRole = 'admin';

// function switchPortal(btn, portal) {
//   document.querySelectorAll('.ptab').forEach(b => b.classList.remove('active'));
//   btn.classList.add('active');
//   document.getElementById('adminPortal').classList.toggle('dn', portal !== 'admin');
//   document.getElementById('facultyPortal').classList.toggle('dn', portal !== 'faculty');
// }

// function pickAdminRole(btn) {
//   document.querySelectorAll('.role-chip').forEach(b => b.classList.remove('active'));
//   btn.classList.add('active');
//   _pickedAdminRole = btn.dataset.role;
// }

// function fillFacDemo() {
//   const v = document.getElementById('facDemoSelect').value;
//   if (v) document.getElementById('facIdInput').value = v;
// }

// async function loginAdmin() {
//   const email = document.getElementById('adminEmail').value.trim();
//   const pass  = document.getElementById('adminPass').value.trim();
//   const btns  = document.querySelectorAll('.btn-signin');
//   btns[0].innerHTML = '<i class="fa fa-spinner fa-spin"></i> Signing in...';
//   try {
//     const res = await api.login(email, pass, _pickedAdminRole, '');
//     _token = res.access_token; _role = res.role||_pickedAdminRole;
//     _user = { username: res.username||email, role: _role };
//     APP.role = _role;
//     startApp();
//   } catch(e) {
//     toast('Login failed: ' + e.message, 'error');
//     btns[0].innerHTML = '<i class="fa fa-right-to-bracket"></i> Sign In';
//   }
// }

// async function loginFaculty() {
//   const facId = document.getElementById('facIdInput').value.trim().toUpperCase();
//   const pass  = document.getElementById('facPassInput').value.trim();
//   const btns  = document.querySelectorAll('.btn-signin');
//   const btn   = btns[1]||btns[0];
//   if (!facId) { toast('Enter Faculty ID', 'warn'); return; }
//   btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Signing in...';
//   try {
//     const res = await api.login('', pass, 'faculty', facId);
//     _token = res.access_token; _role = 'faculty';
//     _user = { fac_id: facId, name: res.name||facId, role:'faculty' };
//     APP.role = 'faculty';
//     startApp();
//   } catch(e) {
//     toast('Login failed: ' + e.message, 'error');
//     btn.innerHTML = '<i class="fa fa-right-to-bracket"></i> Faculty Sign In';
//   }
// }

// function doLogout() {
//   _token=null; _role=null; _user={};
//   clearInterval(APP.attPollTimer); clearInterval(APP.trainPollTimer);
//   document.getElementById('appShell').classList.add('dn');
//   document.getElementById('loginScreen').style.display = '';
// }

// function startApp() {
//   document.getElementById('loginScreen').style.display = 'none';
//   document.getElementById('appShell').classList.remove('dn');
//   populateFacSelect();
//   buildSideNav();
//   setTopbarProfile();
//   startClock();
//   showPage(APP.role==='faculty' ? 'fac-dashboard' : 'dashboard');
//   toast('Welcome! Signed in as '+getRoleLabel(), 'success');
// }

// function getRoleLabel() {
//   const m={admin:'Administrator',hod:'HOD',classincharge:'Class Incharge',teacher:'Teacher',faculty:_user.name||'Faculty'};
//   return m[APP.role]||APP.role;
// }

// function populateFacSelect() {
//   const sel = document.getElementById('facDemoSelect');
//   if (sel) {
//     sel.innerHTML = '<option value="">-- Demo Faculty --</option>';
//     ['FAC001','FAC002','FAC003','FAC004','FAC005'].forEach(id => sel.innerHTML += '<option value="'+id+'">'+id+'</option>');
//   }
// }

// // ── NAV ───────────────────────────────────────────────────────
// const NAV_CFG = {
//   admin:[
//     {section:'OVERVIEW',links:[{icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'}]},
//     {section:'STUDENT SYSTEM',links:[
//       {icon:'fa-camera',label:'Take Attendance',page:'attendance',pill:'LIVE'},
//       {icon:'fa-users',label:'Students',page:'students'},
//       {icon:'fa-calendar-week',label:'Timetable',page:'timetable'},
//     ]},
//     {section:'MANAGEMENT',links:[
//       {icon:'fa-pen-to-square',label:'Overrides',page:'overrides'},
//       {icon:'fa-chart-line',label:'Reports',page:'reports'},
//       {icon:'fa-bell',label:'Alerts',page:'alerts',pill:'alert'},
//       {icon:'fa-gear',label:'Settings',page:'settings'},
//     ]},
//     {section:'TRAINING',links:[{icon:'fa-brain',label:'Train Models',page:'train'}]},
//   ],
//   hod:[
//     {section:'OVERVIEW',links:[{icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'}]},
//     {section:'DATA',links:[
//       {icon:'fa-users',label:'Students',page:'students'},
//       {icon:'fa-chart-line',label:'Reports',page:'reports'},
//       {icon:'fa-bell',label:'Alerts',page:'alerts',pill:'alert'},
//     ]},
//   ],
//   classincharge:[
//     {section:'MY CLASS',links:[
//       {icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'},
//       {icon:'fa-camera',label:'Take Attendance',page:'attendance',pill:'LIVE'},
//       {icon:'fa-pen-to-square',label:'Overrides',page:'overrides'},
//       {icon:'fa-bell',label:'Alerts',page:'alerts',pill:'alert'},
//     ]},
//   ],
//   teacher:[
//     {section:'MY CLASSES',links:[
//       {icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'},
//       {icon:'fa-camera',label:'Take Attendance',page:'attendance',pill:'LIVE'},
//       {icon:'fa-pen-to-square',label:'Overrides',page:'overrides'},
//     ]},
//   ],
//   faculty:[
//     {section:'MY PORTAL',links:[
//       {icon:'fa-chart-pie',label:'My Dashboard',page:'fac-dashboard'},
//       {icon:'fa-calendar-week',label:'Timetable',page:'timetable'},
//       {icon:'fa-chart-line',label:'My Reports',page:'reports'},
//     ]},
//   ],
// };

// const PAGE_TITLES = {
//   dashboard:'Dashboard',attendance:'Student Attendance',students:'Student Management',
//   timetable:'Timetable',overrides:'Attendance Overrides',reports:'Reports & Analytics',
//   alerts:'Smart Alerts',settings:'System Settings',train:'Train Models',
//   'fac-dashboard':'My Dashboard',
// };

// function buildSideNav() {
//   const nav = document.getElementById('sbNav');
//   nav.innerHTML = '';
//   (NAV_CFG[APP.role]||NAV_CFG.admin).forEach(grp => {
//     const lbl = document.createElement('div');
//     lbl.className = 'nav-section-lbl'; lbl.textContent = grp.section;
//     nav.appendChild(lbl);
//     grp.links.forEach(lnk => {
//       const a = document.createElement('a');
//       a.className='nav-link'; a.dataset.page=lnk.page;
//       a.onclick = () => showPage(lnk.page);
//       let pill = lnk.pill==='LIVE' ? '<span class="nav-pill live">LIVE</span>' :
//                  lnk.pill==='alert' ? '<span class="nav-pill alert" id="navAlertPill">0</span>' : '';
//       a.innerHTML = '<i class="fa '+lnk.icon+'"></i><span>'+lnk.label+'</span>'+pill;
//       nav.appendChild(a);
//     });
//   });
// }

// function setTopbarProfile() {
//   const label = getRoleLabel();
//   setEl('sucAv', label.substring(0,2).toUpperCase());
//   setEl('sucName', label);
//   setEl('sucRole', APP.role==='faculty'?'Staff Faculty':label);
//   setEl('sucDept', APP.role==='faculty'?'My Portal':'Smart Attendance System');
//   setEl('tbpAv', label.substring(0,2).toUpperCase());
//   setEl('tbpName', label.split(' ')[0]);
//   setEl('tbpRole', APP.role);
// }

// function showPage(pid) {
//   document.querySelectorAll('.page').forEach(p => p.classList.add('dn'));
//   document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));
//   const pg = document.getElementById('pg-'+pid);
//   if (pg) pg.classList.remove('dn');
//   document.querySelector('[data-page="'+pid+'"]')?.classList.add('active');
//   setEl('tbPageTitle', PAGE_TITLES[pid]||pid);
//   APP.currentPage = pid;
//   closeSidebar();
//   const init={dashboard:renderDashboard,attendance:initAttendancePage,students:renderStudentsPage,
//     timetable:renderTimetablePage,overrides:renderOverridesPage,reports:renderReportsPage,
//     alerts:renderAlertsPage,settings:renderSettingsPage,train:renderTrainPage,'fac-dashboard':renderFacDashboard};
//   init[pid]?.();
// }

// function toggleSidebar(){ document.getElementById('sidebar').classList.toggle('open'); }
// function closeSidebar() { document.getElementById('sidebar').classList.remove('open'); }

// function startClock() {
//   const el = document.getElementById('tbClock');
//   const t = () => { if(el) el.textContent = new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); };
//   t(); setInterval(t,1000);
// }

// // ── DASHBOARD ─────────────────────────────────────────────────
// async function renderDashboard() {
//   if (APP.role==='faculty') { renderFacDashboard(); return; }
//   const cont = document.getElementById('dashboardContent');
//   if (!cont) return;
//   cont.innerHTML = '<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>Loading...</p></div>';
//   try {
//     const [data, today] = await Promise.all([api.analytics(), api.todayAtt()]);
//     const {total_students:total,present_today:present,absent_today:absent,pct_today:pct,avg_attendance:avgAtt,critical_count:crit} = data;
//     cont.innerHTML = `
//       <div class="page-header">
//         <div class="ph-left"><h2>${getRoleLabel()} Dashboard</h2>
//         <p>${new Date().toLocaleDateString('en-IN',{weekday:'long',year:'numeric',month:'long',day:'numeric'})}</p></div>
//         <div class="ph-right"><button class="btn-secondary" onclick="renderDashboard()"><i class="fa fa-rotate-right"></i> Refresh</button></div>
//       </div>
//       <div class="kpi-strip">
//         ${kpi('Total Students',total,'fa-users','#4ecba8')}
//         ${kpi('Present Today',present,'fa-circle-check','#4da6f5')}
//         ${kpi('Absent Today',absent,'fa-circle-xmark','#ff7070')}
//         ${kpi('Today %',pct+'%','fa-percent','#ffb347')}
//         ${kpi('30-day Avg',avgAtt+'%','fa-chart-line','#9b87f5')}
//         ${kpi('Critical',crit,'fa-radiation','#e05454')}
//       </div>
//       <div class="two-col">
//         <div class="card">
//           <div class="card-head"><h4><i class="fa fa-list-check"></i> Today's Attendance</h4>
//             <button class="btn-sm" onclick="exportTodayCSV()"><i class="fa fa-download"></i> CSV</button>
//           </div>
//           <div class="table-scroll"><table class="data-tbl">
//             <thead><tr><th>Name</th><th>ID</th><th>Period</th><th>Time</th><th>Confidence</th><th>Engine</th></tr></thead>
//             <tbody>${today.length?today.map(r=>'<tr><td><strong>'+(r.name||'?')+'</strong></td><td><code>'+(r.student_id||'?')+'</code></td><td>'+(r.period||'—')+'</td><td style="font-family:var(--mono)">'+String(r.time||'').slice(0,8)+'</td><td>'+confBadge(r.confidence)+'</td><td><span class="badge b-lav">'+(r.engine||'—')+'</span></td></tr>').join('')
//             :'<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text3)">No attendance today — start a camera session</td></tr>'}</tbody>
//           </table></div>
//         </div>
//         <div class="card">
//           <div class="card-head"><h4><i class="fa fa-chart-pie"></i> Today Status</h4></div>
//           <div class="chart-pad"><canvas id="dashDonut" height="200"></canvas></div>
//         </div>
//       </div>`;
//     setTimeout(() => mkDonut('dashDonut',['Present','Absent','Critical'],[present,absent-crit,crit],['#4ecba8','#4da6f5','#ff7070']), 60);
//   } catch(e) {
//     cont.innerHTML = '<div class="empty-msg"><i class="fa fa-triangle-exclamation"></i><p>'+e.message+'</p><button class="btn-primary" onclick="renderDashboard()"><i class="fa fa-rotate-right"></i> Retry</button></div>';
//   }
// }

// // ── ATTENDANCE ─────────────────────────────────────────────────
// function initAttendancePage() {
//   clearInterval(APP.attPollTimer);
//   const cb = document.getElementById('camViewport');
//   if (cb) {
//     cb.innerHTML = '<div class="cv-idle" id="cvIdle"><div class="cv-idle-icon"><i class="fa fa-camera-slash"></i></div><h4>Camera Offline</h4><p>Click Start Session to begin face recognition</p></div>'
//       +'<img id="mjpegImg" class="dn" src="" style="width:100%;height:100%;object-fit:cover;position:absolute;inset:0"/>'
//       +'<div class="cv-tag dn" id="cvTag">Scanning...</div>'
//       +'<div class="cv-live-badge dn" id="cvLiveBadge">● LIVE</div>';
//   }
//   // Add period input if not already present
//   const hdr = document.getElementById('attHeaderControls');
//   if (hdr && !document.getElementById('attPeriodInput')) {
//     hdr.innerHTML = '<input class="sel" id="attPeriodInput" placeholder="Period name e.g. Period_1" value="Period_1"/>' + hdr.innerHTML;
//   }
//   renderSessionStatus();
// }

// async function startAttendance() {
//   const p = (document.getElementById('attPeriodInput')?.value||'Period_1').trim();
//   try {
//     await api.sessionStart(p);
//     const img=document.getElementById('mjpegImg'), idle=document.getElementById('cvIdle'),
//           tag=document.getElementById('cvTag'), badge=document.getElementById('cvLiveBadge');
//     if(img){img.src='/video_feed?'+Date.now();img.classList.remove('dn');}
//     if(idle) idle.classList.add('dn');
//     if(tag)  tag.classList.remove('dn');
//     if(badge)badge.classList.remove('dn');
//     document.getElementById('btnStartCam').disabled=true;
//     document.getElementById('btnStopCam').disabled=false;
//     toast('Session started: '+p,'success');
//     clearInterval(APP.attPollTimer);
//     APP.attPollTimer = setInterval(renderSessionStatus,2500);
//   } catch(e) { toast('Start failed: '+e.message,'error'); }
// }

// async function stopAttendance() {
//   try {
//     await api.sessionStop();
//     clearInterval(APP.attPollTimer);
//     const img=document.getElementById('mjpegImg'),idle=document.getElementById('cvIdle'),
//           tag=document.getElementById('cvTag'),badge=document.getElementById('cvLiveBadge');
//     if(img){img.src='';img.classList.add('dn');}
//     if(idle){idle.classList.remove('dn');idle.innerHTML='<div class="cv-idle-icon"><i class="fa fa-check" style="color:var(--mint-d)"></i></div><h4 style="color:var(--mint-d)">Session Complete</h4><p>Check the log</p>';}
//     if(tag)  tag.classList.add('dn');
//     if(badge)badge.classList.add('dn');
//     document.getElementById('btnStartCam').disabled=false;
//     document.getElementById('btnStopCam').disabled=true;
//     toast('Session stopped','info');
//     renderSessionStatus();
//   } catch(e) { toast('Stop failed: '+e.message,'error'); }
// }

// async function renderSessionStatus() {
//   try {
//     const s = await api.sessionStatus();
//     setEl('alcP', s.marked_count+' Present');
//     setEl('alcA', s.absent_count+' Absent');
//     const bar = document.getElementById('alcProgBar');
//     if(bar&&s.total_students>0) bar.style.width=Math.min(s.marked_count/s.total_students*100,100)+'%';
//     const body = document.getElementById('alcBody');
//     if (!body) return;
//     if (!s.already_marked?.length) {
//       body.innerHTML = '<div class="alc-empty"><i class="fa fa-inbox"></i><p>No entries yet</p></div>';
//     } else {
//       body.innerHTML = s.already_marked.map(r=>'<div class="log-entry"><div class="le-av p">'+initials(r.name)+'</div><div><div class="le-name">'+r.name+'</div><div class="le-meta">'+r.student_id+'</div></div><span class="le-time">'+r.time+'</span></div>').join('');
//     }
//   } catch(e) {}
// }

// function resetAttSession(){ renderSessionStatus(); }
// function openOverrideFromAtt(){ openOverrideModal(); }

// async function exportTodayCSV() {
//   try {
//     const res=await api.exportCsv();
//     const blob=await res.blob();
//     const a=Object.assign(document.createElement('a'),{href:URL.createObjectURL(blob),download:'attendance_'+new Date().toISOString().slice(0,10)+'.csv'});
//     a.click(); toast('CSV exported!','success');
//   } catch(e){ toast('Export failed: '+e.message,'error'); }
// }

// // ── STUDENTS ──────────────────────────────────────────────────
// async function renderStudentsPage() {
//   const cont=document.getElementById('pg-students');
//   if(!cont) return;
//   cont.innerHTML=`<div class="page-header"><div class="ph-left"><h2>Student Management</h2><p>Students in SQLite database</p></div>
//     <div class="ph-right">
//       <input class="sel" id="stuSearch" placeholder="Search..." oninput="filterStuTable()"/>
//       <button class="btn-primary" onclick="openAddStudentModal()"><i class="fa fa-plus"></i> Add Student</button>
//     </div></div>
//     <div class="card"><div class="card-head"><h4><i class="fa fa-users"></i> Student Roster</h4>
//       <span id="stuCount" style="font-size:.78rem;color:var(--text3)">Loading...</span></div>
//     <div class="table-scroll"><table class="data-tbl">
//       <thead><tr><th>#</th><th>Name</th><th>Roll No</th><th>Section</th><th>Mobile</th><th>Enrolled</th><th>Actions</th></tr></thead>
//       <tbody id="stuTbody"><tr><td colspan="7" style="text-align:center;padding:20px"><i class="fa fa-spinner fa-spin"></i></td></tr></tbody>
//     </table></div></div>`;
//   try {
//     const students = await api.students();
//     window._allStudents = students;
//     renderStuRows(students);
//     setEl('stuCount', students.length+' students');
//   } catch(e) {
//     document.getElementById('stuTbody').innerHTML='<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--coral-d)">'+e.message+'</td></tr>';
//   }
// }

// function renderStuRows(students) {
//   const tbody=document.getElementById('stuTbody');
//   if(!tbody) return;
//   if(!students.length){tbody.innerHTML='<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text3)">No students yet. Enroll via python main.py → [1]</td></tr>';return;}
//   tbody.innerHTML=students.map((s,i)=>'<tr><td style="font-family:var(--mono);color:var(--text3)">'+(i+1)+'</td><td><strong>'+(s.name||'?')+'</strong></td><td><code>'+(s.roll_number||s.student_id||'?')+'</code></td><td>'+(s.section||'—')+'</td><td>'+(s.mobile||'—')+'</td><td style="font-size:.75rem;color:var(--text3)">'+(s.enrolled_on||'').slice(0,10)||'—'+'</td><td><button class="btn-sm" style="color:var(--coral-d)" onclick="deleteStudent(\''+s.student_id+'\')"><i class="fa fa-trash"></i></button></td></tr>').join('');
// }

// function filterStuTable(){ const q=(document.getElementById('stuSearch')?.value||'').toLowerCase(); renderStuRows((window._allStudents||[]).filter(s=>(s.name||'').toLowerCase().includes(q)||(s.roll_number||'').toLowerCase().includes(q))); }

// function openAddStudentModal() {
//   document.getElementById('infoModalTitle').innerHTML='<i class="fa fa-user-plus"></i> Add Student';
//   document.getElementById('infoModalBody').innerHTML='<p style="font-size:.82rem;color:var(--text2);margin-bottom:16px">Adds student to database. To enrol face: run <code>python main.py → [1] Enrol</code>.</p><div class="fg"><label>Full Name *</label><input id="ns_name" placeholder="e.g. Aarav Kumar"/></div><div class="fg-2"><div class="fg"><label>Roll Number *</label><input id="ns_roll" placeholder="cs22001"/></div><div class="fg"><label>Section</label><select id="ns_sec"><option value="A">A</option><option value="B">B</option></select></div></div><div class="fg"><label>Mobile</label><input id="ns_mobile" placeholder="10-digit"/></div>';
//   document.querySelector('#infoModal .modal-footer').innerHTML='<button class="btn-secondary" onclick="closeModal(\'infoModal\')">Cancel</button><button class="btn-primary" onclick="submitAddStudent()"><i class="fa fa-save"></i> Save</button>';
//   document.getElementById('infoModal').classList.remove('dn');
// }

// async function submitAddStudent() {
//   const name=document.getElementById('ns_name')?.value.trim(),roll=document.getElementById('ns_roll')?.value.trim(),section=document.getElementById('ns_sec')?.value,mobile=document.getElementById('ns_mobile')?.value.trim();
//   if(!name||!roll){toast('Name and Roll Number required','warn');return;}
//   try { const res=await api.addStudent({name,roll_number:roll,section,mobile}); closeModal('infoModal'); toast(name+' added! ID: '+res.student_id,'success'); renderStudentsPage(); }
//   catch(e) { toast('Add failed: '+e.message,'error'); }
// }

// async function deleteStudent(id) {
//   if(!confirm('Delete '+id+'? This removes attendance records too.')) return;
//   try { await api.deleteStudent(id); toast(id+' removed','info'); renderStudentsPage(); }
//   catch(e) { toast('Delete failed: '+e.message,'error'); }
// }

// // ── TIMETABLE ─────────────────────────────────────────────────
// async function renderTimetablePage() {
//   const ttCont=document.getElementById('ttContent');
//   if(!ttCont) return;
//   ttCont.innerHTML='<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>Loading...</p></div>';
//   try {
//     const periods=await api.timetable();
//     if(!periods.length){ttCont.innerHTML='<div class="empty-msg"><i class="fa fa-calendar-days"></i><p>No timetable configured. Add periods in config.py DEFAULT_PERIODS.</p></div>';return;}
//     ttCont.innerHTML='<div class="card"><div class="card-head"><h4><i class="fa fa-calendar-week"></i> Configured Periods</h4></div><div class="table-scroll"><table class="data-tbl"><thead><tr><th>#</th><th>Period Name</th><th>Start</th><th>End</th><th>Status</th></tr></thead><tbody>'+periods.map((p,i)=>'<tr><td style="font-family:var(--mono)">'+(i+1)+'</td><td><strong>'+(p.period_name||p.name||'?')+'</strong></td><td style="font-family:var(--mono)">'+(p.start_time||'—')+'</td><td style="font-family:var(--mono)">'+(p.end_time||'—')+'</td><td>'+(p.active?'<span class="badge b-g">Active</span>':'<span class="badge b-w">Inactive</span>')+'</td></tr>').join('')+'</tbody></table></div></div>';
//   } catch(e){ttCont.innerHTML='<div class="empty-msg"><i class="fa fa-triangle-exclamation"></i><p>'+e.message+'</p></div>';}
// }

// // ── OVERRIDES ─────────────────────────────────────────────────
// function renderOverridesPage() {
//   // Page content is in HTML — just ensure the override button works
//   loadOverrideStudents();
// }

// function openOverrideModal(type) {
//   const sel=document.getElementById('ov_type');
//   if(sel&&type) sel.value=type;
//   onOvTypeChange();
//   loadOverrideStudents();
//   document.getElementById('overrideModal').classList.remove('dn');
// }

// function onOvTypeChange() {
//   const type=document.getElementById('ov_type')?.value;
//   const sf=document.getElementById('ovStaffFields'),cf=document.getElementById('ovCatField');
//   if(type==='staff'){sf.style.display='block';cf.style.display='none';}
//   else if(type==='classincharge'){sf.style.display='none';cf.style.display='block';}
//   else{sf.style.display='none';cf.style.display='none';}
// }

// async function loadOverrideStudents() {
//   const sel=document.getElementById('ov_student');
//   if(!sel) return;
//   try {
//     const students=await api.students();
//     sel.innerHTML='<option value="">Select student</option>';
//     students.forEach(s=>sel.innerHTML+='<option value="'+s.student_id+'">'+s.name+' — '+(s.roll_number||s.student_id)+'</option>');
//   } catch(e){ sel.innerHTML='<option value="">Could not load students</option>'; }
// }

// function ovLoadCourses(){}
// function ovLoadStudents(){ loadOverrideStudents(); }

// async function submitOverride() {
//   const staffId=document.getElementById('ov_staffId')?.value.trim(),type=document.getElementById('ov_type')?.value,
//     studentId=document.getElementById('ov_student')?.value,period=document.getElementById('ov_period')?.value,
//     to=document.getElementById('ov_to')?.value,cat=document.getElementById('ov_cat')?.value,
//     reason=document.getElementById('ov_reason')?.value.trim();
//   if(!staffId){toast('Staff/Modifier ID required','warn');return;}
//   if(!studentId){toast('Select a student','warn');return;}
//   if(!reason){toast('Reason is mandatory','warn');return;}
//   if(type==='staff'&&!period){toast('Select period','warn');return;}
//   const actionMap={present:'mark_present',absent:'mark_absent',late:'mark_present',od:'mark_present',medical:'mark_present'};
//   try {
//     await api.override({student_id:studentId,period:period||'Manual',action:actionMap[to]||'mark_present',reason,modifier_id:staffId,category:cat||''});
//     closeModal('overrideModal'); toast('Override saved to database!','success');
//   } catch(e){ toast('Override failed: '+e.message,'error'); }
// }

// // ── REPORTS ───────────────────────────────────────────────────
// async function renderReportsPage() {
//   const pg=document.getElementById('pg-reports');
//   if(!pg) return;
//   pg.innerHTML=`<div class="page-header"><div class="ph-left"><h2>Reports & Analytics</h2><p>Attendance data from SQLite database</p></div>
//     <div class="ph-right"><select class="sel" id="repDays" onchange="renderReportsPage()"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option></select>
//     <button class="btn-primary" onclick="exportTodayCSV()"><i class="fa fa-download"></i> Export CSV</button></div></div>
//     <div class="kpi-strip" id="repKpis">${[1,2,3,4].map(()=>'<div class="kpi-card" style="--kc:#e8ecf4"><div class="kpi-icon"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-val">—</div><div class="kpi-lbl">Loading</div></div>').join('')}</div>
//     <div class="two-col">
//       <div class="card"><div class="card-head"><h4><i class="fa fa-chart-bar"></i> Period-wise</h4></div><div class="chart-pad"><canvas id="repPeriodChart" height="180"></canvas></div></div>
//       <div class="card"><div class="card-head"><h4><i class="fa fa-chart-pie"></i> Attendance Status</h4></div><div class="chart-pad"><canvas id="repStatusChart" height="180"></canvas></div></div>
//     </div>
//     <div class="card"><div class="card-head"><h4><i class="fa fa-users"></i> Student Summary</h4></div>
//     <div class="table-scroll"><table class="data-tbl"><thead><tr><th>Name</th><th>Roll No</th><th>Section</th><th>Present</th><th>Att%</th><th>Status</th></tr></thead>
//     <tbody id="repTbody"><tr><td colspan="6" style="text-align:center;padding:20px"><i class="fa fa-spinner fa-spin"></i></td></tr></tbody></table></div></div>`;
//   try {
//     const days=parseInt(document.getElementById('repDays')?.value||30);
//     const [summary,periods] = await Promise.all([api.attSummary(days), api.periodStats()]);
//     const total=summary.length, avgAtt=summary.length?Math.round(summary.reduce((a,r)=>a+(r.present_count||0)/((r.total_days||1))*100,0)/summary.length):0;
//     const crit=summary.filter(r=>(r.present_count||0)/((r.total_days||1))*100<65).length;
//     setEl('repKpis',`${kpi('Students',total,'fa-users','#4ecba8')}${kpi('Avg Att',avgAtt+'%','fa-percent','#ffb347')}${kpi('Critical',crit,'fa-radiation','#e05454')}${kpi('Days',days,'fa-calendar','#4da6f5')}`);
//     if(periods.length) mkBar('repPeriodChart',periods.map(p=>p.period||'?'),periods.map(p=>p.count||0),'#4ecba8','');
//     const g=summary.filter(r=>(r.present_count||0)/((r.total_days||1))*100>=75).length,
//           w=summary.filter(r=>{const p=(r.present_count||0)/((r.total_days||1))*100;return p>=65&&p<75;}).length;
//     mkDonut('repStatusChart',['Good (≥75%)','Warning (65-75%)','Critical (<65%)'],[g,w,crit],['#4ecba8','#ffb347','#ff7070']);
//     const tbody=document.getElementById('repTbody');
//     if(tbody) tbody.innerHTML=summary.map(r=>{const pct=Math.round((r.present_count||0)/((r.total_days||1))*100);const st=getStatus(pct);return'<tr><td><strong>'+(r.name||'?')+'</strong></td><td><code>'+(r.roll_number||'?')+'</code></td><td>'+(r.section||'—')+'</td><td style="font-family:var(--mono)">'+(r.present_count||0)+'/'+(r.total_days||0)+'</td><td>'+attBar(pct)+'</td><td><span class="badge '+st.bc+'">'+st.label+'</span></td></tr>';}).join('')||'<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text3)">No data yet</td></tr>';
//   } catch(e){ toast('Reports failed: '+e.message,'error'); }
// }

// // ── ALERTS ────────────────────────────────────────────────────
// async function renderAlertsPage() {
//   try {
//     const summary=await api.attSummary(30);
//     APP.localAlerts=[];
//     let id=1;
//     summary.forEach(r=>{
//       const pct=Math.round((r.present_count||0)/((r.total_days||1))*100);
//       const info={name:r.name,roll:r.roll_number||r.student_id,section:r.section,pct};
//       if(pct<65) APP.localAlerts.push({id:id++,type:'critical',...info,msg:'CRITICAL — '+pct+'% — HOD alerted'});
//       else if(pct<70) APP.localAlerts.push({id:id++,type:'incharge',...info,msg:'Incharge notified — '+pct+'%'});
//       else if(pct<75) APP.localAlerts.push({id:id++,type:'student',...info,msg:'Student notified — '+pct+'%'});
//     });
//     setEl('notifBadge', APP.localAlerts.length);
//     const pill=document.getElementById('navAlertPill');
//     if(pill) pill.textContent=APP.localAlerts.length;
//     renderAlertFeed();
//     const crit=summary.filter(r=>(r.present_count||0)/((r.total_days||1))*100<65);
//     setEl('critCountBadge', crit.length+' critical');
//     const critEl=document.getElementById('critStudentList');
//     if(critEl) critEl.innerHTML=crit.length?crit.sort((a,b)=>a.present_count-b.present_count).map(r=>{const p=Math.round((r.present_count||0)/((r.total_days||1))*100);return'<div class="crit-item"><div class="crit-av">'+initials(r.name||'?')+'</div><div><div class="crit-name">'+(r.name||'?')+'</div><div class="crit-info">'+(r.roll_number||'')+'  Sec '+(r.section||'?')+'</div></div><div class="crit-pct">'+p+'%</div></div>';}).join(''):'<div style="padding:20px;text-align:center;color:var(--mint-d)">✓ No critical students</div>';
//   } catch(e){ toast('Alerts failed: '+e.message,'error'); }
// }

// function renderAlertFeed() {
//   const feed=document.getElementById('alertFeedEl');
//   if(!feed) return;
//   const list=APP.alertFilter==='all'?APP.localAlerts:APP.localAlerts.filter(a=>a.type===APP.alertFilter);
//   const icons={student:'fa-user-clock',incharge:'fa-clipboard-user',critical:'fa-radiation'};
//   feed.innerHTML=list.length?list.map(a=>'<div class="alert-item"><div class="ai-icon '+a.type+'"><i class="fa '+icons[a.type]+'"></i></div><div><div class="ai-title">'+a.name+' — '+a.roll+'</div><div class="ai-msg">'+a.msg+'</div><div class="ai-msg" style="color:var(--text3)">Section '+(a.section||'?')+'</div></div><div class="ai-badge-wrap"><span class="badge '+(a.type==='student'?'b-amber':a.type==='incharge'?'b-d':'b-c')+'">'+a.type+'</span></div></div>').join('')
//   :'<div style="padding:28px;text-align:center;color:var(--text3)"><i class="fa fa-check-circle" style="font-size:2rem;color:var(--mint-d);display:block;margin-bottom:8px"></i>No alerts</div>';
// }

// function setAlertFilter(type,btn){ APP.alertFilter=type; document.querySelectorAll('.tab-b').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); renderAlertFeed(); }
// async function runAlerts(){ await renderAlertsPage(); toast('Alert engine ran','warn'); }
// async function bulkSendAlerts(){ toast('Bulk alert logged','warn'); }

// // ── SETTINGS ──────────────────────────────────────────────────
// async function renderSettingsPage() {
//   const pg=document.getElementById('pg-settings');
//   if(!pg) return;
//   pg.innerHTML='<div class="page-header"><div class="ph-left"><h2>System Settings</h2><p>Recognition thresholds</p></div></div><div class="card" id="settingsCard"><div class="card-head"><h4><i class="fa fa-gear"></i> Thresholds</h4></div><div style="padding:20px"><i class="fa fa-spinner fa-spin"></i> Loading...</div></div>';
//   try {
//     const s=await api.settings();
//     document.getElementById('settingsCard').innerHTML='<div class="card-head"><h4><i class="fa fa-gear"></i> Recognition Thresholds</h4><button class="btn-primary" onclick="saveSettings()"><i class="fa fa-save"></i> Save</button></div><div style="padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:14px">'+Object.entries(s).map(([k,v])=>'<div class="fg"><label>'+k.replace(/_/g,' ')+'</label><input id="stg_'+k+'" value="'+v+'" type="'+(typeof v==='boolean'?'checkbox':'text')+'" '+(typeof v==='boolean'&&v?'checked':'')+'/></div>').join('')+'</div>';
//   } catch(e){ toast('Settings failed: '+e.message,'error'); }
// }

// async function saveSettings() {
//   const keys=['LBPH_THRESHOLD','DLIB_DISTANCE','MIN_CONFIDENCE_PCT','CONFIRM_FRAMES_REQUIRED','LIVENESS_THRESHOLD','LIVENESS_ON','CAMERA_INDEX'];
//   const data={};
//   keys.forEach(k=>{const el=document.getElementById('stg_'+k);if(el)data[k]=el.type==='checkbox'?el.checked:el.value;});
//   try{ await api.saveSettings(data); toast('Settings saved!','success'); } catch(e){ toast('Save failed: '+e.message,'error'); }
// }

// // ── TRAIN ─────────────────────────────────────────────────────
// function renderTrainPage() {
//   const pg=document.getElementById('pg-train');
//   if(!pg) return;
//   pg.innerHTML=`<div class="page-header"><div class="ph-left"><h2>Train Models</h2><p>Rebuild LBPH + dlib face recognition models from enrolled images</p></div></div>
//     <div class="card"><div class="card-head"><h4><i class="fa fa-brain"></i> Model Training</h4></div>
//     <div style="padding:24px">
//       <p style="font-size:.88rem;color:var(--text2);margin-bottom:16px">Run after enrolling students via <code>python main.py → [1] Enrol</code>.</p>
//       <div style="display:flex;gap:12px;margin-bottom:20px">
//         <button class="btn-primary" id="btnTrain" onclick="startTraining()"><i class="fa fa-play"></i> Start Training</button>
//         <button class="btn-secondary" onclick="checkTrainStatus()"><i class="fa fa-rotate-right"></i> Check Status</button>
//       </div>
//       <div id="trainStatus" class="card" style="background:var(--bg);padding:16px;font-family:var(--mono);font-size:.78rem;min-height:80px;white-space:pre-wrap;color:var(--text2)">Ready. Press Start Training.</div>
//     </div></div>`;
// }

// async function startTraining() {
//   const btn=document.getElementById('btnTrain');
//   btn.disabled=true; btn.innerHTML='<i class="fa fa-spinner fa-spin"></i> Training...';
//   setEl('trainStatus','Training started in background...');
//   try {
//     await api.trainStart(); toast('Training started!','info');
//     clearInterval(APP.trainPollTimer);
//     APP.trainPollTimer=setInterval(checkTrainStatus,3000);
//   } catch(e){ toast('Failed: '+e.message,'error'); btn.disabled=false; btn.innerHTML='<i class="fa fa-play"></i> Start Training'; }
// }

// async function checkTrainStatus() {
//   try {
//     const s=await api.trainStatus();
//     const el=document.getElementById('trainStatus');
//     if(el) el.textContent=s.log?.join('\n')||'Running...';
//     if(!s.running){ clearInterval(APP.trainPollTimer); const btn=document.getElementById('btnTrain'); if(btn){btn.disabled=false;btn.innerHTML='<i class="fa fa-play"></i> Start Training';} if(s.error)toast('Training error: '+s.error,'error'); else if(s.done)toast('Training complete!','success'); }
//   } catch(e){}
// }

// // ── FACULTY DASHBOARD ─────────────────────────────────────────
// async function renderFacDashboard() {
//   const el=document.getElementById('facDashContent');
//   if(!el) return;
//   el.innerHTML='<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>Loading...</p></div>';
//   try {
//     const [analytics,today]=await Promise.all([api.analytics(),api.todayAtt()]);
//     el.innerHTML=`<div class="fac-dash-welcome"><div class="fdw-bg"></div>
//       <div class="fdw-title">Welcome, ${(_user.name||'Faculty').split(' ')[0]}! 👋</div>
//       <div class="fdw-sub">Faculty Portal · ${_user.fac_id||''}</div>
//       <div class="fdw-meta"><span class="fdw-m"><i class="fa fa-id-card"></i> ${_user.fac_id||'—'}</span><span class="fdw-m"><i class="fa fa-calendar-day"></i> ${new Date().toLocaleDateString('en-IN')}</span></div>
//     </div>
//     <div class="kpi-strip">
//       ${kpi('Total Students',analytics.total_students,'fa-users','#4ecba8')}
//       ${kpi('Present Today',analytics.present_today,'fa-circle-check','#4da6f5')}
//       ${kpi('Today %',analytics.pct_today+'%','fa-percent','#ffb347')}
//       ${kpi('Critical',analytics.critical_count,'fa-radiation','#e05454')}
//     </div>
//     <div class="card"><div class="card-head"><h4><i class="fa fa-list-check"></i> Today's Attendance</h4></div>
//     <div class="table-scroll"><table class="data-tbl"><thead><tr><th>Name</th><th>ID</th><th>Period</th><th>Time</th><th>Confidence</th></tr></thead>
//     <tbody>${today.length?today.map(r=>'<tr><td><strong>'+(r.name||'?')+'</strong></td><td><code>'+(r.student_id||'?')+'</code></td><td>'+(r.period||'—')+'</td><td style="font-family:var(--mono)">'+String(r.time||'').slice(0,8)+'</td><td>'+confBadge(r.confidence)+'</td></tr>').join(''):'<tr><td colspan="5" style="text-align:center;padding:16px;color:var(--text3)">No attendance today</td></tr>'}</tbody></table></div></div>`;
//   } catch(e){ el.innerHTML='<div class="empty-msg"><i class="fa fa-triangle-exclamation"></i><p>'+e.message+'</p></div>'; }
// }

// // ── CHARTS ────────────────────────────────────────────────────
// function mkBar(id,labels,data,colors,suffix){
//   const ctx=document.getElementById(id); if(!ctx) return;
//   try{APP.charts[id]?.destroy();}catch(e){}
//   APP.charts[id]=new Chart(ctx,{type:'bar',data:{labels,datasets:[{data,backgroundColor:Array.isArray(colors)?colors:data.map(()=>colors),borderRadius:8,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:true,plugins:{legend:{display:false},tooltip:{backgroundColor:'#fff',titleColor:'#1a2332',bodyColor:'#5a6a80',borderColor:'#dde4f0',borderWidth:1.5,padding:10,cornerRadius:10,callbacks:{label:c=>' '+c.parsed.y+(suffix||'')}}},scales:{x:{grid:{display:false},ticks:{color:'#96a8be',font:{size:10,family:'Plus Jakarta Sans'}}},y:{grid:{color:'rgba(0,0,0,.06)'},ticks:{color:'#96a8be',font:{size:10}},beginAtZero:true}}}});
// }

// function mkDonut(id,labels,data,colors){
//   const ctx=document.getElementById(id); if(!ctx) return;
//   try{APP.charts[id]?.destroy();}catch(e){}
//   APP.charts[id]=new Chart(ctx,{type:'doughnut',data:{labels,datasets:[{data,backgroundColor:colors,borderWidth:3,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:true,cutout:'65%',plugins:{legend:{position:'bottom',labels:{color:'#5a6a80',font:{size:10.5,family:'Plus Jakarta Sans'},padding:10,boxWidth:12}},tooltip:{backgroundColor:'#fff',titleColor:'#1a2332',bodyColor:'#5a6a80',borderColor:'#dde4f0',borderWidth:1.5,padding:10,cornerRadius:10}}}});
// }

// // ── HELPERS ───────────────────────────────────────────────────
// function kpi(label,value,icon,color){return'<div class="kpi-card" style="--kc:'+color+'"><div class="kpi-icon"><i class="fa '+icon+'"></i></div><div class="kpi-val">'+value+'</div><div class="kpi-lbl">'+label+'</div></div>';}
// function attBar(pct){const st=getStatus(pct);return'<div class="att-bar"><div class="att-track"><div class="att-fill '+st.cls+'" style="width:'+pct+'%"></div></div><span class="att-pct" style="color:'+st.color+'">'+pct+'%</span></div>';}
// function confBadge(conf){const p=Math.round(parseFloat(conf||0)*100);return'<span class="badge '+(p>=75?'b-g':p>=50?'b-w':'b-d')+'">'+p+'%</span>';}
// function getStatus(pct){if(pct>=75)return{cls:'g',bc:'b-g',label:'✓ Good',color:'var(--mint-d)'};if(pct>=70)return{cls:'w',bc:'b-w',label:'⚠ Warn',color:'var(--amber-d)'};if(pct>=65)return{cls:'d',bc:'b-d',label:'✗ Poor',color:'var(--coral-d)'};return{cls:'d',bc:'b-c',label:'☠ Critical',color:'#b22222'};}
// function initials(name){return(name||'').split(' ').map(n=>n[0]).join('').toUpperCase().slice(0,2)||'??';}
// function setEl(id,val){const el=document.getElementById(id);if(el)el.innerHTML=val;}
// function closeModal(id){document.getElementById(id)?.classList.add('dn');}
// function toast(msg,type){const icons={success:'fa-circle-check',error:'fa-circle-exclamation',info:'fa-circle-info',warn:'fa-triangle-exclamation'};const z=document.getElementById('toastContainer');if(!z)return;const el=document.createElement('div');el.className='toast '+(type||'info');el.innerHTML='<i class="fa '+(icons[type||'info']||'fa-circle-info')+'"></i><span>'+msg+'</span>';z.appendChild(el);setTimeout(()=>{el.classList.add('toast-out');setTimeout(()=>el.remove(),300);},4000);}

// // Stubs for HTML-referenced functions
// function attOnDeptChange(){}function attOnCourseChange(){}function ttOnDeptChange(){}function ttOnCourseChange(){}function renderTimetable(){}function renderCIPage(){}function loadCIData(){}function ciAlert(){}function onAnlLevelChange(){}function renderAnalytics(){}function drillGoto(){}function drillToCourse(){}function drillToSection(){}function drillToSectionDetail(){}function initDeptDrill(){}function renderMyTimetable(){renderTimetablePage();}function renderMyClasses(){}function renderMyAttendance(){renderReportsPage();}function renderFacultyPage(){}function openMarkFacultyModal(){}function editFacAtt(){}function saveFacultyAttendance(){}function viewFacDetail(){}

// document.addEventListener('keydown',e=>{if(e.key!=='Enter')return;const ls=document.getElementById('loginScreen');if(ls&&ls.style.display!=='none'){const fac=document.querySelector('.ptab.active')?.dataset?.portal==='faculty';fac?loginFaculty():loginAdmin();}});
// document.addEventListener('click',e=>{const sb=document.getElementById('sidebar');if(sb?.classList.contains('open')&&!sb.contains(e.target)&&!e.target.closest('.mob-ham'))closeSidebar();});



'use strict';
/* ═══════════════════════════════════════════════════════════
   EduTrack Pro — Frontend v9.6
   Connects to the Smart Attendance System backend REST API.
   Base URL: same origin (served by FastAPI at /app)
   All data comes from the SQLite database via /api/* endpoints.
   ═══════════════════════════════════════════════════════════ */

const API_BASE = '';
let _token = null, _role = null, _user = {};

async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = 'Bearer ' + _token;
  const res = await fetch(API_BASE + path, { ...opts, headers: { ...headers, ...(opts.headers||{}) } });
  if (!res.ok) {
    let detail = 'HTTP ' + res.status;
    try { detail = (await res.json()).detail || detail; } catch(e) {}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res;
}

const api = {
  login:         (email, pass, role, facId) => apiFetch('/api/login', { method:'POST', body:JSON.stringify({email, password:pass, role, fac_id:facId||''}) }),
  students:      ()          => apiFetch('/api/students'),
  addStudent:    (data)      => apiFetch('/api/students', { method:'POST', body:JSON.stringify(data) }),
  deleteStudent: (id)        => apiFetch('/api/students/'+id, { method:'DELETE' }),
  todayAtt:      (period)    => apiFetch('/api/attendance/today'+(period?'?period='+encodeURIComponent(period):'')),
  attSummary:    (days)      => apiFetch('/api/attendance/summary?days='+(days||30)),
  override:      (data)      => apiFetch('/api/attendance/override', { method:'POST', body:JSON.stringify(data) }),
  sessionStart:  (period)    => apiFetch('/api/session/start', { method:'POST', body:JSON.stringify({period}) }),
  sessionStop:   ()          => apiFetch('/api/session/stop', { method:'POST' }),
  sessionStatus: ()          => apiFetch('/api/session/status'),
  trainStart:    ()          => apiFetch('/api/train', { method:'POST' }),
  trainStatus:   ()          => apiFetch('/api/train/status'),
  analytics:     ()          => apiFetch('/api/analytics/summary'),
  timetable:     ()          => apiFetch('/api/timetable'),
  settings:      ()          => apiFetch('/api/settings'),
  saveSettings:  (data)      => apiFetch('/api/settings', { method:'POST', body:JSON.stringify(data) }),
  periodStats:   ()          => apiFetch('/api/analytics/period'),
  exportCsv:     ()          => apiFetch('/api/export/csv'),
};

const APP = { role:'admin', currentPage:'dashboard', attPollTimer:null, trainPollTimer:null, charts:{}, alertFilter:'all', localAlerts:[] };

// ── LOGIN ──────────────────────────────────────────────────────
let _pickedAdminRole = 'admin';

function switchPortal(btn, portal) {
  document.querySelectorAll('.ptab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('adminPortal').classList.toggle('dn', portal !== 'admin');
  document.getElementById('facultyPortal').classList.toggle('dn', portal !== 'faculty');
}

function pickAdminRole(btn) {
  document.querySelectorAll('.role-chip').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _pickedAdminRole = btn.dataset.role;
}

function fillFacDemo() {
  const v = document.getElementById('facDemoSelect').value;
  if (v) document.getElementById('facIdInput').value = v;
}

async function loginAdmin() {
  const email = document.getElementById('adminEmail').value.trim();
  const pass  = document.getElementById('adminPass').value.trim();
  const btns  = document.querySelectorAll('.btn-signin');
  btns[0].innerHTML = '<i class="fa fa-spinner fa-spin"></i> Signing in...';
  try {
    const res = await api.login(email, pass, _pickedAdminRole, '');
    _token = res.access_token; _role = res.role||_pickedAdminRole;
    _user = { username: res.username||email, role: _role };
    APP.role = _role;
    startApp();
  } catch(e) {
    toast('Login failed: ' + e.message, 'error');
    btns[0].innerHTML = '<i class="fa fa-right-to-bracket"></i> Sign In';
  }
}

async function loginFaculty() {
  const facId = document.getElementById('facIdInput').value.trim().toUpperCase();
  const pass  = document.getElementById('facPassInput').value.trim();
  const btns  = document.querySelectorAll('.btn-signin');
  const btn   = btns[1]||btns[0];
  if (!facId) { toast('Enter Faculty ID', 'warn'); return; }
  btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Signing in...';
  try {
    const res = await api.login('', pass, 'faculty', facId);
    _token = res.access_token; _role = 'faculty';
    _user = { fac_id: facId, name: res.name||facId, role:'faculty' };
    APP.role = 'faculty';
    startApp();
  } catch(e) {
    toast('Login failed: ' + e.message, 'error');
    btn.innerHTML = '<i class="fa fa-right-to-bracket"></i> Faculty Sign In';
  }
}

function doLogout() {
  _token=null; _role=null; _user={};
  clearInterval(APP.attPollTimer); clearInterval(APP.trainPollTimer);
  document.getElementById('appShell').classList.add('dn');
  document.getElementById('loginScreen').style.display = '';
}

function startApp() {
  document.getElementById('loginScreen').style.display = 'none';
  document.getElementById('appShell').classList.remove('dn');
  populateFacSelect();
  buildSideNav();
  setTopbarProfile();
  startClock();
  showPage(APP.role==='faculty' ? 'fac-dashboard' : 'dashboard');
  toast('Welcome! Signed in as '+getRoleLabel(), 'success');
}

function getRoleLabel() {
  const m={admin:'Administrator',hod:'HOD',classincharge:'Class Incharge',teacher:'Teacher',faculty:_user.name||'Faculty'};
  return m[APP.role]||APP.role;
}

function populateFacSelect() {
  const sel = document.getElementById('facDemoSelect');
  if (sel) {
    sel.innerHTML = '<option value="">-- Demo Faculty --</option>';
    ['FAC001','FAC002','FAC003','FAC004','FAC005'].forEach(id => sel.innerHTML += '<option value="'+id+'">'+id+'</option>');
  }
}

// ── NAV ───────────────────────────────────────────────────────
const NAV_CFG = {
  admin:[
    {section:'OVERVIEW',links:[{icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'}]},
    {section:'STUDENT SYSTEM',links:[
      {icon:'fa-camera',label:'Take Attendance',page:'attendance',pill:'LIVE'},
      {icon:'fa-users',label:'Students',page:'students'},
      {icon:'fa-calendar-week',label:'Timetable',page:'timetable'},
    ]},
    {section:'MANAGEMENT',links:[
      {icon:'fa-pen-to-square',label:'Overrides',page:'overrides'},
      {icon:'fa-building-columns',label:'Departments',page:'departments'},
      {icon:'fa-chalkboard-teacher',label:'Faculty',page:'faculty'},
      {icon:'fa-chart-line',label:'Reports',page:'reports'},
      {icon:'fa-bell',label:'Alerts',page:'alerts',pill:'alert'},
      {icon:'fa-gear',label:'Settings',page:'settings'},
    ]},
    {section:'TRAINING',links:[{icon:'fa-brain',label:'Train Models',page:'train'}]},
  ],
  hod:[
    {section:'OVERVIEW',links:[{icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'}]},
    {section:'DATA',links:[
      {icon:'fa-users',label:'Students',page:'students'},
      {icon:'fa-building-columns',label:'Departments',page:'departments'},
      {icon:'fa-chalkboard-teacher',label:'Faculty',page:'faculty'},
      {icon:'fa-chart-line',label:'Reports',page:'reports'},
      {icon:'fa-bell',label:'Alerts',page:'alerts',pill:'alert'},
    ]},
  ],
  classincharge:[
    {section:'MY CLASS',links:[
      {icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'},
      {icon:'fa-camera',label:'Take Attendance',page:'attendance',pill:'LIVE'},
      {icon:'fa-pen-to-square',label:'Overrides',page:'overrides'},
      {icon:'fa-bell',label:'Alerts',page:'alerts',pill:'alert'},
    ]},
  ],
  teacher:[
    {section:'MY CLASSES',links:[
      {icon:'fa-chart-pie',label:'Dashboard',page:'dashboard'},
      {icon:'fa-camera',label:'Take Attendance',page:'attendance',pill:'LIVE'},
      {icon:'fa-pen-to-square',label:'Overrides',page:'overrides'},
    ]},
  ],
  faculty:[
    {section:'MY PORTAL',links:[
      {icon:'fa-chart-pie',label:'My Dashboard',page:'fac-dashboard'},
      {icon:'fa-calendar-week',label:'Timetable',page:'timetable'},
      {icon:'fa-chart-line',label:'My Reports',page:'reports'},
    ]},
  ],
};

const PAGE_TITLES = {
  dashboard:'Dashboard',attendance:'Student Attendance',students:'Student Management',
  timetable:'Timetable',overrides:'Attendance Overrides',reports:'Reports & Analytics',
  alerts:'Smart Alerts',settings:'System Settings',train:'Train Models',
  'fac-dashboard':'My Dashboard',
  departments:'Department Analytics',faculty:'Faculty Management',
};

function buildSideNav() {
  const nav = document.getElementById('sbNav');
  nav.innerHTML = '';
  (NAV_CFG[APP.role]||NAV_CFG.admin).forEach(grp => {
    const lbl = document.createElement('div');
    lbl.className = 'nav-section-lbl'; lbl.textContent = grp.section;
    nav.appendChild(lbl);
    grp.links.forEach(lnk => {
      const a = document.createElement('a');
      a.className='nav-link'; a.dataset.page=lnk.page;
      a.onclick = () => showPage(lnk.page);
      let pill = lnk.pill==='LIVE' ? '<span class="nav-pill live">LIVE</span>' :
                 lnk.pill==='alert' ? '<span class="nav-pill alert" id="navAlertPill">0</span>' : '';
      a.innerHTML = '<i class="fa '+lnk.icon+'"></i><span>'+lnk.label+'</span>'+pill;
      nav.appendChild(a);
    });
  });
}

function setTopbarProfile() {
  const label = getRoleLabel();
  setEl('sucAv', label.substring(0,2).toUpperCase());
  setEl('sucName', label);
  setEl('sucRole', APP.role==='faculty'?'Staff Faculty':label);
  setEl('sucDept', APP.role==='faculty'?'My Portal':'Smart Attendance System');
  setEl('tbpAv', label.substring(0,2).toUpperCase());
  setEl('tbpName', label.split(' ')[0]);
  setEl('tbpRole', APP.role);
}

function showPage(pid) {
  document.querySelectorAll('.page').forEach(p => p.classList.add('dn'));
  document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));
  const pg = document.getElementById('pg-'+pid);
  if (pg) pg.classList.remove('dn');
  document.querySelector('[data-page="'+pid+'"]')?.classList.add('active');
  setEl('tbPageTitle', PAGE_TITLES[pid]||pid);
  APP.currentPage = pid;
  closeSidebar();
  const init={dashboard:renderDashboard,attendance:initAttendancePage,students:renderStudentsPage,
    timetable:renderTimetablePage,overrides:renderOverridesPage,reports:renderReportsPage,
    alerts:renderAlertsPage,settings:renderSettingsPage,train:renderTrainPage,'fac-dashboard':renderFacDashboard};
  init[pid]?.();
}

function toggleSidebar(){ document.getElementById('sidebar').classList.toggle('open'); }
function closeSidebar() { document.getElementById('sidebar').classList.remove('open'); }

function startClock() {
  const el = document.getElementById('tbClock');
  const t = () => { if(el) el.textContent = new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); };
  t(); setInterval(t,1000);
}

// ── DASHBOARD ─────────────────────────────────────────────────
async function renderDashboard() {
  if (APP.role==='faculty') { renderFacDashboard(); return; }
  const cont = document.getElementById('dashboardContent');
  if (!cont) return;
  cont.innerHTML = '<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>Loading...</p></div>';
  try {
    const [data, today] = await Promise.all([api.analytics(), api.todayAtt()]);
    const {total_students:total,present_today:present,absent_today:absent,pct_today:pct,avg_attendance:avgAtt,critical_count:crit} = data;
    cont.innerHTML = `
      <div class="page-header">
        <div class="ph-left"><h2>${getRoleLabel()} Dashboard</h2>
        <p>${new Date().toLocaleDateString('en-IN',{weekday:'long',year:'numeric',month:'long',day:'numeric'})}</p></div>
        <div class="ph-right"><button class="btn-secondary" onclick="renderDashboard()"><i class="fa fa-rotate-right"></i> Refresh</button></div>
      </div>
      <div class="kpi-strip">
        ${kpi('Total Students',total,'fa-users','#4ecba8')}
        ${kpi('Present Today',present,'fa-circle-check','#4da6f5')}
        ${kpi('Absent Today',absent,'fa-circle-xmark','#ff7070')}
        ${kpi('Today %',pct+'%','fa-percent','#ffb347')}
        ${kpi('30-day Avg',avgAtt+'%','fa-chart-line','#9b87f5')}
        ${kpi('Critical',crit,'fa-radiation','#e05454')}
      </div>
      <div class="two-col">
        <div class="card">
          <div class="card-head"><h4><i class="fa fa-list-check"></i> Today's Attendance</h4>
            <button class="btn-sm" onclick="exportTodayCSV()"><i class="fa fa-download"></i> CSV</button>
          </div>
          <div class="table-scroll"><table class="data-tbl">
            <thead><tr><th>Name</th><th>ID</th><th>Period</th><th>Time</th><th>Confidence</th><th>Engine</th></tr></thead>
            <tbody>${today.length?today.map(r=>'<tr><td><strong>'+(r.name||'?')+'</strong></td><td><code>'+(r.student_id||'?')+'</code></td><td>'+(r.period||'—')+'</td><td style="font-family:var(--mono)">'+String(r.time||'').slice(0,8)+'</td><td>'+confBadge(r.confidence)+'</td><td><span class="badge b-lav">'+(r.engine||'—')+'</span></td></tr>').join('')
            :'<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text3)">No attendance today — start a camera session</td></tr>'}</tbody>
          </table></div>
        </div>
        <div class="card">
          <div class="card-head"><h4><i class="fa fa-chart-pie"></i> Today Status</h4></div>
          <div class="chart-pad"><canvas id="dashDonut" height="200"></canvas></div>
        </div>
      </div>`;
    setTimeout(() => mkDonut('dashDonut',['Present','Absent','Critical'],[present,absent-crit,crit],['#4ecba8','#4da6f5','#ff7070']), 60);
  } catch(e) {
    cont.innerHTML = '<div class="empty-msg"><i class="fa fa-triangle-exclamation"></i><p>'+e.message+'</p><button class="btn-primary" onclick="renderDashboard()"><i class="fa fa-rotate-right"></i> Retry</button></div>';
  }
}

// ── ATTENDANCE ─────────────────────────────────────────────────
function initAttendancePage() {
  clearInterval(APP.attPollTimer);
  const cb = document.getElementById('camViewport');
  if (cb) {
    cb.innerHTML = '<div class="cv-idle" id="cvIdle"><div class="cv-idle-icon"><i class="fa fa-camera-slash"></i></div><h4>Camera Offline</h4><p>Click Start Session to begin face recognition</p></div>'
      +'<img id="mjpegImg" class="dn" src="" style="width:100%;height:100%;object-fit:cover;position:absolute;inset:0"/>'
      +'<div class="cv-tag dn" id="cvTag">Scanning...</div>'
      +'<div class="cv-live-badge dn" id="cvLiveBadge">● LIVE</div>';
  }
  // Add period input if not already present
  const hdr = document.getElementById('attHeaderControls');
  if (hdr && !document.getElementById('attPeriodInput')) {
    hdr.innerHTML = '<input class="sel" id="attPeriodInput" placeholder="Period name e.g. Period_1" value="Period_1"/>' + hdr.innerHTML;
  }
  renderSessionStatus();
}

async function startAttendance() {
  const p = (document.getElementById('attPeriodInput')?.value||'Period_1').trim();
  try {
    await api.sessionStart(p);
    const img=document.getElementById('mjpegImg'), idle=document.getElementById('cvIdle'),
          tag=document.getElementById('cvTag'), badge=document.getElementById('cvLiveBadge');
    if(img){img.src='/video_feed?'+Date.now();img.classList.remove('dn');}
    if(idle) idle.classList.add('dn');
    if(tag)  tag.classList.remove('dn');
    if(badge)badge.classList.remove('dn');
    document.getElementById('btnStartCam').disabled=true;
    document.getElementById('btnStopCam').disabled=false;
    toast('Session started: '+p,'success');
    clearInterval(APP.attPollTimer);
    APP.attPollTimer = setInterval(renderSessionStatus,2500);
  } catch(e) { toast('Start failed: '+e.message,'error'); }
}

async function stopAttendance() {
  try {
    await api.sessionStop();
    clearInterval(APP.attPollTimer);
    const img=document.getElementById('mjpegImg'),idle=document.getElementById('cvIdle'),
          tag=document.getElementById('cvTag'),badge=document.getElementById('cvLiveBadge');
    if(img){img.src='';img.classList.add('dn');}
    if(idle){idle.classList.remove('dn');idle.innerHTML='<div class="cv-idle-icon"><i class="fa fa-check" style="color:var(--mint-d)"></i></div><h4 style="color:var(--mint-d)">Session Complete</h4><p>Check the log</p>';}
    if(tag)  tag.classList.add('dn');
    if(badge)badge.classList.add('dn');
    document.getElementById('btnStartCam').disabled=false;
    document.getElementById('btnStopCam').disabled=true;
    toast('Session stopped','info');
    renderSessionStatus();
  } catch(e) { toast('Stop failed: '+e.message,'error'); }
}

async function renderSessionStatus() {
  try {
    const s = await api.sessionStatus();
    setEl('alcP', s.marked_count+' Present');
    setEl('alcA', s.absent_count+' Absent');
    const bar = document.getElementById('alcProgBar');
    if(bar&&s.total_students>0) bar.style.width=Math.min(s.marked_count/s.total_students*100,100)+'%';
    const body = document.getElementById('alcBody');
    if (!body) return;
    if (!s.already_marked?.length) {
      body.innerHTML = '<div class="alc-empty"><i class="fa fa-inbox"></i><p>No entries yet</p></div>';
    } else {
      body.innerHTML = s.already_marked.map(r=>'<div class="log-entry"><div class="le-av p">'+initials(r.name)+'</div><div><div class="le-name">'+r.name+'</div><div class="le-meta">'+r.student_id+'</div></div><span class="le-time">'+r.time+'</span></div>').join('');
    }
  } catch(e) {}
}

function resetAttSession(){ renderSessionStatus(); }
function openOverrideFromAtt(){ openOverrideModal(); }

async function exportTodayCSV() {
  try {
    const res=await api.exportCsv();
    const blob=await res.blob();
    const a=Object.assign(document.createElement('a'),{href:URL.createObjectURL(blob),download:'attendance_'+new Date().toISOString().slice(0,10)+'.csv'});
    a.click(); toast('CSV exported!','success');
  } catch(e){ toast('Export failed: '+e.message,'error'); }
}

// ── STUDENTS ──────────────────────────────────────────────────
async function renderStudentsPage() {
  const cont=document.getElementById('pg-students');
  if(!cont) return;
  cont.innerHTML=`<div class="page-header"><div class="ph-left"><h2>Student Management</h2><p>Students in SQLite database</p></div>
    <div class="ph-right">
      <input class="sel" id="stuSearch" placeholder="Search..." oninput="filterStuTable()"/>
      <button class="btn-primary" onclick="openAddStudentModal()"><i class="fa fa-plus"></i> Add Student</button>
    </div></div>
    <div class="card"><div class="card-head"><h4><i class="fa fa-users"></i> Student Roster</h4>
      <span id="stuCount" style="font-size:.78rem;color:var(--text3)">Loading...</span></div>
    <div class="table-scroll"><table class="data-tbl">
      <thead><tr><th>#</th><th>Name</th><th>Roll No</th><th>Section</th><th>Mobile</th><th>Enrolled</th><th>Actions</th></tr></thead>
      <tbody id="stuTbody"><tr><td colspan="7" style="text-align:center;padding:20px"><i class="fa fa-spinner fa-spin"></i></td></tr></tbody>
    </table></div></div>`;
  try {
    const students = await api.students();
    window._allStudents = students;
    renderStuRows(students);
    setEl('stuCount', students.length+' students');
  } catch(e) {
    document.getElementById('stuTbody').innerHTML='<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--coral-d)">'+e.message+'</td></tr>';
  }
}

function renderStuRows(students) {
  const tbody=document.getElementById('stuTbody');
  if(!tbody) return;
  if(!students.length){tbody.innerHTML='<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text3)">No students yet. Enroll via python main.py → [1]</td></tr>';return;}
  tbody.innerHTML=students.map((s,i)=>'<tr><td style="font-family:var(--mono);color:var(--text3)">'+(i+1)+'</td><td><strong>'+(s.name||'?')+'</strong></td><td><code>'+(s.roll_number||s.student_id||'?')+'</code></td><td>'+(s.section||'—')+'</td><td>'+(s.mobile||'—')+'</td><td style="font-size:.75rem;color:var(--text3)">'+(s.enrolled_on||'').slice(0,10)||'—'+'</td><td><button class="btn-sm" style="color:var(--coral-d)" onclick="deleteStudent(\''+s.student_id+'\')"><i class="fa fa-trash"></i></button></td></tr>').join('');
}

function filterStuTable(){ const q=(document.getElementById('stuSearch')?.value||'').toLowerCase(); renderStuRows((window._allStudents||[]).filter(s=>(s.name||'').toLowerCase().includes(q)||(s.roll_number||'').toLowerCase().includes(q))); }

function openAddStudentModal() {
  document.getElementById('infoModalTitle').innerHTML='<i class="fa fa-user-plus"></i> Add Student';
  document.getElementById('infoModalBody').innerHTML='<p style="font-size:.82rem;color:var(--text2);margin-bottom:16px">Adds student to database. To enrol face: run <code>python main.py → [1] Enrol</code>.</p><div class="fg"><label>Full Name *</label><input id="ns_name" placeholder="e.g. Aarav Kumar"/></div><div class="fg-2"><div class="fg"><label>Roll Number *</label><input id="ns_roll" placeholder="cs22001"/></div><div class="fg"><label>Section</label><select id="ns_sec"><option value="A">A</option><option value="B">B</option></select></div></div><div class="fg"><label>Mobile</label><input id="ns_mobile" placeholder="10-digit"/></div>';
  document.querySelector('#infoModal .modal-footer').innerHTML='<button class="btn-secondary" onclick="closeModal(\'infoModal\')">Cancel</button><button class="btn-primary" onclick="submitAddStudent()"><i class="fa fa-save"></i> Save</button>';
  document.getElementById('infoModal').classList.remove('dn');
}

async function submitAddStudent() {
  const name=document.getElementById('ns_name')?.value.trim(),roll=document.getElementById('ns_roll')?.value.trim(),section=document.getElementById('ns_sec')?.value,mobile=document.getElementById('ns_mobile')?.value.trim();
  if(!name||!roll){toast('Name and Roll Number required','warn');return;}
  try { const res=await api.addStudent({name,roll_number:roll,section,mobile}); closeModal('infoModal'); toast(name+' added! ID: '+res.student_id,'success'); renderStudentsPage(); }
  catch(e) { toast('Add failed: '+e.message,'error'); }
}

async function deleteStudent(id) {
  if(!confirm('Delete '+id+'? This removes attendance records too.')) return;
  try { await api.deleteStudent(id); toast(id+' removed','info'); renderStudentsPage(); }
  catch(e) { toast('Delete failed: '+e.message,'error'); }
}

// ── TIMETABLE ─────────────────────────────────────────────────
async function renderTimetablePage() {
  const ttCont=document.getElementById('ttContent');
  if(!ttCont) return;
  ttCont.innerHTML='<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>Loading...</p></div>';
  try {
    const periods=await api.timetable();
    if(!periods.length){ttCont.innerHTML='<div class="empty-msg"><i class="fa fa-calendar-days"></i><p>No timetable configured. Add periods in config.py DEFAULT_PERIODS.</p></div>';return;}
    ttCont.innerHTML='<div class="card"><div class="card-head"><h4><i class="fa fa-calendar-week"></i> Configured Periods</h4></div><div class="table-scroll"><table class="data-tbl"><thead><tr><th>#</th><th>Period Name</th><th>Start</th><th>End</th><th>Status</th></tr></thead><tbody>'+periods.map((p,i)=>'<tr><td style="font-family:var(--mono)">'+(i+1)+'</td><td><strong>'+(p.period_name||p.name||'?')+'</strong></td><td style="font-family:var(--mono)">'+(p.start_time||'—')+'</td><td style="font-family:var(--mono)">'+(p.end_time||'—')+'</td><td>'+(p.active?'<span class="badge b-g">Active</span>':'<span class="badge b-w">Inactive</span>')+'</td></tr>').join('')+'</tbody></table></div></div>';
  } catch(e){ttCont.innerHTML='<div class="empty-msg"><i class="fa fa-triangle-exclamation"></i><p>'+e.message+'</p></div>';}
}

// ── OVERRIDES ─────────────────────────────────────────────────
function renderOverridesPage() {
  // Page content is in HTML — just ensure the override button works
  loadOverrideStudents();
}

function openOverrideModal(type) {
  const sel=document.getElementById('ov_type');
  if(sel&&type) sel.value=type;
  onOvTypeChange();
  loadOverrideStudents();
  document.getElementById('overrideModal').classList.remove('dn');
}

function onOvTypeChange() {
  const type=document.getElementById('ov_type')?.value;
  const sf=document.getElementById('ovStaffFields'),cf=document.getElementById('ovCatField');
  if(type==='staff'){sf.style.display='block';cf.style.display='none';}
  else if(type==='classincharge'){sf.style.display='none';cf.style.display='block';}
  else{sf.style.display='none';cf.style.display='none';}
}

async function loadOverrideStudents() {
  const sel=document.getElementById('ov_student');
  if(!sel) return;
  try {
    const students=await api.students();
    sel.innerHTML='<option value="">Select student</option>';
    students.forEach(s=>sel.innerHTML+='<option value="'+s.student_id+'">'+s.name+' — '+(s.roll_number||s.student_id)+'</option>');
  } catch(e){ sel.innerHTML='<option value="">Could not load students</option>'; }
}

function ovLoadCourses(){}
function ovLoadStudents(){ loadOverrideStudents(); }

async function submitOverride() {
  const staffId=document.getElementById('ov_staffId')?.value.trim(),type=document.getElementById('ov_type')?.value,
    studentId=document.getElementById('ov_student')?.value,period=document.getElementById('ov_period')?.value,
    to=document.getElementById('ov_to')?.value,cat=document.getElementById('ov_cat')?.value,
    reason=document.getElementById('ov_reason')?.value.trim();
  if(!staffId){toast('Staff/Modifier ID required','warn');return;}
  if(!studentId){toast('Select a student','warn');return;}
  if(!reason){toast('Reason is mandatory','warn');return;}
  if(type==='staff'&&!period){toast('Select period','warn');return;}
  const actionMap={present:'mark_present',absent:'mark_absent',late:'mark_present',od:'mark_present',medical:'mark_present'};
  try {
    await api.override({student_id:studentId,period:period||'Manual',action:actionMap[to]||'mark_present',reason,modifier_id:staffId,category:cat||''});
    closeModal('overrideModal'); toast('Override saved to database!','success');
  } catch(e){ toast('Override failed: '+e.message,'error'); }
}

// ── REPORTS ───────────────────────────────────────────────────
async function renderReportsPage() {
  const pg=document.getElementById('pg-reports');
  if(!pg) return;
  pg.innerHTML=`<div class="page-header"><div class="ph-left"><h2>Reports & Analytics</h2><p>Attendance data from SQLite database</p></div>
    <div class="ph-right"><select class="sel" id="repDays" onchange="renderReportsPage()"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option></select>
    <button class="btn-primary" onclick="exportTodayCSV()"><i class="fa fa-download"></i> Export CSV</button></div></div>
    <div class="kpi-strip" id="repKpis">${[1,2,3,4].map(()=>'<div class="kpi-card" style="--kc:#e8ecf4"><div class="kpi-icon"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-val">—</div><div class="kpi-lbl">Loading</div></div>').join('')}</div>
    <div class="two-col">
      <div class="card"><div class="card-head"><h4><i class="fa fa-chart-bar"></i> Period-wise</h4></div><div class="chart-pad"><canvas id="repPeriodChart" height="180"></canvas></div></div>
      <div class="card"><div class="card-head"><h4><i class="fa fa-chart-pie"></i> Attendance Status</h4></div><div class="chart-pad"><canvas id="repStatusChart" height="180"></canvas></div></div>
    </div>
    <div class="card"><div class="card-head"><h4><i class="fa fa-users"></i> Student Summary</h4></div>
    <div class="table-scroll"><table class="data-tbl"><thead><tr><th>Name</th><th>Roll No</th><th>Section</th><th>Present</th><th>Att%</th><th>Status</th></tr></thead>
    <tbody id="repTbody"><tr><td colspan="6" style="text-align:center;padding:20px"><i class="fa fa-spinner fa-spin"></i></td></tr></tbody></table></div></div>`;
  try {
    const days=parseInt(document.getElementById('repDays')?.value||30);
    const [summary,periods] = await Promise.all([api.attSummary(days), api.periodStats()]);
    const total=summary.length, avgAtt=summary.length?Math.round(summary.reduce((a,r)=>a+(r.present_count||0)/((r.total_days||1))*100,0)/summary.length):0;
    const crit=summary.filter(r=>(r.present_count||0)/((r.total_days||1))*100<65).length;
    setEl('repKpis',`${kpi('Students',total,'fa-users','#4ecba8')}${kpi('Avg Att',avgAtt+'%','fa-percent','#ffb347')}${kpi('Critical',crit,'fa-radiation','#e05454')}${kpi('Days',days,'fa-calendar','#4da6f5')}`);
    if(periods.length) mkBar('repPeriodChart',periods.map(p=>p.period||'?'),periods.map(p=>p.count||0),'#4ecba8','');
    const g=summary.filter(r=>(r.present_count||0)/((r.total_days||1))*100>=75).length,
          w=summary.filter(r=>{const p=(r.present_count||0)/((r.total_days||1))*100;return p>=65&&p<75;}).length;
    mkDonut('repStatusChart',['Good (≥75%)','Warning (65-75%)','Critical (<65%)'],[g,w,crit],['#4ecba8','#ffb347','#ff7070']);
    const tbody=document.getElementById('repTbody');
    if(tbody) tbody.innerHTML=summary.map(r=>{const pct=Math.round((r.present_count||0)/((r.total_days||1))*100);const st=getStatus(pct);return'<tr><td><strong>'+(r.name||'?')+'</strong></td><td><code>'+(r.roll_number||'?')+'</code></td><td>'+(r.section||'—')+'</td><td style="font-family:var(--mono)">'+(r.present_count||0)+'/'+(r.total_days||0)+'</td><td>'+attBar(pct)+'</td><td><span class="badge '+st.bc+'">'+st.label+'</span></td></tr>';}).join('')||'<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text3)">No data yet</td></tr>';
  } catch(e){ toast('Reports failed: '+e.message,'error'); }
}

// ── ALERTS ────────────────────────────────────────────────────
async function renderAlertsPage() {
  try {
    const summary=await api.attSummary(30);
    APP.localAlerts=[];
    let id=1;
    summary.forEach(r=>{
      const pct=Math.round((r.present_count||0)/((r.total_days||1))*100);
      const info={name:r.name,roll:r.roll_number||r.student_id,section:r.section,pct};
      if(pct<65) APP.localAlerts.push({id:id++,type:'critical',...info,msg:'CRITICAL — '+pct+'% — HOD alerted'});
      else if(pct<70) APP.localAlerts.push({id:id++,type:'incharge',...info,msg:'Incharge notified — '+pct+'%'});
      else if(pct<75) APP.localAlerts.push({id:id++,type:'student',...info,msg:'Student notified — '+pct+'%'});
    });
    setEl('notifBadge', APP.localAlerts.length);
    const pill=document.getElementById('navAlertPill');
    if(pill) pill.textContent=APP.localAlerts.length;
    renderAlertFeed();
    const crit=summary.filter(r=>(r.present_count||0)/((r.total_days||1))*100<65);
    setEl('critCountBadge', crit.length+' critical');
    const critEl=document.getElementById('critStudentList');
    if(critEl) critEl.innerHTML=crit.length?crit.sort((a,b)=>a.present_count-b.present_count).map(r=>{const p=Math.round((r.present_count||0)/((r.total_days||1))*100);return'<div class="crit-item"><div class="crit-av">'+initials(r.name||'?')+'</div><div><div class="crit-name">'+(r.name||'?')+'</div><div class="crit-info">'+(r.roll_number||'')+'  Sec '+(r.section||'?')+'</div></div><div class="crit-pct">'+p+'%</div></div>';}).join(''):'<div style="padding:20px;text-align:center;color:var(--mint-d)">✓ No critical students</div>';
  } catch(e){ toast('Alerts failed: '+e.message,'error'); }
}

function renderAlertFeed() {
  const feed=document.getElementById('alertFeedEl');
  if(!feed) return;
  const list=APP.alertFilter==='all'?APP.localAlerts:APP.localAlerts.filter(a=>a.type===APP.alertFilter);
  const icons={student:'fa-user-clock',incharge:'fa-clipboard-user',critical:'fa-radiation'};
  feed.innerHTML=list.length?list.map(a=>'<div class="alert-item"><div class="ai-icon '+a.type+'"><i class="fa '+icons[a.type]+'"></i></div><div><div class="ai-title">'+a.name+' — '+a.roll+'</div><div class="ai-msg">'+a.msg+'</div><div class="ai-msg" style="color:var(--text3)">Section '+(a.section||'?')+'</div></div><div class="ai-badge-wrap"><span class="badge '+(a.type==='student'?'b-amber':a.type==='incharge'?'b-d':'b-c')+'">'+a.type+'</span></div></div>').join('')
  :'<div style="padding:28px;text-align:center;color:var(--text3)"><i class="fa fa-check-circle" style="font-size:2rem;color:var(--mint-d);display:block;margin-bottom:8px"></i>No alerts</div>';
}

function setAlertFilter(type,btn){ APP.alertFilter=type; document.querySelectorAll('.tab-b').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); renderAlertFeed(); }
async function runAlerts(){ await renderAlertsPage(); toast('Alert engine ran','warn'); }
async function bulkSendAlerts(){ toast('Bulk alert logged','warn'); }

// ── SETTINGS ──────────────────────────────────────────────────
async function renderSettingsPage() {
  const pg=document.getElementById('pg-settings');
  if(!pg) return;
  pg.innerHTML='<div class="page-header"><div class="ph-left"><h2>System Settings</h2><p>Recognition thresholds</p></div></div><div class="card" id="settingsCard"><div class="card-head"><h4><i class="fa fa-gear"></i> Thresholds</h4></div><div style="padding:20px"><i class="fa fa-spinner fa-spin"></i> Loading...</div></div>';
  try {
    const s=await api.settings();
    document.getElementById('settingsCard').innerHTML='<div class="card-head"><h4><i class="fa fa-gear"></i> Recognition Thresholds</h4><button class="btn-primary" onclick="saveSettings()"><i class="fa fa-save"></i> Save</button></div><div style="padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:14px">'+Object.entries(s).map(([k,v])=>'<div class="fg"><label>'+k.replace(/_/g,' ')+'</label><input id="stg_'+k+'" value="'+v+'" type="'+(typeof v==='boolean'?'checkbox':'text')+'" '+(typeof v==='boolean'&&v?'checked':'')+'/></div>').join('')+'</div>';
  } catch(e){ toast('Settings failed: '+e.message,'error'); }
}

async function saveSettings() {
  const keys=['LBPH_THRESHOLD','DLIB_DISTANCE','MIN_CONFIDENCE_PCT','CONFIRM_FRAMES_REQUIRED','LIVENESS_THRESHOLD','LIVENESS_ON','CAMERA_INDEX'];
  const data={};
  keys.forEach(k=>{const el=document.getElementById('stg_'+k);if(el)data[k]=el.type==='checkbox'?el.checked:el.value;});
  try{ await api.saveSettings(data); toast('Settings saved!','success'); } catch(e){ toast('Save failed: '+e.message,'error'); }
}

// ── TRAIN ─────────────────────────────────────────────────────
function renderTrainPage() {
  const pg=document.getElementById('pg-train');
  if(!pg) return;
  pg.innerHTML=`<div class="page-header"><div class="ph-left"><h2>Train Models</h2><p>Rebuild LBPH + dlib face recognition models from enrolled images</p></div></div>
    <div class="card"><div class="card-head"><h4><i class="fa fa-brain"></i> Model Training</h4></div>
    <div style="padding:24px">
      <p style="font-size:.88rem;color:var(--text2);margin-bottom:16px">Run after enrolling students via <code>python main.py → [1] Enrol</code>.</p>
      <div style="display:flex;gap:12px;margin-bottom:20px">
        <button class="btn-primary" id="btnTrain" onclick="startTraining()"><i class="fa fa-play"></i> Start Training</button>
        <button class="btn-secondary" onclick="checkTrainStatus()"><i class="fa fa-rotate-right"></i> Check Status</button>
      </div>
      <div id="trainStatus" class="card" style="background:var(--bg);padding:16px;font-family:var(--mono);font-size:.78rem;min-height:80px;white-space:pre-wrap;color:var(--text2)">Ready. Press Start Training.</div>
    </div></div>`;
}

async function startTraining() {
  const btn=document.getElementById('btnTrain');
  btn.disabled=true; btn.innerHTML='<i class="fa fa-spinner fa-spin"></i> Training...';
  setEl('trainStatus','Training started in background...');
  try {
    await api.trainStart(); toast('Training started!','info');
    clearInterval(APP.trainPollTimer);
    APP.trainPollTimer=setInterval(checkTrainStatus,3000);
  } catch(e){ toast('Failed: '+e.message,'error'); btn.disabled=false; btn.innerHTML='<i class="fa fa-play"></i> Start Training'; }
}

async function checkTrainStatus() {
  try {
    const s=await api.trainStatus();
    const el=document.getElementById('trainStatus');
    if(el) el.textContent=s.log?.join('\n')||'Running...';
    if(!s.running){ clearInterval(APP.trainPollTimer); const btn=document.getElementById('btnTrain'); if(btn){btn.disabled=false;btn.innerHTML='<i class="fa fa-play"></i> Start Training';} if(s.error)toast('Training error: '+s.error,'error'); else if(s.done)toast('Training complete!','success'); }
  } catch(e){}
}

// ── FACULTY DASHBOARD ─────────────────────────────────────────
async function renderFacDashboard() {
  const el=document.getElementById('facDashContent');
  if(!el) return;
  el.innerHTML='<div class="empty-msg"><i class="fa fa-spinner fa-spin"></i><p>Loading...</p></div>';
  try {
    const [analytics,today]=await Promise.all([api.analytics(),api.todayAtt()]);
    el.innerHTML=`<div class="fac-dash-welcome"><div class="fdw-bg"></div>
      <div class="fdw-title">Welcome, ${(_user.name||'Faculty').split(' ')[0]}! 👋</div>
      <div class="fdw-sub">Faculty Portal · ${_user.fac_id||''}</div>
      <div class="fdw-meta"><span class="fdw-m"><i class="fa fa-id-card"></i> ${_user.fac_id||'—'}</span><span class="fdw-m"><i class="fa fa-calendar-day"></i> ${new Date().toLocaleDateString('en-IN')}</span></div>
    </div>
    <div class="kpi-strip">
      ${kpi('Total Students',analytics.total_students,'fa-users','#4ecba8')}
      ${kpi('Present Today',analytics.present_today,'fa-circle-check','#4da6f5')}
      ${kpi('Today %',analytics.pct_today+'%','fa-percent','#ffb347')}
      ${kpi('Critical',analytics.critical_count,'fa-radiation','#e05454')}
    </div>
    <div class="card"><div class="card-head"><h4><i class="fa fa-list-check"></i> Today's Attendance</h4></div>
    <div class="table-scroll"><table class="data-tbl"><thead><tr><th>Name</th><th>ID</th><th>Period</th><th>Time</th><th>Confidence</th></tr></thead>
    <tbody>${today.length?today.map(r=>'<tr><td><strong>'+(r.name||'?')+'</strong></td><td><code>'+(r.student_id||'?')+'</code></td><td>'+(r.period||'—')+'</td><td style="font-family:var(--mono)">'+String(r.time||'').slice(0,8)+'</td><td>'+confBadge(r.confidence)+'</td></tr>').join(''):'<tr><td colspan="5" style="text-align:center;padding:16px;color:var(--text3)">No attendance today</td></tr>'}</tbody></table></div></div>`;
  } catch(e){ el.innerHTML='<div class="empty-msg"><i class="fa fa-triangle-exclamation"></i><p>'+e.message+'</p></div>'; }
}

// ── CHARTS ────────────────────────────────────────────────────
function mkBar(id,labels,data,colors,suffix){
  const ctx=document.getElementById(id); if(!ctx) return;
  try{APP.charts[id]?.destroy();}catch(e){}
  APP.charts[id]=new Chart(ctx,{type:'bar',data:{labels,datasets:[{data,backgroundColor:Array.isArray(colors)?colors:data.map(()=>colors),borderRadius:8,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:true,plugins:{legend:{display:false},tooltip:{backgroundColor:'#fff',titleColor:'#1a2332',bodyColor:'#5a6a80',borderColor:'#dde4f0',borderWidth:1.5,padding:10,cornerRadius:10,callbacks:{label:c=>' '+c.parsed.y+(suffix||'')}}},scales:{x:{grid:{display:false},ticks:{color:'#96a8be',font:{size:10,family:'Plus Jakarta Sans'}}},y:{grid:{color:'rgba(0,0,0,.06)'},ticks:{color:'#96a8be',font:{size:10}},beginAtZero:true}}}});
}

function mkDonut(id,labels,data,colors){
  const ctx=document.getElementById(id); if(!ctx) return;
  try{APP.charts[id]?.destroy();}catch(e){}
  APP.charts[id]=new Chart(ctx,{type:'doughnut',data:{labels,datasets:[{data,backgroundColor:colors,borderWidth:3,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:true,cutout:'65%',plugins:{legend:{position:'bottom',labels:{color:'#5a6a80',font:{size:10.5,family:'Plus Jakarta Sans'},padding:10,boxWidth:12}},tooltip:{backgroundColor:'#fff',titleColor:'#1a2332',bodyColor:'#5a6a80',borderColor:'#dde4f0',borderWidth:1.5,padding:10,cornerRadius:10}}}});
}

// ── HELPERS ───────────────────────────────────────────────────
function kpi(label,value,icon,color){return'<div class="kpi-card" style="--kc:'+color+'"><div class="kpi-icon"><i class="fa '+icon+'"></i></div><div class="kpi-val">'+value+'</div><div class="kpi-lbl">'+label+'</div></div>';}
function attBar(pct){const st=getStatus(pct);return'<div class="att-bar"><div class="att-track"><div class="att-fill '+st.cls+'" style="width:'+pct+'%"></div></div><span class="att-pct" style="color:'+st.color+'">'+pct+'%</span></div>';}
function confBadge(conf){const p=Math.round(parseFloat(conf||0)*100);return'<span class="badge '+(p>=75?'b-g':p>=50?'b-w':'b-d')+'">'+p+'%</span>';}
function getStatus(pct){if(pct>=75)return{cls:'g',bc:'b-g',label:'✓ Good',color:'var(--mint-d)'};if(pct>=70)return{cls:'w',bc:'b-w',label:'⚠ Warn',color:'var(--amber-d)'};if(pct>=65)return{cls:'d',bc:'b-d',label:'✗ Poor',color:'var(--coral-d)'};return{cls:'d',bc:'b-c',label:'☠ Critical',color:'#b22222'};}
function initials(name){return(name||'').split(' ').map(n=>n[0]).join('').toUpperCase().slice(0,2)||'??';}
function setEl(id,val){const el=document.getElementById(id);if(el)el.innerHTML=val;}
function closeModal(id){document.getElementById(id)?.classList.add('dn');}
function toast(msg,type){const icons={success:'fa-circle-check',error:'fa-circle-exclamation',info:'fa-circle-info',warn:'fa-triangle-exclamation'};const z=document.getElementById('toastContainer');if(!z)return;const el=document.createElement('div');el.className='toast '+(type||'info');el.innerHTML='<i class="fa '+(icons[type||'info']||'fa-circle-info')+'"></i><span>'+msg+'</span>';z.appendChild(el);setTimeout(()=>{el.classList.add('toast-out');setTimeout(()=>el.remove(),300);},4000);}

// Stubs for HTML-referenced functions
// ── Stub functions (overridden by features.js after DOMContentLoaded) ──────────
// Non-feature stubs (keep as real no-ops)
function attOnDeptChange(){}
function attOnCourseChange(){}
function ttOnDeptChange(){}
function ttOnCourseChange(){}
function renderTimetable(){}
function renderCIPage(){}
function loadCIData(){}
function ciAlert(){}
function onAnlLevelChange(){}
function renderAnalytics(){}
function renderMyTimetable(){ renderTimetablePage(); }
function renderMyClasses(){}
function renderMyAttendance(){ renderReportsPage(); }

// Feature 1 stubs — replaced by features.js
function drillGoto(){}
function drillToCourse(d){ window.drillToCourse && window.drillToCourse(d); }
function drillToSection(c,col,dk){ window.drillToSection && window.drillToSection(c,col,dk); }
function drillToSectionDetail(c,s,col,dk){ window.drillToSectionDetail && window.drillToSectionDetail(c,s,col,dk); }
function initDeptDrill(){ window.initDeptDrill && window.initDeptDrill(); }

// Feature 2 stubs — replaced by features.js
function renderFacultyPage(){ window.renderFacultyPage && window.renderFacultyPage(); }
function openMarkFacultyModal(){ window.openMarkFacultyModal && window.openMarkFacultyModal(); }
function editFacAtt(id,lid){ window.editFacAtt && window.editFacAtt(id,lid); }
function saveFacultyAttendance(){ window.saveFacultyAttendance && window.saveFacultyAttendance(); }
function viewFacDetail(id){ window.viewFacDetail && window.viewFacDetail(id); }

document.addEventListener('keydown',e=>{if(e.key!=='Enter')return;const ls=document.getElementById('loginScreen');if(ls&&ls.style.display!=='none'){const fac=document.querySelector('.ptab.active')?.dataset?.portal==='faculty';fac?loginFaculty():loginAdmin();}});
document.addEventListener('click',e=>{const sb=document.getElementById('sidebar');if(sb?.classList.contains('open')&&!sb.contains(e.target)&&!e.target.closest('.mob-ham'))closeSidebar();});
