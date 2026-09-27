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
    ["game", "游戏显示名"], ["status", "复核状态"], ["evidence", "来源 / 证据"]
  ];
  const EDIT_FIELDS = ["standard_name_zh", "overall_status", "identity_mapping_status", "display_name_status",
    "resource_status", "game_data_status", "relations_status", "reason", "export_enabled"];

  const el = id => document.getElementById(id);
  const app = {
    master: null, masterHash: "", records: [], byId: new Map(),
    observationsByEntity: new Map(), findingsByEntity: new Map(), sourceById: new Map(),
    externalSourceById: new Map(), searchQueryById: new Map(),
    database: null, currentCategory: "monster", page: 0, selectedId: null,
    originalDraft: {}, dirtyFields: new Set(), visibleColumns: new Set(COLUMN_DEFS.map(c => c[0])),
    candidateDownload: null, broadcast: null, sourceFilterIds: new Map()
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
      identity.standard_name_ja, identity.website_name, identity.website_source_id,
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
    const status = el("workspace-status");
    status.textContent = message;
    status.classList.toggle("is-error", isError);
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

  async function readWorkspace() {
    const tx = app.database.transaction("workspace", "readonly");
    const saved = await readRequest(tx.objectStore("workspace").get("workspace"));
    return saved || { id: "workspace", revision: 0, drafts: {}, events: [] };
  }

  function saveWorkspaceUpdate(recordId, originalDraft, changes) {
    return new Promise((resolve, reject) => {
      const tx = app.database.transaction("workspace", "readwrite");
      const store = tx.objectStore("workspace");
      const request = store.get("workspace");
      let nextState;
      let conflict = null;
      request.onsuccess = () => {
        const current = request.result || { id: "workspace", revision: 0, drafts: {}, events: [] };
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
        nextState = { id: "workspace", revision: current.revision + 1, drafts, events };
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
    app.records.forEach(record => { record._search = searchValue(record); });
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
    const statusSelect = el("status-filter");
    for (const value of [...statuses].sort()) statusSelect.add(new Option(statusLabel(value), value));
    const sourceSelect = el("source-filter");
    for (const value of [...sources].sort()) {
      const label = app.sourceById.get(value)?.path || value;
      sourceSelect.add(new Option(label, value));
    }
    createColumnOptions();
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
      card.append(createRecordButton(record, "查看对照与证据", "audit-card-action"));
      cards.append(card);
    }
    el("result-summary").textContent = `${numberFormat(rows.length)} 条记录 · 第 ${app.page + 1} / ${pageCount} 页 · 每页 ${PAGE_SIZE} 条`;
    el("page-label").textContent = `${app.page + 1} / ${pageCount}`;
    el("previous-page").disabled = app.page === 0;
    el("next-page").disabled = app.page >= pageCount - 1;
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
    setStatus(app.database ? `工作区修订 ${app.state.revision}` : "本地存储不可用；只读模式", !app.database);
    el("record-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderHistory(recordId) {
    const host = el("audit-history"); host.replaceChildren();
    const events = (app.state.events || []).filter(event => event.entity_id === recordId).slice(-20).reverse();
    for (const event of events) {
      const li = node("li", "history-entry");
      const time = new Date(event.at).toLocaleString("zh-CN", { hour12: false });
      appendText(li, "strong", "", `修订 ${event.revision} · ${time}`);
      appendText(li, "small", "", Object.entries(event.after || {}).filter(([key, value]) => JSON.stringify(event.before?.[key]) !== JSON.stringify(value))
        .map(([key, value]) => `${fieldLabel(key)} → ${typeof value === "boolean" ? (value ? "启用" : "关闭") : value}`).join("；") || "记录本地修改");
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
    if (!app.database || !app.selectedId) return;
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
    if (!bundle || bundle.schema_version !== 1 || bundle.base_master_sha256 !== app.masterHash || !bundle.workspace) {
      throw new Error("导入文件版本或主数据 SHA-256 不匹配；拒绝覆盖当前工作区。");
    }
    const workspace = bundle.workspace;
    if (!workspace.drafts || typeof workspace.drafts !== "object" || !Array.isArray(workspace.events)) throw new Error("工作区结构不正确。");
    const allowed = new Set(EDIT_FIELDS);
    for (const [id, draft] of Object.entries(workspace.drafts)) {
      if (!app.byId.has(id) || !draft || typeof draft !== "object") throw new Error(`工作区包含未知记录：${id}`);
      for (const key of Object.keys(draft)) if (!allowed.has(key)) throw new Error(`不支持的编辑字段：${key}`);
      for (const field of ["overall_status", "identity_mapping_status", "display_name_status", "resource_status", "game_data_status", "relations_status"]) {
        if (draft[field] != null && !Object.hasOwn(STATUS_LABELS, draft[field])) throw new Error(`状态不在允许清单中：${draft[field]}`);
      }
      if (draft.standard_name_zh != null && (typeof draft.standard_name_zh !== "string" || draft.standard_name_zh.length > 120)) throw new Error(`中文标准名不合法：${id}`);
      if (draft.reason != null && (typeof draft.reason !== "string" || draft.reason.length > 1000)) throw new Error(`复核理由不合法：${id}`);
      if (draft.export_enabled && (!draft.standard_name_zh || !["approved", "corrected"].includes(draft.overall_status)
          || !["confirmed", "source_confirmed"].includes(draft.identity_mapping_status))) throw new Error(`翻译导出批准条件不完整：${id}`);
    }
    return workspace;
  }

  function downloadJson(filename, value) {
    const blob = new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename;
    document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
  }

  function exportWorkspace() {
    const bundle = { schema_version: 1, exported_at: new Date().toISOString(), base_master_sha256: app.masterHash, workspace: app.state };
    downloadJson("mir3-alignment-workspace.json", bundle);
  }

  async function importWorkspace(file) {
    const bundle = JSON.parse(await file.text());
    const workspace = validateBundle(bundle);
    if (!window.confirm(`将用 ${Object.keys(workspace.drafts).length} 条草稿替换此浏览器中的本地工作区。公开主数据不会改变。继续？`)) return;
    const tx = app.database.transaction("workspace", "readwrite");
    tx.objectStore("workspace").put({ ...workspace, id: "workspace", revision: (app.state.revision || 0) + 1 });
    await new Promise((resolve, reject) => { tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || new Error("导入已中止")); });
    app.state = await readWorkspace(); refreshStats(); renderRows();
    if (app.selectedId) openRecord(app.selectedId);
    setStatus(`已导入 ${Object.keys(app.state.drafts).length} 条本地草稿。`);
    app.broadcast?.postMessage({ revision: app.state.revision, imported: true });
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
      el("export-message").textContent = `${result.changes.length} 项中文值变化；${result.approved_record_count} 条记录显式批准。未批准项和所有未触及 locale 保持原样。候选 SHA-256：${candidateHash}。此文件不会写入 Zircon。`;
      el("export-preview").textContent = JSON.stringify({ changes: result.changes, rollback: result.rollback }, null, 2);
      el("export-dialog").showModal();
    } catch (error) {
      el("export-message").textContent = error.message;
      el("export-preview").textContent = "候选未生成；请解决身份键冲突或缺失的批准条件。";
      app.candidateDownload = null;
      el("export-dialog").showModal();
    }
  }

  function bindEvents() {
    el("search-input").addEventListener("input", () => { app.page = 0; renderRows(); });
    for (const id of ["status-filter", "source-filter", "sort-select"]) el(id).addEventListener("change", () => { app.page = 0; renderRows(); });
    el("previous-page").addEventListener("click", () => { app.page = Math.max(0, app.page - 1); renderRows(); });
    el("next-page").addEventListener("click", () => { app.page += 1; renderRows(); });
    for (const host of [el("table-body"), el("card-list"), el("detail-comparison"), el("relations-view")]) {
      host.addEventListener("click", event => {
        const button = event.target.closest("[data-record-id]");
        if (button) openRecord(button.dataset.recordId);
      });
    }
    el("close-detail").addEventListener("click", () => { el("record-detail").hidden = true; app.selectedId = null; });
    const fieldMap = { "edit-name": "standard_name_zh", "edit-overall": "overall_status", "edit-identity": "identity_mapping_status",
      "edit-display": "display_name_status", "edit-resource": "resource_status", "edit-game-data": "game_data_status",
      "edit-relations": "relations_status", "edit-reason": "reason", "edit-export": "export_enabled" };
    for (const [id, field] of Object.entries(fieldMap)) {
      const control = el(id); control.dataset.field = field;
      control.addEventListener(control.type === "checkbox" || control.tagName === "SELECT" ? "change" : "input", markDirty);
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
    el("close-export").addEventListener("click", () => el("export-dialog").close());
    el("close-export-footer").addEventListener("click", () => el("export-dialog").close());
    el("download-export").addEventListener("click", () => {
      if (!app.candidateDownload) return;
      downloadJson("mir3-db_names-translation-candidate.json", app.candidateDownload);
    });
    if (window.BroadcastChannel) {
      app.broadcast = new BroadcastChannel("mir3-alignment-workspace");
      app.broadcast.onmessage = async event => {
        if (!Number.isInteger(event.data?.revision) || event.data.revision <= app.state.revision) return;
        app.state = await readWorkspace(); refreshStats(); renderRows();
        if (app.selectedId) setStatus("另一标签页已保存工作区；当前记录草稿未覆盖，请比较后再保存。", true);
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
      try {
        app.database = await openDatabase();
        app.state = await readWorkspace();
        setStatus(`本地工作区已载入 · 修订 ${app.state.revision}`);
      } catch (error) {
        app.database = null;
        setStatus(`${error.message}；本页保持只读。`, true);
        el("save-draft").disabled = true; el("import-button").disabled = true;
      }
      createCategoryNav(); fillFilters(); refreshStats(); renderSnapshot(); renderResearchContext(); renderRows();
      setStatus(app.database ? `本地工作区已载入 · 修订 ${app.state.revision}` : "本地编辑不可用；公开记录只读", !app.database);
    } catch (error) {
      el("load-error").hidden = false;
      el("load-error").textContent = `无法载入审计数据：${error.message}。请通过网站或本地 HTTP 服务访问此页面。`;
      el("result-summary").textContent = "主数据不可用";
      setStatus("读取失败；当前未写入任何数据。", true);
    }
  }

  start();
})();
