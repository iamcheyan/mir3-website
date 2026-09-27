# 传奇3 · 资料站

17173 传奇3 资料站(`mir3.17173.com`)重构版,全新风格的静态资料站,部署于 GitHub Pages:

- 线上地址:由 GitHub Pages 仓库配置管理
- 源仓库:当前 GitHub 仓库
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

# 4. 本地可选同步 dist/ 到根目录,与 Pages workflow 的产物保持一致
cp -r dist/index.html dist/mobs dist/items dist/skills dist/missions dist/maps dist/audit dist/data dist/images dist/static ./
git add index.html mobs items skills missions maps audit data images static
git commit -m "..."
git push
```

Python 环境需要 Python 3、Flask、Jinja2、BeautifulSoup4 与 lxml。
`.github/workflows/pages.yml` 使用 GitHub Pages Actions artifact 部署 `dist/`，不是仓库根目录；`app.py build` 把 `data/alignment/` 写入产物，只有仓库提供 `CNAME` 时才会额外复制。推送 `main` 或当前功能分支自动部署；其他分支可通过 `workflow_dispatch` 明确触发。

## 数据审计台

`/audit/` 对照网站资料、当前 Zircon `System.db` 只读快照与研究证据。主数据为 `data/alignment/master.json` 清单及 `data/alignment/` 中带 SHA-256 的 JSON 分片；游戏实体以 `表名:Index` 作为身份键，网站记录以来源 ID 作为身份键。分片构建时限制单文件不超过 25 MiB，静态托管时浏览器逐片校验摘要与记录数。来源元数据会脱敏本地路径，主数据校验拒绝常见 Unix/Windows 本机绝对路径和私网 IP。

为降低公开仓库中不必要的身份暴露，发布元数据不再包含自定义域名/所有者标识；对齐记录中的个人域名链接已脱敏，来源标题与审计记录保留，相关外部链接不再点击打开。

### 生成和校验主数据

只从明确授权的只读 `SystemDbProbe` 导出和本地研究仓库生成；导入脚本不连接或修改 `System.db`：

```bash
python3 tools/import_alignment.py \\
  --system-snapshot "$SYSTEM_DB_READ_ONLY_EXPORT" \\
  --research "$MIR3_RESEARCH_CHECKOUT" \\
  --zircon "$ZIRCON_CHECKOUT" \\
  --db-names "$ZIRCON_CHECKOUT/GodotClient/translations/db_names.json"
python3 tools/alignment.py validate data/alignment/master.json
python3 -m unittest tests.test_alignment tests.test_catalog_matches tests.test_match_preview_catalog -v
node --test tests/alignment-workspace.test.mjs
python3 app.py build
```

游戏名称候选的既有“审批翻译候选”流程仍要求逐条确认身份、显示名、理由及导出开关；其导出不会直接写入 Zircon。

### 浏览器内人工匹配

- 网站来源条目（怪物、物品、技能、任务攻略、地图分组）提供同类型 Zircon 候选；可以切换到“仅看待匹配”队列。候选列表每页 48 条，按英文内部名、中文显示名、Index 或 `表名:Index` 身份键搜索，并显示实际 Zircon 缩略图。匹配行显示已选 Index 与身份键，支持重新选择和清除；任务攻略、地图分组支持多选。
- 选择立即事务写入当前浏览器 `mir3-alignment-workspace` IndexedDB，并仅在事务成功后显示已保存；不上传、不改公开主数据或 Zircon 仓库。工作区不会同步到其他设备；更换设备或清理站点数据前，请先导出工作区备份。
- “导出工作区”生成 v2 JSON，包含草稿、修改历史、匹配 ID 与稳定身份键。导入要求版本、主数据 SHA-256、字段、事件、类型和身份键全部通过校验；随后必须在自绘确认窗口再次确认替换，并显示当前/导入记录数。旧版或不兼容文件不会覆盖现有工作区。
- “导出游戏 db_names.json”使用随主数据保存、与 Zircon 当前 `GodotClient/translations/db_names.json` 对应的真实基线；只更新人工匹配且可一对一导出的怪物、物品、技能中文名，保留其它记录和 locale。将下载文件备份核对后，手动放到游戏仓库的 `GodotClient/translations/db_names.json`；网站不会写游戏文件。共用相同运行时名称键的多个 Index 必须全部逐一匹配且中文名一致，否则阻止导出。
- 任务攻略与地图分组是多对多关系，只写入“匹配清单”（含 `QuestInfo:Index` / `MapInfo:Index`），不会把攻略或集合标题冒充单个游戏任务/地图名称；每条人工选定关系会标记 `confirmation_status: "confirmed"`。
- 怪物/技能/地图预览按客户端资源索引生成。没有可解码客户端帧的候选显示“无小地图”/占位，而不会伪造缩略图。**物品图号已知存在较多错位**：缩略图忠实显示客户端当前 `ItemInfo.Image` 指向的 `Storeitems.Zl` 帧，只能辅助辨认，需结合英文名与 Index，不能单凭图片确认。缩略图从本地 Zircon 客户端资源生成，只提交轻量 WebP；更新时运行 `python tools/build_match_previews.py`（依赖本机 Zircon 与 `Mir3-Research/Tools/common/zlsdk.py` 只读资源），不会修改 Zircon。

### 本地工作区与发布边界

- 复核草稿、人工匹配和历史保存在当前浏览器 IndexedDB。`导出工作区`备份后，只有同一主数据摘要的 v2 文件可导入；导入会显式替换本浏览器当前工作区，不是跨设备同步或服务器备份；更换设备或清理站点数据前必须先备份。
- 公开主数据保持只读。浏览器工作区不会同步到服务器、其他浏览器或线上数据库。
- 现有发布资源中未发现受保护的在线编辑 API / Worker / 管理后台与获准写入凭据；因此生产在线编辑和 GitHub 自动写入处于 **BLOCKED**。启用前必须配置受 Cloudflare Access 保护的服务端写入端点、专用最小权限 GitHub App 凭据（仅由服务端保管）、受保护分支 / PR 审核流程及明确授权的审阅者；不得把令牌放进静态站点。
- 无线上写入端点前，只发布只读资料与浏览器本地工作区；不要把浏览器 IndexedDB 当作共享或服务器备份。

## 页面结构

| 页面 | 路径 |
|------|------|
| 首页(统计 + 分类入口 + 搜索) | `index.html` |
| 怪物图鉴(按区域分组 + 页内搜索) | `mobs/index.html`, 详情 `mobs/mob-N.html` |
| 物品大全 | `items/index.html`, 详情 `items/item-N.html` |
| 技能资料 | `skills/index.html`, 详情 `skills/skill-*.html` |
| 任务攻略 | `missions/index.html`, 详情 `missions/mission-*.html` |
| 地图资料 | `maps/index.html` |
| 数据审计与本地复核 | `audit/index.html` |

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
