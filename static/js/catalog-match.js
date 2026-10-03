import { MATCH_CONFIG, createMatchSelection, zirconIdentityKey } from "./alignment-workspace.mjs?v=20260928";

(() => {
  const $ = id => document.getElementById(`catalog-match-${id}`);
  const drawer = $("drawer"), backdrop = $("backdrop");
  if (!drawer || !backdrop) return;

  const PAGE_SIZE = 60;
  const ITEM_CATEGORY_MAP = {
    "武器": ["Weapon"],
    "盔甲": ["Armour"],
    "衣服": ["Armour"],
    "戒指": ["Ring"],
    "手镯": ["Bracelet"],
    "手套": ["Bracelet"],
    "项链": ["Necklace"],
    "头盔": ["Helmet"],
    "鞋子": ["Shoes"],
    "特殊饰品": ["Amulet", "Emblem", "Torch", "Shield"],
    "普通道具": ["Consumable", "Ore", "Meat", "Poison", "DarkStone", "Currency"],
    "任务道具": ["Consumable", "Nothing", "Book"],
    "套装道具": ["Weapon", "Armour", "Ring", "Bracelet", "Necklace", "Helmet", "Shoes"]
  };

  let records = new Map();
  let db = null;
  let serverWorkspace = false;
  let state = { revision: 0, matches: {}, drafts: {}, events: [] };
  let source = null;
  let priorFocus = null;
  let candidates = [];
  let itemTypeFilter = "all";
  let currentPage = 0;
  let websiteCategory = "";

  function setStatus(message, error = false) {
    const el = $("status");
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("is-error", error);
  }

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("mir3-alignment-workspace", 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains("workspace")) {
          request.result.createObjectStore("workspace", { keyPath: "id" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function readState() {
    if (serverWorkspace) {
      return fetch("/api/workspace", { cache: "no-store" }).then(res => {
        if (!res.ok) throw new Error("项目工作区读取失败");
        return res.json();
      });
    }
    return new Promise((resolve, reject) => {
      const request = db.transaction("workspace").objectStore("workspace").get("workspace");
      request.onsuccess = () => resolve(request.result || { id: "workspace", revision: 0, matches: {}, drafts: {}, events: [] });
      request.onerror = () => reject(request.error);
    });
  }

  function recordName(record) {
    return record?.identity?.zircon_internal_name
      || record?.identity?.current_game_name
      || record?.identity?.standard_name_zh
      || record?.id
      || "";
  }

  function selectedIds() {
    if (!source) return [];
    return state.matches[source.id]?.target_entity_ids || [];
  }

  function getOrCreateSource(sourceId, card = null) {
    if (!sourceId) return null;
    let rec = [...records.values()].find(row => row.identity?.website_source_id === sourceId);
    if (rec) return rec;

    let entityType = "monster";
    if (sourceId.startsWith("item-") || location.pathname.includes("/items/")) {
      entityType = "item";
    } else if (sourceId.startsWith("skill-") || location.pathname.includes("/skills/")) {
      entityType = "skill";
    } else if (sourceId.startsWith("mob-") || location.pathname.includes("/mobs/")) {
      entityType = "monster";
    }

    const syntheticId = `${entityType}:website:${sourceId}`;
    if (records.has(syntheticId)) return records.get(syntheticId);

    const websiteName = card?.querySelector(".card-name, .detail-name")?.textContent?.trim() || sourceId;

    rec = {
      id: syntheticId,
      entity_type: entityType,
      identity: {
        website_source_id: sourceId,
        website_name: websiteName,
        standard_name_zh: websiteName
      },
      game_data: {},
      relations: {},
      evidence: []
    };
    records.set(syntheticId, rec);
    return rec;
  }

  function syncListBadges() {
    for (const button of document.querySelectorAll(".catalog-match-button")) {
      const sourceId = button.dataset.sourceId;
      if (!sourceId) continue;
      const card = button.closest(".data-card") || button.closest(".detail-portrait");
      const rec = getOrCreateSource(sourceId, card);
      const targetIds = rec ? (state.matches[rec.id]?.target_entity_ids || []) : [];
      const badge = card?.querySelector(".zircon-match");
      if (targetIds.length > 0) {
        const target = records.get(targetIds[0]);
        button.textContent = "已匹配 · 修改";
        button.classList.add("is-saved");
        if (card && card.classList.contains("data-card")) {
          card.setAttribute("data-zircon-state", "matched");
        }
        if (badge) {
          badge.className = "zircon-match zircon-match--matched";
          const label = badge.querySelector(".zircon-match-label");
          const details = badge.querySelector(".zircon-match-details");
          if (label) label.textContent = "Zircon：已建立匹配";
          if (details) {
            details.textContent = target
              ? `Index ${target.identity?.zircon_index} · ${recordName(target)}${target.identity?.current_translation?.zh ? ' (' + target.identity.current_translation.zh + ')' : ''}`
              : targetIds[0];
          }
        }
      } else {
        button.classList.remove("is-saved");
        button.textContent = "匹配";
      }
    }
    const activeFilter = document.querySelector('.zircon-filter-button[aria-pressed="true"]');
    if (activeFilter) activeFilter.click();
  }

  function renderCurrentMatchBanner() {
    const banner = $("current");
    const chosen = selectedIds();
    if (!chosen.length) {
      banner.hidden = true;
      banner.replaceChildren();
      return;
    }
    const target = records.get(chosen[0]);
    banner.hidden = false;
    banner.replaceChildren();

    const info = document.createElement("span");
    info.innerHTML = `当前匹配：<strong>${target ? recordName(target) : chosen[0]}</strong> ${target?.identity?.zircon_index != null ? `(Index ${target.identity.zircon_index})` : ''} · ${target?.identity?.current_translation?.zh || target?.identity?.current_game_name || ''}`;
    
    const unmatchBtn = document.createElement("button");
    unmatchBtn.type = "button";
    unmatchBtn.className = "button button-quiet";
    unmatchBtn.textContent = "取消匹配";
    unmatchBtn.style.padding = "2px 8px";
    unmatchBtn.style.fontSize = "10px";
    unmatchBtn.addEventListener("click", () => save([]));

    banner.append(info, unmatchBtn);
  }

  function renderCategoryFilterTabs() {
    const container = $("filter-bar");
    if (source?.entity_type !== "item") {
      container.hidden = true;
      container.replaceChildren();
      return;
    }

    container.hidden = false;
    container.replaceChildren();

    const tabs = [
      { id: "all", label: "全部物品" },
      { id: "Weapon", label: "武器" },
      { id: "Armour", label: "盔甲/衣服" },
      { id: "Ring", label: "戒指" },
      { id: "Bracelet", label: "手镯/手套" },
      { id: "Necklace", label: "项链" },
      { id: "Helmet", label: "头盔" },
      { id: "Shoes", label: "鞋子" },
      { id: "Book", label: "技能书" },
      { id: "Consumable", label: "消耗品/药" }
    ];

    for (const tab of tabs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `match-filter-tab${itemTypeFilter === tab.id ? " is-active" : ""}`;
      btn.textContent = tab.label;
      btn.addEventListener("click", () => {
        itemTypeFilter = tab.id;
        currentPage = 0;
        renderCategoryFilterTabs();
        renderCandidates();
      });
      container.append(btn);
    }
  }

  function getFilteredCandidates() {
    const query = $("search").value.trim().toLocaleLowerCase("zh-CN");
    return candidates.filter(row => {
      if (source?.entity_type === "item" && itemTypeFilter !== "all") {
        const rowType = row.game_data?.ItemType;
        if (rowType !== itemTypeFilter) return false;
      }
      if (!query) return true;
      const haystack = [
        recordName(row),
        row.identity?.current_game_name,
        row.identity?.current_translation?.zh,
        row.identity?.current_translation?.ja,
        String(row.identity?.zircon_index),
        row.game_data?.ItemType,
        zirconIdentityKey(row)
      ].filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
      return haystack.includes(query);
    });
  }

  function renderCandidates() {
    const list = $("list");
    list.replaceChildren();

    const filtered = getFilteredCandidates();
    const totalCount = filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
    if (currentPage >= totalPages) currentPage = totalPages - 1;
    if (currentPage < 0) currentPage = 0;

    $("count").textContent = `${totalCount} 个候选`;
    $("page-label").textContent = `${currentPage + 1} / ${totalPages}`;
    $("prev").disabled = currentPage === 0;
    $("next").disabled = currentPage >= totalPages - 1;

    const pageRows = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
    const selected = new Set(selectedIds());

    if (!pageRows.length) {
      const empty = document.createElement("p");
      empty.className = "match-empty";
      empty.textContent = "没有找到符合条件的候选。可以清空筛选或尝试搜英文名、中文名、Index。";
      list.append(empty);
      return;
    }

    const prefix = location.pathname.split("/").filter(Boolean).length > 1 ? ".." : "";

    for (const row of pageRows) {
      const isSelected = selected.has(row.id);
      const card = document.createElement("article");
      card.className = `match-candidate-card${isSelected ? " is-selected" : ""}`;

      const media = document.createElement("div");
      media.className = "match-candidate-thumb";

      const previewPath = window.previewAssets?.[row.id];
      if (previewPath && previewPath.startsWith("images/zircon-match/") && !previewPath.split("/").includes("..")) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.src = `${prefix}/${previewPath}`;
        img.alt = `${recordName(row)} 候选图`;
        media.append(img);
      } else {
        const placeholder = document.createElement("span");
        placeholder.className = "match-thumb-placeholder";
        placeholder.textContent = "无图像";
        media.append(placeholder);
      }

      const copy = document.createElement("div");
      copy.className = "match-candidate-copy";
      const title = document.createElement("strong");
      title.textContent = recordName(row);
      const subtitle = document.createElement("p");
      const zh = row.identity?.current_translation?.zh || row.identity?.current_game_name || "—";
      subtitle.textContent = `游戏当前名：${zh}`;
      const details = document.createElement("small");
      const extras = [
        `Index ${row.identity?.zircon_index}`,
        row.game_data?.ItemType || (row.entity_type === "monster" && row.game_data?.Level != null ? `Lv ${row.game_data.Level}` : null),
        zirconIdentityKey(row)
      ].filter(Boolean).join(" · ");
      details.textContent = extras;
      copy.append(title, subtitle, details);

      const action = document.createElement("button");
      action.type = "button";
      action.className = "match-choice-action";
      action.textContent = isSelected ? "✓ 已匹配" : "匹配此项";
      action.setAttribute("aria-pressed", String(isSelected));
      action.addEventListener("click", () => save([row.id]));

      card.append(media, copy, action);
      list.append(card);
    }

    $("clear").hidden = !selected.size;
  }

  function save(ids) {
    if ((!db && !serverWorkspace) || !source) {
      return setStatus("本地工作区不可用，匹配未保存。", true);
    }
    let selection;
    try {
      selection = createMatchSelection(source.id, ids, records);
    } catch (err) {
      return setStatus(err.message, true);
    }

    if (serverWorkspace) {
      (async () => {
        const current = await readState();
        const matches = { ...current.matches };
        const before = matches[source.id]?.target_entity_ids || [];
        if (ids.length) matches[source.id] = selection;
        else delete matches[source.id];
        const revision = current.revision + 1;
        const next = {
          ...current,
          revision,
          matches,
          events: [
            ...current.events,
            {
              id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
              at: new Date().toISOString(),
              entity_id: source.id,
              revision,
              action: "match",
              before,
              after: ids
            }
          ]
        };
        const res = await fetch("/api/workspace", {
          method: "PUT",
          headers: { "Content-Type": "application/json", "If-Match-Revision": String(current.revision) },
          body: JSON.stringify(next)
        });
        if (!res.ok) throw new Error(res.status === 409 ? "工作区已在其他页面更新，请刷新重试。" : "项目工作区写入失败。");
        state = await res.json();
        setStatus(`已保存到项目工作区 · 修订 ${state.revision}`);
        renderCurrentMatchBanner();
        renderCandidates();
        syncListBadges();
      })().catch(err => setStatus(err.message, true));
      return;
    }

    const tx = db.transaction("workspace", "readwrite");
    const store = tx.objectStore("workspace");
    const req = store.get("workspace");
    req.onsuccess = () => {
      const current = req.result || { id: "workspace", revision: 0, matches: {}, drafts: {}, events: [] };
      const matches = { ...current.matches };
      const before = matches[source.id]?.target_entity_ids || [];
      if (ids.length) matches[source.id] = selection;
      else delete matches[source.id];
      const revision = (current.revision || 0) + 1;
      const events = [
        ...(current.events || []),
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          at: new Date().toISOString(),
          entity_id: source.id,
          revision,
          action: "match",
          before,
          after: ids
        }
      ];
      store.put({ ...current, id: "workspace", revision, matches, events });
    };
    tx.oncomplete = async () => {
      state = await readState();
      setStatus(`已保存到浏览器本地工作区 · 修订 ${state.revision}`);
      renderCurrentMatchBanner();
      renderCandidates();
      syncListBadges();
    };
    tx.onerror = () => setStatus("匹配保存失败。", true);
  }

  function close() {
    drawer.hidden = backdrop.hidden = true;
    document.body.classList.remove("match-open");
    if (priorFocus?.isConnected) priorFocus.focus();
  }

  function openDrawer(button) {
    const sourceId = button.dataset.sourceId;
    const card = button.closest(".data-card") || button.closest(".detail-portrait");
    source = getOrCreateSource(sourceId, card);
    if (!source) {
      return setStatus(`未在主数据中找到条目：${sourceId}`, true);
    }

    priorFocus = button;
    const config = MATCH_CONFIG[source.entity_type];
    candidates = [...records.values()].filter(row => row.entity_type === config.target && zirconIdentityKey(row));

    const websiteName = card?.querySelector(".card-name, .detail-name")?.textContent?.trim()
      || source.identity?.website_name
      || source.identity?.standard_name_zh
      || sourceId;

    $("title").textContent = websiteName;
    $("source-id").textContent = `${sourceId} · ${source.entity_type}`;
    $("type").textContent = config.label;

    const sourceMedia = $("source-media");
    sourceMedia.replaceChildren();
    const cardImg = card?.querySelector("img");
    if (cardImg && cardImg.src) {
      const clonedImg = document.createElement("img");
      clonedImg.src = cardImg.src;
      clonedImg.alt = websiteName;
      sourceMedia.append(clonedImg);
    } else {
      const span = document.createElement("span");
      span.textContent = websiteName.slice(0, 2);
      sourceMedia.append(span);
    }

    if (source.entity_type === "item") {
      websiteCategory = "";
      if (sourceId.startsWith("item-")) {
        const parts = sourceId.split("-");
        if (parts.length >= 2) websiteCategory = parts[1];
      }
      if (!websiteCategory) {
        const catText = card?.querySelector(".detail-cat")?.textContent || "";
        const m = catText.match(/物品类型[：:]\s*(.+)/);
        if (m) websiteCategory = m[1].trim();
      }

      const mappedTypes = ITEM_CATEGORY_MAP[websiteCategory];
      if (mappedTypes && mappedTypes.length === 1) {
        itemTypeFilter = mappedTypes[0];
      } else {
        itemTypeFilter = "all";
      }
    } else {
      itemTypeFilter = "all";
    }

    currentPage = 0;
    $("search").value = "";
    drawer.hidden = backdrop.hidden = false;
    document.body.classList.add("match-open");

    setStatus(serverWorkspace ? "已连接后端项目文件 (.local/alignment-workspace.json)" : "保存在当前浏览器的 IndexedDB");
    renderCurrentMatchBanner();
    renderCategoryFilterTabs();
    renderCandidates();
    window.setTimeout(() => $("search").focus(), 50);
  }

  function bindButtons() {
    document.querySelectorAll(".catalog-match-button").forEach(btn => {
      if (!btn.dataset.bound) {
        btn.dataset.bound = "true";
        btn.addEventListener("click", () => openDrawer(btn));
      }
    });
  }

  $("close").addEventListener("click", close);
  backdrop.addEventListener("click", close);
  $("search").addEventListener("input", () => {
    currentPage = 0;
    renderCandidates();
  });
  $("prev").addEventListener("click", () => {
    if (currentPage > 0) {
      currentPage--;
      renderCandidates();
    }
  });
  $("next").addEventListener("click", () => {
    currentPage++;
    renderCandidates();
  });
  $("clear").addEventListener("click", () => save([]));
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !drawer.hidden) close();
  });

  (async () => {
    try {
      bindButtons();
      const prefix = location.pathname.split("/").filter(Boolean).length > 1 ? ".." : "";
      const masterUrl = `${prefix}/data/alignment/master.json`;
      const response = await fetch(masterUrl);
      if (!response.ok) throw new Error("匹配主数据文件不存在");
      const manifest = await response.json();
      const descriptors = Object.values(manifest.shards).flat();
      const loaded = await Promise.all(descriptors.map(async desc => {
        const res = await fetch(new URL(desc.path, response.url));
        if (!res.ok) throw new Error(`分片 ${desc.path} 加载失败`);
        return res.json();
      }));
      for (const row of loaded.flat()) records.set(row.id, row);

      try {
        const preview = await fetch(`${prefix}/data/alignment/match-preview-index.json`);
        if (preview.ok) window.previewAssets = (await preview.json()).assets || {};
      } catch { /* optional preview images */ }

      try {
        const api = await fetch("/api/workspace", { cache: "no-store" });
        if (api.ok) {
          serverWorkspace = true;
          state = await api.json();
        } else {
          db = await openDb();
          state = await readState();
        }
      } catch {
        db = await openDb();
        state = await readState();
      }

      document.querySelectorAll(".catalog-match-button").forEach(b => {
        b.disabled = false;
      });
      syncListBadges();
    } catch (err) {
      console.error("加载匹配数据失败:", err);
      document.querySelectorAll(".catalog-match-button").forEach(b => {
        b.disabled = true;
        b.title = err.message;
      });
    }
  })();

  if (window.BroadcastChannel) {
    const channel = new BroadcastChannel("mir3-alignment-workspace");
    channel.onmessage = async () => {
      try {
        state = await readState();
        syncListBadges();
        if (source && !drawer.hidden) {
          renderCurrentMatchBanner();
          renderCandidates();
        }
      } catch { /* ignore */ }
    };
  }
})();
