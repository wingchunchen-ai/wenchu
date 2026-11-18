# 稳厨知识库原型：数据库怎么走

## 当前实现边界

正式知识 schema 是与旧演示数据隔离的本地 SQLite 原型，默认文件为 `knowledge_prototype.sqlite3`，可用环境变量 `WENCHU_FORMAL_KNOWLEDGE_DB` 或 `--db` 指定其他路径。它不接管 `厨房数据库.sqlite3`（旧菜谱演示库）或 `dish_knowledge.sqlite3`（旧 AI 分析/别名库）。迁移采用编号 SQL 和校验和；初始化、导入和状态检查可显式运行：

```bash
python3 knowledge_schema.py init
python3 knowledge_schema.py status
python3 import_legacy_demo.py --dry-run
python3 import_legacy_demo.py
```

`--dry-run` 会先确保目标 schema 已迁移到最新版本，但会回滚导入数据；确认预览后再省略该参数执行导入。也可指定独立目标库：

```bash
python3 import_legacy_demo.py --source /absolute/path/厨房数据库.sqlite3 \
  --db /absolute/path/knowledge_prototype.sqlite3 --dry-run
```

导入模块被 Python import 时没有写库副作用；只有显式运行 CLI 才初始化目标库并导入。若目标数据库有表却没有本 schema 的 `schema_migrations` 历史，迁移器会停止，不会接管或改表。已经执行的迁移文件不可改写；后续结构变化应增加编号迁移。没有自动审核任何演示内容。

## 旧 demo 导入结果

当前本地知识库已从旧 demo 做过一次只读、可重复的结构导入：8 个分类、12 道演示菜、12 个菜谱版本、61 个步骤、69 个去重后的食材原始词条、32 个去重后的锅具/工具词条、12 条单独待审的安全提示经验、85 条来源证据和 81 条导入台账映射。目标库当前通过 SQLite 完整性检查，外键违规为零。

导入仅选择 `recipes.user_id IS NULL` 的 curated demo 行。旧 `厨房数据库.sqlite3` 用 SQLite `mode=ro` 和 `query_only` 打开，未写入；图片列、用户菜、提问、投票、厨房设置和原始补充文字均不导入。`dish_knowledge.sqlite3` 的旧分析记录/两条旧格式别名也没有导入，别名仍需要将旧整数 ID 映射到正式 `Recipe` 后单独核验。

旧菜谱映射为稳定 `Recipe` 身份和 `draft` `RecipeVersion`；分类、食材、工具主数据和证据均为 `draft`，安全提示作为 `pending_review` 的独立 `Experience`。`Recipe.record_status=active` 只代表身份记录未归档，不代表菜谱内容审核通过；检索还必须有有效审核版本、来源和主数据。步骤文字和工具用法被保留。旧食材、工具自由文本仅按括号深度拆分顶层 `、`，不猜测数量、计量单位、烹饪方法或工具必需性；对应食材角色为未分类，锅具/工具类型为未分类。受当前关系枚举约束，菜谱工具关联的 `optional` 是未审核占位值，其条件备注明确提醒不可视为原资料确认的可选项。旧 `time_minutes` 只映射到烹饪时间，不能当作准备时间。

旧 demo 被登记为一个无 URL、`internal_only`、来源审核 `draft`、权利状态 `pending_review` 的来源。所有 evidence 仍是 `draft`。因此虽然记录已经导入，它们**不能用于 DeepSeek 分析**，也没有被标成已审核；之后必须由人核对内容、食材/工具规范化和权利边界。即便通过内容审核，旧来源仍需有人确认使用权，并明确改为可用于自有总结的许可策略后，检索才可能纳入。

`LegacyImportLedger` 对每个源分类、菜谱行和步骤保存来源哈希及目标 ID。相同内容重复运行会跳过，保留目标库里的人工修改；旧源内容发生变化会拒绝整批并回滚，不自动覆盖。确定性目标 ID 已被无台账记录占用时也会拒绝。导入器不会自动删除源中已不存在的记录；新增/变更内容应先人工评估，再通过正式的新版本/迁移处理。

## DeepSeek 的知识检索边界

本地菜品分析只查询正式知识库：输入菜名必须精确命中已审核菜名，或命中单独审核且未过期的别名；随后只取该菜最新的有效审核版本，以及明确关联到这道菜的已审核经验。菜谱包、来源内容/权利审核、链接检查都必须在有效期内；食材、锅具、做法等关联主数据也必须已审核且未过期。`internal_only` 和仅可展示链接的 `link_only` 来源不会作为知识内容发给模型。

模型提示词不再附带整批旧 demo 菜谱，也不再附带仅因锅具相同而命中的其他菜品历史经验。没有精确匹配的有效知识时，就只根据本轮用户输入分析，不声称该菜已由稳厨正式审核或收录。导入的 12 道菜目前全部为草稿，所以当前检索结果为空，这是预期的 fail-closed 行为。

`approved_recipe_versions(...)`、`approved_experiences(...)` 和 `retrieve_relevant_knowledge(...)` 只返回审核通过且仍有效的知识。菜谱版本实质内容或关系变化会自动将审核状态改为 `needs_update` 并写流水；经验适用关系变化也会重开审核。版本和经验通常 90 天复核；有 URL 的来源还必须在 30 天链接检查期限内。来源权利审核、内容审核和链接可访问性互相独立。`summary_only` 只允许向模型传稳厨自有总结及出处，不允许传原文、字幕或整段转录；未来使用其他许可范围时仍需遵守来源具体条件。

运行本地测试：

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile app.py knowledge_schema.py import_legacy_demo.py
```

## 以后切换到托管 PostgreSQL

SQLite 适合本地单机原型；正式服务切换前，先确认托管 PostgreSQL 的持久化、备份恢复、网络访问控制、TLS、密钥管理、连接上限和多实例写入方案。建议步骤：

1. 保留每次 schema 变更的迁移编号与审查，不在生产库手改结构；可把迁移管理接到 Alembic（或同等迁移工具）。
2. 将旧 SQLite 和正式原型库分别导出到 PostgreSQL staging，迁移前后核对行数、关系、审核状态、有效期和权限过滤；不要把 draft/pending_review 自动升级。
3. 将 ISO 时间文本迁为 `TIMESTAMPTZ`、AI JSON 文本迁为 `JSONB`；复核 CHECK、外键、唯一索引、部分索引和 `ON DELETE` 行为。可保留文本主键或改用 UUID。SQLite 多态 `EvidenceLink.target_type + target_id` 没有普通外键，生产时应继续做受限应用校验，或改为对象专属来源关联表/统一知识对象表。
4. 应用切换到 PostgreSQL 驱动和连接池后，先跑迁移、备份恢复演练和只读验证；切换流量后保留旧文件作回滚快照，确认稳定后再归档。

这只是后续路线；目前只在本地工作区建库、导入和验证，没有创建托管数据库、公开部署或把旧演示库改成正式库。
