import {
  MATCH_CONFIG, buildGameNamesExport as createGameNamesExport,
  buildMatchManifest as createMatchManifest, createMatchSelection,
  matchConfigFor, validateWorkspaceBundle, zirconIdentityKey,
} from "./alignment-workspace.mjs?v=20260927-match5";

(() => {
  "use strict";

  const root = document.getElementById("alignment-app");
  if (!root) return;

  const PAGE_SIZE = 50;
  const STATUS_LABELS = {
    pending_review: "待复核", pending_evidence: "待补证据", source_confirmed: "来源确认",
    confirmed: "已确认", candidate: "候选", conflict: "冲突", cross_entity_conflict: "跨实体冲突",
    ambiguous: "存在歧义", display_name_error: "显示名错误", approved: "已批准",
    corrected: "已更正", rejected: "不采纳", not_applicable: "不适用"
  };
  const CATEGORY_DEFS = [
    ["all", "全部记录", e => true], ["monster", "怪物", e => e.entity_type === "monster"],
    ["item", "物品", e => e.entity_type === "item"], ["skill", "技能", e => e.entity_type === "skill"],
    ["npc", "NPC", e => e.entity_type === "npc"], ["map", "MapInfo", e => e.entity_type === "map"],
    ["respawn", "刷新点", e => e.entity_type === "respawn"],
    ["ecology", "地图区域 / MapRegion", e => ["map_area", "map_group", "map_region"].includes(e.entity_type)],
    ["quest", "任务 / 任务链", e => e.entity_type.startsWith("quest") || e.entity_type === "mission"],
    ["drop", "掉落关系", e => e.entity_type === "drop"],
    ["shop", "商店关系", e => ["store_entry", "store_item"].includes(e.entity_type)]
  ];
  const COLUMN_DEFS = [
    ["index", "Index / ID"], ["identity", "实体身份"], ["website", "网站标准名"],
    ["game", "游戏显示名"], ["status", "复核状态"], ["evidence", "来源 / 证据"], ["match", "人工匹配"]
  ];
  const MATCH_PAGE_SIZE = 48;

  const el = id => document.getElementById(id);
  const app = {
    master: null, masterHash: "", records: [], byId: new Map(),
    database: null, serverWorkspace: false, currentCategory: "monster", page: 0, selectedId: null,
    sourceById: new Map(), observationsByEntity: new Map(), findingsByEntity: new Map(),
    originalDraft: {}, dirtyFields: new Set(), visibleColumns: new Set(COLUMN_DEFS.map(c => c[0])),
    candidateDownload: null, broadcast: null, sourceFilterIds: new Map(), previewById: new Map(),
    candidatesByType: new Map(), matchSourceId: null, matchPage: 0, matchShowSelected: false, matchBusy: false,
    priorFocus: null, modalReturnFocus: null, modalAction: null, onlyUnmatched: false, storagePersistence: false,
    state: { id: "workspace", revision: 0, drafts: {}, matches: {}, events: [] }
  };

  const safeText = value => value == null ? "—" : String(value);
  const effectiveDraft = record => app.state.drafts[record.id] || {};
  const baselineAssessment = record => record.assessment || { overall_status: "pending_review", fields: {}, export_enabled: false };
  const effectiveStatus = record => effectiveDraft(record).overall_status || baselineAssessment(record).overall_status || "pending_review";
  const fieldStatus = (record, field, draftKey) => effectiveDraft(record)[draftKey]
    || baselineAssessment(record).fields?.[field]?.status || (field === "resource_identity" ? "pending_evidence" : "pending_review");
  const statusLabel = status => STATUS_LABELS[status] || status || "待复核";
  const numberFormat = value => new Intl.NumberFormat("zh-CN").format(value || 0);

  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text != null) item.textContent = String(text);
    return item;
  }

  function appendText(parent, tag, className, text) {
    const item = node(tag, className, text);
    parent.append(item);
    return item;
  }

  function indexValue(record) {
    const index = record.identity?.zircon_index;
    return Number.isInteger(index) ? index : Number.MAX_SAFE_INTEGER;
  }

  function searchValue(record) {
    const identity = record.identity || {};
    const names = [identity.zircon_internal_name, identity.current_game_name, identity.standard_name_zh,
      identity.standard_name_ja, identity.current_translation?.zh, identity.current_translation?.ja,
      identity.website_name, identity.website_source_id, zirconIdentityKey(record),
      Number.isSafeInteger(identity.zircon_index) ? `Index ${identity.zircon_index}` : null,
      ...(identity.website_source_ids || []), ...(identity.aliases || []),
      ...(identity.candidate_website_names || []).flatMap(x => [x.name, x.source_id])];
    const scalarData = [];
    for (const [key, value] of Object.entries(record.game_data || {})) {
      if (["string", "number"].includes(typeof value)) scalarData.push(key, value);
    }
    return [...names, record.id, record.entity_type, indexValue(record) === Number.MAX_SAFE_INTEGER ? "" : indexValue(record), ...scalarData]
      .filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
  }

  function setStatus(message, isError = false) {
    for (const status of [el("workspace-status"), el("action-status")].filter(Boolean)) {
      status.textContent = message;
      status.classList.toggle("is-error", isError);
    }
  }

  function readRequest(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("本地数据库读取失败"));
    });
  }

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) return reject(new Error("此浏览器未提供 IndexedDB，本地编辑不可用。"));
      const request = indexedDB.open("mir3-alignment-workspace", 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains("workspace")) request.result.createObjectStore("workspace", { keyPath: "id" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("本地工作区无法打开"));
    });
  }

  function normalizeMatchEntries(matches) {
    if (!matches || typeof matches !== "object" || Array.isArray(matches)) throw new Error("本地匹配工作区结构损坏；未覆盖已保存数据。");
    const normalized = {};
    for (const [sourceId, saved] of Object.entries(matches)) {
      if (!saved || typeof saved !== "object" || !Array.isArray(saved.target_entity_ids)) {
        throw new Error(`本地匹配记录结构损坏：${sourceId}；未覆盖已保存数据。`);
      }
      if (Object.hasOwn(saved, "updated_at")
          && (typeof saved.updated_at !== "string" || !Number.isFinite(Date.parse(saved.updated_at)))) {
        throw new Error(`本地匹配保存时间无效：${sourceId}；未覆盖已保存数据。`);
      }
      const selection = createMatchSelection(sourceId, saved.target_entity_ids, app.byId, saved.updated_at || undefined);
      if (Object.hasOwn(saved, "target_identity_keys")
          && (!Array.isArray(saved.target_identity_keys)
            || JSON.stringify(saved.target_identity_keys) !== JSON.stringify(selection.target_identity_keys))) {
        throw new Error(`本地匹配身份键与当前 Zircon 主数据不一致：${sourceId}；未覆盖已保存数据。`);
      }
      normalized[sourceId] = { ...selection, updated_at: saved.updated_at || selection.updated_at };
    }
    return normalized;
  }

  async function readWorkspace() {
    if (app.serverWorkspace) {
      const response = await fetch("/api/workspace", { cache: "no-store" });
      if (!response.ok) throw new Error(`项目工作区读取失败（HTTP ${response.status}）`);
      const workspace = await response.json();
      return validateWorkspaceBundle({ schema_version: 2, format: "mir3-alignment-workspace",
        exported_at: new Date().toISOString(), base_master_sha256: app.masterHash, workspace },
      { masterHash: app.masterHash, recordsById: app.byId });
    }
    const tx = app.database.transaction("workspace", "readonly");
    const saved = await readRequest(tx.objectStore("workspace").get("workspace"));
    const workspace = saved
      ? { ...saved, drafts: saved.drafts || {}, matches: normalizeMatchEntries(saved.matches || {}), events: saved.events || [] }
      : { id: "workspace", revision: 0, drafts: {}, matches: {}, events: [] };
    return validateWorkspaceBundle({
      schema_version: 2, format: "mir3-alignment-workspace", exported_at: new Date().toISOString(),
      base_master_sha256: app.masterHash, workspace,
    }, { masterHash: app.masterHash, recordsById: app.byId });
  }

  function saveWorkspaceUpdate(recordId, originalDraft, changes) {
    if (app.serverWorkspace) return (async () => {
      const current = await readWorkspace(), savedDraft = current.drafts[recordId] || {};
      for (const field of app.dirtyFields) if (JSON.stringify(savedDraft[field]) !== JSON.stringify(originalDraft[field]))
        throw new Error(`此记录的“${fieldLabel(field)}”已在另一页面修改。已阻止覆盖；请刷新详情后比较。`);
      const after = { ...savedDraft, ...changes }, revision = current.revision + 1;
      const next = { ...current, revision, drafts: { ...current.drafts, [recordId]: after }, events: [...current.events, {
        id: `${Date.now()}-${crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`,
        at: new Date().toISOString(), entity_id: recordId, revision, action: "edit", before: savedDraft, after,
      }] };
      const response = await fetch("/api/workspace", { method: "PUT", headers: { "Content-Type": "application/json", "If-Match-Revision": String(current.revision) }, body: JSON.stringify(next) });
      if (response.status === 409) throw new Error("项目工作区已在另一页面更新，请刷新后重试。");
      if (!response.ok) throw new Error(`项目工作区写入失败（HTTP ${response.status}）`);
      return validateWorkspaceBundle({ schema_version: 2, format: "mir3-alignment-workspace", exported_at: new Date().toISOString(), base_master_sha256: app.masterHash, workspace: await response.json() }, { masterHash: app.masterHash, recordsById: app.byId });
    })();
    return new Promise((resolve, reject) => {
      const tx = app.database.transaction("workspace", "readwrite");
      const store = tx.objectStore("workspace");
      const request = store.get("workspace");
      let nextState;
      let conflict = null;
      request.onsuccess = () => {
        const current = request.result || { id: "workspace", revision: 0, drafts: {}, matches: {}, events: [] };
        const savedDraft = current.drafts[recordId] || {};
        for (const field of app.dirtyFields) {
          if (JSON.stringify(savedDraft[field]) !== JSON.stringify(originalDraft[field])) {
            conflict = `此记录的“${fieldLabel(field)}”已在另一标签页修改。已阻止覆盖；请刷新详情后比较。`;
            tx.abort();
            return;
          }
        }
        const before = { ...savedDraft };
        const after = { ...savedDraft, ...changes };
        const drafts = { ...current.drafts, [recordId]: after };
        const events = [...(current.events || []), {
          id: `${Date.now()}-${crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`,
          at: new Date().toISOString(), entity_id: recordId, revision: current.revision + 1,
          action: "edit", before, after: { ...after }
        }];
        nextState = { ...current, id: "workspace", revision: current.revision + 1, drafts,
          matches: current.matches || {}, events };
        store.put(nextState);
      };
      tx.oncomplete = () => resolve(nextState);
      tx.onerror = () => reject(tx.error || new Error("本地草稿保存失败"));
      tx.onabort = () => conflict ? reject(new Error(conflict)) : reject(tx.error || new Error("本地保存事务已中止"));
    });
  }

  function fieldLabel(key) {
    return ({ standard_name_zh: "中文标准名", overall_status: "整体判定", identity_mapping_status: "身份映射",
      display_name_status: "显示名", resource_status: "资源身份", game_data_status: "业务数据",
      relations_status: "关系", reason: "复核理由", export_enabled: "翻译导出开关" })[key] || key;
  }

  function buildIndexes() {
    app.records = app.master.entities;
    app.byId = new Map(app.records.map(record => [record.id, record]));
    app.sourceById.clear();
    for (const source of app.master.provenance?.inputs || []) {
      if (!app.sourceById.has(source.source_id)) app.sourceById.set(source.source_id, source);
    }
    app.externalSourceById = new Map((app.master.external_sources || []).map(source => [source.id, source]));
    app.searchQueryById = new Map((app.master.search_queries || []).map(query => [query.id, query]));
    app.observationsByEntity.clear();
    for (const observation of app.master.source_observations || []) {
      for (const id of observation.entity_refs || []) {
        if (!app.observationsByEntity.has(id)) app.observationsByEntity.set(id, []);
        app.observationsByEntity.get(id).push(observation);
      }
    }
    app.findingsByEntity.clear();
    for (const finding of app.master.research_findings || []) {
      for (const id of finding.entity_refs || []) {
        if (!app.findingsByEntity.has(id)) app.findingsByEntity.set(id, []);
        app.findingsByEntity.get(id).push(finding);
      }
    }
    app.candidatesByType = new Map();
    const candidateTypes = new Set(Object.values(MATCH_CONFIG).map(config => config.target));
    for (const record of app.records) {
      record._search = searchValue(record);
      if (!candidateTypes.has(record.entity_type) || !Number.isInteger(record.identity?.zircon_index)) continue;
      if (!app.candidatesByType.has(record.entity_type)) app.candidatesByType.set(record.entity_type, []);
      app.candidatesByType.get(record.entity_type).push(record);
    }
    for (const candidates of app.candidatesByType.values()) {
      candidates.sort((a, b) => indexValue(a) - indexValue(b)
        || (a.identity?.zircon_internal_name || a.id).localeCompare(b.identity?.zircon_internal_name || b.id, "en"));
    }
  }

  function categoryRecords(key) {
    const definition = CATEGORY_DEFS.find(item => item[0] === key) || CATEGORY_DEFS[0];
    return app.records.filter(definition[2]);
  }

  function createCategoryNav() {
    const nav = el("category-nav");
    nav.replaceChildren();
    for (const [key, title, filter] of CATEGORY_DEFS) {
      const button = node("button", "category-button");
      button.type = "button";
      button.dataset.category = key;
      button.setAttribute("aria-pressed", String(key === app.currentCategory));
      appendText(button, "span", "category-name", title);
      appendText(button, "span", "category-count", numberFormat(app.records.filter(filter).length));
      button.addEventListener("click", () => {
        app.currentCategory = key; app.page = 0;
        nav.querySelectorAll("button").forEach(item => item.setAttribute("aria-pressed", String(item.dataset.category === key)));
        renderRows();
      });
      nav.append(button);
    }
    el("category-total").textContent = numberFormat(app.records.length);
  }

  function fillFilters() {
    const statuses = new Set();
    const sources = new Set();
    for (const record of app.records) {
      statuses.add(effectiveStatus(record));
      for (const finding of app.findingsByEntity.get(record.id) || []) if (finding.source_status) statuses.add(finding.source_status);
      for (const observation of app.observationsByEntity.get(record.id) || []) {
        if (observation.source_status) statuses.add(observation.source_status);
        for (const ref of observation.evidence_refs || []) if (ref.source_id) sources.add(ref.source_id);
      }
      for (const ref of record.evidence || []) if (ref.source_id) sources.add(ref.source_id);
    }
    const statusOptions = [{ value: "", label: "所有状态" }, ...[...statuses].sort()
      .map(value => ({ value, label: statusLabel(value) }))];
    setPickerOptions(el("status-filter"), statusOptions);
    setPickerOptions(el("source-filter"), [{ value: "", label: "所有来源" }, ...[...sources].sort().map(value => ({
      value, label: app.sourceById.get(value)?.path || value
    }))]);
    createColumnOptions();
  }

  function setPickerOptions(picker, options) {
    const menu = picker.querySelector(".custom-picker-menu");
    menu.replaceChildren();
    for (const option of options) {
      const item = node("button", "custom-picker-option", option.label);
      item.type = "button";
      item.setAttribute("role", "option");
      item.dataset.pickerValue = option.value;
      item.setAttribute("aria-selected", String(picker.dataset.value === option.value));
      menu.append(item);
    }
    if (![...menu.children].some(option => option.dataset.pickerValue === picker.dataset.value)) {
      picker.dataset.value = options[0]?.value ?? "";
    }
    syncPicker(picker);
  }

  function syncPicker(picker) {
    const options = [...picker.querySelectorAll(".custom-picker-option")];
    const selected = options.find(option => option.dataset.pickerValue === picker.dataset.value);
    picker.querySelector(".custom-picker-current").textContent = selected?.textContent || picker.dataset.placeholder || "";
    for (const option of options) option.setAttribute("aria-selected", String(option === selected));
  }

  function setPickerValue(picker, value) {
    picker.dataset.value = String(value);
    syncPicker(picker);
  }

  function closePicker(picker, returnFocus = false) {
    if (!picker?.classList.contains("is-open")) return;
    picker.classList.remove("is-open");
    picker.querySelector(".custom-picker-menu").hidden = true;
    picker.querySelector(".custom-picker-trigger").setAttribute("aria-expanded", "false");
    if (returnFocus) picker.querySelector(".custom-picker-trigger").focus();
  }

  function openPicker(picker) {
    document.querySelectorAll(".custom-picker.is-open").forEach(item => closePicker(item));
    const trigger = picker.querySelector(".custom-picker-trigger");
    const menu = picker.querySelector(".custom-picker-menu");
    picker.classList.add("is-open");
    menu.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    const option = [...menu.children].find(item => item.dataset.pickerValue === picker.dataset.value) || menu.firstElementChild;
    option?.focus();
  }

  function setupPickers() {
    const editorOptions = {
      "edit-overall": ["pending_review", "pending_evidence", "confirmed", "conflict", "cross_entity_conflict", "corrected", "approved", "rejected"],
      "edit-identity": ["pending_review", "pending_evidence", "candidate", "source_confirmed", "confirmed", "conflict", "ambiguous", "rejected"],
      "edit-display": ["pending_review", "pending_evidence", "conflict", "display_name_error", "corrected", "approved", "rejected"],
      "edit-resource": ["pending_evidence", "pending_review", "candidate", "confirmed", "conflict", "not_applicable"],
      "edit-game-data": ["pending_review", "pending_evidence", "confirmed", "conflict", "corrected", "rejected"],
      "edit-relations": ["pending_review", "pending_evidence", "confirmed", "conflict", "rejected"],
    };
    for (const picker of document.querySelectorAll(".custom-picker")) {
      Object.defineProperty(picker, "value", {
        configurable: true,
        get() { return this.dataset.value || ""; },
        set(value) { setPickerValue(this, value); },
      });
      const id = picker.id;
      const options = id in editorOptions
        ? editorOptions[id].map(value => ({ value, label: statusLabel(value) }))
        : id === "sort-select"
          ? [{ value: "index", label: "Index 顺序" }, { value: "name", label: "名称顺序" }, { value: "status", label: "状态顺序" }]
          : [{ value: "", label: picker.dataset.placeholder }];
      setPickerOptions(picker, options);
      const trigger = picker.querySelector(".custom-picker-trigger");
      const menu = picker.querySelector(".custom-picker-menu");
      trigger.addEventListener("click", () => picker.classList.contains("is-open") ? closePicker(picker) : openPicker(picker));
      trigger.addEventListener("keydown", event => {
        if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
          event.preventDefault();
          openPicker(picker);
        }
      });
      menu.addEventListener("click", event => {
        const option = event.target.closest("[data-picker-value]");
        if (!option) return;
        const changed = picker.dataset.value !== option.dataset.pickerValue;
        setPickerValue(picker, option.dataset.pickerValue);
        closePicker(picker, true);
        if (changed) picker.dispatchEvent(new Event("change", { bubbles: true }));
      });
      menu.addEventListener("keydown", event => {
        const options = [...menu.querySelectorAll("[role=option]")];
        const index = options.indexOf(document.activeElement);
        let next = null;
        if (event.key === "ArrowDown") next = Math.min(options.length - 1, index + 1);
        else if (event.key === "ArrowUp") next = Math.max(0, index - 1);
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = options.length - 1;
        else if (event.key === "Escape") { event.preventDefault(); closePicker(picker, true); }
        if (next != null && options[next]) { event.preventDefault(); options[next].focus(); }
      });
    }
    document.addEventListener("pointerdown", event => {
      for (const picker of document.querySelectorAll(".custom-picker.is-open")) {
        if (!picker.contains(event.target)) closePicker(picker);
      }
    });
  }

  function createColumnOptions() {
    const host = el("column-options");
    host.replaceChildren();
    for (const [key, label] of COLUMN_DEFS) {
      const wrapper = node("label", "column-option");
      const check = document.createElement("input");
      check.type = "checkbox"; check.checked = app.visibleColumns.has(key); check.dataset.column = key;
      check.addEventListener("change", () => {
        check.checked ? app.visibleColumns.add(key) : app.visibleColumns.delete(key);
        renderRows();
      });
      wrapper.append(check, document.createTextNode(label));
      host.append(wrapper);
    }
  }

  function filteredRecords() {
    const predicate = CATEGORY_DEFS.find(item => item[0] === app.currentCategory)?.[2] || (() => true);
    const query = el("search-input").value.trim().toLocaleLowerCase("zh-CN");
    const status = el("status-filter").value;
    const source = el("source-filter").value;
    const rows = app.records.filter(record => {
      if (!predicate(record)) return false;
      if (app.onlyUnmatched && (!matchConfigFor(record) || savedTargets(record.id).length > 0)) return false;
      if (query && !record._search.includes(query)) return false;
      if (status && effectiveStatus(record) !== status
        && !(app.findingsByEntity.get(record.id) || []).some(x => x.source_status === status)
        && !(app.observationsByEntity.get(record.id) || []).some(x => x.source_status === status)) return false;
      if (source && !(record.evidence || []).some(x => x.source_id === source)
        && !(app.observationsByEntity.get(record.id) || []).some(x => (x.evidence_refs || []).some(ref => ref.source_id === source))
        && !(app.findingsByEntity.get(record.id) || []).some(x => (x.evidence_refs || []).some(ref => ref.source_id === source))) return false;
      return true;
    });
    const sort = el("sort-select").value;
    rows.sort((a, b) => sort === "name"
      ? displayName(a).localeCompare(displayName(b), "zh-CN") || a.id.localeCompare(b.id)
      : sort === "status"
        ? effectiveStatus(a).localeCompare(effectiveStatus(b)) || a.id.localeCompare(b.id)
        : indexValue(a) - indexValue(b) || a.id.localeCompare(b.id));
    return rows;
  }

  function displayName(record) {
    return record.identity?.website_name || record.identity?.standard_name_zh
      || record.identity?.current_game_name || record.identity?.zircon_internal_name || record.id;
  }

  function cellValue(record, column) {
    const identity = record.identity || {};
    if (column === "index") return Number.isInteger(identity.zircon_index) ? String(identity.zircon_index) : identity.website_source_id || record.id;
    if (column === "identity") return identity.zircon_internal_name || identity.website_name || identity.website_source_id || record.entity_type;
    if (column === "website") return identity.standard_name_zh || identity.website_name || (identity.candidate_website_names || []).map(x => x.name).filter(Boolean).join("、") || "未映射";
    if (column === "game") return identity.current_game_name || identity.zircon_internal_name || "—";
    if (column === "status") return statusLabel(effectiveStatus(record));
    if (column === "evidence") return `${(record.evidence || []).length} 来源 · ${(app.findingsByEntity.get(record.id) || []).length} 发现`;
    return "";
  }

  function visibleColumns() { return COLUMN_DEFS.filter(column => app.visibleColumns.has(column[0])); }

  function createRecordButton(record, label, className = "record-open") {
    const button = node("button", className, label);
    button.type = "button"; button.dataset.recordId = record.id;
    button.setAttribute("aria-label", `查看 ${label} 详情`);
    return button;
  }

  function matchConfigFor(record) {
    const config = MATCH_CONFIG[record?.entity_type];
    const identity = record?.identity || {};
    // A Zircon row carrying website_source_id is already cross-referenced. Only
    // website-side records (no Zircon index) need a manual matching action.
    return config && identity.website_source_id && !Number.isInteger(identity.zircon_index) ? config : null;
  }

  function savedTargets(sourceId) {
    return app.state?.matches?.[sourceId]?.target_entity_ids || [];
  }

  function matchActionButton(record) {
    const config = matchConfigFor(record);
    const identity = record.identity || {};
    if (!config) return node("span", identity.website_source_id && Number.isInteger(identity.zircon_index)
      ? "match-linked-label" : "match-unavailable-label", identity.website_source_id && Number.isInteger(identity.zircon_index) ? "已有对照" : "—");
    const targets = savedTargets(record.id);
    const wrapper = node("div", "match-row");
    const button = node("button", "match-row-button");
    button.type = "button";
    button.dataset.matchId = record.id;
    button.classList.toggle("is-saved", targets.length > 0);
    button.textContent = targets.length ? (config.multi ? `已选 ${targets.length}` : "已匹配") : "匹配";
    button.setAttribute("aria-label", `${targets.length ? "修改" : "为"} ${displayName(record)} 的 Zircon 匹配`);
    button.disabled = !app.database && !app.serverWorkspace;
    wrapper.append(button);
    if (targets.length) {
      const names = targets.map(id => app.byId.get(id)).filter(Boolean).map(target =>
        `Index ${target.identity.zircon_index} · ${candidateEnglishName(target)} · ${zirconIdentityKey(target)}`);
      appendText(wrapper, "span", "match-row-target", names.slice(0, 2).join("；")
        + (names.length > 2 ? `；另有 ${names.length - 2} 项` : ""));
    }
    return wrapper;
  }

  function refreshMatchSummary() {
    const host = el("match-summary");
    if (!host || !app.state) return;
    const sources = app.records.filter(matchConfigFor);
    const matched = sources.filter(record => savedTargets(record.id).length > 0).length;
    host.textContent = `本浏览器已保存 ${numberFormat(matched)} / ${numberFormat(sources.length)} 条匹配`;
    const queue = el("match-queue-filter");
    if (queue) {
      const pending = sources.length - matched;
      queue.textContent = app.onlyUnmatched ? `返回全部记录 · ${numberFormat(pending)} 待匹配` : `仅看待匹配 · ${numberFormat(pending)}`;
      queue.setAttribute("aria-pressed", String(app.onlyUnmatched));
    }
  }

  function renderRows() {
    if (!app.master) return;
    const rows = filteredRecords();
    const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    app.page = Math.min(app.page, pageCount - 1);
    const pageRows = rows.slice(app.page * PAGE_SIZE, (app.page + 1) * PAGE_SIZE);
    const columns = visibleColumns();
    const header = el("table-head"); header.replaceChildren();
    for (const [key, label] of columns) appendText(header, "th", `column-${key}`, label);
    const body = el("table-body"); body.replaceChildren();
    const fragment = document.createDocumentFragment();
    for (const record of pageRows) {
      const tr = document.createElement("tr");
      tr.dataset.recordId = record.id;
      for (const [key] of columns) {
        const td = node("td", `column-${key}`);
        if (key === "status") {
          const chip = node("span", `status-chip status-${effectiveStatus(record)}`, statusLabel(effectiveStatus(record)));
          td.append(chip);
        } else if (key === "match") {
          td.append(matchActionButton(record));
        } else {
          const value = cellValue(record, key);
          const button = createRecordButton(record, value);
          td.append(button);
        }
        tr.append(td);
      }
      fragment.append(tr);
    }
    body.append(fragment);
    const cards = el("card-list"); cards.replaceChildren();
    for (const record of pageRows) {
      const card = node("article", "audit-card");
      const top = node("div", "audit-card-top");
      appendText(top, "span", "record-index", cellValue(record, "index"));
      top.append(node("span", `status-chip status-${effectiveStatus(record)}`, statusLabel(effectiveStatus(record))));
      card.append(top);
      card.append(createRecordButton(record, displayName(record), "audit-card-title"));
      appendText(card, "p", "audit-card-internal", `${cellValue(record, "identity")} · ${cellValue(record, "game")}`);
      appendText(card, "p", "audit-card-source", `网站：${cellValue(record, "website")} · ${(record.evidence || []).length} 个来源`);
      const actions = node("div", "audit-card-actions");
      actions.append(createRecordButton(record, "查看对照与证据", "audit-card-action"));
      const matchAction = matchActionButton(record);
      actions.append(matchAction);
      card.append(actions);
      cards.append(card);
    }
    el("result-summary").textContent = `${numberFormat(rows.length)} 条记录 · 第 ${app.page + 1} / ${pageCount} 页 · 每页 ${PAGE_SIZE} 条`;
    el("page-label").textContent = `${app.page + 1} / ${pageCount}`;
    el("previous-page").disabled = app.page === 0;
    el("next-page").disabled = app.page >= pageCount - 1;
    refreshMatchSummary();
  }

  function sourceUrl(sourceId, record) {
    const input = app.sourceById.get(sourceId);
    if (!input || !input.path || input.repository === "read-only SystemDbProbe export") return null;
    const repo = input.repository;
    const revision = input.revision || app.master.provenance?.repositories?.[repo]?.commit;
    if (!/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(repo) || !revision || revision === "unavailable") return null;
    const path = input.path.split("#", 1)[0].split("/").map(encodeURIComponent).join("/");
    let fragment = "";
    const lineMatch = String(record || "").match(/(?:^|:)L(\d+)$/);
    if (lineMatch) fragment = `#L${lineMatch[1]}`;
    return `https://github.com/${repo}/blob/${encodeURIComponent(revision)}/${path}${fragment}`;
  }

  function addEvidenceLink(host, ref, label) {
    const url = sourceUrl(ref.source_id, ref.record);
    if (!url) return appendText(host, "span", "evidence-ref local-source", `${label}: ${ref.record || "本地快照"}（${ref.source_id}）`);
    const anchor = node("a", "evidence-ref", `${label}: ${ref.record || "来源文件"}`);
    anchor.href = url; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
    host.append(anchor);
    return anchor;
  }

  function addEvidenceCard(host, title, detail, refs = [], status = "") {
    const card = node("article", "evidence-card");
    const heading = node("div", "evidence-card-heading");
    appendText(heading, "strong", "", title);
    if (status) heading.append(node("span", `evidence-status status-${status}`, statusLabel(status)));
    card.append(heading);
    if (detail) appendText(card, "p", "evidence-detail", detail);
    for (const ref of refs) addEvidenceLink(card, ref, app.sourceById.get(ref.source_id)?.path || ref.source_id);
    host.append(card);
  }

  function appendImage(parent, resource, alt) {
    if (!resource?.path || !/^images\//.test(resource.path) || resource.path.split("/").includes("..")) return;
    const rootPath = root.dataset.root || "";
    const image = document.createElement("img");
    image.loading = "lazy"; image.alt = alt;
    image.src = `${rootPath}/${resource.path}`.replace(/^\/\//, "/");
    image.addEventListener("error", () => image.replaceWith(node("span", "image-missing", "图片不可用")), { once: true });
    parent.append(image);
  }

  function renderComparison(record) {
    const host = el("detail-comparison"); host.replaceChildren();
    const identity = record.identity || {};
    const website = node("article", "comparison-card comparison-website");
    appendText(website, "p", "kicker", "WEBSITE / 17173 MIRROR");
    appendText(website, "h3", "", identity.standard_name_zh || identity.website_name || "未映射到网站条目");
    const siteData = record.resources?.website;
    if (siteData) {
      const media = node("div", "comparison-media"); appendImage(media, siteData, identity.website_name || "网站资料图片");
      const caption = [siteData.width && `${siteData.width} × ${siteData.height}`, siteData.format, siteData.sha256 && `SHA-256 ${siteData.sha256.slice(0, 12)}…`].filter(Boolean).join(" · ");
      if (caption) appendText(media, "small", "media-caption", caption);
      website.append(media);
    }
    appendText(website, "p", "comparison-label", `网站记录：${identity.website_source_id || "无"}`);
    appendText(website, "p", "comparison-label", `别名 / 候选：${(identity.candidate_website_names || []).map(x => x.name).filter(Boolean).join("、") || "未提供"}`);
    const zircon = node("article", "comparison-card comparison-game");
    appendText(zircon, "p", "kicker", "ZIRCON / CURRENT SNAPSHOT");
    appendText(zircon, "h3", "", identity.current_game_name || identity.zircon_internal_name || "无直接游戏实体");
    appendText(zircon, "p", "comparison-label", `内部名：${identity.zircon_internal_name || "—"}`);
    appendText(zircon, "p", "comparison-label", `Index：${Number.isInteger(identity.zircon_index) ? identity.zircon_index : "未闭合"}`);
    const mediaInfo = record.resources?.zircon || {};
    appendText(zircon, "p", "comparison-label", `资源：${[mediaInfo.library, mediaInfo.shape, mediaInfo.resource_name, mediaInfo.frame, mediaInfo.face, mediaInfo.icon].filter(x => x != null).join(" · ") || "无已验证资源坐标"}`);
    appendText(zircon, "p", "comparison-label", `当前中文：${identity.current_translation?.zh || identity.current_game_name || "—"} · 日文：${identity.current_translation?.ja || "—"}`);
    host.append(website, zircon);
    const candidateIds = record.relations?.candidate_entity_ids || record.relations?.conflict_counterparts || [];
    const uniqueCandidates = [...new Set(candidateIds)].map(id => app.byId.get(id)).filter(Boolean);
    if (uniqueCandidates.length) {
      const section = node("section", "candidate-comparison");
      appendText(section, "h3", "", `相关候选（${uniqueCandidates.length}）`);
      const list = node("div", "candidate-list");
      for (const candidate of uniqueCandidates) {
        const candidateCard = node("article", "candidate-card");
        appendText(candidateCard, "strong", "", `Index ${candidate.identity?.zircon_index ?? "—"} · ${candidate.identity?.zircon_internal_name || candidate.id}`);
        appendText(candidateCard, "span", "", `显示名：${candidate.identity?.current_game_name || candidate.identity?.current_translation?.zh || "—"}`);
        const candidateObs = app.observationsByEntity.get(candidate.id) || [];
        const resourceData = candidateObs.flatMap(x => x.candidate_resources || []).find(x => x.zircon_index === candidate.identity?.zircon_index);
        if (resourceData) appendText(candidateCard, "small", "", `资源证据：${resourceData.resource_name || "—"} · ${resourceData.shape || "shape 未知"} · ${(resourceData.resource_evidence?.sample_frames || []).length} 帧样本元数据`);
        candidateCard.append(createRecordButton(candidate, "查看实体", "text-link"));
        list.append(candidateCard);
      }
      section.append(list); host.append(section);
    }
  }

  function renderRelations(record) {
    const host = el("relations-view"); host.replaceChildren();
    const relations = record.relations || {};
    let count = 0;
    for (const [key, value] of Object.entries(relations)) {
      const targets = Array.isArray(value) ? value : [value];
      for (const target of targets) {
        if (typeof target !== "string" || !target.includes(":")) continue;
        const related = app.byId.get(target);
        if (!related) continue;
        count += 1;
        const row = node("div", "relation-row");
        appendText(row, "span", "relation-key", key.replaceAll("_", " "));
        row.append(createRecordButton(related, `${related.identity?.zircon_index ?? ""} ${displayName(related)}`, "relation-link"));
        host.append(row);
      }
    }
    if (!count) appendText(host, "p", "empty-note", "此记录没有已解析的实体关系。");
  }

  function renderEvidence(record) {
    const host = el("evidence-view"); host.replaceChildren();
    const observations = app.observationsByEntity.get(record.id) || [];
    const findings = app.findingsByEntity.get(record.id) || [];
    const baselineRefs = record.evidence || [];
    el("evidence-count").textContent = `${baselineRefs.length} 个直接来源 · ${observations.length} 项来源观察 · ${findings.length} 条网络审计`;
    for (const reference of baselineRefs) addEvidenceCard(host, "主数据来源", reference.record, [reference]);
    for (const observation of observations) {
      const title = observation.id;
      const status = observation.source_status;
      const detail = Object.entries(observation).filter(([key, value]) => !["id", "entity_refs", "evidence_refs", "source_status"].includes(key) && value != null)
        .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" · ");
      addEvidenceCard(host, title, detail, observation.evidence_refs || [], STATUS_LABELS[status] ? status : "");
    }
    for (const finding of findings) {
      const queryDetails = (finding.search_query_refs || []).map(id => app.searchQueryById.get(id)).filter(Boolean)
        .map(query => `检索「${query.query}」：${query.outcome || "未记录检索结论"}`);
      const detail = [`${finding.direction || "方向未定"} · ${finding.website_name || "—"} ↔ ${finding.zircon_internal_name || "—"} · ${finding.confidence || "置信度未给出"}${finding.review_required ? " · 需要复核" : ""}`,
        ...queryDetails].join("\n");
      addEvidenceCard(host, finding.id, detail, finding.evidence_refs || [], STATUS_LABELS[finding.source_status] ? finding.source_status : "");
      for (const url of finding.public_sources || []) {
        if (!/^https?:\/\//.test(url)) continue;
        const source = (finding.external_source_refs || []).map(id => app.externalSourceById.get(id)).find(item => item?.url === url);
        const link = node("a", "evidence-ref external-source", source?.title || url);
        link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
        host.lastElementChild.append(link);
      }
    }
    if (!baselineRefs.length && !observations.length && !findings.length) appendText(host, "p", "empty-note", "未导入来源观察；请保持待复核并补充证据。");
  }

  function formValues() {
    return {
      standard_name_zh: el("edit-name").value.trim(), overall_status: el("edit-overall").value,
      identity_mapping_status: el("edit-identity").value, display_name_status: el("edit-display").value,
      resource_status: el("edit-resource").value, game_data_status: el("edit-game-data").value,
      relations_status: el("edit-relations").value, reason: el("edit-reason").value.trim(),
      export_enabled: el("edit-export").checked
    };
  }

  function openRecord(recordId) {
    const record = app.byId.get(recordId);
    if (!record) return;
    app.selectedId = recordId;
    const draft = effectiveDraft(record);
    app.originalDraft = { ...draft };
    app.dirtyFields.clear();
    el("detail-title").textContent = displayName(record);
    el("detail-id").textContent = `${record.id} · ${record.entity_type}`;
    el("record-detail").hidden = false;
    renderComparison(record);
    renderRelations(record);
    renderEvidence(record);
    el("game-data-view").textContent = JSON.stringify(record.game_data || {}, null, 2);
    const identity = record.identity || {};
    const assessment = baselineAssessment(record);
    el("edit-name").value = draft.standard_name_zh ?? identity.standard_name_zh ?? identity.website_name ?? "";
    el("edit-overall").value = draft.overall_status || assessment.overall_status || "pending_review";
    el("edit-identity").value = draft.identity_mapping_status || assessment.fields?.identity_mapping?.status || "pending_review";
    el("edit-display").value = draft.display_name_status || assessment.fields?.display_name?.status || "pending_review";
    el("edit-resource").value = draft.resource_status || assessment.fields?.resource_identity?.status || "pending_evidence";
    el("edit-game-data").value = draft.game_data_status || assessment.fields?.game_data?.status || "pending_review";
    el("edit-relations").value = draft.relations_status || assessment.fields?.relations?.status || "pending_review";
    el("edit-reason").value = draft.reason ?? assessment.reason ?? "";
    el("edit-export").checked = Boolean(draft.export_enabled ?? assessment.export_enabled);
    el("edit-export").disabled = !["approved", "corrected"].includes(el("edit-overall").value)
      || !["confirmed", "source_confirmed"].includes(el("edit-identity").value);
    renderHistory(recordId);
    setStatus(app.database || app.serverWorkspace ? `工作区修订 ${app.state.revision}` : "本地存储不可用；只读模式", !app.database && !app.serverWorkspace);
    el("record-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderHistory(recordId) {
    const host = el("audit-history"); host.replaceChildren();
    const events = (app.state.events || []).filter(event => event.entity_id === recordId).slice(-20).reverse();
    const matchTargets = targetIds => {
      if (!Array.isArray(targetIds) || !targetIds.length) return "未匹配";
      return targetIds.map(id => {
        const target = app.byId.get(id);
        return target ? `${candidateEnglishName(target)} (${zirconIdentityKey(target)})` : id;
      }).join("、");
    };
    for (const event of events) {
      const li = node("li", "history-entry");
      const time = new Date(event.at).toLocaleString("zh-CN", { hour12: false });
      appendText(li, "strong", "", `修订 ${event.revision} · ${time}`);
      const summary = event.action === "match"
        ? `匹配目标：${matchTargets(event.before)} → ${matchTargets(event.after)}`
        : Object.entries(event.after || {})
          .filter(([key, value]) => JSON.stringify(event.before?.[key]) !== JSON.stringify(value))
          .map(([key, value]) => `${fieldLabel(key)} → ${typeof value === "boolean" ? (value ? "启用" : "关闭") : value}`)
          .join("；") || "记录本地修改";
      appendText(li, "small", "", summary);
      host.append(li);
    }
    if (!events.length) appendText(host, "li", "empty-note", "尚无本地修改记录。");
  }

  function markDirty(event) {
    const field = event.currentTarget.dataset.field;
    if (field) app.dirtyFields.add(field);
    el("edit-export").disabled = !["approved", "corrected"].includes(el("edit-overall").value)
      || !["confirmed", "source_confirmed"].includes(el("edit-identity").value);
  }

  async function saveDraft() {
    if ((!app.database && !app.serverWorkspace) || !app.selectedId) return;
    const changes = formValues();
    if (!app.dirtyFields.size) { setStatus("没有修改需要保存。"); return; }
    if (changes.export_enabled && !["approved", "corrected"].includes(changes.overall_status)) {
      setStatus("翻译候选开关需要整体状态为已批准或已更正。", true); return;
    }
    if (changes.export_enabled && !["confirmed", "source_confirmed"].includes(changes.identity_mapping_status)) {
      setStatus("翻译候选开关需要身份映射已确认。", true); return;
    }
    if (changes.export_enabled && !changes.standard_name_zh) {
      setStatus("翻译候选开关需要非空中文标准名。", true); return;
    }
    try {
      app.state = await saveWorkspaceUpdate(app.selectedId, app.originalDraft, changes);
      app.originalDraft = { ...changes };
      app.dirtyFields.clear();
      app.broadcast?.postMessage({ revision: app.state.revision, entity_id: app.selectedId });
      setStatus(`已保存本地草稿 · 修订 ${app.state.revision}`);
      refreshStats(); renderRows(); renderHistory(app.selectedId);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function matchSourceName(record) {
    const draft = effectiveDraft(record);
    return (draft.standard_name_zh || record.identity?.standard_name_zh || record.identity?.website_name || displayName(record) || "").trim();
  }

  function selectedMatchIds(sourceId = app.matchSourceId) {
    return [...savedTargets(sourceId)];
  }

  function candidateEnglishName(record) {
    return record.identity?.zircon_internal_name || record.game_data?.QuestName || record.identity?.current_game_name || record.id;
  }

  function candidateExtra(record) {
    const data = record.game_data || {};
    if (record.entity_type === "monster") return [Number.isInteger(data.Level) && `Lv ${data.Level}`, data.Image && `Image ${data.Image}`].filter(Boolean).join(" · ");
    if (record.entity_type === "item") return [data.ItemType, Number.isInteger(data.Image) && `Image ${data.Image}`].filter(Boolean).join(" · ");
    if (record.entity_type === "skill") return [data.RequiredClass, data.School, Number.isInteger(data.Icon) && `Icon ${data.Icon}`].filter(Boolean).join(" · ");
    if (record.entity_type === "map") return [data.FileName && `Map ${data.FileName}`, Number.isInteger(data.MiniMap) && `MiniMap ${data.MiniMap}`].filter(Boolean).join(" · ");
    if (record.entity_type === "quest") return [data.QuestType, `Index ${record.identity?.zircon_index ?? "—"}`].filter(Boolean).join(" · ");
    return "";
  }

  function candidateImageUrl(record) {
    const path = app.previewById.get(record.id);
    if (typeof path !== "string" || !path.startsWith("images/zircon-match/") || path.split("/").includes("..")) return null;
    const rootPath = root.dataset.root || "";
    return new URL(`${rootPath}/${path}`, window.location.href).href;
  }

  function appendCandidateThumb(parent, record) {
    const thumb = node("div", "match-candidate-thumb");
    const src = candidateImageUrl(record);
    if (!src) {
      const placeholder = record.entity_type === "quest" ? "任务" : record.entity_type === "map" ? "无小地图" : "无图像";
      appendText(thumb, "span", "match-thumb-placeholder", placeholder);
      parent.append(thumb);
      return;
    }
    const image = document.createElement("img");
    image.loading = "lazy";
    image.decoding = "async";
    image.alt = `${candidateEnglishName(record)} · Zircon 候选图`;
    image.src = src;
    image.addEventListener("error", () => thumb.replaceChildren(node("span", "match-thumb-placeholder", "图像不可用")), { once: true });
    thumb.append(image);
    parent.append(thumb);
  }

  function setMatchSaveStatus(message, isError = false) {
    const status = el("match-save-status");
    status.textContent = message;
    status.classList.toggle("is-error", isError);
  }

  function currentMatchCandidates() {
    const source = app.byId.get(app.matchSourceId);
    const config = matchConfigFor(source);
    if (!source || !config) return [];
    const query = el("match-search-input").value.trim().toLocaleLowerCase("zh-CN");
    const selected = new Set(selectedMatchIds());
    return (app.candidatesByType.get(config.target) || []).filter(record =>
      (!app.matchShowSelected || selected.has(record.id))
      && (!query || (record._search || searchValue(record)).includes(query)));
  }

  function renderMatchCandidates() {
    if (!app.matchSourceId || el("match-drawer").hidden) return;
    const source = app.byId.get(app.matchSourceId);
    const config = matchConfigFor(source);
    if (!config) return;
    const rows = currentMatchCandidates();
    const pageCount = Math.max(1, Math.ceil(rows.length / MATCH_PAGE_SIZE));
    app.matchPage = Math.min(app.matchPage, pageCount - 1);
    const pageRows = rows.slice(app.matchPage * MATCH_PAGE_SIZE, (app.matchPage + 1) * MATCH_PAGE_SIZE);
    const selected = new Set(selectedMatchIds());
    const host = el("match-candidate-list");
    host.replaceChildren();
    if (!pageRows.length) appendText(host, "p", "match-empty", app.matchShowSelected ? "此条目还没有保存的匹配。" : "没有找到候选。试试英文名、中文名或 Index。 ");
    for (const candidate of pageRows) {
      const isSelected = selected.has(candidate.id);
      const card = node("article", `match-candidate-card${isSelected ? " is-selected" : ""}`);
      card.setAttribute("role", "group");
      appendCandidateThumb(card, candidate);
      const copy = node("div", "match-candidate-copy");
      appendText(copy, "strong", "", candidateEnglishName(candidate));
      appendText(copy, "p", "", `当前显示名：${candidate.identity?.current_translation?.zh || candidate.identity?.current_game_name || "—"}`);
      appendText(copy, "small", "", [`Index ${candidate.identity.zircon_index}`, zirconIdentityKey(candidate), candidateExtra(candidate)].filter(Boolean).join(" · "));
      card.append(copy);
      const action = node("button", "match-choice-action", app.matchBusy ? "保存中" : isSelected ? (config.multi ? "✓ 已选" : "✓ 已匹配") : (config.multi ? "加入匹配" : "匹配此项"));
      action.type = "button";
      action.dataset.matchCandidateId = candidate.id;
      action.setAttribute("aria-pressed", String(isSelected));
      action.setAttribute("aria-label", `${isSelected ? "已选" : "选择"} ${candidateEnglishName(candidate)}，Index ${candidate.identity.zircon_index}`);
      action.disabled = app.matchBusy || (!app.database && !app.serverWorkspace);
      card.append(action);
      host.append(card);
    }
    const countLabel = `${numberFormat(rows.length)} 个候选${app.matchShowSelected ? " · 仅显示已选" : ""}`;
    el("match-candidate-count").textContent = countLabel;
    el("match-page-label").textContent = `${app.matchPage + 1} / ${pageCount}`;
    el("match-previous").disabled = app.matchPage === 0 || app.matchBusy;
    el("match-next").disabled = app.matchPage >= pageCount - 1 || app.matchBusy;
    el("match-selection-count").textContent = config.multi ? `已保存 ${selected.size} 项` : (selected.size ? "已保存 1 项" : "尚未匹配");
    el("match-clear").disabled = selected.size === 0 || app.matchBusy || (!app.database && !app.serverWorkspace);
    el("match-selected-filter").textContent = app.matchShowSelected ? "返回全部候选" : "只看已选";
    el("match-selected-filter").setAttribute("aria-pressed", String(app.matchShowSelected));
  }

  function matchSourceImage(record) {
    const media = el("match-source-media");
    media.replaceChildren();
    if (record.resources?.website?.path) appendImage(media, record.resources.website, `${matchSourceName(record)} · 网站资料图`);
    else appendText(media, "span", "", (matchSourceName(record).slice(0, 2) || "条目"));
  }

  function openMatchDrawer(sourceId) {
    const source = app.byId.get(sourceId);
    const config = matchConfigFor(source);
    if (!config) return;
    app.priorFocus = document.activeElement;
    app.matchSourceId = sourceId;
    app.matchPage = 0;
    app.matchShowSelected = false;
    el("match-search-input").value = "";
    el("match-drawer-title").textContent = matchSourceName(source);
    el("match-source-id").textContent = `${source.identity.website_source_id} · ${source.entity_type}`;
    el("match-type-label").textContent = config.label;
    matchSourceImage(source);
    const notes = {
      monster: "按 Zircon 怪物实体匹配。图片由当前 MonsterInfo.Image → MonsterLookup → 客户端怪物图库生成；图片只辅助辨认，请同时核对英文名与 Index。",
      item: "按 Zircon 道具实体匹配。缩略图按客户端当前 ItemInfo.Image → Storeitems.Zl 帧显示；已知不少数据库图号与正确物品外观存在错位，图片只是当前客户端画面参考，不能单凭图片确认，请同时核对英文名与 Index。",
      skill: "按 Zircon 技能实体匹配。图标取 MagicInfo.Icon 对应帧；确认后会进入本地匹配工作区。",
      mission: "任务攻略可能覆盖多个游戏任务，支持多选。QuestInfo 没有统一条目图像时会显示占位；清单会保留每个选择的 Index 与英文任务名。",
      map_group: "网站地图条目是地图集合，支持多选 Zircon MapInfo。缩略图取游戏客户端 MiniMap 帧；该关系导出到匹配清单，不会把集合标题误写成单张地图名。"
    };
    const storageNote = app.serverWorkspace
      ? "每次选择都会立即写入项目目录 .local/alignment-workspace.json。"
      : "每次选择都会立即写入此浏览器的 IndexedDB；更换设备或清理站点数据前，请先导出工作区备份。";
    el("match-drawer-note").textContent = `${notes[source.entity_type] || "选择同类型游戏候选。"} ${storageNote} 工作区不会上传，也不会修改网站主数据或游戏文件。`;
    el("match-drawer").hidden = false;
    el("match-backdrop").hidden = false;
    document.body.classList.add("match-open");
    setMatchSaveStatus(app.serverWorkspace ? "直接保存到项目目录 .local/alignment-workspace.json"
      : !app.database ? "IndexedDB 不可用，当前只读"
        : app.storagePersistence ? "此浏览器已授予持久存储；每次选择都会立即保存"
          : "已即时写入浏览器 IndexedDB；浏览器仍可能清理站点数据，请定期导出工作区", !app.database && !app.serverWorkspace);
    renderMatchCandidates();
    window.setTimeout(() => el("match-search-input").focus(), 0);
  }

  function closeMatchDrawer() {
    el("match-drawer").hidden = true;
    el("match-backdrop").hidden = true;
    document.body.classList.remove("match-open");
    app.matchSourceId = null;
    if (app.priorFocus?.isConnected) app.priorFocus.focus();
  }

  function saveMatchSelection(sourceId, targetIds) {
    if (app.serverWorkspace) return (async () => {
      const selection = createMatchSelection(sourceId, targetIds, app.byId);
      const current = await readWorkspace(), matches = { ...current.matches }, before = matches[sourceId]?.target_entity_ids || [];
      if (selection.target_entity_ids.length) matches[sourceId] = selection; else delete matches[sourceId];
      const revision = current.revision + 1;
      const next = { ...current, revision, matches, events: [...current.events, {
        id: `${Date.now()}-${crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`,
        at: new Date().toISOString(), entity_id: sourceId, revision, action: "match", before, after: selection.target_entity_ids,
      }] };
      const response = await fetch("/api/workspace", { method: "PUT", headers: { "Content-Type": "application/json", "If-Match-Revision": String(current.revision) }, body: JSON.stringify(next) });
      if (response.status === 409) throw new Error("项目工作区已在另一页面更新，请刷新后重试。");
      if (!response.ok) throw new Error(`项目工作区写入失败（HTTP ${response.status}）`);
      return validateWorkspaceBundle({ schema_version: 2, format: "mir3-alignment-workspace", exported_at: new Date().toISOString(), base_master_sha256: app.masterHash, workspace: await response.json() }, { masterHash: app.masterHash, recordsById: app.byId });
    })();
    return new Promise((resolve, reject) => {
      if (!app.database && !app.serverWorkspace) return reject(new Error("本地存储不可用；匹配没有保存。"));
      let selection;
      try { selection = createMatchSelection(sourceId, targetIds, app.byId); }
      catch (error) { return reject(error); }
      const unique = selection.target_entity_ids;
      const tx = app.database.transaction("workspace", "readwrite");
      const store = tx.objectStore("workspace");
      const request = store.get("workspace");
      let nextState;
      request.onsuccess = () => {
        const current = request.result || { id: "workspace", revision: 0, drafts: {}, matches: {}, events: [] };
        const matches = { ...(current.matches || {}) };
        const before = matches[sourceId] || null;
        if (unique.length) matches[sourceId] = selection;
        else delete matches[sourceId];
        const revision = (current.revision || 0) + 1;
        const events = [...(current.events || []), {
          id: `${Date.now()}-${crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`,
          at: new Date().toISOString(), entity_id: sourceId, revision, action: "match",
          before: before?.target_entity_ids || [], after: unique
        }];
        nextState = { ...current, id: "workspace", revision, drafts: current.drafts || {}, matches, events };
        store.put(nextState);
      };
      tx.oncomplete = () => resolve(nextState);
      tx.onerror = () => reject(tx.error || new Error("匹配保存失败。"));
      tx.onabort = () => reject(tx.error || new Error("匹配保存事务中止。"));
    });
  }

  async function chooseMatchCandidate(candidateId) {
    if (app.matchBusy || !app.matchSourceId) return;
    const source = app.byId.get(app.matchSourceId);
    const config = matchConfigFor(source);
    if (!config) return;
    const chosen = new Set(selectedMatchIds());
    if (config.multi) chosen.has(candidateId) ? chosen.delete(candidateId) : chosen.add(candidateId);
    else chosen.clear(), chosen.add(candidateId);
    app.matchBusy = true;
    setMatchSaveStatus("正在写入本地 IndexedDB…");
    renderMatchCandidates();
    try {
      app.state = await saveMatchSelection(source.id, [...chosen]);
      app.broadcast?.postMessage({ revision: app.state.revision, entity_id: source.id, matches: true });
      setMatchSaveStatus(`已保存到此浏览器 · 修订 ${app.state.revision}`);
      renderRows();
    } catch (error) {
      setMatchSaveStatus(`${error.message} · 仍未保存`, true);
    } finally {
      app.matchBusy = false;
      renderMatchCandidates();
    }
  }

  async function clearCurrentMatch() {
    if (!app.matchSourceId || app.matchBusy) return;
    const sourceId = app.matchSourceId;
    app.matchBusy = true;
    setMatchSaveStatus("正在清除并保存…");
    renderMatchCandidates();
    try {
      app.state = await saveMatchSelection(sourceId, []);
      app.broadcast?.postMessage({ revision: app.state.revision, entity_id: sourceId, matches: true });
      setMatchSaveStatus(`已清除此匹配 · 修订 ${app.state.revision}`);
      renderRows();
    } catch (error) {
      setMatchSaveStatus(`${error.message} · 状态未改变`, true);
    } finally {
      app.matchBusy = false;
      renderMatchCandidates();
    }
  }

  function buildMatchManifest() {
    return createMatchManifest({
      masterHash: app.masterHash,
      matches: app.state.matches || {},
      recordsById: app.byId,
      sourceNameFor: sourceId => matchSourceName(app.byId.get(sourceId)),
    });
  }

  function buildGameNamesExport() {
    return createGameNamesExport({
      baseline: app.master.translation_baseline || {},
      matches: app.state.matches || {},
      recordsById: app.byId,
      sourceNameFor: sourceId => matchSourceName(app.byId.get(sourceId)),
    });
  }

  function downloadGameNames() {
    try {
      const result = buildGameNamesExport();
      downloadJson("db_names.json", result.translation);
      setStatus(`已下载游戏可用 db_names.json · ${result.changed_keys.length} 个游戏名称键由人工匹配更新。只下载，不写入游戏仓库。`);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function downloadMatchManifest() {
    try {
      const manifest = buildMatchManifest();
      downloadJson("mir3-website-zircon-matches.json", manifest);
      setStatus(`已下载匹配清单 · ${manifest.matches.length} 条 · 包含任务与地图分组对应关系。`);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function loadMatchPreviewIndex(url) {
    return fetch(url, { cache: "no-cache", credentials: "same-origin" }).then(response => {
      if (!response.ok) throw new Error(`候选缩略图清单 HTTP ${response.status}`);
      return response.json();
    }).then(index => {
      if (index.schema_version !== 1 || !index.assets || typeof index.assets !== "object") throw new Error("候选缩略图清单版本无效。");
      app.previewById = new Map(Object.entries(index.assets).filter(([, path]) => typeof path === "string"
        && path.startsWith("images/zircon-match/") && !path.split("/").includes("..")));
    });
  }

  function refreshStats() {
    const pending = app.records.filter(record => ["pending_review", "pending_evidence"].includes(effectiveStatus(record))).length;
    const conflicts = app.records.filter(record => ["conflict", "cross_entity_conflict", "ambiguous", "display_name_error"].includes(effectiveStatus(record))).length;
    el("stat-entities").textContent = numberFormat(app.records.length);
    el("stat-pending").textContent = numberFormat(pending);
    el("stat-conflicts").textContent = numberFormat(conflicts);
    el("stat-findings").textContent = numberFormat(app.master.research_findings?.length || 0);
    for (const button of el("category-nav").querySelectorAll("button")) {
      const definition = CATEGORY_DEFS.find(item => item[0] === button.dataset.category);
      const count = app.records.filter(definition[2]).length;
      button.querySelector(".category-count").textContent = numberFormat(count);
    }
  }

  function renderSnapshot() {
    const repositories = app.master.provenance?.repositories || {};
    const version = repositories.zircon?.system_database_version || "版本未提供";
    el("snapshot-version").textContent = `System.db ${version}`;
    el("snapshot-source").textContent = `捕获 ${app.master.captured_at || "日期未提供"} · website ${repositories.website?.commit?.slice(0, 8) || "—"} · research ${repositories.research?.commit?.slice(0, 8) || "—"}`;
  }

  function renderResearchContext() {
    const sources = app.master.external_sources || [];
    const queries = app.master.search_queries || [];
    el("research-context-summary").textContent = `${sources.length} 个外部来源 · ${queries.length} 条检索记录`;
    const sourceHost = el("research-source-list");
    sourceHost.replaceChildren();
    for (const source of sources) {
      const card = node("article", "research-source-card");
      appendText(card, "strong", "", source.title || source.id);
      appendText(card, "small", "", [source.publisher, source.accessed_at, source.bytes ? `${numberFormat(source.bytes)} bytes` : null,
        source.sha256 ? `SHA-256 ${source.sha256}` : null].filter(Boolean).join(" · "));
      if (source.used_for?.length) appendText(card, "p", "", source.used_for.join("；"));
      if (source.url && /^https?:\/\//.test(source.url)) {
        const link = node("a", "evidence-ref external-source", source.url);
        link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer";
        card.append(link);
      }
      sourceHost.append(card);
    }
    const queryHost = el("research-query-list");
    queryHost.replaceChildren();
    for (const query of queries) {
      const card = node("article", "research-query-card");
      appendText(card, "strong", "", query.query);
      appendText(card, "p", "", query.outcome || "未记录检索结论");
      const refs = (query.source_refs || []).map(id => app.externalSourceById.get(id)).filter(Boolean);
      for (const source of refs) {
        if (!source.url) continue;
        const link = node("a", "evidence-ref external-source", source.title || source.url);
        link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer";
        card.append(link);
      }
      queryHost.append(card);
    }
  }

  function validateBundle(bundle) {
    return validateWorkspaceBundle(bundle, { masterHash: app.masterHash, recordsById: app.byId });
  }

  function downloadJson(filename, value) {
    const blob = new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename;
    document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function openWorkspaceDialog({ title, message, preview, actionLabel, action, returnFocus = document.activeElement }) {
    app.modalReturnFocus = returnFocus;
    app.modalAction = action || null;
    el("export-dialog-title").textContent = title;
    el("export-message").textContent = message;
    el("export-preview").textContent = preview || "";
    el("download-export").textContent = actionLabel || "确认";
    el("download-export").disabled = !action;
    el("export-dialog").hidden = false;
    el("export-backdrop").hidden = false;
    document.body.classList.add("export-open");
    window.requestAnimationFrame(() => (action ? el("download-export") : el("close-export-footer")).focus());
  }

  function closeWorkspaceDialog() {
    el("export-dialog").hidden = true;
    el("export-backdrop").hidden = true;
    document.body.classList.remove("export-open");
    app.modalAction = null;
    if (app.modalReturnFocus?.isConnected && !app.modalReturnFocus.hidden) app.modalReturnFocus.focus();
  }
  function trapFocus(container, event) {
    if (event.key !== "Tab") return;
    const focusable = [...container.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])")]
      .filter(item => !item.hidden && item.getClientRects().length > 0);
    if (!focusable.length) { event.preventDefault(); container.focus(); return; }
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !container.contains(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !container.contains(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  }

  function updateVisualViewport() {
    const viewport = window.visualViewport;
    root.style.setProperty("--visual-viewport-height", `${Math.ceil(viewport?.height || window.innerHeight)}px`);
    root.style.setProperty("--visual-viewport-offset-top", `${Math.ceil(viewport?.offsetTop || 0)}px`);
  }

  async function runWorkspaceDialogAction() {
    const action = app.modalAction;
    if (!action) return;
    const button = el("download-export");
    button.disabled = true;
    try {
      const close = await action();
      if (close !== false) closeWorkspaceDialog();
      else button.disabled = false;
    } catch (error) {
      el("export-message").textContent = `操作未完成：${error.message}`;
      button.disabled = false;
    }
  }

  function exportWorkspace() {
    const bundle = {
      schema_version: 2, format: "mir3-alignment-workspace", exported_at: new Date().toISOString(),
      base_master_sha256: app.masterHash, workspace: app.state,
    };
    downloadJson("mir3-alignment-workspace.json", bundle);
    setStatus(`已下载完整本地工作区 · ${Object.keys(app.state.drafts).length} 条草稿 · ${Object.keys(app.state.matches).length} 条匹配。`);
  }

  async function importWorkspace(file) {
    const bundle = JSON.parse(await file.text());
    const workspace = validateBundle(bundle);
    const currentCounts = {
      drafts: Object.keys(app.state.drafts).length,
      matches: Object.keys(app.state.matches).length,
      events: app.state.events.length,
    };
    const importCounts = {
      drafts: Object.keys(workspace.drafts).length,
      matches: Object.keys(workspace.matches).length,
      events: workspace.events.length,
    };
    openWorkspaceDialog({
      title: "替换当前浏览器工作区？",
      message: `已验证 v${bundle.schema_version} 文件、主数据 SHA-256、草稿、事件、匹配类型与 Zircon 身份键。确认后将替换此浏览器现有内容；网站公开数据和游戏文件不会更改。`,
      preview: JSON.stringify({ "当前工作区（将被替换）": currentCounts, "导入文件": importCounts }, null, 2),
      actionLabel: "导入并替换",
      returnFocus: el("import-button"),
      action: async () => {
        if (app.serverWorkspace) {
          const current = await readWorkspace();
          const next = { ...workspace, id: "workspace", revision: Math.max(current.revision, app.state.revision, workspace.revision) + 1 };
          const response = await fetch("/api/workspace", { method: "PUT", headers: { "Content-Type": "application/json", "If-Match-Revision": String(current.revision) }, body: JSON.stringify(next) });
          if (response.status === 409) throw new Error("项目工作区已在其他页面更新，请重新导入。");
          if (!response.ok) throw new Error(`项目工作区写入失败（HTTP ${response.status}）`);
        } else {
        const tx = app.database.transaction("workspace", "readwrite");
        const store = tx.objectStore("workspace");
        const request = store.get("workspace");
        request.onsuccess = () => {
          const latestRevision = request.result?.revision || 0;
          store.put({
            ...workspace,
            id: "workspace",
            revision: Math.max(latestRevision, app.state.revision, workspace.revision) + 1,
          });
        };
        await new Promise((resolve, reject) => {
          tx.oncomplete = resolve;
          tx.onerror = () => reject(tx.error || new Error("导入事务失败。"));
          tx.onabort = () => reject(tx.error || new Error("导入已中止。"));
        });
        }
        app.state = await readWorkspace();
        refreshStats(); renderRows();
        if (app.selectedId) openRecord(app.selectedId);
        if (app.matchSourceId) renderMatchCandidates();
        setStatus(`已导入 ${importCounts.drafts} 条草稿、${importCounts.matches} 条匹配。`);
        app.broadcast?.postMessage({ revision: app.state.revision, imported: true });
        return true;
      },
    });
  }

  function translationCandidate() {
    const baseline = structuredClone(app.master.translation_baseline || {});
    const typeSections = { monster: "monsters", item: "items", skill: "magics", npc: "npcs", map: "maps" };
    const all = new Map();
    for (const record of app.records) {
      const type = record.entity_type, name = record.identity?.zircon_internal_name;
      if (!typeSections[type] || !name) continue;
      const key = `${type}\u0000${name}`;
      if (!all.has(key)) all.set(key, []);
      all.get(key).push(record);
    }
    const approved = [];
    for (const record of app.records) {
      const draft = effectiveDraft(record), identity = record.identity || {};
      if (!draft.export_enabled || !["approved", "corrected"].includes(draft.overall_status)
          || !["confirmed", "source_confirmed"].includes(draft.identity_mapping_status)
          || !["approved", "corrected"].includes(draft.display_name_status)
          || !typeSections[record.entity_type] || !Number.isInteger(identity.zircon_index)
          || typeof identity.zircon_internal_name !== "string" || !draft.standard_name_zh?.trim()) continue;
      approved.push(record);
    }
    const grouped = new Map();
    for (const record of approved) {
      const key = `${record.entity_type}\u0000${record.identity.zircon_internal_name}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(record);
    }
    const changes = [];
    for (const [key, records] of grouped) {
      const [type, name] = key.split("\u0000");
      const sameName = all.get(key) || [];
      if (sameName.some(record => !approved.includes(record))) throw new Error(`${name} 的多个 Index 共用运行时名称键；必须全部批准并同名后才能导出。`);
      const values = new Set(records.map(record => effectiveDraft(record).standard_name_zh.trim()));
      if (values.size !== 1) throw new Error(`${name} 对应的已批准 Index 中文名不一致。`);
      const section = typeSections[type], next = values.values().next().value;
      const old = baseline[section]?.[name];
      const previous = old?.zh ?? null;
      if (previous === next) continue;
      baseline[section] ||= {};
      baseline[section][name] = { ...(old || {}), zh: next };
      for (const record of records) changes.push({ entity_id: record.id, section, internal_name: name, previous_zh: previous, next_zh: next });
    }
    changes.sort((a, b) => a.section.localeCompare(b.section) || a.internal_name.localeCompare(b.internal_name) || a.entity_id.localeCompare(b.entity_id));
    return { translation: baseline, changes, rollback: changes.map(change => ({ section: change.section, internal_name: change.internal_name, restore_zh: change.previous_zh })), approved_record_count: approved.length };
  }

  async function showTranslationCandidate() {
    try {
      const result = translationCandidate();
      const serialized = JSON.stringify(result.translation, null, 2) + "\n";
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(serialized));
      const candidateHash = [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("");
      app.candidateDownload = result.translation;
      openWorkspaceDialog({
        title: "审批翻译候选文件",
        message: `${result.changes.length} 项中文值变化；${result.approved_record_count} 条记录显式批准。未批准项和所有未触及 locale 保持原样。候选 SHA-256：${candidateHash}。此文件不会写入 Zircon。`,
        preview: JSON.stringify({ changes: result.changes, rollback: result.rollback }, null, 2),
        actionLabel: "下载 JSON",
        returnFocus: el("translation-button"),
        action: () => {
          downloadJson("mir3-db_names-translation-candidate.json", app.candidateDownload);
          setStatus("已下载审批翻译候选；文件未写入游戏仓库。");
          return false;
        },
      });
    } catch (error) {
      app.candidateDownload = null;
      openWorkspaceDialog({
        title: "无法生成翻译候选",
        message: error.message,
        preview: "候选未生成；请解决身份键冲突或缺失的批准条件。",
        actionLabel: "不可下载",
        returnFocus: el("translation-button"),
      });
    }
  }

  function bindEvents() {
    setupPickers();
    updateVisualViewport();
    window.addEventListener("resize", updateVisualViewport);
    window.visualViewport?.addEventListener("resize", updateVisualViewport);
    window.visualViewport?.addEventListener("scroll", updateVisualViewport);
    el("search-input").addEventListener("input", () => { app.page = 0; renderRows(); });
    for (const id of ["status-filter", "source-filter", "sort-select"]) el(id).addEventListener("change", () => { app.page = 0; renderRows(); });
    el("match-queue-filter").addEventListener("click", () => { app.onlyUnmatched = !app.onlyUnmatched; app.page = 0; renderRows(); });
    el("previous-page").addEventListener("click", () => { app.page = Math.max(0, app.page - 1); renderRows(); });
    el("next-page").addEventListener("click", () => { app.page += 1; renderRows(); });
    for (const host of [el("table-body"), el("card-list"), el("detail-comparison"), el("relations-view")]) {
      host.addEventListener("click", event => {
        const matchButton = event.target.closest("[data-match-id]");
        if (matchButton) { openMatchDrawer(matchButton.dataset.matchId); return; }
        const button = event.target.closest("[data-record-id]");
        if (button) openRecord(button.dataset.recordId);
      });
    }
    el("match-close").addEventListener("click", closeMatchDrawer);
    el("match-backdrop").addEventListener("click", closeMatchDrawer);
    el("match-search-input").addEventListener("input", () => { app.matchPage = 0; renderMatchCandidates(); });
    el("match-selected-filter").addEventListener("click", () => { app.matchShowSelected = !app.matchShowSelected; app.matchPage = 0; renderMatchCandidates(); });
    el("match-previous").addEventListener("click", () => { app.matchPage = Math.max(0, app.matchPage - 1); renderMatchCandidates(); });
    el("match-next").addEventListener("click", () => { app.matchPage += 1; renderMatchCandidates(); });
    el("match-candidate-list").addEventListener("click", event => {
      const button = event.target.closest("[data-match-candidate-id]");
      if (button) chooseMatchCandidate(button.dataset.matchCandidateId);
    });
    el("match-clear").addEventListener("click", clearCurrentMatch);
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        const picker = document.querySelector(".custom-picker.is-open");
        if (picker) { event.preventDefault(); closePicker(picker, true); return; }
        if (!el("export-dialog").hidden) { event.preventDefault(); closeWorkspaceDialog(); return; }
        if (!el("match-drawer").hidden) { event.preventDefault(); closeMatchDrawer(); return; }
      }
      if (event.defaultPrevented) return;
      if (!el("export-dialog").hidden) trapFocus(el("export-dialog"), event);
      else if (!el("match-drawer").hidden) trapFocus(el("match-drawer"), event);
    });
    el("close-detail").addEventListener("click", () => { el("record-detail").hidden = true; app.selectedId = null; });
    const fieldMap = { "edit-name": "standard_name_zh", "edit-overall": "overall_status", "edit-identity": "identity_mapping_status",
      "edit-display": "display_name_status", "edit-resource": "resource_status", "edit-game-data": "game_data_status",
      "edit-relations": "relations_status", "edit-reason": "reason", "edit-export": "export_enabled" };
    for (const [id, field] of Object.entries(fieldMap)) {
      const control = el(id); control.dataset.field = field;
      control.addEventListener(control.type === "checkbox" || control.classList.contains("custom-picker") ? "change" : "input", markDirty);
    }
    el("save-draft").addEventListener("click", saveDraft);
    el("export-button").addEventListener("click", exportWorkspace);
    el("import-button").addEventListener("click", () => el("import-file").click());
    el("import-file").addEventListener("change", async event => {
      const file = event.target.files?.[0]; if (!file) return;
      try { await importWorkspace(file); } catch (error) { setStatus(error.message, true); }
      event.target.value = "";
    });
    el("translation-button").addEventListener("click", showTranslationCandidate);
    el("download-game-names").addEventListener("click", downloadGameNames);
    el("download-match-manifest").addEventListener("click", downloadMatchManifest);
    el("close-export").addEventListener("click", closeWorkspaceDialog);
    el("close-export-footer").addEventListener("click", closeWorkspaceDialog);
    el("export-backdrop").addEventListener("click", closeWorkspaceDialog);
    el("download-export").addEventListener("click", runWorkspaceDialogAction);
    if (window.BroadcastChannel) {
      app.broadcast = new BroadcastChannel("mir3-alignment-workspace");
      app.broadcast.onmessage = async event => {
        if (!Number.isInteger(event.data?.revision) || event.data.revision <= app.state.revision) return;
        app.state = await readWorkspace(); refreshStats(); renderRows();
        if (app.selectedId) setStatus("另一标签页已保存工作区；当前记录草稿未覆盖，请比较后再保存。", true);
        if (app.matchSourceId) renderMatchCandidates();
      };
    }
  }

  async function start() {
    bindEvents();
    try {
      const response = await fetch(root.dataset.masterUrl, { cache: "no-cache", credentials: "same-origin" });
      if (!response.ok) throw new Error(`主数据读取失败（HTTP ${response.status}）`);
      const source = await response.text();
      const manifest = JSON.parse(source);
      if (manifest.schema_version !== 1 || !manifest.shards) throw new Error("主数据版本或分片清单不受支持。");
      const collectionNames = ["entities", "research_findings", "source_observations"];
      const loaded = await Promise.all(collectionNames.flatMap(collection => {
        const descriptors = manifest.shards[collection];
        if (!Array.isArray(descriptors)) throw new Error(`主数据分片清单缺少 ${collection}。`);
        return descriptors.map(async descriptor => {
          if (typeof descriptor.path !== "string" || descriptor.path.startsWith("/") || descriptor.path.split("/").includes("..")
              || !/^[0-9a-f]{64}$/.test(descriptor.sha256)) throw new Error("主数据分片路径或摘要不合法。");
          const shardUrl = new URL(descriptor.path, response.url);
          if (shardUrl.origin !== window.location.origin) throw new Error("主数据分片不在当前网站来源内。");
          const shardResponse = await fetch(shardUrl, { cache: "no-cache", credentials: "same-origin" });
          if (!shardResponse.ok) throw new Error(`分片读取失败（HTTP ${shardResponse.status}）：${descriptor.path}`);
          const text = await shardResponse.text();
          const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
          const hash = [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("");
          if (hash !== descriptor.sha256) throw new Error(`主数据分片摘要不匹配：${descriptor.path}`);
          const rows = JSON.parse(text);
          if (!Array.isArray(rows) || rows.length !== descriptor.count) throw new Error(`主数据分片记录数不匹配：${descriptor.path}`);
          return { collection, descriptor, rows };
        });
      }));
      app.master = { ...manifest };
      for (const collection of collectionNames) app.master[collection] = [];
      for (const part of loaded) app.master[part.collection].push(...part.rows);
      const hashParts = loaded.slice().sort((a, b) => {
        const collectionOrder = ["entities", "research_findings", "source_observations"];
        const orderDifference = collectionOrder.indexOf(a.collection) - collectionOrder.indexOf(b.collection);
        return orderDifference || (a.descriptor.path < b.descriptor.path ? -1 : a.descriptor.path > b.descriptor.path ? 1 : 0);
      }).map(part => part.descriptor.sha256);
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${source}\n${hashParts.join("\n")}\n`));
      app.masterHash = [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("");
      buildIndexes();
      const rootPath = root.dataset.root || "";
      const previewUrl = new URL(`${rootPath}/data/alignment/match-preview-index.json`, window.location.href);
      try { await loadMatchPreviewIndex(previewUrl.href); }
      catch (error) { app.previewById = new Map(); console.warn("Zircon 候选缩略图不可用：", error.message); }
      try {
        const serverWorkspace = await fetch("/api/workspace", { cache: "no-store" });
        if (serverWorkspace.ok) app.serverWorkspace = true;
        else app.database = await openDatabase();
        app.state = await readWorkspace();
        if (navigator.storage?.persist) {
          try { app.storagePersistence = await navigator.storage.persist(); }
          catch { app.storagePersistence = false; }
        }
        setStatus(`本地工作区已载入 · 修订 ${app.state.revision}`);
      } catch (error) {
        app.database = null;
        setStatus(`${error.message}；本页保持只读。`, true);
        el("save-draft").disabled = true; el("import-button").disabled = true;
      }
      createCategoryNav(); fillFilters(); refreshStats(); renderSnapshot(); renderResearchContext(); renderRows();
      setStatus(app.serverWorkspace ? `项目文件工作区已载入 · 修订 ${app.state.revision}` : app.database ? `本地工作区已载入 · 修订 ${app.state.revision}` : "本地编辑不可用；公开记录只读", !app.database && !app.serverWorkspace);
    } catch (error) {
      el("load-error").hidden = false;
      el("load-error").textContent = `无法载入审计数据：${error.message}。请通过网站或本地 HTTP 服务访问此页面。`;
      el("result-summary").textContent = "主数据不可用";
      setStatus("读取失败；当前未写入任何数据。", true);
    }
  }

  start();
})();
