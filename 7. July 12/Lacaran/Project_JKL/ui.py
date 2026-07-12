INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BuildScope Consultation Portal</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {
      --ink: #17202a;
      --muted: #5b6573;
      --line: #d9e0ea;
      --panel: #ffffff;
      --soft: #f5f7fa;
      --accent: #2563eb;
      --green: #0f766e;
      --warn: #b45309;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #eef2f6;
    }
    header {
      background: linear-gradient(135deg, #f8fbff 0%, #eef4f1 52%, #f7f1e8 100%);
      border-bottom: 1px solid var(--line);
      padding: 24px clamp(16px, 4vw, 42px);
    }
    header h1 { margin: 0 0 8px; font-size: clamp(28px, 4vw, 42px); line-height: 1.05; }
    header p { margin: 0; max-width: 920px; color: var(--muted); }
    main { padding: 18px clamp(14px, 3vw, 34px) 42px; }
    .notice {
      border-left: 5px solid var(--warn);
      background: #fff7ed;
      color: #5f370e;
      border-radius: 6px;
      padding: 12px 14px;
      margin-bottom: 16px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }
    .tabs, .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    button, .button {
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 8px;
      min-height: 38px;
      padding: 9px 12px;
      font-weight: 650;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button.success { background: var(--green); border-color: var(--green); color: white; }
    button.active { background: #dbeafe; border-color: #93c5fd; color: #1e3a8a; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .span-12 { grid-column: span 12; }
    .span-8 { grid-column: span 8; }
    .span-6 { grid-column: span 6; }
    .span-4 { grid-column: span 4; }
    h2, h3 { margin: 0 0 12px; }
    h3 { font-size: 18px; }
    label { display: block; font-size: 13px; font-weight: 650; color: #344054; margin: 10px 0 5px; }
    input, select, textarea {
      width: 100%;
      border: 1px solid #cfd7e3;
      border-radius: 7px;
      padding: 10px;
      font: inherit;
      background: white;
    }
    textarea { min-height: 82px; resize: vertical; }
    input[type="checkbox"] { width: auto; margin-right: 8px; }
    .two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .three { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
    .metric { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 13px; }
    .metric strong { display: block; font-size: 26px; }
    .metric span { color: var(--muted); font-size: 13px; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid var(--line); font-size: 14px; vertical-align: top; }
    th { background: #f8fafc; color: #344054; }
    tr:hover td { background: #f7fbff; }
    .status { display: inline-block; border-radius: 999px; padding: 3px 9px; background: #eef2ff; color: #3730a3; font-size: 12px; font-weight: 700; }
    .muted { color: var(--muted); }
    .hidden { display: none !important; }
    #map { height: 340px; border-radius: 8px; border: 1px solid var(--line); }
    .file-list { margin: 8px 0 0; padding-left: 18px; }
    .note { background: #f8fafc; border: 1px solid var(--line); border-radius: 7px; padding: 10px; margin-top: 8px; }
    @media (max-width: 900px) {
      .span-8, .span-6, .span-4 { grid-column: span 12; }
      .two, .three, .metrics { grid-template-columns: 1fr; }
      .topbar { align-items: stretch; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <h1>BuildScope Consultation Portal</h1>
    <p>Collect complete client, site, budget, upload, and technical requirements before preparing a proposal or scheduling professional review.</p>
  </header>
  <main>
    <div class="notice"><strong>Professional review required.</strong> This app collects requirements only. It does not generate final structural designs, calculations, engineering approvals, or construction instructions. All structural design, analysis, and recommendations must be reviewed and approved by a licensed professional engineer or architect according to applicable local codes and regulations.</div>

    <div class="topbar">
      <div class="tabs">
        <button id="clientTab" class="active" onclick="showRole('client')">Client/User</button>
        <button id="adminTab" onclick="showRole('admin')">Admin/Engineer</button>
      </div>
      <div class="actions">
        <button onclick="newSubmission()">New submission</button>
        <button class="primary" onclick="saveProject('Draft')">Save draft</button>
        <button class="success" onclick="saveProject('Submitted')">Submit final</button>
      </div>
    </div>

    <section id="clientView" class="grid">
      <div class="panel span-12">
        <h2>Client Project Submission</h2>
        <p class="muted">Fill in what you know now. Drafts can be continued later from the status table.</p>
      </div>

      <form id="projectForm" class="span-12 grid">
        <section class="panel span-6">
          <h3>Client Information</h3>
          <div class="two">
            <div><label>Full name</label><input name="client.full_name" required></div>
            <div><label>Email address</label><input name="client.email" type="email" required></div>
            <div><label>Phone number</label><input name="client.phone"></div>
            <div><label>Company name, if applicable</label><input name="client.company"></div>
            <div><label>Client type</label><select name="client.client_type"></select></div>
            <div><label>Preferred contact method</label><select name="client.contact_method"></select></div>
          </div>
          <label>Current address</label><textarea name="client.current_address"></textarea>
          <label>Billing address, if different</label><textarea name="client.billing_address"></textarea>
          <label><input type="checkbox" name="client.consent">Consent to data privacy and use of uploaded information for project review</label>
        </section>

        <section class="panel span-6">
          <h3>Project Basic Information</h3>
          <div class="two">
            <div><label>Project title</label><input name="project.title" required></div>
            <div><label>Project type</label><select name="project.type"></select></div>
            <div><label>Desired start date</label><input name="project.desired_start_date" type="date"></div>
            <div><label>Target completion date</label><input name="project.target_completion_date" type="date"></div>
            <div><label>Project priority</label><select name="project.priority"></select></div>
            <div><label>Current project stage</label><select name="project.stage"></select></div>
          </div>
          <label>Project description</label><textarea name="project.description"></textarea>
        </section>

        <section class="panel span-8">
          <h3>Location and Site Information</h3>
          <div id="map"></div>
          <div class="two">
            <div><label>Latitude</label><input name="location.latitude" type="number" step="0.000001"></div>
            <div><label>Longitude</label><input name="location.longitude" type="number" step="0.000001"></div>
          </div>
          <label>Project address</label><textarea name="location.project_address"></textarea>
          <div class="three">
            <div><label>Country</label><input name="location.country" value="Philippines"></div>
            <div><label>Region / province / state</label><input name="location.region"></div>
            <div><label>City / municipality</label><input name="location.city"></div>
            <div><label>Barangay / district / neighborhood</label><input name="location.district"></div>
            <div><label>ZIP / postal code</label><input name="location.zip_code"></div>
            <div><label>Lot number / title reference</label><input name="location.lot_reference"></div>
          </div>
          <div class="two">
            <div><label>Site accessibility notes</label><textarea name="location.accessibility_notes"></textarea></div>
            <div><label>Nearby landmarks</label><textarea name="location.landmarks"></textarea></div>
          </div>
        </section>

        <section class="panel span-4">
          <h3>Optional Site Conditions</h3>
          <label>Site terrain / condition</label><select name="site.conditions" multiple size="7"></select>
          <label>Is the site accessible by road?</label><select name="site.road_access"><option>Unknown</option><option>Yes</option><option>No</option></select>
          <label>Road width near the property</label><input name="site.road_width">
          <label>Distance from main road</label><input name="site.distance_main_road">
          <label>Nearby water or drainage systems</label><input name="site.water_nearby">
          <label>Known flooding history</label><textarea name="site.flooding_history"></textarea>
          <label>Known landslide risk</label><textarea name="site.landslide_risk"></textarea>
          <label>Known soil issues</label><textarea name="site.soil_issues"></textarea>
          <label>Existing structures on site</label><textarea name="site.existing_structures"></textarea>
          <label>Nearby buildings or boundary constraints</label><textarea name="site.boundary_constraints"></textarea>
        </section>

        <section class="panel span-6">
          <h3>Weather, Climate, and Environmental Information</h3>
          <div class="two">
            <div><label>Local weather conditions</label><input name="environment.weather"></div>
            <div><label>Rainfall intensity</label><input name="environment.rainfall"></div>
            <div><label>Wind exposure</label><input name="environment.wind_exposure"></div>
            <div><label>Flood risk</label><input name="environment.flood_risk"></div>
            <div><label>Seismic zone or earthquake risk</label><input name="environment.seismic_risk"></div>
          </div>
          <label>Other environmental notes</label><textarea name="environment.notes"></textarea>
        </section>

        <section class="panel span-6">
          <h3>Budget, Technical Needs, and Uploads</h3>
          <div class="two">
            <div><label>Estimated budget range</label><select name="budget.range"></select></div>
            <div><label>Estimated floors / levels</label><input name="technical.floors" type="number" min="0"></div>
            <div><label>Approximate floor area (sqm)</label><input name="technical.floor_area_sqm" type="number" min="0" step="0.01"></div>
            <div><label>Services needed</label><select name="technical.services_needed" multiple size="5"></select></div>
          </div>
          <label>Budget notes</label><textarea name="budget.notes"></textarea>
          <label>Preferred construction materials or system</label><textarea name="technical.materials"></textarea>
          <label>Special requirements / constraints</label><textarea name="technical.special_requirements"></textarea>
          <label>Upload photos, sketches, plans, titles, or reference files</label><input id="uploads" type="file" multiple>
          <ul id="existingUploads" class="file-list"></ul>
        </section>
      </form>

      <section class="panel span-12">
        <h3>Submission Status</h3>
        <div id="clientStatus"></div>
      </section>
    </section>

    <section id="adminView" class="hidden">
      <div id="metrics" class="metrics"></div>
      <section class="panel">
        <h2>Admin / Engineer Review</h2>
        <div class="three">
          <div><label>Project type</label><select id="filterType"></select></div>
          <div><label>Status</label><select id="filterStatus"></select></div>
          <div><label>Location contains</label><input id="filterLocation"></div>
          <div><label>Budget</label><select id="filterBudget"></select></div>
          <div><label>Created on or after</label><input id="filterDate" type="date"></div>
          <div><label>&nbsp;</label><a class="button" href="/api/export.csv">Export all CSV</a></div>
        </div>
        <div id="adminTable" style="margin-top:14px"></div>
      </section>
      <section id="detailPanel" class="panel" style="margin-top:14px"></section>
    </section>
  </main>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const lists = {
      clientTypes: ["Individual", "Contractor", "Developer", "Company", "Government", "Other"],
      contactMethods: ["Email", "Phone", "SMS", "WhatsApp", "Viber", "Other"],
      projectTypes: ["Residential house", "Apartment", "Commercial building", "Warehouse", "Road", "Bridge", "Renovation", "Extension", "Structural assessment", "Retrofitting", "Other"],
      priorities: ["Low", "Medium", "High", "Urgent"],
      stages: ["Idea only", "With sketch", "With architectural plan", "With existing structural plan", "Already under construction", "Existing structure for assessment", "Other"],
      siteConditions: ["Flat", "Sloped", "Hilly", "Coastal", "Flood-prone", "Mountainous", "Unknown"],
      statuses: ["Draft", "Submitted", "Under Review", "Needs More Info", "Proposal Prepared", "On Hold", "Closed"],
      budgets: ["Not sure", "Under 500k", "500k - 1M", "1M - 3M", "3M - 5M", "5M - 10M", "10M+"],
      services: ["Architectural planning", "Structural design", "Structural assessment", "Retrofitting advice", "Bill of materials estimate", "Site inspection", "Construction consultation", "Permit support"]
    };
    let projects = [];
    let currentProject = blankProject();
    let map, marker;

    function optionFill(selector, values, all=false) {
      const el = document.querySelector(selector);
      el.innerHTML = (all ? ["All", ...values] : values).map(v => `<option>${v}</option>`).join("");
    }
    function initLists() {
      optionFill('[name="client.client_type"]', lists.clientTypes);
      optionFill('[name="client.contact_method"]', lists.contactMethods);
      optionFill('[name="project.type"]', lists.projectTypes);
      optionFill('[name="project.priority"]', lists.priorities);
      optionFill('[name="project.stage"]', lists.stages);
      optionFill('[name="site.conditions"]', lists.siteConditions);
      optionFill('[name="budget.range"]', lists.budgets);
      optionFill('[name="technical.services_needed"]', lists.services);
      optionFill('#filterType', lists.projectTypes, true);
      optionFill('#filterStatus', lists.statuses, true);
      optionFill('#filterBudget', lists.budgets, true);
    }
    function blankProject() {
      return { id: "", status: "Draft", client: {}, project: {}, location: { latitude: 14.5995, longitude: 120.9842, country: "Philippines" }, site: {}, environment: {}, technical: {}, budget: {}, uploads: [], internal_notes: [] };
    }
    function showRole(role) {
      document.getElementById("clientView").classList.toggle("hidden", role !== "client");
      document.getElementById("adminView").classList.toggle("hidden", role !== "admin");
      document.getElementById("clientTab").classList.toggle("active", role === "client");
      document.getElementById("adminTab").classList.toggle("active", role === "admin");
      if (role === "admin") renderAdmin();
      setTimeout(() => map && map.invalidateSize(), 100);
    }
    function getByPath(obj, path) {
      return path.split(".").reduce((acc, part) => acc && acc[part], obj);
    }
    function setByPath(obj, path, value) {
      const parts = path.split(".");
      let ref = obj;
      parts.slice(0, -1).forEach(part => ref = ref[part] ||= {});
      ref[parts.at(-1)] = value;
    }
    function fillForm(project) {
      currentProject = JSON.parse(JSON.stringify(project));
      document.querySelectorAll("[name]").forEach(el => {
        const value = getByPath(currentProject, el.name);
        if (el.type === "checkbox") el.checked = Boolean(value);
        else if (el.multiple) [...el.options].forEach(o => o.selected = (value || []).includes(o.value));
        else el.value = value ?? "";
      });
      document.querySelector('[name="location.latitude"]').value = currentProject.location.latitude || 14.5995;
      document.querySelector('[name="location.longitude"]').value = currentProject.location.longitude || 120.9842;
      document.getElementById("existingUploads").innerHTML = (currentProject.uploads || []).map(f => `<li>${escapeHtml(f.name)}</li>`).join("");
      moveMarker(Number(currentProject.location.latitude) || 14.5995, Number(currentProject.location.longitude) || 120.9842);
    }
    function collectForm() {
      const data = JSON.parse(JSON.stringify(currentProject));
      document.querySelectorAll("[name]").forEach(el => {
        let value = el.type === "checkbox" ? el.checked : el.multiple ? [...el.selectedOptions].map(o => o.value) : el.value;
        setByPath(data, el.name, value);
      });
      return data;
    }
    async function filesToPayload() {
      const files = [...document.getElementById("uploads").files];
      return Promise.all(files.map(file => new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = () => resolve({ name: file.name, data: reader.result.split(",")[1] });
        reader.readAsDataURL(file);
      })));
    }
    async function saveProject(status) {
      const data = collectForm();
      if (status === "Submitted" && !data.client.consent) {
        alert("Please check the consent box before final submission.");
        return;
      }
      data.status = status;
      data.new_uploads = await filesToPayload();
      const res = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      currentProject = await res.json();
      document.getElementById("uploads").value = "";
      fillForm(currentProject);
      await loadProjects();
      alert(`${currentProject.status} saved. Reference ID: ${currentProject.id}`);
      if (status === "Submitted") newSubmission();
    }
    function newSubmission() {
      fillForm(blankProject());
    }
    async function loadProjects() {
      projects = await (await fetch("/api/projects")).json();
      renderClientStatus();
      renderAdmin();
    }
    function flatten(p) {
      return {
        id: p.id, status: p.status, title: p.project?.title || "Untitled", type: p.project?.type || "",
        priority: p.project?.priority || "", client: p.client?.full_name || "", email: p.client?.email || "",
        location: [p.location?.city, p.location?.region, p.location?.country].filter(Boolean).join(", "),
        budget: p.budget?.range || "", created: (p.created_at || "").slice(0, 10), uploads: (p.uploads || []).length
      };
    }
    function table(rows, click=false) {
      if (!rows.length) return `<p class="muted">No records yet.</p>`;
      return `<table><thead><tr>${["ID","Status","Title","Type","Priority","Client","Location","Budget","Created","Files"].map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>` +
        rows.map(p => { const r = flatten(p); return `<tr ${click ? `onclick="openDetail('${p.id}')" style="cursor:pointer"` : `onclick="editProject('${p.id}')" style="cursor:pointer"`}><td>${r.id}</td><td><span class="status">${r.status}</span></td><td>${escapeHtml(r.title)}</td><td>${r.type}</td><td>${r.priority}</td><td>${escapeHtml(r.client)}</td><td>${escapeHtml(r.location)}</td><td>${r.budget}</td><td>${r.created}</td><td>${r.uploads}</td></tr>`; }).join("") +
        `</tbody></table>`;
    }
    function renderClientStatus() {
      document.getElementById("clientStatus").innerHTML = table(projects, false);
    }
    function editProject(id) {
      const p = projects.find(item => item.id === id);
      if (p) fillForm(p);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    function filteredProjects() {
      const type = document.getElementById("filterType").value;
      const status = document.getElementById("filterStatus").value;
      const budget = document.getElementById("filterBudget").value;
      const loc = document.getElementById("filterLocation").value.toLowerCase();
      const date = document.getElementById("filterDate").value;
      return projects.filter(p => {
        const f = flatten(p);
        return (type === "All" || f.type === type) &&
          (status === "All" || f.status === status) &&
          (budget === "All" || f.budget === budget) &&
          (!loc || f.location.toLowerCase().includes(loc)) &&
          (!date || f.created >= date);
      });
    }
    function renderAdmin() {
      const rows = filteredProjects();
      const review = projects.filter(p => ["Submitted", "Under Review", "Needs More Info"].includes(p.status)).length;
      const urgent = projects.filter(p => p.project?.priority === "Urgent").length;
      document.getElementById("metrics").innerHTML = [
        ["Total projects", projects.length], ["Final submissions", projects.filter(p => p.status !== "Draft").length],
        ["Needs review", review], ["Urgent priority", urgent]
      ].map(([label, count]) => `<div class="metric"><strong>${count}</strong><span>${label}</span></div>`).join("");
      document.getElementById("adminTable").innerHTML = table(rows, true);
    }
    function openDetail(id) {
      const p = projects.find(item => item.id === id);
      if (!p) return;
      const maps = `https://www.google.com/maps/search/?api=1&query=${p.location?.latitude || ""},${p.location?.longitude || ""}`;
      document.getElementById("detailPanel").innerHTML = `
        <h2>${escapeHtml(p.project?.title || "Untitled project")}</h2>
        <div class="three">
          <div><strong>Project ID</strong><br>${p.id}</div>
          <div><strong>Status</strong><br><span class="status">${p.status}</span></div>
          <div><strong>Client</strong><br>${escapeHtml(p.client?.full_name || "")}</div>
        </div>
        <p><a class="button" target="_blank" href="${maps}">Open location in Google Maps</a> <a class="button" href="/api/project/${p.id}.pdf">Export PDF</a></p>
        <div class="two">
          <div><label>Update status</label><select id="detailStatus">${lists.statuses.map(s => `<option ${s === p.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
          <div><label>Add internal note</label><textarea id="detailNote"></textarea></div>
        </div>
        <button class="primary" onclick="saveAdmin('${p.id}')">Save admin updates</button>
        <h3>Project Profile</h3>
        <pre>${escapeHtml(JSON.stringify(p, null, 2))}</pre>
        <h3>Uploaded Files</h3>
        ${(p.uploads || []).length ? (p.uploads || []).map(f => `<p><a class="button" href="/api/download/${p.id}/${encodeURIComponent(f.name)}">Download ${escapeHtml(f.name)}</a></p>`).join("") : `<p class="muted">No uploaded files.</p>`}
        <h3>Internal Notes</h3>
        ${(p.internal_notes || []).slice().reverse().map(n => `<div class="note">${escapeHtml(n.created_at)}: ${escapeHtml(n.text)}</div>`).join("") || `<p class="muted">No notes yet.</p>`}
      `;
    }
    async function saveAdmin(id) {
      await fetch(`/api/project/${id}/admin`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: document.getElementById("detailStatus").value, note: document.getElementById("detailNote").value }) });
      await loadProjects();
      openDetail(id);
    }
    function initMap() {
      if (!window.L) {
        document.getElementById("map").innerHTML = '<div class="note">Map tiles are unavailable. Enter latitude and longitude manually, then the admin can still open the point in Google Maps.</div>';
        return;
      }
      map = L.map("map").setView([14.5995, 120.9842], 13);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(map);
      marker = L.marker([14.5995, 120.9842]).addTo(map);
      map.on("click", e => {
        document.querySelector('[name="location.latitude"]').value = e.latlng.lat.toFixed(6);
        document.querySelector('[name="location.longitude"]').value = e.latlng.lng.toFixed(6);
        moveMarker(e.latlng.lat, e.latlng.lng);
      });
    }
    function moveMarker(lat, lng) {
      if (!marker || !map) return;
      marker.setLatLng([lat, lng]);
      map.setView([lat, lng], map.getZoom() || 13);
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, s => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[s]));
    }
    document.addEventListener("input", e => { if (e.target.id?.startsWith("filter")) renderAdmin(); });
    initLists();
    initMap();
    fillForm(blankProject());
    loadProjects();
  </script>
</body>
</html>"""
