# 传奇3 · 资料站

17173 传奇3 资料站(`mir3.17173.com`)重构版,全新风格的静态资料站,部署于 GitHub Pages:

- 线上地址:https://mir3.iamcheyan.com
- 源仓库:https://github.com/iamcheyan/mir3-website
- 数据与图片版权归 17173.com 所有,仅供个人研究使用

## 新架构

```
原 42 个 htm 页面(已删除)
        │  解析
        ▼
data/*.json ──┐  结构化数据(怪物/物品/技能/任务/地图/站点元信息)
tools/extract.py
              │  渲染
              ▼
app.py + templates/* + static/css/style.css (Flask + Jinja2)
              │  python app.py build
              ▼
dist/ ──同步──▶ 仓库根(静态站, GitHub Pages 部署)
```

- **数据层**:`tools/extract.py` 把原站 HTML 解析为 JSON,存于 `data/`
- **渲染层**:`app.py` 读 JSON → Jinja2 模板 → 输出静态 HTML
- **部署层**:`dist/` 为构建产物,内容同步到仓库根(页面在 `mobs/ items/ skills/ missions/ maps/` 子目录,图片用 `images/` 相对路径)

## 内容统计

| 分类 | 数量 | 说明 |
|------|------|------|
| 怪物 | 154 | 21 个区域分类 |
| 物品 | 371 | 12 个类型(武器/盔甲/手镯/戒指/项链/套装/普通道具/任务道具等) |
| 技能 | 61 | 战士 13 / 法师 26 / 道士 22 |
| 任务 | 24 | 初级 3 / 中级 9 / 技能学习 3 / 万事通随机 9 |
| 地图 | 3 | 迷宫地图 17 区域 / 世界地图 / 神舰 4 层 |

## 构建与维护

```bash
# 1. 重新提取数据(原 htm 已删除, 无需重复执行; 如需重抓镜像按旧 README 方法)
python tools/extract.py          # 生成 data/*.json

# 2. 构建静态站
python app.py build              # 生成 dist/

# 3. 本地预览(可选, Flask 动态渲染)
python app.py serve 5000

# 4. 部署: 同步 dist 内容到仓库根并推送
cp -r dist/index.html dist/mobs dist/items dist/skills dist/missions dist/maps dist/static ./
git add -A && git commit -m "..." && git push origin main
```

Python 环境:`/home/tetsuya/mir3-venv/bin/python3`(依赖 flask / jinja2 / beautifulsoup4 / lxml)。

## 页面结构

| 页面 | 路径 |
|------|------|
| 首页(统计 + 分类入口 + 搜索) | `index.html` |
| 怪物图鉴(按区域分组 + 页内搜索) | `mobs/index.html`, 详情 `mobs/mob-N.html` |
| 物品大全 | `items/index.html`, 详情 `items/item-N.html` |
| 技能资料 | `skills/index.html`, 详情 `skills/skill-*.html` |
| 任务攻略 | `missions/index.html`, 详情 `missions/mission-*.html` |
| 地图资料 | `maps/index.html` |

## 图片路径方案

图片统一保留相对路径 `../images/...`:列表/详情页位于分类子目录(`mobs/`、`items/` 等),相对路径指向仓库根 `images/`(582 张本地化图片原样保留)。构建时 `app.py` 会把 `images/` 复制进 `dist/` 保证产物自包含;部署时直接用仓库根的 `images/`,不重复拷贝。

## 数据提取说明

原 42 个 htm 页面布局各异,解析器按实际结构处理:

- **怪物页**:每页一个区域分类,卡片 = 图片 + 名字 + 描述 + 可选红字属性(生命/经验/所在地图/所爆物品)或神舰页的灰底能力数值
- **物品页**:装备页为多列表格(道具/名称/重量/耐久/破坏/魔法/等级等),普通/任务道具页为名称+描述
- **技能页**:每职业一页,卡片 = 图片 + 名字 + 描述(含等级修炼要求)
- **任务页**:初级任务按职业分表,中级任务按章节(标题+步骤表),技能学习任务为职业文本,万事通为区域随机任务表(NPC/坐标/条件/奖励)
- **地图页**:迷宫地图(区域链接图)、世界地图、神舰 4 层

## 镜像方法(历史)

原站 HTML 在 `mir3.17173.com`,图片在 `i.17173cdn.com`(EdgeOne 反爬,需浏览器 cookie + 间隔 ≥3s 抓取)。细节见 git 历史 `ce8fe01` 前的 README。

## 已知限制

- 怪物属性字段不完整:原站仅部分怪物页提供红字属性(生命/经验/所在地图),未提供的页(如 mob8 沙漠绿洲)字段为空
- 神舰怪物的"能力数值"为 10 张属性图标对应数值,图标含义原站未标注文字
- 技能描述中的等级要求为自由文本(未结构化),展示在详情页原文中
- 万事通任务部分条件/奖励含原站排版噪声(如 `**` 打码),未逐条清洗
