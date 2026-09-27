import assert from "node:assert/strict";
import test from "node:test";
import {
  buildGameNamesExport,
  buildMatchManifest,
  createMatchSelection,
  matchConfigFor,
  validateWorkspaceBundle,
  zirconIdentityKey,
} from "../static/js/alignment-workspace.mjs";

const SOURCE_HASH = "a".repeat(64);

function siteRecord(id, entityType, sourceId, name) {
  return {
    id,
    entity_type: entityType,
    identity: { website_source_id: sourceId, website_name: name },
  };
}

function gameRecord(id, entityType, index, internalName, translation = null) {
  return {
    id,
    entity_type: entityType,
    identity: {
      zircon_index: index,
      zircon_internal_name: internalName,
      current_translation: translation ? { zh: translation } : null,
    },
  };
}

function workspace(matches = {}, drafts = {}, events = []) {
  return { id: "workspace", revision: 3, drafts, matches, events };
}

function bundle(value) {
  return {
    schema_version: 2,
    format: "mir3-alignment-workspace",
    exported_at: "2026-09-27T00:00:00.000Z",
    base_master_sha256: SOURCE_HASH,
    workspace: value,
  };
}

const source = siteRecord("item:website:item-wooden-sword", "item", "item-wooden-sword", "木剑");
const item = gameRecord("item:zircon:126", "item", 126, "Wooden Sword", "木剑");
const questSource = siteRecord("mission:website:mission-training", "mission", "mission-training", "新手任务攻略");
const quest = gameRecord("quest:zircon:4", "quest", 4, "TrainingQuest");
const mapSource = siteRecord("map_group:website:world-map", "map_group", "world-map", "世界地图集合");
const map = gameRecord("map:zircon:3", "map", 3, "Bichon Town");
const records = new Map([source, item, questSource, quest, mapSource, map].map((row) => [row.id, row]));

function selected(sourceRow, targetRows) {
  return createMatchSelection(sourceRow.id, targetRows.map((row) => row.id), records, "2026-09-27T00:00:00.000Z");
}

test("manual matches preserve stable table identity keys and reject cross-type or duplicate targets", () => {
  assert.equal(matchConfigFor(source).target, "item");
  assert.equal(zirconIdentityKey(item), "ItemInfo:126");
  assert.deepEqual(selected(source, [item]).target_identity_keys, ["ItemInfo:126"]);
  assert.throws(() => selected(source, [quest]), /类型/);
  assert.throws(() => createMatchSelection(source.id, [item.id, item.id], records), /重复/);
});

test("workspace import requires compatible schema, master digest, source types and stable candidate identities", () => {
  const match = selected(source, [item]);
  const valid = bundle(workspace({ [source.id]: match }));
  const accepted = validateWorkspaceBundle(valid, { masterHash: SOURCE_HASH, recordsById: records });
  assert.equal(accepted.matches[source.id].target_identity_keys[0], "ItemInfo:126");

  assert.throws(() => validateWorkspaceBundle({ ...valid, schema_version: 1 }, { masterHash: SOURCE_HASH, recordsById: records }), /版本/);
  assert.throws(() => validateWorkspaceBundle({ ...valid, base_master_sha256: "b".repeat(64) }, { masterHash: SOURCE_HASH, recordsById: records }), /SHA-256/);
  assert.throws(() => validateWorkspaceBundle(bundle(workspace({ [source.id]: { ...match, target_identity_keys: ["QuestInfo:4"] } })), { masterHash: SOURCE_HASH, recordsById: records }), /身份键/);
  assert.throws(() => validateWorkspaceBundle(bundle(workspace({ [source.id]: { ...match, target_entity_ids: [quest.id] } })), { masterHash: SOURCE_HASH, recordsById: records }), /类型|身份键/);
});
test("workspace import rejects unknown metadata, malformed history and incomplete match timestamps", () => {
  const match = selected(source, [item]);
  const valid = bundle(workspace({ [source.id]: match }));
  const options = { masterHash: SOURCE_HASH, recordsById: records };

  assert.throws(() => validateWorkspaceBundle({
    ...valid, workspace: { ...valid.workspace, unexpected: true },
  }, options), /工作区结构/);

  const malformedEvent = {
    id: "event-1", at: "2026-09-27T00:00:00.000Z", entity_id: source.id, revision: 3,
    action: "edit", before: {}, after: {}, unexpected: true,
  };
  assert.throws(() => validateWorkspaceBundle(bundle(workspace({}, {}, [malformedEvent])), options), /历史记录/);

  assert.throws(() => validateWorkspaceBundle(bundle(workspace({
    [source.id]: { ...match, updated_at: null },
  })), options), /保存时间/);
});


test("game export changes only manually matched one-to-one names and preserves baseline locales", () => {
  const missionMatch = selected(questSource, [quest]);
  const mapMatch = selected(mapSource, [map]);
  const result = buildGameNamesExport({
    baseline: {
      items: { "Wooden Sword": { zh: "旧木剑名", ja: "木の剣" }, Untouched: { zh: "保留", ja: "保持" } },
      monsters: { Existing: { zh: "旧名", ja: "保持" } },
      magics: {},
      npcs: {},
      maps: { "Bichon Town": { zh: "比奇" } },
    },
    matches: { [source.id]: selected(source, [item]), [questSource.id]: missionMatch, [mapSource.id]: mapMatch },
    recordsById: records,
    sourceNameFor: (id) => records.get(id).identity.website_name,
  });

  assert.deepEqual(result.translation.items["Wooden Sword"], { zh: "木剑", ja: "木の剣" });
  assert.deepEqual(result.translation.items.Untouched, { zh: "保留", ja: "保持" });
  assert.deepEqual(result.translation.monsters, { Existing: { zh: "旧名", ja: "保持" } });
  assert.deepEqual(result.translation.maps, { "Bichon Town": { zh: "比奇" } });
  assert.equal(result.changed_keys.length, 1);
  assert.equal(result.changed_keys[0].previous_zh, "旧木剑名");

  assert.throws(() => buildGameNamesExport({
    baseline: {}, matches: { [questSource.id]: missionMatch, [mapSource.id]: mapMatch },
    recordsById: records, sourceNameFor: (id) => records.get(id).identity.website_name,
  }), /尚无.*可导出/);
});

test("game export blocks unresolved duplicate runtime-name keys and conflicting website labels", () => {
  const duplicate = gameRecord("item:zircon:127", "item", 127, "Wooden Sword");
  const expanded = new Map([...records, [duplicate.id, duplicate]]);
  const singleMatch = createMatchSelection(source.id, [item.id], expanded);
  assert.throws(() => buildGameNamesExport({
    baseline: { items: { "Wooden Sword": { zh: "旧名" } } },
    matches: { [source.id]: singleMatch }, recordsById: expanded,
    sourceNameFor: () => "木剑",
  }), /共用运行时名称键/);

  const secondSource = siteRecord("item:website:item-wood-sword-alt", "item", "item-wood-sword-alt", "木剑（旧称）");
  const bothSources = new Map([...expanded, [secondSource.id, secondSource]]);
  assert.throws(() => buildGameNamesExport({
    baseline: { items: { "Wooden Sword": { zh: "旧名" } } },
    matches: {
      [source.id]: createMatchSelection(source.id, [item.id], bothSources),
      [secondSource.id]: createMatchSelection(secondSource.id, [item.id], bothSources),
    }, recordsById: bothSources,
    sourceNameFor: (id) => bothSources.get(id).identity.website_name,
  }), /不同中文名/);
});

test("match manifest keeps quest攻略 and map集合 as explicit relations, not game-name entries", () => {
  const result = buildMatchManifest({
    masterHash: SOURCE_HASH,
    matches: { [questSource.id]: selected(questSource, [quest]), [mapSource.id]: selected(mapSource, [map]) },
    recordsById: records,
    sourceNameFor: (id) => records.get(id).identity.website_name,
  });
  assert.equal(result.matches.length, 2);
  assert.equal(result.matches[0].zircon[0].identity_key, "MapInfo:3");
  assert.equal(result.matches[1].zircon[0].identity_key, "QuestInfo:4");
  assert.equal(matchConfigFor(gameRecord("mission:zircon:1", "mission", 1, "Training")), null);
});
