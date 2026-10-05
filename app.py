#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传奇3 资料站 · 静态站构建器与本地预览
====================================
读取 data/*.json → Jinja2 模板渲染 → 输出静态 HTML 到 dist/。

用法:
    python app.py build    # 生成 dist/ 静态站(GitHub Pages 部署产物)
    python app.py serve    # 本地预览(Flask 动态渲染, 调试用)

目录结构:
    dist/index.html            首页
    dist/mobs/index.html       怪物列表(按分类分组)
    dist/mobs/<id>.html        怪物详情
    dist/items/...             物品列表 + 详情
    dist/skills/...            技能列表 + 详情
    dist/missions/...          任务列表 + 详情
    dist/maps/index.html       地图资料
    dist/images/               图片(复制自仓库 images/)
    dist/static/               样式/脚本
"""

import json
import os
import shutil
import sys
import threading
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TPL_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"
LOCAL_WORKSPACE_PATH = ROOT / ".local" / "alignment-workspace.json"
LOCAL_WORKSPACE_LOCK = threading.Lock()

# 导航结构(与 data/meta.json 一致)
NAV = [
    ("首页", "index.html", "home"),
    ("怪物图鉴", "mobs/index.html", "mobs"),
    ("物品大全", "items/index.html", "items"),
    ("技能资料", "skills/index.html", "skills"),
    ("任务攻略", "missions/index.html", "missions"),
    ("地图资料", "maps/index.html", "maps"),
    ("数据审计", "audit/index.html", "audit"),
]


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def _zircon_match_index():
    """Index website-origin alignment records by their stable source ID."""
    master_path = DATA_DIR / "alignment" / "master.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    records = {}
    for shard in master.get("shards", {}).get("entities", []):
        path = DATA_DIR / "alignment" / shard["path"]
        for entity in json.loads(path.read_text(encoding="utf-8")):
            identity = entity.get("identity") or {}
            source_ids = list(identity.get("website_source_ids") or [])
            single_id = identity.get("website_source_id")
            if single_id and single_id not in source_ids:
                source_ids.append(single_id)
            for sid in source_ids:
                records[sid] = entity
    return records


def _match_badge(entity):
    """Summarize evidence without treating an unreviewed candidate as confirmed."""
    if not entity:
        return {"label": "尚无对照记录", "state": "unreviewed", "details": []}
    identity = entity.get("identity") or {}
    assessment = entity.get("assessment") or {}
    status = assessment.get("overall_status", "pending_review")
    indexes = []
    direct = identity.get("zircon_index")
    if isinstance(direct, int):
        indexes.append(direct)
    indexes.extend(i for i in identity.get("zircon_candidate_indexes", [])
                   if isinstance(i, int) and i not in indexes)
    names = []
    if identity.get("zircon_internal_name"):
        names.append(str(identity["zircon_internal_name"]))
    for name in identity.get("zircon_candidate_names", []):
        if name and str(name) not in names:
            names.append(str(name))
    if status in {"conflict", "cross_entity_conflict", "ambiguous"}:
        label, state = "存在冲突 · 待复核", "conflict"
    elif direct is not None and status in {"confirmed", "approved", "corrected"}:
        label, state = "已确认匹配", "matched"
    elif indexes:
        label, state = "有 Zircon 候选 · 待复核", "candidate"
    else:
        label, state = "尚未建立匹配 · 待核对", "unmatched"
    details = [f"Index {i}" for i in indexes]
    details.extend(names)
    current = identity.get("current_game_name")
    if current and current not in names:
        details.append(f"游戏当前名：{current}")
    return {"label": label, "state": state, "details": details}


def load_data():
    """Read site data and attach conservative Zircon cross-reference summaries."""
    out = {}
    for name in ("monsters", "items", "skills", "missions", "maps", "meta"):
        p = DATA_DIR / f"{name}.json"
        out[name] = json.loads(p.read_text(encoding="utf-8"))
    id_keys = {"monsters": "mob", "items": "item", "skills": "skill",
               "missions": "mission"}
    for name, prefix in id_keys.items():
        for i, it in enumerate(out[name]):
            it.setdefault("id", f"{prefix}-{i}")

    crossrefs = _zircon_match_index()
    for it in out["monsters"]:
        record = crossrefs.get(it["id"])
        it["zircon_match"] = _match_badge(record)
        it["alignment_source_id"] = it["id"]
    for it in out["items"]:
        source_id = f"item-{it.get('category', '')}-{it.get('name', '')}"
        it["zircon_match"] = _match_badge(crossrefs.get(source_id))
        it["alignment_source_id"] = source_id
    for it in out["skills"] + out["missions"]:
        it["zircon_match"] = _match_badge(crossrefs.get(it["id"]))
        it["alignment_source_id"] = it["id"]
    # maps.json 现为全服 627 张地图的结构化文档（旧版是 3 个图集卡片的列表）。
    # 两种结构都要能读：列表走旧的图集对照，字典直接跳过——其内容已由
    # Zircon System.db 精确导出，无需再做候选推断。
    if isinstance(out["maps"], list):
        for group in out["maps"]:
            record = crossrefs.get(group["id"])
            it = _match_badge(record)
            identity = (record or {}).get("identity") or {}
            candidate_areas = identity.get("zircon_candidate_indexes", [])
            if candidate_areas:
                it["details"] = [f"候选 MapInfo Index：{', '.join(map(str, candidate_areas))}"]
            elif record:
                it["details"] = ["网站地图是区域集合；游戏侧按单张地图记录，需逐区域核对。"]
            group["zircon_match"] = it
    return out


def image_src(src):
    """图片路径规范化: 统一为站内相对路径(页面位于 dist/<type>/ 子目录)。"""
    if not src:
        return None
    # 去掉可能的 CDN 前缀
    src = src.replace("//images.17173cdn.com/mir3/images/", "../images/")
    if src.startswith("../images/"):
        return src
    if src.startswith("images/"):
        return "../" + src
    return "../" + src.lstrip("/")


def build_env():
    """构建 Jinja2 环境 + 全局过滤器。"""
    env = Environment(
        loader=FileSystemLoader(str(TPL_DIR)),
        autoescape=select_autoescape(["html", "htm", "xml"]),
    )
    env.globals["NAV"] = NAV
    env.filters["img"] = image_src
    # 描述文本分行(技能等级要求等)
    env.filters["lines"] = lambda s: (s or "").split("\n")
    return env


# ---------------------------------------------------------------------------
# 上下文构造
# ---------------------------------------------------------------------------

def page_ctx(data, section, prefix=""):
    """公共上下文: 当前导航高亮 + 页面相对前缀(用于 CSS/图片)。"""
    meta = data["meta"]
    return {
        "site": meta["site"],
        "nav": meta["nav"],
        "section": section,
        "prefix": prefix,
    }


def mob_cards(mob):
    """怪物详情页补充展示字段。"""
    attrs = dict(mob.get("attrs") or {})
    icons = attrs.pop("属性图标", None)
    stat = attrs.pop("属性数值", None)
    return {"mob": mob, "attrs": attrs, "stat": stat, "icons": icons}


def item_props(item):
    """物品详情页: 把属性字段(非基础字段)整理为有序键值对。"""
    base = {"id", "name", "category", "image", "description", "zircon_match", "alignment_source_id"}
    props = [(k, v) for k, v in item.items() if k not in base and v not in ("", "-", None)]
    return props


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render_all(data, env):
    """Validate the canonical alignment bundle, then render and sync deployable output."""
    from tools.alignment import load_master, validate_master

    master_path = DATA_DIR / "alignment" / "master.json"
    master = load_master(master_path)
    errors = validate_master(master)
    if errors:
        raise ValueError("对齐主数据校验失败:\n" + "\n".join(errors[:30]))
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    # 复制静态资源、版本化对齐主数据与可选自定义域名配置；构建不读取研究仓库或 System.db。
    shutil.copytree(ROOT / "images", DIST_DIR / "images")
    shutil.copytree(STATIC_DIR, DIST_DIR / "static")
    shutil.copytree(DATA_DIR / "alignment", DIST_DIR / "data" / "alignment")
    cname = ROOT / "CNAME"
    if cname.is_file():
        shutil.copy2(cname, DIST_DIR / "CNAME")

    meta = data["meta"]
    stats = meta["stats"]

    def render(tpl, name, ctx):
        out = env.get_template(tpl).render(**ctx)
        # 生成静态文件前清理模板空白，避免批量产物出现无意义的行尾空格。
        out = "\n".join(line.rstrip() for line in out.splitlines()) + "\n"
        p = DIST_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")
        if name == "audit/index.html":
            root_page = ROOT / name
            root_page.parent.mkdir(parents=True, exist_ok=True)
            root_page.write_text(out, encoding="utf-8")

    # ---------- 首页 ----------
    render("index.html", "index.html", {
        **page_ctx(data, "home", ""),
        "stats": stats,
        "cats": meta["categories"],
    })
    # ---------- 数据审计台 ----------
    render("audit.html", "audit/index.html", page_ctx(data, "audit", ".."))

    # ---------- 怪物 ----------
    mobs = data["monsters"]
    render("category.html", "mobs/index.html", {
        **page_ctx(data, "mobs", ".."),
        "title": "怪物图鉴",
        "desc": f"共 {len(mobs)} 种怪物, 按分类整理",
        "groups": _mob_groups(mobs),
        "kind": "mob",
    })
    for m in mobs:
        render("detail.html", f"mobs/{m['id']}.html", {
            **page_ctx(data, "mobs", ".."),
            "kind": "mob",
            "name": m["name"],
            "crumbs": [("怪物图鉴", "mobs/index.html"), (m["category"], None)],
            **mob_cards(m),
        })

    # ---------- 物品 ----------
    items = data["items"]
    render("category.html", "items/index.html", {
        **page_ctx(data, "items", ".."),
        "title": "物品大全",
        "desc": f"共 {len(items)} 件物品, 按类型分类",
        "groups": _group_by(items, "category"),
        "kind": "item",
    })
    for it in items:
        render("detail.html", f"items/{it['id']}.html", {
            **page_ctx(data, "items", ".."),
            "kind": "item",
            "name": it["name"],
            "crumbs": [("物品大全", "items/index.html"), (it["category"], None)],
            "item": it,
            "props": item_props(it),
        })

    # ---------- 技能 ----------
    skills = data["skills"]
    render("category.html", "skills/index.html", {
        **page_ctx(data, "skills", ".."),
        "title": "技能资料",
        "desc": f"共 {len(skills)} 项技能, 按职业分类",
        "groups": _group_by(skills, "class"),
        "kind": "skill",
    })
    for sk in skills:
        render("detail.html", f"skills/{sk['id']}.html", {
            **page_ctx(data, "skills", ".."),
            "kind": "skill",
            "name": sk["name"],
            "crumbs": [("技能资料", "skills/index.html"), (sk["class"], None)],
            "skill": sk,
            "desc_lines": (sk.get("description") or "").split("\n"),
        })

    # ---------- 任务 ----------
    missions = data["missions"]
    render("category.html", "missions/index.html", {
        **page_ctx(data, "missions", ".."),
        "title": "任务攻略",
        "desc": f"共 {len(missions)} 个任务, 按任务类型分类",
        "groups": _group_by(missions, "category"),
        "kind": "mission",
    })
    for mi in missions:
        render("detail.html", f"missions/{mi['id']}.html", {
            **page_ctx(data, "missions", ".."),
            "kind": "mission",
            "name": mi.get("title", mi["id"]),
            "crumbs": [("任务攻略", "missions/index.html"), (mi["category"], None)],
            "mission": mi,
        })

    # ---------- 地图 ----------
    render("maps.html", "maps/index.html", maps_ctx(data))


def _group_by(items, key):
    """按字段分组, 保持出现顺序。"""
    groups = []
    seen = []
    for it in items:
        k = it.get(key) or "未分类"
        if k not in seen:
            seen.append(k)
            groups.append({"name": k, "items": []})
        groups[seen.index(k)]["items"].append(it)
    return groups


# 怪物目录置顶的跨区域分类(召唤兽 / 城防守卫), 其余分组保持数据顺序。
FEATURED_MOB_CATEGORIES = ("召唤类", "守卫类")


def _mob_groups(mobs):
    """怪物目录分组: 召唤类/守卫类置顶, 其余保持数据出现顺序。"""
    groups = _group_by(mobs, "category")
    rank = {name: i for i, name in enumerate(FEATURED_MOB_CATEGORIES)}
    return sorted(groups, key=lambda g: rank.get(g["name"], len(rank)))


# ---------------------------------------------------------------------------
# 命令入口
# ---------------------------------------------------------------------------

def maps_ctx(data):
    """地图页上下文：全服 627 张地图按分类成套展示，并标注每条通道的两端坐标。"""
    doc = data["maps"]
    if isinstance(doc, list):          # 兼容旧结构（仅 3 个图集卡片）
        return {**page_ctx(data, "maps", ".."),
                "title": "地图资料", "desc": "传奇3 迷宫与世界地图资料",
                "groups": [{"name": "地图", "items": doc}], "stats": None,
                "exportedAt": ""}
    return {**page_ctx(data, "maps", ".."),
            "title": "地图资料",
            "desc": "全服地图总览：按城镇与副本成套归类，逐条标注从哪张图怎么走到哪张图",
            "groups": doc.get("groups", []),
            "stats": doc.get("stats"),
            "exportedAt": doc.get("exportedAt", "")}


# 构建后需要同步回仓库根的产物（根目录页面才是 GitHub Pages 的部署对象，
# dist/ 仅在 .gitignore 中）。地图页体量大，必须随数据重建，否则会与
# data/maps.json 脱节。
SYNC_TO_ROOT = ("maps/index.html", "static/css/style.css")


def cmd_build():
    data = load_data()
    env = build_env()
    render_all(data, env)
    n = sum(1 for _ in (DIST_DIR / "images").rglob("*") if _.is_file())
    print(f"[build] 完成: dist/ 共 {n} 张图片")
    for rel in SYNC_TO_ROOT:
        src, dst = DIST_DIR / rel, ROOT / rel
        if not src.is_file():
            print(f"[build] [WARN] 缺少产物 {rel}，未同步")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"[build] 已同步到根目录: {rel}")
    print("[build] 页面清单:")
    for p in sorted(DIST_DIR.rglob("*.html")):
        print(f"  {p.relative_to(DIST_DIR)}")


def cmd_serve(port=5000):
    """Flask 动态预览(读 JSON + 模板, 不依赖 dist)。"""
    from flask import Flask, abort, jsonify, request, send_from_directory

    data = load_data()
    env = build_env()
    app = Flask(__name__)

    def read_local_workspace():
        if not LOCAL_WORKSPACE_PATH.is_file():
            return {"id": "workspace", "revision": 0, "drafts": {}, "matches": {}, "events": []}
        try:
            value = json.loads(LOCAL_WORKSPACE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("本地工作区文件无法读取或 JSON 格式错误。") from exc
        if (not isinstance(value, dict) or value.get("id") != "workspace"
                or not isinstance(value.get("revision"), int)
                or not isinstance(value.get("drafts"), dict)
                or not isinstance(value.get("matches"), dict)
                or not isinstance(value.get("events"), list)):
            raise ValueError("本地工作区文件结构不正确。")
        return value

    def write_local_workspace(value):
        if (not isinstance(value, dict) or value.get("id") != "workspace"
                or not isinstance(value.get("revision"), int)
                or not isinstance(value.get("drafts"), dict)
                or not isinstance(value.get("matches"), dict)
                or not isinstance(value.get("events"), list)):
            abort(400, description="工作区结构无效。")
        LOCAL_WORKSPACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = LOCAL_WORKSPACE_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, LOCAL_WORKSPACE_PATH)

    @app.get("/api/workspace")
    def get_workspace():
        try:
            with LOCAL_WORKSPACE_LOCK:
                return jsonify(read_local_workspace())
        except ValueError as exc:
            abort(500, description=str(exc))

    @app.put("/api/workspace")
    def put_workspace():
        value = request.get_json(silent=True)
        with LOCAL_WORKSPACE_LOCK:
            try:
                current = read_local_workspace()
            except ValueError as exc:
                abort(500, description=str(exc))
            expected = request.headers.get("If-Match-Revision")
            if expected is not None and expected != str(current["revision"]):
                return jsonify({"error": "工作区已在其他页面更新，请刷新后重试。", "revision": current["revision"]}), 409
            write_local_workspace(value)
        return jsonify(value)

    def render_named(tpl, name, ctx):
        return env.get_template(tpl).render(**ctx)

    def find(data_list, id_):
        if id_.endswith(".html"):
            id_ = id_[:-5]
        for x in data_list:
            if x["id"] == id_:
                return x
        return None

    @app.get("/")
    @app.get("/index.html")
    def index():
        return render_named("index.html", "index", {
            **page_ctx(data, "home", ""),
            "stats": data["meta"]["stats"],
            "cats": data["meta"]["categories"],
        })

    @app.get("/mobs/")
    @app.get("/mobs/index.html")
    def mobs_list():
        return render_named("category.html", "mobs", {
            **page_ctx(data, "mobs", ".."),
            "title": "怪物图鉴", "desc": f"共 {len(data['monsters'])} 种怪物, 按分类整理",
            "groups": _mob_groups(data["monsters"]), "kind": "mob",
        })

    @app.get("/mobs/<id_>")
    def mob_detail(id_):
        m = find(data["monsters"], id_)
        if not m:
            abort(404)
        return render_named("detail.html", "mob", {
            **page_ctx(data, "mobs", ".."),
            "kind": "mob", "name": m["name"],
            "crumbs": [("怪物图鉴", "mobs/"), (m["category"], None)],
            **mob_cards(m),
        })

    @app.get("/items/")
    @app.get("/items/index.html")
    def items_list():
        return render_named("category.html", "items", {
            **page_ctx(data, "items", ".."),
            "title": "物品大全", "desc": f"共 {len(data['items'])} 件物品",
            "groups": _group_by(data["items"], "category"), "kind": "item",
        })

    @app.get("/items/<id_>")
    def item_detail(id_):
        it = find(data["items"], id_)
        if not it:
            abort(404)
        return render_named("detail.html", "item", {
            **page_ctx(data, "items", ".."),
            "kind": "item", "name": it["name"],
            "crumbs": [("物品大全", "items/"), (it["category"], None)],
            "item": it, "props": item_props(it),
        })

    @app.get("/skills/")
    @app.get("/skills/index.html")
    def skills_list():
        return render_named("category.html", "skills", {
            **page_ctx(data, "skills", ".."),
            "title": "技能资料", "desc": f"共 {len(data['skills'])} 项技能",
            "groups": _group_by(data["skills"], "class"), "kind": "skill",
        })

    @app.get("/skills/<id_>")
    def skill_detail(id_):
        sk = find(data["skills"], id_)
        if not sk:
            abort(404)
        return render_named("detail.html", "skill", {
            **page_ctx(data, "skills", ".."),
            "kind": "skill", "name": sk["name"],
            "crumbs": [("技能资料", "skills/"), (sk["class"], None)],
            "skill": sk, "desc_lines": (sk.get("description") or "").split("\n"),
        })

    @app.get("/missions/")
    @app.get("/missions/index.html")
    def missions_list():
        return render_named("category.html", "missions", {
            **page_ctx(data, "missions", ".."),
            "title": "任务攻略", "desc": f"共 {len(data['missions'])} 个任务",
            "groups": _group_by(data["missions"], "category"), "kind": "mission",
        })

    @app.get("/missions/<id_>")
    def mission_detail(id_):
        mi = find(data["missions"], id_)
        if not mi:
            abort(404)
        return render_named("detail.html", "mission", {
            **page_ctx(data, "missions", ".."),
            "kind": "mission", "name": mi.get("title", mi["id"]),
            "crumbs": [("任务攻略", "missions/"), (mi["category"], None)],
            "mission": mi,
        })

    @app.get("/maps/")
    @app.get("/maps/index.html")
    def maps_list():
        return render_named("maps.html", "maps", maps_ctx(data))

    @app.get("/audit/")
    @app.get("/audit/index.html")
    def audit_page():
        return render_named("audit.html", "audit", page_ctx(data, "audit", ".."))

    @app.get("/data/<path:path>")
    def data_files(path):
        return send_from_directory(str(DATA_DIR), path)
    @app.get("/images/<path:path>")
    def images(path):
        return send_from_directory(str(ROOT / "images"), path)

    @app.get("/static/<path:path>")
    def static_files(path):
        return send_from_directory(str(STATIC_DIR), path)

    print(f"[serve] http://0.0.0.0:{port} (loopback + LAN)")
    app.run(host="0.0.0.0", port=port, debug=False)


def main():
    args = sys.argv[1:]
    if args and args[0] == "build":
        cmd_build()
        return
    if args and args[0] not in {"serve", "--help", "-h"}:
        print("用法: python app.py [serve [端口] | build]")
        sys.exit(2)
    if args and args[0] in {"--help", "-h"}:
        print("用法: python app.py [serve [端口] | build]\n默认命令启动本地动态工作站。")
        return
    port = int(args[1]) if len(args) > 1 else 5000
    cmd_serve(port)


if __name__ == "__main__":
    main()
