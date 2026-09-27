export const MATCH_CONFIG = Object.freeze({
  monster: Object.freeze({ target: "monster", table: "MonsterInfo", label: "怪物 → Zircon MonsterInfo", multi: false, section: "monsters" }),
  item: Object.freeze({ target: "item", table: "ItemInfo", label: "物品 → Zircon ItemInfo", multi: false, section: "items" }),
  skill: Object.freeze({ target: "skill", table: "MagicInfo", label: "技能 → Zircon MagicInfo", multi: false, section: "magics" }),
  mission: Object.freeze({ target: "quest", table: "QuestInfo", label: "任务攻略 → Zircon QuestInfo", multi: true, section: null }),
  map_group: Object.freeze({ target: "map", table: "MapInfo", label: "地图分组 → Zircon MapInfo", multi: true, section: null }),
});

export const EDIT_FIELDS = Object.freeze([
  "standard_name_zh", "overall_status", "identity_mapping_status", "display_name_status",
  "resource_status", "game_data_status", "relations_status", "reason", "export_enabled",
]);

const STATUS_VALUES = new Set([
  "pending_review", "pending_evidence", "source_confirmed", "confirmed", "candidate",
  "conflict", "cross_entity_conflict", "ambiguous", "display_name_error", "approved",
  "corrected", "rejected", "not_applicable",
]);
const STATUS_FIELDS = [
  "overall_status", "identity_mapping_status", "display_name_status", "resource_status",
  "game_data_status", "relations_status",
];
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const hasOnlyKeys = (value, keys) => Object.keys(value).every((key) => keys.includes(key));
const parseableDate = (value) => typeof value === "string" && Number.isFinite(Date.parse(value));

export function matchConfigFor(record) {
  const config = MATCH_CONFIG[record?.entity_type];
  const identity = record?.identity || {};
  return config && typeof identity.website_source_id === "string" && identity.website_source_id.length > 0
    && !Number.isInteger(identity.zircon_index) ? config : null;
}

export function zirconIdentityKey(record) {
  const config = Object.values(MATCH_CONFIG).find((item) => item.target === record?.entity_type);
  const index = record?.identity?.zircon_index;
  if (!config || !Number.isSafeInteger(index) || index < 0 || record.id !== `${record.entity_type}:zircon:${index}`) return null;
  return `${config.table}:${index}`;
}

function validateTarget(sourceId, config, targetId, recordsById) {
  const target = recordsById.get(targetId);
  if (!target || target.entity_type !== config.target || !zirconIdentityKey(target)) {
    throw new Error(`匹配目标类型或 Zircon 身份键无效：${targetId}（来源 ${sourceId}）。`);
  }
  return target;
}

function validateSavedMatch(sourceId, saved, recordsById) {
  const source = recordsById.get(sourceId);
  const config = matchConfigFor(source);
  if (!config || !isObject(saved) || !hasOnlyKeys(saved, ["target_entity_ids", "target_identity_keys", "updated_at"])
      || !Array.isArray(saved.target_entity_ids) || !Array.isArray(saved.target_identity_keys)) {
    throw new Error(`工作区包含无效来源或缺少候选身份键：${sourceId}`);
  }
  const ids = saved.target_entity_ids;
  const identityKeys = saved.target_identity_keys;
  if (!ids.length || new Set(ids).size !== ids.length || (!config.multi && ids.length !== 1)
      || identityKeys.length !== ids.length) {
    throw new Error(`匹配数量、重复目标或身份键数量无效：${sourceId}`);
  }
  const targets = ids.map((id, index) => {
    const target = validateTarget(sourceId, config, id, recordsById);
    const identityKey = zirconIdentityKey(target);
    if (identityKeys[index] !== identityKey) throw new Error(`候选身份键与 Zircon 主数据不一致：${identityKeys[index]}`);
    return target;
  });
  if (!parseableDate(saved.updated_at)) throw new Error(`匹配保存时间无效：${sourceId}`);
  return { source, config, targets };
}

export function createMatchSelection(sourceId, targetIds, recordsById, updatedAt = new Date().toISOString()) {
  const source = recordsById.get(sourceId);
  const config = matchConfigFor(source);
  if (!config || !Array.isArray(targetIds)) throw new Error(`匹配来源类型或候选列表无效：${sourceId}`);
  const uniqueIds = [...new Set(targetIds)];
  if (uniqueIds.length !== targetIds.length) throw new Error("匹配中存在重复候选。");
  if ((!config.multi && uniqueIds.length > 1) || (uniqueIds.length > 0 && !parseableDate(updatedAt))) {
    throw new Error("匹配类型、数量或保存时间不合法。");
  }
  const targets = uniqueIds.map((id) => validateTarget(sourceId, config, id, recordsById));
  return {
    target_entity_ids: uniqueIds,
    target_identity_keys: targets.map(zirconIdentityKey),
    updated_at: uniqueIds.length ? updatedAt : null,
  };
}

function validateDraft(id, draft) {
  if (!isObject(draft)) throw new Error(`草稿结构不合法：${id}`);
  for (const key of Object.keys(draft)) if (!EDIT_FIELDS.includes(key)) throw new Error(`不支持的编辑字段：${key}`);
  for (const field of STATUS_FIELDS) {
    if (draft[field] != null && !STATUS_VALUES.has(draft[field])) throw new Error(`状态不在允许清单中：${draft[field]}`);
  }
  if (draft.standard_name_zh != null && (typeof draft.standard_name_zh !== "string" || draft.standard_name_zh.length > 120)) {
    throw new Error(`中文标准名不合法：${id}`);
  }
  if (draft.reason != null && (typeof draft.reason !== "string" || draft.reason.length > 1000)) {
    throw new Error(`复核理由不合法：${id}`);
  }
  if (draft.export_enabled != null && typeof draft.export_enabled !== "boolean") throw new Error(`翻译导出开关不合法：${id}`);
  if (draft.export_enabled && (!draft.standard_name_zh?.trim() || !["approved", "corrected"].includes(draft.overall_status)
      || !["confirmed", "source_confirmed"].includes(draft.identity_mapping_status))) {
    throw new Error(`翻译导出批准条件不完整：${id}`);
  }
}

function validateMatchEventTargets(sourceId, ids, recordsById) {
  const config = matchConfigFor(recordsById.get(sourceId));
  if (!config || !Array.isArray(ids)) throw new Error(`历史中有无效匹配来源：${sourceId}`);
  for (const id of ids) validateTarget(sourceId, config, id, recordsById);
}

export function validateWorkspaceBundle(bundle, { masterHash, recordsById }) {
  if (!isObject(bundle)) throw new Error("工作区文件版本不受支持；拒绝覆盖当前工作区。");
  if (!hasOnlyKeys(bundle, ["schema_version", "format", "exported_at", "base_master_sha256", "workspace"])) {
    throw new Error("工作区结构包含未识别字段；文件可能已损坏。");
  }
  if (bundle.schema_version !== 2 || bundle.format !== "mir3-alignment-workspace") {
    throw new Error("工作区文件版本不受支持；拒绝覆盖当前工作区。");
  }
  if (typeof masterHash !== "string" || bundle.base_master_sha256 !== masterHash
      || !/^[0-9a-f]{64}$/.test(bundle.base_master_sha256 || "")) {
    throw new Error("工作区主数据 SHA-256 不匹配；拒绝覆盖当前工作区。");
  }
  if (!parseableDate(bundle.exported_at)) throw new Error("工作区导出时间无效；文件可能已损坏。");
  const workspace = bundle.workspace;
  if (!isObject(workspace) || !hasOnlyKeys(workspace, ["id", "revision", "drafts", "matches", "events"])
      || workspace.id !== "workspace" || !Number.isSafeInteger(workspace.revision)
      || workspace.revision < 0 || !isObject(workspace.drafts) || !isObject(workspace.matches)
      || !Array.isArray(workspace.events)) {
    throw new Error("工作区结构、修订号或匹配清单不正确；文件可能已损坏。");
  }
  for (const [id, draft] of Object.entries(workspace.drafts)) {
    if (!recordsById.has(id)) throw new Error(`工作区包含未知记录：${id}`);
    validateDraft(id, draft);
  }
  for (const [sourceId, saved] of Object.entries(workspace.matches)) validateSavedMatch(sourceId, saved, recordsById);

  const eventIds = new Set();
  for (const event of workspace.events) {
    if (!isObject(event) || !hasOnlyKeys(event, ["id", "at", "entity_id", "revision", "action", "before", "after"])
        || typeof event.id !== "string" || !event.id || eventIds.has(event.id)
        || !parseableDate(event.at) || !recordsById.has(event.entity_id)
        || !Number.isSafeInteger(event.revision) || event.revision < 1 || event.revision > workspace.revision
        || !["edit", "match"].includes(event.action)) {
      throw new Error("工作区历史记录损坏或引用未知身份键。");
    }
    eventIds.add(event.id);
    if (event.action === "match") {
      validateMatchEventTargets(event.entity_id, event.before, recordsById);
      validateMatchEventTargets(event.entity_id, event.after, recordsById);
    } else {
      if (!isObject(event.before) || !isObject(event.after)) throw new Error(`草稿历史记录结构不合法：${event.entity_id}`);
      validateDraft(event.entity_id, event.before);
      validateDraft(event.entity_id, event.after);
    }
  }
  return structuredClone(workspace);
}

export function buildMatchManifest({ masterHash, matches, recordsById, sourceNameFor, exportedAt = new Date().toISOString() }) {
  if (!isObject(matches)) throw new Error("匹配工作区结构不正确。");
  const rows = [];
  for (const [sourceId, saved] of Object.entries(matches)) {
    const { source, targets } = validateSavedMatch(sourceId, saved, recordsById);
    rows.push({
      confirmation_status: "confirmed",
      website: {
        entity_id: source.id,
        entity_type: source.entity_type,
        source_id: source.identity.website_source_id,
        name: sourceNameFor(sourceId),
      },
      zircon: targets.map((target) => ({
        entity_id: target.id,
        entity_type: target.entity_type,
        table: MATCH_CONFIG[Object.keys(MATCH_CONFIG).find((type) => MATCH_CONFIG[type].target === target.entity_type)].table,
        identity_key: zirconIdentityKey(target),
        index: target.identity.zircon_index,
        internal_name: target.identity.zircon_internal_name || target.game_data?.QuestName || target.identity.current_game_name || target.id,
        current_display_name: target.identity.current_translation?.zh || target.identity.current_game_name || null,
      })).sort((left, right) => left.index - right.index),
      updated_at: saved.updated_at || null,
    });
  }
  rows.sort((left, right) => left.website.entity_type.localeCompare(right.website.entity_type)
    || left.website.source_id.localeCompare(right.website.source_id));
  if (!rows.length) throw new Error("当前浏览器没有已保存的人工匹配。");
  return {
    schema_version: 1,
    format: "mir3-website-zircon-match-manifest",
    exported_at: exportedAt,
    source_master_sha256: masterHash,
    storage_scope: "browser-local-indexeddb",
    matches: rows,
  };
}

export function buildGameNamesExport({ baseline, matches, recordsById, sourceNameFor }) {
  if (!isObject(baseline) || !isObject(matches)) throw new Error("游戏名称基线或匹配工作区结构不正确。");
  const output = structuredClone(baseline);
  const changesByKey = new Map();
  const selectedTargetIdsByKey = new Map();
  const candidatesByName = new Map();

  for (const record of recordsById.values()) {
    const config = Object.values(MATCH_CONFIG).find((item) => item.target === record.entity_type && item.section);
    const name = record.identity?.zircon_internal_name;
    if (!config || typeof name !== "string" || !name.trim() || !zirconIdentityKey(record)) continue;
    const key = `${config.section}\u0000${name}`;
    if (!candidatesByName.has(key)) candidatesByName.set(key, []);
    candidatesByName.get(key).push(record);
  }

  let mappedEntityCount = 0;
  for (const [sourceId, saved] of Object.entries(matches)) {
    const { source, config, targets } = validateSavedMatch(sourceId, saved, recordsById);
    if (!config.section) continue;
    const translatedName = sourceNameFor(sourceId);
    if (typeof translatedName !== "string" || !translatedName.trim()) throw new Error(`匹配来源没有可导出的中文名称：${sourceId}`);
    for (const target of targets) {
      const internalName = target.identity.zircon_internal_name;
      if (typeof internalName !== "string" || !internalName.trim()) {
        throw new Error(`Zircon ${config.table} Index ${target.identity.zircon_index} 缺少游戏内部英文名。`);
      }
      const key = `${config.section}\u0000${internalName}`;
      const existing = changesByKey.get(key);
      if (existing && existing.zh !== translatedName) {
        throw new Error(`游戏名称键“${internalName}”被匹配到不同中文名（${existing.zh} / ${translatedName}）。请先解决冲突。`);
      }
      if (!changesByKey.has(key)) changesByKey.set(key, { section: config.section, internal_name: internalName, zh: translatedName });
      if (!selectedTargetIdsByKey.has(key)) selectedTargetIdsByKey.set(key, new Set());
      selectedTargetIdsByKey.get(key).add(target.id);
      mappedEntityCount += 1;
    }
  }
  if (!mappedEntityCount) throw new Error("尚无怪物、物品或技能的可导出匹配；任务攻略与地图集合只写入匹配清单。");

  const changedKeys = [];
  for (const [key, change] of changesByKey) {
    const allSameName = candidatesByName.get(key) || [];
    const selectedIds = selectedTargetIdsByKey.get(key);
    const missing = allSameName.filter((record) => !selectedIds.has(record.id));
    if (missing.length) {
      const indexes = missing.map((record) => record.identity.zircon_index).sort((a, b) => a - b);
      throw new Error(`游戏名称键“${change.internal_name}”由多个 ${change.section} Index 共用运行时名称键；尚未逐一匹配 Index ${indexes.join(", ")}。`);
    }
    if (!isObject(output[change.section])) throw new Error(`真实 db_names.json 缺少对象分组：${change.section}`);
    const previous = output[change.section][change.internal_name];
    if (previous != null && !isObject(previous)) throw new Error(`真实 db_names.json 中的名称条目结构无效：${change.internal_name}`);
    const previousZh = previous?.zh ?? null;
    if (previousZh === change.zh) continue;
    output[change.section][change.internal_name] = { ...(previous || {}), zh: change.zh };
    changedKeys.push({ ...change, previous_zh: previousZh, identity_keys: allSameName.map(zirconIdentityKey).sort() });
  }
  changedKeys.sort((left, right) => left.section.localeCompare(right.section) || left.internal_name.localeCompare(right.internal_name));
  return { translation: output, changed_keys: changedKeys, mapped_entity_count: mappedEntityCount };
}
