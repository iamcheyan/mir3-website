# Goal: 传奇3最终资料站数据审计台、可编辑主数据与 Zircon 名称同步

> 执行模型：`openai-codex/gpt-6-luna`。新 OMP session；不得续用其他 goal/session。
> 规范仓库：`/home/tetsuya/development/mir3-website`。在该规范 checkout 的专用 feature branch 工作。
> 用户授权：完成此目标所需的网站、代码、数据结构、测试、构建、提交和推送均可执行；按本文中的生产数据/凭据安全边界执行。

## 0. 目标与用户意图

将 `https://mir3.iamcheyan.com`（`iamcheyan/mir3-website`，GitHub Pages 静态站）升级为传奇3最终公开资料站和数据审计/编辑入口。网站资料代表游戏最终应呈现给玩家的标准数据；需要把网站标准数据与 Zircon 当前数据、当前显示中文、内部英文名/Index、资源身份和既有研究目标结果逐条对照。首要价值是暴露错误翻译及错误实体关联（例：Oma/半兽人被显示成“祖玛”，Oma Warrior/半兽战士错误显示成“祖玛卫士”，而真正祖玛卫士是另一独立实体），**本任务是审计、编辑工作台和安全同步管线，不是擅自裁决或修复所有游戏数据**。

网站需从“每个怪物一个大卡片”转为清晰、密度适中的数据库式列表：固定表头，排序/筛选/搜索/分类，重点冲突高亮；每行可展开/打开详情，以并排方式呈现网站标准、Zircon 原始身份、当前游戏显示、图片/Shape、地图/坐标/刷新/掉落/任务引用、证据和结论。桌面端以可横向比较的大表为主，手机端保持可用（行详情/字段分组，而非把宽表压成难读的小字）。保持资料站精致的游戏档案视觉，但整体不再是单调卡片网格。

更关键的是，设计一个**单一编辑真源 + 确定性导出**：网站里的编辑结果必须可以按 Zircon 当前消费者所用 JSON 合同导出，并可验证/应用到游戏翻译文件，使以后修正名称后不必在网站和游戏里各自再手调。当前游戏读取 `GodotClient/translations/db_names.json`，由 `GodotClient/Scripts/LocalizedName.cs` 按英文/描述字符串映射 `zh`/`ja`，缺项回退原文。复用既有结构，先验证实际合同和重复键风险；不要假设游戏已经按 Index 查表。若要解决同名/映射碰撞，提出并实现向后兼容策略及必要的测试，不要静默改变运行行为。

## 1. 先行规则与仓库

1. 开工先读本仓库 README、`refactor_goal.md`（只作历史上下文，不视为当前需求）、当前模板/CSS/JS/构建器、数据 schema；确认分支、remote、HEAD、状态。读取 `Mir3-Research/AGENTS.md`、`zircon/AGENTS.md` 中与数据安全/公开仓库/游戏 JSON 相关条款。尊重其他仓库已有 dirty changes，不清理/覆盖。
2. `mir3-website` 当前为干净 `main`，先在此规范 checkout 创建并推送 feature branch；goal 不得在 main 上长期开发，不得建旁路 clone/worktree。
3. 相关研究材料（先阅读，勿只看计数）：
   - `/home/tetsuya/development/Mir3-Research/docs/research/ei-ui-layout/artifacts/website-alignment-2026-09-26/`：`manifest.json`、`final-production-targets-20260926.json`、`production-apply-evidence-20260926.json`、各 monster/item/NPC/map/respawn/skill/mission manifest、verification/extension 文件。
   - `/home/tetsuya/development/Mir3-Research/docs/research/ei-ui-layout/artifacts/web-entity-audit-2026-09-26/`：`audit_summary.json`、`verification.json`、`external_sources.json`、`search_queries.json` 及 raw evidence。
   - `/home/tetsuya/development/Mir3-Research/docs/research/ei-ui-layout/artifacts/npc-monster-alignment-2026-09-25/` 和相关已完成分析文档。
   这些是有日期的快照，必须核对时间戳、来源 commit/hash 和当前 Zircon 数据；旧数据不能冒充当前生产状态。
4. 当前证据中 website alignment 统计（以文件实读为依据）：网站 monsters 154、skills 61；Zircon `MonsterInfo=434`、`MagicInfo=174`、`NPCInfo=294`、`MapInfo=627`、`RespawnInfo=2475`；网络审计总量 monsters 527、NPC 294、items 1402、skills 176、maps 472、respawns 2475、quests 62。它们是基线供核对，不是验收硬编码常量，也不代表所有结果已闭合。
5. `zircon` 工作树已有用户未提交文件，严格只读；不得 reset/checkout/clean/stash。不得改 `System.db`/`Users.db`/生产 server 数据，运行中服务绝不写 DB。只有用户另行批准后续数据变更 goal，才可实际删除/改游戏实体数据。

## 2. 必须实现的审计数据模型

在 website repo 内设计版本化、可校验、可确定性重建的 alignment master data（不要把网站的旧攻略 JSON 当作 Zircon 数据或反过来覆盖）。主键需要稳定且显式分类型；优先 `entity_type + zircon index`，网站 ID、内部名作为属性/辅助关联；不能仅用中文名或英文字符串作为实体主键。字段至少分为：

- `identity`: entity type、最终标准中文名（可含 ja/en）、网站 source ID/名称、Zircon Index、内部英文原名、当前中文显示名、实体/别名/版本信息。
- `resources`: 网站图/图标、Zircon resource filename/library/Shape/frame/face/icon，以及实际存在性和可视证据引用。
- `game_data`: 仅有来源支持的游戏属性（怪物等级/Boss、物品类型/属性、技能职业/属性、NPC 类型/功能、地图 filename/尺寸等）。
- `relations`: 地图/区域、NPC 坐标、怪物刷新（RespawnInfo/MapRegion、count/delay/坐标）、掉落、商店、任务交叉引用及对象 Index。
- `assessment`: 独立字段级状态 + overall status、理由、reviewer/时间、建议动作、证据 refs。必须区分正确、中文显示名错误、身份映射错误/两个实体交叉串错、图片错配、属性错误、地图/坐标/刷新/掉落错、双方冲突、website-only、Zircon-only-after-web-audit、旧版专属、待证据/待人工复核、production-applied、retain-current。
- `evidence`: 来源类型、相对路径或公开 URL、文件版本/commit/hash、记录/行/Index、采集时间、可验证摘要。公开产物禁止绝对私有路径、IP、凭据、私聊和未公开细节；私密操作日志不进公开仓库。

关键验收：可以清晰表示“两个实体都存在，但翻译/关联串错”；一条记录的 `Index`、英文名、当前显示中文、网站标准名不可混为一列；冲突必须关联双方记录并能从任一方发现。缺少证据时显示 pending，绝不根据名字相似、一次搜索失败或人工臆测自动判独有/直接修复。

## 3. 编辑界面与可持久化设计

- 建立“数据对照/数据健康”入口与分类表格：怪物、物品、技能、NPC、地图、刷新/生态、任务关联；表头明确显示“网站最终名 | Zircon Index | 游戏英文内部名 | 当前游戏中文 | 网站名称 | 资源身份 | 关系/属性差异 | 状态 | 建议动作”。按字段允许切换列、排序、全局搜索、状态/来源筛选，列表汇总真实计数且计数由当前 master 计算。
- 点行能看到可读的双侧详情与全部证据/关系；错误名称、cross-link 两方记录醒目，但用状态/图标/文字同时表达，不能只靠红绿颜色。
- 编辑操作必须能持久保存并有审计轨迹/版本冲突检测；多文件更新有校验及可恢复机制。不能把 GitHub token、写权限 token 或未认证 write API 放在浏览器、静态 JS、public JSON。
- 当前站是 GitHub Pages 静态站，没有假设存在写入后端。先探查现有托管/认证/Worker 资源，并在技术方案中确保生产写入安全。若可在现有 Cloudflare/Pages + Access 配置中安全部署 GitHub-backed admin/API，可实现并真实验证；后台凭据仅由服务端 secret 保存、Access 仅允许用户本人，写入带 SHA/冲突处理，不能公开访问写端。若尚无可用的授权资源/凭证，不能伪造持久化或留下开放写接口：完成可本地使用的审计/编辑体验和 deterministic JSON/patch 导入导出，并把线上管理发布的确切缺项写为 BLOCKED，保留静态公开页面安全可用。
- 不引入账号密码系统或未授权第三方依赖，不将网站公开页面变成修改仓库的匿名 API。

## 4. Zircon 同步合同

- 先审计 `GodotClient/translations/db_names.json` 全结构及 `LocalizedName.cs` 所有类别/key 读取方式、构建/热更新含义；记录当前行为测试。
- 提供确定性工具（运行两次输出逐字/哈希相同）从已审定 master 生成：①网站可读完整审计数据；②现有游戏兼容的 `db_names.json`（`items/monsters/npcs/magics/maps`, 内部 key -> `zh/ja`）。不得把审计字段塞进当前游戏 parser 不接受的对象。保留英文 fallback 语义和未审定现有翻译；仅从明确 `approved/corrected + export_enabled` 记录导出。拒绝重复键/Index 或 ambiguous internal name 并输出诊断，不准 last-write-wins。
- 导出过程默认 dry-run，报告新增/变更/删除候选；没有批准不得从游戏输出中实际删除数据。输出可用于明确审阅的 patch/文件及回滚旧文件方式；不直接写运行中 DB。
- 若 key-by-name 无法安全区分实体，优先提出最小兼容扩展（比如 `entity_type+Index` 可选覆盖、旧字符串 fallback）；仅在确有冲突证据、写了 migration/compat tests 并核对所有调用方后改 Zircon parser。所有对 Zircon 的写仅限定翻译映射代码/JSON；现存 untracked/modified 文件保持不动。
- 游戏 JSON 可生成的最终位置为 Zircon `GodotClient/translations/db_names.json`；变更需同时在 Zircon feature branch 完成、构建客户端并验证数据加载/正确查名。网站端必须保留 master 的审计字段和来源，游戏只接收运行时所需字段。

## 5. UI、技术质量和端到端验收

- 尊重现有 Flask/Jinja 静态构建，不为使用框架而迁移；添加必要的静态数据页/脚本即可。沿用公共站 SEO、相对路径、CNAME、可复现构建。
- `python app.py build` 生成的 dist/ 与仓库根部署页面一致；构建脚本必须检查 JSON schema/主键重复/来源及导出安全。避免构建时清除仓库源数据；读取原有 build 行为并加安全校验。
- 单元/集成测试：导入所有现存 manifests；校验实体数汇总、dangling relation、duplicated IDs/keys、unknown status、source refs、export compatibility 和稳定性；制作至少 Oma/半兽人/Oma Warrior/祖玛卫士两组明确冲突 fixtures，证明网页可同时指出标准名、英文名、当前错误中文及另一独立实体，且不会把这类数据自动“修复”。
- 构建、lint、测试、静态路由检查，浏览器真实验收：桌面 1280×800 或更宽，手机 390×844；各至少截图、console/page errors、横向溢出（table 可明确横向滚动容器）和关键交互测试。可用的浏览器工具按项目环境选用。
- 本地 HTTP 验证首页/旧资料页/对照表/详情/编辑导出；若需要部署线上，验证公开地址、GitHub Pages Actions/实际内容，不把本地通过说成线上完成。无 Cloudflare/Access 能力则声明 BLOCKED。
- 发布前做公开仓库敏感信息扫描；所有可公开 JSON/HTML 只含脱敏安全证据摘要。确认 `git diff --check`。

## 6. 分阶段提交、进度与完成标准

允许持续运行 20–30 小时。阶段完成不代表终态；必须把所有 acceptance items 做完或逐项证明 BLOCKED。按文件边界管理 website 与 Zircon 两仓；遵守各自 branch/remote/工作树边界。每个有意义的已验证阶段均 commit，并 push 对应 feature branch；提交前审查 staged diff，严禁把用户现有 dirty 文件带入提交。不得 force push。合并 main/发布生产在目标完成前先保持 feature branch，需进行正常 review/验收后再按 repo 流程合并。

终态前必须：
1. 实际 build/test/E2E 结果与精确命令；
2. 统计已纳入主表/缺证据/字段冲突/待人工确认实体数（脚本计算并对照导入数）；
3. GitHub commit/远端 SHA 与线上验证；
4. Zircon JSON 生成 diff、确定性、客户端编译与加载验证；
5. 生产数据库/怪物物品地图没有擅自删除或写入；
6. 告知保留/未解决风险及每项 BLOCKED 原因；
7. 完成状态只能用 `complete`，全部状态有硬性未解决阻碍用 `blocked`，仍在处理用 `working`，不得用阶段总结伪装完成。

终态通知用户并询问是否回收 tmux/session；没有用户明确同意，保持目标 session 和恢复入口，不 kill。
