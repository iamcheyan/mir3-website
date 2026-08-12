#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传奇3 资料站 · HTML 内容提取器
================================
解析 17173 传奇3 镜像站的全部 42 个 htm 页面, 提取结构化数据到 data/*.json。

用法:
    python tools/extract.py

产物:
    data/monsters.json   怪物图鉴 (分类/名字/图片/描述/属性)
    data/items.json      物品资料 (分类/名字/图片/描述/属性)
    data/skills.json     技能资料 (职业/名字/图片/描述/等级要求)
    data/missions.json   任务资料 (分类/章节/步骤表)
    data/maps.json       地图资料 (迷宫地图/世界地图/神舰地图)
    data/meta.json       全站分类与导航结构
"""

import json
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
# 允许从外部目录读原版 htm (如 /tmp/legacy_htm), 便于重构后重新提取
if os.environ.get("EXTRACT_SRC"):
    ROOT = Path(os.environ["EXTRACT_SRC"])
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def read_page(rel: str) -> str:
    """读取页面, 容错编码。"""
    p = ROOT / rel
    raw = p.read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def soup_of(rel: str) -> BeautifulSoup:
    """解析页面并剔除导航/脚本等无关内容。"""
    soup = BeautifulSoup(read_page(rel), "lxml")
    for tag in soup(["script", "style", "head", "object", "embed", "noscript", "iframe"]):
        tag.decompose()
    return soup


def clean_text(s: str) -> str:
    """去空白、去全角空格, 压缩多余空格。"""
    if s is None:
        return ""
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_attr_line(text: str) -> dict:
    """解析怪物属性红字行, 如:
    '生命：300　经验值：300 所在地图:比奇附近'
    '生命：2000　经验值：6550　属性：死系 所爆物品： 莲丸戒指 (战士戒指)'
    '生命：400,所在地图:毒蛇山谷,沙巴克周围'
    返回 {生命/经验值/属性/所在地图/可爆物品/可暴/所爆物品} 子集。
    """
    out = {}
    rest = text
    # 逐字段提取
    for key in ("生命", "经验值", "经验", "属性", "所在地图"):
        m = re.search(key + r"\s*[:：]\s*([^,\s，　]+)", rest)
        if m:
            out[key] = m.group(1)
            rest = rest.replace(m.group(0), " ", 1)
    # 掉落类: 可爆 / 可暴 / 所爆物品 / 爆出物品
    for key in ("可爆物品", "可暴物品", "所爆物品", "可爆", "可暴", "爆出物品", "爆出"):
        m = re.search(key + r"\s*[:：]?\s*([^\s]+.*)", rest)
        if m:
            out[key] = clean_text(m.group(1))
            break
    return out


def attr_num(v) -> str:
    """属性值统一转字符串, 空/'-' 保留原样。"""
    return v if v in (None, "") else str(v)


# ---------------------------------------------------------------------------
# 怪物
# ---------------------------------------------------------------------------

MOB_PAGES = [
    ("mob/mob1.htm", "一般怪物"),
    ("mob/mob2.htm", "毒蛇山谷"),
    ("mob/mob3.htm", "盟重"),
    ("mob/mob4.htm", "天然洞穴"),
    ("mob/mob5.htm", "银杏废矿"),
    ("mob/mob6.htm", "矿区"),
    ("mob/mob7.htm", "潘夜岛"),
    ("mob/mob8.htm", "沙漠绿洲"),
    ("mob/mob9.htm", "灌木林"),
    ("mob/mob10.htm", "失乐园"),
    ("mob/mob11.htm", "赤月山谷"),
    ("mob/mob12.htm", "蚂蚁洞"),
    ("mob/mob13.htm", "虫峡谷"),
    ("mob/mob14.htm", "罪孽洞穴"),
    ("mob/mob15.htm", "石阁庙"),
    ("mob/mob16.htm", "沃玛神殿"),
    ("mob/mob17.htm", "祖玛神殿"),
    ("mob/mob18.htm", "潘夜石窟"),
    ("mob/mob19.htm", "潘夜神殿"),
    ("mob/mob20.htm", "神舰"),
    ("mob/mob21.htm", "真天黑度"),
]

def extract_mobs():
    """怪物图鉴: 每页 = 分类, 页内多个怪物卡片(cc9933 表)。
    卡片行序列(各页结构不同, 按行累积):
      - 2td 图片行: td0 含怪物图(名字在内嵌黄底表或后续行), td1 白底描述
      - 1td 黄底行: 怪物名字(mob20/21 等)
      - 1td 灰底行: 属性数值 + 属性图标(mob20)
      - 1td 浅绿/白底行: 属性文本(生命/经验/所爆物品, mob20)
      - 2td 无图行: mob2 的 [白底名字, 白底描述]
    """
    monsters = []
    seen = set()
    for rel, cat in MOB_PAGES:
        soup = soup_of(rel)
        tables = [t for t in soup.find_all("table") if (t.get("bgcolor") or "").lower() == "#cc9933"]
        n = 0
        for t in tables:
            cur = None
            for tr in t.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue
                img_td = tds[0].find("img")
                img_src = img_td.get("src") if img_td else None
                # 图片行 → 新卡片 (排除灰底属性图标行)
                if (img_src and "mob" in img_src
                        and (tds[0].get("bgcolor") or "").lower() != "#666666"):
                    if cur and cur.get("name"):
                        n += _finish_monster(monsters, seen, cur, cat)
                    cur = {"name": "", "image": img_src, "description": "", "attrs": {}}
                    # 名字: td0 内嵌黄底表
                    nt = tds[0].find("table")
                    if nt:
                        nm = clean_text(nt.get_text(" ", strip=True))
                        if nm:
                            cur["name"] = nm
                    # 描述: 白底格(位置不定, 取最长) + 红色属性文本
                    best = ""
                    for td in tds[1:]:
                        if (td.get("bgcolor") or "").lower() == "#ffffff":
                            d = clean_text(td.get_text(" ", strip=True))
                            if len(d) > len(best):
                                best = d
                            for f in td.find_all("font", attrs={"color": re.compile("red", re.I)}):
                                cur["attrs"].update(parse_attr_line(clean_text(f.get_text(" ", strip=True))))
                    if best and not best.startswith("生命"):
                        cur["description"] = best
                    continue
                if cur is None:
                    continue
                if len(tds) == 1:
                    td = tds[0]
                    bg = (td.get("bgcolor") or "").lower()
                    txt = clean_text(td.get_text(" ", strip=True))
                    if bg == "#ffcc00" and txt and not cur["name"]:
                        cur["name"] = txt
                    elif bg.startswith("#666") and txt:
                        cur["attrs"]["属性数值"] = txt
                        cur["attrs"]["属性图标"] = [i.get("src") for i in td.find_all("img") if i.get("src")]
                    elif txt and txt != cur["name"] and len(txt) > len(cur["description"]):
                        # 无背景/浅色背景的单格描述行
                        cur["description"] = txt
                elif len(tds) >= 2:
                    # 无图 2td+ 行: 灰底属性数值 | 浅绿属性文本 | 白底/浅蓝描述
                    for td in tds:
                        bg = (td.get("bgcolor") or "").lower()
                        txt = clean_text(td.get_text(" ", strip=True))
                        if bg.startswith("#666") and txt:
                            cur["attrs"]["属性数值"] = txt
                            cur["attrs"]["属性图标"] = [i.get("src") for i in td.find_all("img") if i.get("src")]
                        elif bg == "#d6f4ec" and txt:
                            cur["attrs"].update(parse_attr_line(txt))
                        elif txt and txt != cur["name"] and len(txt) > len(cur["description"]):
                            cur["description"] = txt
            if cur and cur.get("name"):
                n += _finish_monster(monsters, seen, cur, cat)
        print(f"  [mob] {rel} ({cat}): {n} 只")
    return monsters


def _finish_monster(monsters, seen, cur, cat):
    """结算一张怪物卡片(去重、补 id), 返回新增数。"""
    key = (cur["name"], cur["image"])
    if key in seen:
        return 0
    seen.add(key)
    monsters.append({
        "id": f"mob-{len(monsters)}",
        "name": cur["name"],
        "category": cat,
        "image": cur["image"],
        "description": cur["description"],
        "attrs": cur["attrs"],
    })
    return 1


# ---------------------------------------------------------------------------
# 物品
# ---------------------------------------------------------------------------

ITEM_PAGES = {
    "item/item1.htm": "武器",
    "item/item2.htm": "盔甲",
    "item/item3.htm": "手镯",
    "item/item4.htm": "戒指",
    "item/item5.htm": "项链",
    "item/item6.htm": "套装道具",
    "item/item7.htm": "普通道具",
    "item/item8.htm": "任务道具",
    "item/item9.htm": "手套",
    "item/item10.htm": "鞋子",
    "item/item11.htm": "头盔",
    "item/item12.htm": "特殊饰品",
}


def _item_from_tr(tr, headers):
    """把物品表格的一行转成 dict, 返回 (name, dict) 或 None。"""
    tds = tr.find_all("td")
    if len(tds) < 2:
        return None
    img = tds[0].find("img")
    src = img.get("src") if img else None
    name = clean_text(tds[1].get_text(" ", strip=True)) if len(tds) > 1 else ""
    # 中文名内排版空格清理(如 '记 忆 套 装')
    if name and re.search(r"[\u4e00-\u9fff]", name):
        name = re.sub(r"\s+", "", name)
    if not name:
        return None
    item = {"image": src, "name": name}
    for i, h in enumerate(headers):
        if i == 0 or i == 1:
            continue
        if i < len(tds):
            item[h] = clean_text(tds[i].get_text(" ", strip=True))
    return name, item


def _extract_item_table(t):
    """解析装备表(表头 道具/名称/重量/…): 返回 (items, headers)。"""
    rows = t.find_all("tr")
    if not rows:
        return [], []
    # 表头行: 含 '名称' 或 '道具'
    header_row = None
    for r in rows:
        txt = r.get_text(" ", strip=True)
        if ("名称" in txt or "道具" in txt) and "img" not in str(r)[:200].lower():
            header_row = r
            break
    if header_row is None:
        return [], []
    headers = [clean_text(td.get_text(" ", strip=True)) for td in header_row.find_all("td")]
    items = []
    started = False
    for r in rows:
        if r is header_row:
            started = True
            continue
        if not started:
            continue
        res = _item_from_tr(r, headers)
        if res:
            items.append(res[1])
    return items, headers


def _extract_special_table(t):
    """解析普通道具/任务道具表(名称+描述, 图片在首格): 返回 (items, headers)。
    行结构: [空/图片格, 名称, 描述] 或 [名称, 描述]。
    """
    rows = t.find_all("tr")
    items = []
    for r in rows:
        tds = r.find_all("td")
        if len(tds) < 2:
            continue
        img = tds[0].find("img")
        src = img.get("src") if img else None
        # 首格可能为空(图片占位), 名称在第二格
        name = clean_text(tds[1].get_text(" ", strip=True)) if len(tds) > 1 else clean_text(tds[0].get_text(" ", strip=True))
        desc = clean_text(tds[-1].get_text(" ", strip=True))
        if not name:
            name = clean_text(tds[0].get_text(" ", strip=True))
        # 中文名内排版空格清理(如 '记 忆 套 装')
        if name and re.search(r"[\u4e00-\u9fff]", name):
            name = re.sub(r"\s+", "", name)
        if name and (src or desc):
            items.append({"image": src, "name": name, "描述": desc})
    return items, ["道具", "描述"]


def extract_items():
    items = []
    for rel, cat in ITEM_PAGES.items():
        soup = soup_of(rel)
        tables = soup.find_all("table")
        found = False
        # 装备页: 含表头 '名称'/'道具' 的多列表
        for t in tables:
            txt = t.get_text(" ", strip=True)
            if "名称" in txt or "道具" in txt:
                imgs = t.find_all("img")
                if len(imgs) < 2:
                    continue
                items_t, headers = _extract_item_table(t)
                if items_t:
                    for it in items_t:
                        it["category"] = cat
                        items.append(it)
                    found = True
                    break
        if not found:
            # 特殊页(普通/任务道具): 名称+描述表, 排除侧栏导航表
            NAV_WORDS = {"武器", "盔甲", "手套", "鞋子", "头盔", "手镯", "戒指", "项链",
                         "套装道具", "特殊饰品", "普通道具", "任务道具"}
            best = []
            for t in tables:
                imgs = t.find_all("img")
                if len(imgs) < 2:
                    continue
                items_t, headers = _extract_special_table(t)
                # 过滤导航表: 名字不在导航词里
                items_t = [it for it in items_t if it["name"] not in NAV_WORDS and it["name"] != "道具"]
                if len(items_t) > len(best):
                    best = items_t
            for it in best:
                it["category"] = cat
                items.append(it)
            if best:
                found = True
        print(f"  [item] {rel} ({cat}): {sum(1 for x in items if x['category']==cat)} 件")
    return items


# ---------------------------------------------------------------------------
# 技能
# ---------------------------------------------------------------------------

SKILL_PAGES = {
    "skill/skill.htm": "战士",
    "skill/2.htm": "法师",
    "skill/3.htm": "道士",
}


def extract_skills():
    skills = []
    for rel, job in SKILL_PAGES.items():
        soup = soup_of(rel)
        tables = [t for t in soup.find_all("table") if (t.get("bgcolor") or "").lower() == "#cc9933"]
        # 第 1 张是修炼方法说明, 其余为技能卡片
        for t in tables[1:]:
            trs = t.find_all("tr")
            cur_img = None
            cur_desc = ""
            for tr in trs:
                tds = tr.find_all("td")
                if not tds:
                    continue
                first = tds[0]
                # 名字行: 黄底且文字短。原版结构每两行一组:
                #   trN   = [图片 + 白底描述]   → 填充 cur_img / cur_desc
                #   trN+1 = [黄底名字]          → 此时 cur_img/cur_desc 正是本组的,
                #                                  立即用「当前名字」结算(不能结算上一个)
                if (first.get("bgcolor") or "").lower() == "#ffcc00":
                    nm = clean_text(first.get_text(" ", strip=True))
                    if nm and len(nm) <= 12:
                        if cur_img:
                            skills.append({
                                "id": f"skill-{job}-{nm}",
                                "name": nm,
                                "class": job,
                                "image": cur_img,
                                "description": cur_desc,
                            })
                        cur_img = None   # 本组已结算, 等待下一组图片行重新填充
                        cur_desc = ""
                        continue
                # 图片
                im = first.find("img")
                if im and im.get("src"):
                    cur_img = im.get("src")
                # 描述: 白底长文本
                for td in tds:
                    if (td.get("bgcolor") or "").lower() == "#ffffff":
                        txt = clean_text(td.get_text(" ", strip=True))
                        if len(txt) > len(cur_desc):
                            cur_desc = txt
        print(f"  [skill] {rel} ({job}): {sum(1 for x in skills if x['class']==job)} 个")
    return skills


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------

def _parse_mission_steps(table):
    """解析任务步骤表(顺序/NPC名字/任务内容)。返回步骤列表。"""
    rows = table.find_all("tr")
    steps = []
    for r in rows:
        tds = r.find_all("td")
        if len(tds) < 3:
            continue
        seq = clean_text(tds[0].get_text(" ", strip=True))
        npc = clean_text(tds[1].get_text(" ", strip=True))
        content = clean_text(tds[2].get_text(" ", strip=True))
        if not seq or not npc or not content:
            continue
        steps.append({"顺序": seq, "NPC": npc, "内容": content})
    return steps


def extract_missions():
    """任务: mission.htm(初级任务分职业) / mission1.htm(中级任务章节) / mission2.htm(技能学习) / wan.htm(万事通随机)。"""
    missions = []
    # --- mission.htm 初级任务 ---
    soup = soup_of("mission/mission.htm")
    tables = soup.find_all("table")
    # 三张初级任务表(战士/法师/道士), 表头 顺序/NPC/名字/任务内容
    job_names = ["战士", "法师", "道士"]
    idx = 0
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) >= 3 and "任务内容" in t.get_text(" ", strip=True) and "NPC" in t.get_text(" ", strip=True):
            if idx < len(job_names):
                job = job_names[idx]
                missions.append({
                    "id": f"mission-chuji-{job}",
                    "category": "初级任务",
                    "title": f"初级任务（{job}）",
                    "class": job,
                    "steps": _parse_mission_steps(t),
                })
                idx += 1
    print(f"  [mission] mission.htm: 初级任务 {idx} 个")
    # --- mission1.htm 中级任务章节 ---
    # 结构: 外层大 td 内按序 [标题(strong), 说明, 条件, 步骤表(顺序/NPC名字/任务内容), …]
    # 标题 strong 嵌在大表行内, 用文档序扫描: strong → pending 标题, 叶子步骤表 → 任务
    soup = soup_of("mission/mission1.htm")
    pending_title = None
    SKIP_TITLES = ("初级任务", "中级任务", "魔法技能", "万事通", "合作", "17173", "Copyright", "顺序", "NPC", "任务内容")
    for el in soup.descendants:
        if el.name == "strong":
            txt = clean_text(el.get_text(" ", strip=True))
            if (txt and len(txt) <= 20 and not txt.startswith("条件")
                    and not any(k in txt for k in SKIP_TITLES)):
                pending_title = txt
        elif el.name == "table":
            if el.find("table") is not None:
                continue  # 只处理叶子步骤表, 避免外层嵌套重复
            txt = clean_text(el.get_text(" ", strip=True))
            if "任务内容" in txt and "NPC" in txt and "顺序" in txt:
                steps = _parse_mission_steps(el)
                if steps:
                    title = pending_title or "中级任务"
                    missions.append({
                        "id": f"mission-zhongji-{title[:12]}",
                        "category": "中级任务",
                        "title": title,
                        "steps": steps,
                    })
    print(f"  [mission] mission1.htm: 中级任务章节 {sum(1 for m in missions if m['category']=='中级任务')} 个")
    # --- mission2.htm 魔法技能学习任务 (职业段落文本) ---
    soup = soup_of("mission/mission2.htm")
    txt = soup.get_text("\n", strip=True)
    lines = [l for l in txt.split("\n") if l.strip()]
    # 按 '战 士：/法 师：/道 士：' 分段(冒号可有可无)
    jobs = {"战 士": "战士", "法 师": "法师", "道 士": "道士"}
    cur_job = None
    cur_lines = []
    for l in lines:
        matched = None
        for k, v in jobs.items():
            if l.startswith(k):
                matched = v
                break
        if matched:
            if cur_job and cur_lines:
                missions.append({
                    "id": f"mission-skill-{cur_job}",
                    "category": "魔法技能学习任务",
                    "title": f"{cur_job}技能学习任务",
                    "class": cur_job,
                    "content": "\n".join(cur_lines),
                })
            cur_job = matched
            cur_lines = []
        elif cur_job:
            cur_lines.append(l)
    if cur_job and cur_lines:
        missions.append({
            "id": f"mission-skill-{cur_job}",
            "category": "魔法技能学习任务",
            "title": f"{cur_job}技能学习任务",
            "class": cur_job,
            "content": "\n".join(cur_lines),
        })
    print(f"  [mission] mission2.htm: 技能学习任务 {sum(1 for m in missions if m['category']=='魔法技能学习任务')} 个")
    # --- wan.htm 万事通随机任务 ---
    soup = soup_of("mission/wan.htm")
    tables = soup.find_all("table")
    # 区域表: 第一个格是 '比奇：/银杏：/…', 表头 npc/坐标/条件/奖励
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 3:
            continue
        txt = t.get_text(" ", strip=True)
        if not ("任务条件" in txt or "npc" in txt.lower() or "奖励" in txt):
            continue
        first_cell = clean_text(rows[0].find_all("td")[0].get_text(" ", strip=True)) if rows[0].find_all("td") else ""
        if not first_cell:
            continue
        # 区域名: 首格可能是 '比奇： npc' 或 '道馆'
        region = re.split(r"[：:]", first_cell)[0].strip()
        region = region.replace(" npc", "").strip()
        if len(region) > 8:
            continue
        # 表头行定位
        hdr = None
        for r in rows:
            rt = clean_text(r.get_text(" ", strip=True))
            if "npc" in rt.lower() or "坐标" in rt or "任务条件" in rt or "奖励" in rt:
                hdr = r
                break
        if hdr is None:
            continue
        hdrs = [clean_text(td.get_text(" ", strip=True)) for td in hdr.find_all("td")]
        quests = []
        started = False
        for r in rows:
            if r is hdr:
                started = True
                continue
            if not started:
                continue
            tds = r.find_all("td")
            if len(tds) < 3:
                continue
            npc = clean_text(tds[0].get_text(" ", strip=True))
            coords = clean_text(tds[1].get_text(" ", strip=True)) if len(tds) > 1 else ""
            cond = clean_text(tds[2].get_text(" ", strip=True)) if len(tds) > 2 else ""
            reward = clean_text(tds[3].get_text(" ", strip=True)) if len(tds) > 3 else ""
            if not npc:
                continue
            quests.append({"npc": npc, "坐标": coords, "条件": cond, "奖励": reward})
        if quests:
            missions.append({
                "id": f"mission-wanshitong-{region}",
                "category": "万事通随机任务",
                "title": f"万事通随机任务（{region}）",
                "region": region,
                "quests": quests,
            })
    print(f"  [mission] wan.htm: 万事通区域 {sum(1 for m in missions if m['category']=='万事通随机任务')} 个")
    return missions


# ---------------------------------------------------------------------------
# 地图
# ---------------------------------------------------------------------------

def extract_maps():
    maps = []
    # map.htm: 迷宫地图 + 世界地图
    soup = soup_of("map/map.htm")
    tables = soup.find_all("table")
    # 迷宫地图: 含 '东部石矿' 链接的表格; 世界地图: mainmap.jpg
    for t in tables:
        links = [(clean_text(a.get_text(" ", strip=True)), a.get("href")) for a in t.find_all("a") if a.get("href")]
        imgs = [i.get("src") for i in t.find_all("img") if i.get("src")]
        txt = t.get_text(" ", strip=True)
        if "迷宫地图" in txt and "世界地图" in txt:
            # CDN 链接重写为本地 images/ 路径
            def _local(h):
                return h.replace("//images.17173cdn.com/mir3/images/", "../images/")
            maze = [{"name": n, "image": _local(h)} for n, h in links if h and "mgmap" in h]
            world = [i for i in imgs if "mainmap" in i]
            if maze:
                maps.append({
                    "id": "map-maze",
                    "title": "迷宫地图",
                    "category": "地图",
                    "areas": maze,
                })
            if world:
                maps.append({
                    "id": "map-world",
                    "title": "世界地图",
                    "category": "地图",
                    "areas": [{"name": "世界地图", "image": world[0]}],
                })
    print(f"  [map] map.htm: 迷宫 + 世界")
    # sj.htm: 神舰地图
    soup = soup_of("map/sj.htm")
    imgs = [i.get("src") for i in soup.find_all("img") if i.get("src") and "mgmap" in i.get("src")]
    titles = []
    for t in soup.find_all("table"):
        for td in t.find_all("td"):
            txt = clean_text(td.get_text(" ", strip=True))
            if "神舰" in txt and "地图" in txt and len(txt) < 30:
                titles.append(txt)
    if imgs:
        maps.append({
            "id": "map-sj",
            "title": "神舰地图",
            "category": "地图",
            "areas": [{"name": titles[i].replace("::::", "").strip(" ：!！") if i < len(titles) else f"神舰地图{i+1}", "image": imgs[i]} for i in range(len(imgs))],
        })
    print(f"  [map] sj.htm: 神舰地图 {len(imgs)} 张")
    return maps


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------

def build_meta(monsters, items, skills, missions, maps):
    mob_cats = []
    for m in monsters:
        if m["category"] not in mob_cats:
            mob_cats.append(m["category"])
    item_cats = []
    for i in items:
        if i["category"] not in item_cats:
            item_cats.append(i["category"])
    return {
        "site": {
            "name": "传奇3 · 资料站",
            "domain": "https://mir3.iamcheyan.com",
            "copyright": "数据与图片版权归 17173.com 所有 · 本镜像仅供个人研究使用",
        },
        "nav": [
            {"name": "首页", "url": "index.html"},
            {"name": "怪物图鉴", "url": "mobs.html"},
            {"name": "物品大全", "url": "items.html"},
            {"name": "技能资料", "url": "skills.html"},
            {"name": "任务攻略", "url": "missions.html"},
            {"name": "地图资料", "url": "maps.html"},
        ],
        "categories": {
            "mobs": mob_cats,
            "items": item_cats,
            "skills": ["战士", "法师", "道士"],
            "missions": ["初级任务", "中级任务", "魔法技能学习任务", "万事通随机任务"],
            "maps": ["地图"],
        },
        "stats": {
            "monsters": len(monsters),
            "items": len(items),
            "skills": len(skills),
            "missions": len(missions),
            "maps": len(maps),
        },
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("== 提取怪物 ==")
    monsters = extract_mobs()
    print("== 提取物品 ==")
    items = extract_items()
    print("== 提取技能 ==")
    skills = extract_skills()
    print("== 提取任务 ==")
    missions = extract_missions()
    print("== 提取地图 ==")
    maps = extract_maps()
    print("== 构建 meta ==")
    meta = build_meta(monsters, items, skills, missions, maps)

    (DATA_DIR / "monsters.json").write_text(
        json.dumps(monsters, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / "skills.json").write_text(
        json.dumps(skills, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / "missions.json").write_text(
        json.dumps(missions, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / "maps.json").write_text(
        json.dumps(maps, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n== 汇总 ==")
    print(f"怪物 {len(monsters)} | 物品 {len(items)} | 技能 {len(skills)} | 任务 {len(missions)} | 地图 {len(maps)}")
    print("输出:", DATA_DIR)


if __name__ == "__main__":
    main()
