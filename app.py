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
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TPL_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

# 导航结构(与 data/meta.json 一致)
NAV = [
    ("首页", "index.html", "home"),
    ("怪物图鉴", "mobs/index.html", "mobs"),
    ("物品大全", "items/index.html", "items"),
    ("技能资料", "skills/index.html", "skills"),
    ("任务攻略", "missions/index.html", "missions"),
    ("地图资料", "maps/index.html", "maps"),
]


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_data():
    """读取全部 data/*.json, 为缺失 id 的数据补稳定 id。"""
    out = {}
    for name in ("monsters", "items", "skills", "missions", "maps", "meta"):
        p = DATA_DIR / f"{name}.json"
        out[name] = json.loads(p.read_text(encoding="utf-8"))
    # 详情页 URL 依赖稳定 id: 缺失时按数据顺序补 {type}-{index}
    id_keys = {"monsters": "mob", "items": "item", "skills": "skill",
               "missions": "mission", "maps": "map"}
    for name, prefix in id_keys.items():
        for i, it in enumerate(out[name]):
            it.setdefault("id", f"{prefix}-{i}")
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
    base = {"id", "name", "category", "image", "description"}
    props = [(k, v) for k, v in item.items() if k not in base and v not in ("", "-", None)]
    return props


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render_all(data, env):
    """渲染全部页面到 DIST_DIR。"""
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    # 复制静态资源
    shutil.copytree(ROOT / "images", DIST_DIR / "images")
    shutil.copytree(STATIC_DIR, DIST_DIR / "static")
    # 首页需要的 CNAME 由仓库根保留, dist 不需要

    meta = data["meta"]
    stats = meta["stats"]

    def render(tpl, name, ctx):
        out = env.get_template(tpl).render(**ctx)
        p = DIST_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")

    # ---------- 首页 ----------
    render("index.html", "index.html", {
        **page_ctx(data, "home", ""),
        "stats": stats,
        "cats": meta["categories"],
    })

    # ---------- 怪物 ----------
    mobs = data["monsters"]
    render("category.html", "mobs/index.html", {
        **page_ctx(data, "mobs", ".."),
        "title": "怪物图鉴",
        "desc": f"共 {len(mobs)} 种怪物, 按出没区域分类",
        "groups": _group_by(mobs, "category"),
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
    maps = data["maps"]
    render("category.html", "maps/index.html", {
        **page_ctx(data, "maps", ".."),
        "title": "地图资料",
        "desc": "传奇3 迷宫与世界地图资料",
        "groups": [{"name": "地图", "items": maps}],
        "kind": "map",
    })


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


# ---------------------------------------------------------------------------
# 命令入口
# ---------------------------------------------------------------------------

def cmd_build():
    data = load_data()
    env = build_env()
    render_all(data, env)
    n = sum(1 for _ in (DIST_DIR / "images").rglob("*") if _.is_file())
    print(f"[build] 完成: dist/ 共 {n} 张图片")
    print("[build] 页面清单:")
    for p in sorted(DIST_DIR.rglob("*.html")):
        print(f"  {p.relative_to(DIST_DIR)}")


def cmd_serve(port=5000):
    """Flask 动态预览(读 JSON + 模板, 不依赖 dist)。"""
    from flask import Flask, abort, send_from_directory

    data = load_data()
    env = build_env()
    app = Flask(__name__)

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
    def index():
        return render_named("index.html", "index", {
            **page_ctx(data, "home", ""),
            "stats": data["meta"]["stats"],
            "cats": data["meta"]["categories"],
        })

    @app.get("/mobs/")
    def mobs_list():
        return render_named("category.html", "mobs", {
            **page_ctx(data, "mobs", ".."),
            "title": "怪物图鉴", "desc": f"共 {len(data['monsters'])} 种怪物",
            "groups": _group_by(data["monsters"], "category"), "kind": "mob",
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
    def maps_list():
        return render_named("category.html", "maps", {
            **page_ctx(data, "maps", ".."),
            "title": "地图资料", "desc": "传奇3 迷宫与世界地图资料",
            "groups": [{"name": "地图", "items": data["maps"]}], "kind": "map",
        })

    @app.get("/images/<path:path>")
    def images(path):
        return send_from_directory(str(ROOT / "images"), path)

    @app.get("/static/<path:path>")
    def static_files(path):
        return send_from_directory(str(STATIC_DIR), path)

    print(f"[serve] http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "build"
    if cmd == "build":
        cmd_build()
    elif cmd == "serve":
        port = int(args[1]) if len(args) > 1 else 5000
        cmd_serve(port)
    else:
        print("用法: python app.py [build|serve [端口]]")
        sys.exit(1)


if __name__ == "__main__":
    main()
