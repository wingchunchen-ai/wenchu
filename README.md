# 稳厨

按家里有的锅具，找到能稳稳做成的菜。Flask + SQLite。

## 本地运行

```bash
pip install -r requirements.txt
python app.py            # 默认 http://127.0.0.1:5001 ，可用环境变量 PORT 改端口
```

`厨房数据库.sqlite3` 要和 `app.py` 放在同一个文件夹。启动时会自动补齐旧库缺的列（如 users.avatar）。

可选环境变量：

- `SECRET_KEY`：登录状态加密用的密钥，线上一定要设成一长串随机字符
- `WENCHU_DB`：数据库文件路径（默认是项目里的 厨房数据库.sqlite3）
- `WENCHU_UPLOAD_DIR`：上传图片存放的文件夹（默认 static/uploads）

## 测试

```bash
python tests/test_main_path.py   # 主路径
python tests/test_dish_ai.py     # 这道菜怎么做（AI+规则、限额、别名）
python tests/test_mobile.py      # 手机改版：导航、首页、逛菜谱、拍照认菜、分享照片、PWA
```

会把数据库复制到临时文件夹再测，不会改动项目里的数据库；DeepSeek 全部用假的代替，不连网。全部通过时显示「失败 0 项」。

## 入口（按用户想干什么，手机优先）

- **问怎么做**（首页 `/`）：一个大框「今天想做什么菜？」，框边 📷拍照 / 🖼相册；打字联想「稳厨已有」的菜（站内菜直接去菜谱详情）；快捷入口：我家的锅能做啥（`/recommend`）、30元以内（`/recipes?budget=30`）、15分钟（`/recipes?time=15分钟以内`）、先买哪口锅（`/starter`）；下面是左右滑的今日推荐（带 👍👎，填了锅就只推能做的，按伦敦日期每天换一次顺序）。
- **逛菜谱**（`/recipes`）：原来的放心菜谱和全部菜谱合成一页，「只看放心菜」开关默认开；关掉就是 `/all`（含正在被质疑的菜）。质疑区改名「大家的疑问」（`/questions`）。
- **分享我的菜谱**（`/upload`）：照片优先（拍成品照 / 从相册选），勾了「同意公开这张照片」才存照片；存之前用 Pillow 去掉 EXIF（含拍摄地点）。分享的照片不发给 AI。
- **我的厨房**（`/profile`）：画像；里面有「去看适合我的菜」（为我推荐）和「先买哪口锅」（入门备厨）。
- 页脚：大家的疑问、先买哪口锅、数据口径（演示）（`/stats`）。
- 所有老网址都还在：`/`、`/recipes`、`/all`、`/recipe/<id>`、`/recommend`、`/starter`、`/stats`、`/profile`、`/questions`、`/question/<id>`、`/upload`、`/edit/<id>`、`/dish-ai`、`/daily_recommend` 等。

## 拍照认菜（`/dish-ai/photo`）

- 照片在服务器上只放内存（`app.InMemoryRequest` 让上传文件不写临时文件），用 Pillow 缩到最长边 1024、去掉 EXIF，按 DeepSeek 官方看图格式（`image_url` + base64，`detail: low`，<https://api-docs.deepseek.com/guides/vision>）交给 `deepseek-v4-flash` 认菜名；只要 `{"dish_name", "confidence"}` 的 JSON。认完照片就丢：不存硬盘、不进数据库、不写日志。手机上还会先在浏览器里缩小再上传。
- 用户必须确认：「对，就是它」（站内菜直接去菜谱，其他交给「这道菜怎么做」）/「不对，我来改」。
- 支持 JPG / PNG / WebP，最大 5MB；HEIC 给出怎么办的提示；认不出、出错、没配密钥、今天次数用完 → 提示「请直接打菜名」。
- 每认一次算一次 AI 调用，和「这道菜怎么做」共用每天全站 `DISH_AI_DAILY_CAP`（默认 200）。

## 添加到主屏幕（PWA）

- `/manifest.webmanifest`（名字、`start_url`、`display: standalone`、主题色、192/512 图标），`/apple-touch-icon.png`（180×180），`_head.html` 里引用。图标在 `static/icons/`。
- 不注册 service worker：不做离线缓存、不推送（Chrome 的安装条件不要求 service worker，见 <https://web.dev/articles/install-criteria>）。苹果手机在 Safari 里点「分享 → 添加到主屏幕」。

## 部署（Render）

- Build Command：`pip install -r requirements.txt`
- Start Command：`gunicorn app:app`
- 环境变量：`SECRET_KEY`

## 导购演示（商业模式）

- 商品数据在 `shop_items.json`：现在全部是示例商品，链接是各平台公开搜索页。换成真实联盟推广链接时，只改这个文件里的 `url`、`price`、`is_sample`。
- 页面上的统一声明（`disclaimer`）：「潜在合作示意，未签约，暂不下单；按钮只跳到平台公开搜索页，价格为示例」。真签约之前不要改掉。
- 本餐预算：全部菜谱 / 放心菜谱 / 为你推荐 都能选「本餐预算」≤30 / ≤50 / ≤100 / 不限。每道菜显示「补齐约 ¥X」= 还缺的食材（调味料、可选的按家里已有）+ 按厨房画像还缺的锅；没填画像时锅具先不算。价格都取自 `shop_items.json` 的示例价，算法在 `shop.py` 的 `meal_cost`。
- 页面：菜谱详情里的「做这道菜的锅」「一键备齐食材」、`/starter` 入门备厨、`/stats` 导购点击统计。
- 现成 12 道菜的菜品图在 `static/dishes/`，由 AI（即梦）生成；`菜品图-写入数据库.sql` 可以把图片路径写进别的数据库。

## 这道菜怎么做（原 AI 拆菜，/dish-ai）

输入一道菜（菜名必填，补充说明可选），稳厨给出：主料/辅料/调味料、关键做法、要用的锅具和原因、对照「我的厨房」的已有/还缺，以及沿用「本餐预算」算法的补齐花费（示例价）。

- 第一层 AI 初稿：`dish_ai.py` 调 DeepSeek（OpenAI 兼容接口，模型固定 `deepseek-v4-flash`，要求只回 JSON，20 秒超时），返回内容会被校验、清洗。
- 第二层稳厨经验库：`dish_rules.py` 把做法对到锅具（爆炒→炒锅、清蒸→蒸锅、油炸→炒锅+油温计+漏勺、炖煲→电饭煲/砂锅、烤→空气炸锅/烤箱、煎→平底锅、水煮→小汤锅…；做法名「炒」包含爆炒、小炒、滑炒），锅具名与全站一致。规则拍板：必备锅具一定补上，AI 提的不认识的锅具不列。
- 站内已有的 12 道菜（和上传的菜）不调 AI，直接用菜谱：做法看菜名和步骤标题，锅具和补齐花费跟原菜谱、列表页完全一致，页面标「稳厨菜谱」并给出菜谱链接。
- 没配密钥、AI 超时/出错/返回坏 JSON，或勾选「只用稳厨经验库」时，走规则兜底（站内菜谱 + 常见菜资料 + 菜名关键词），页面会写明用的是「AI+规则」还是「规则兜底」。
- 密钥只放在服务器环境变量 `DEEPSEEK_API_KEY`，不写进代码和仓库。
- 只有一个输入框。边打字边联想「稳厨已有」的菜（`/dish-ai/suggest?q=`，站内 12 道菜 + 经验库常见菜 + 拆过的菜；别名表 + 归一化 + 包含 + 近似字/字重合，不调 AI），点联想直接用现成结果（零 AI）；不点就照常提交，不开 JS 也能用。
- 结果页是手机竖排卡片：要买的食材 → 要用的锅 → 你家还缺什么 + 补齐花费 → 步骤（站内菜用菜谱步骤；AI 的菜让 AI 顺带给最多 6 步要点，存在记录里；老记录没有步骤就只写关键做法）。
- 标准名：一个标准名 = 一条记录。提交时先查别名表 `dish_aliases`（种子见 `dish_match.SEED_ALIASES`，如 宫爆鸡丁→宫保鸡丁、鸡蛋炒饭→蛋炒饭），对上站内菜就用菜谱、对上拆过的就用记录，都不调 AI。都没有才问 AI，并让 AI 给出 `canonical_name`：这个标准名已经有记录 → 不新存，把用户的叫法记成别名、复用旧记录；是站内菜 → 记别名、不另存；全新的菜 → 按标准名存一条。AI 提的新叫法先是「待审核」（`dish_aliases.status = 'pending'`），审核通过前不用来对齐、不进联想；种子别名直接生效。审核：`python tools/aliases.py`（列出）、`python tools/aliases.py ok 叫法`（通过）、`python tools/aliases.py no 叫法`（删掉）。
- 个性化条件（`dish_match.personal_reason`，纯规则）：补充说明里有「没有 / 不用 / 换成 / 只有 / 素食 / 不吃肉 / 过敏 / 不油炸」或点名某件锅具（空气炸锅、电饭煲…）时，会改变锅具或做法，不复用记录和菜谱，带着说明单独问 AI，结果不存。只是口味（不要太辣、少放盐）就照样用标准拆法，页面提醒自己调口味。
- 拆菜记录：`dish_breakdowns` 只存标准名、清洗后的 JSON、模式、模型、token 用量和时间，不存用户的补充说明，也不存 IP；表结构写在 `dish_store.py` 顶部。旧表启动时自动迁移（写了说明的旧记录丢掉，同一标准名只留一条）。
- 限额（只数真正发出去的请求，按伦敦日期每天清零）：每个 IP 每天 `DISH_AI_PER_IP_DAILY` 次（默认 0 = 不限，需要时再设，比如 5；Render 上取 X-Forwarded-For 第一个 IP，库里只存哈希）；全站每天 `DISH_AI_DAILY_CAP` 次（默认 200，设 0 关掉 AI）。超了自动走稳厨经验库，页面写明原因。
- 注意：Render 免费版重新部署会清空 SQLite，拆菜记录和次数也会一起清空。
- 测试：`python tests/test_dish_ai.py`（不连网，DeepSeek 用假的代替）。
