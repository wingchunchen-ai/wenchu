# AI 拆菜的「账本」：拆过的菜存成可复用的记录（也当缓存）、菜名别名表，外加 AI 调用次数的限额
#
# 一个标准名 = 一条记录。各种叫法（宫爆鸡丁、宫保鸡）都记在别名表里，指向同一个标准名。
# 隐私：不存用户写的补充说明，也不存原始 IP。
#
# 表 dish_breakdowns —— 每个标准名一条 AI 拆菜结果，将来是「菜谱库」和 skill 的素材
#   id                 自增主键
#   canonical_key      标准名归一化后的写法（dish_match.normalize），唯一
#   canonical_name     标准名（显示用），例如「宫保鸡丁」
#   result_json        AI 返回并经过 dish_ai.parse_ai_json 校验清洗后的 JSON：
#                      {"canonical_name": "...", "main": [...], "side": [...], "season": [...], "methods": [...],
#                       "cookware": [{"name", "reason"}], "tips": "..."}
#                      存的是「AI 初稿」，锅具最终以 dish_rules 规则核对为准（每次展示时重新核对）
#   mode               这条记录怎么来的，目前固定 'AI+规则'
#   model              调用时用的模型名（deepseek-v4-flash）；api_model 是接口回报的实际模型名
#   prompt_tokens / completion_tokens / cache_hit_tokens / cache_miss_tokens / total_tokens
#                      生成这条记录那次调用的用量（没给就是 NULL），算成本用
#   created_at         第一次存的时间（UTC）
#   updated_at         最近一次被复用或加了别名的时间（UTC）
#
# 表 dish_aliases —— 别名 → 标准名
#   alias_key          叫法归一化后的写法，主键
#   canonical_key      指向的标准名（归一化），可能是站内菜、经验库常见菜或 dish_breakdowns 里的菜
#   source             'seed' 种子（dish_match.SEED_ALIASES）/ 'ai' AI 认出的标准名 / 'migrated' 旧数据迁过来的
#   status             'active' 生效（对齐菜名、进联想）/ 'pending' 待审核（AI 提的新叫法，审核前不生效、不进联想）
#                      种子和迁移来的别名直接 active；AI 提的一律 pending，用 python tools/aliases.py 审核
#   created_at         UTC
#
# 表 dish_ai_calls —— 每一次真正发出去的 AI 请求一条（缓存命中不记），限额就数这张表
#   visitor   访客 IP 的哈希（不存原始 IP）
#   day       伦敦日期（YYYY-MM-DD）；「每天」的限额都按这一列算，过了伦敦午夜就重新计
#   ok        1 = 拿到合格结果，0 = 出错 / 超时 / 返回不合格
#   created_at UTC 时间
#
# 提醒：Render 免费版的 SQLite 在每次重新部署后会清空，这些表也一样。
import hashlib
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import dish_match

DEFAULT_PER_IP_DAILY = 0    # 每个 IP 每天（伦敦日期）最多真正调几次 AI，环境变量 DISH_AI_PER_IP_DAILY；0 = 不限（现在默认不限）
DEFAULT_DAILY_CAP = 200     # 全站每天最多真正调几次 AI，环境变量 DISH_AI_DAILY_CAP
LONDON = ZoneInfo('Europe/London')


def london_day(now=None):
    return (now or datetime.now(LONDON)).astimezone(LONDON).strftime('%Y-%m-%d')


BREAKDOWN_COLS = ['id', 'canonical_key', 'canonical_name', 'result_json', 'mode', 'model', 'api_model', 'prompt_tokens',
                  'completion_tokens', 'cache_hit_tokens', 'cache_miss_tokens', 'total_tokens', 'created_at', 'updated_at']
CREATE_BREAKDOWNS = '''CREATE TABLE IF NOT EXISTS {name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    result_json TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'AI+规则',
    model TEXT NOT NULL,
    api_model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cache_hit_tokens INTEGER,
    cache_miss_tokens INTEGER,
    total_tokens INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)'''


def init_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS dish_aliases (
        alias_key TEXT PRIMARY KEY,
        canonical_key TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'seed',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )''')
    if 'status' not in [r[1] for r in conn.execute('PRAGMA table_info(dish_aliases)')]:
        # 旧表没有审核状态：补上这一列；以前 AI 自动加的别名改成待审核（和知识库设计一致：AI 提的要人审）
        conn.execute("ALTER TABLE dish_aliases ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        conn.execute("UPDATE dish_aliases SET status = 'pending' WHERE source = 'ai'")
    for alias, canon in dish_match.SEED_ALIASES.items():
        conn.execute("INSERT OR IGNORE INTO dish_aliases (alias_key, canonical_key, source, status) VALUES (?, ?, 'seed', 'active')",
                     (normalize_dish(alias), normalize_dish(canon)))
    cols = [r[1] for r in conn.execute('PRAGMA table_info(dish_breakdowns)')]
    if cols and 'canonical_key' not in cols:
        _migrate_old_breakdowns(conn, cols)
    conn.execute(CREATE_BREAKDOWNS.format(name='dish_breakdowns'))
    conn.execute('''CREATE TABLE IF NOT EXISTS dish_ai_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor TEXT NOT NULL,
        day TEXT NOT NULL,
        ok INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dish_ai_calls_day ON dish_ai_calls (day, visitor)')


def _migrate_old_breakdowns(conn, cols):
    # 旧表（按菜名 + 补充说明存）→ 新表（一个标准名一条，不存说明）
    # 只搬没写说明的记录（写了说明的可能带个人情况，直接丢掉）；同一标准名留最新那条；旧菜名记成别名
    rows = conn.execute("SELECT * FROM dish_breakdowns WHERE COALESCE(description, '') = '' ORDER BY id DESC").fetchall()
    conn.execute(CREATE_BREAKDOWNS.format(name='dish_breakdowns_new'))
    for r in rows:
        r = dict(zip([c[0] for c in conn.execute('SELECT * FROM dish_breakdowns LIMIT 0').description], r))
        old_key = r.get('dish_key') or normalize_dish(r.get('dish_name'))
        canon_key = resolve_alias(conn, old_key)
        name = r.get('dish_name') if canon_key == old_key else canon_key
        conn.execute('''INSERT OR IGNORE INTO dish_breakdowns_new (canonical_key, canonical_name, result_json, mode, model, api_model,
                        prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens, total_tokens, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (canon_key, name, r['result_json'], r.get('mode') or 'AI+规则', r['model'], r.get('api_model'),
                      r.get('prompt_tokens'), r.get('completion_tokens'), r.get('cache_hit_tokens'), r.get('cache_miss_tokens'),
                      r.get('total_tokens'), r['created_at'], r['created_at']))
        if old_key != canon_key:
            add_alias(conn, old_key, canon_key, 'migrated')
    conn.execute('DROP TABLE dish_breakdowns')
    conn.execute('ALTER TABLE dish_breakdowns_new RENAME TO dish_breakdowns')


def normalize_dish(name):
    return dish_match.normalize(name)


def resolve_alias(conn, name_or_key):
    # 叫法 → 标准名（归一化）；只认已生效（active）的别名，待审核的不算；别名表里没有就是它自己
    key = normalize_dish(name_or_key)
    row = conn.execute("SELECT canonical_key FROM dish_aliases WHERE alias_key = ? AND status = 'active'", (key,)).fetchone()
    return row[0] if row else key


def add_alias(conn, alias, canonical_key, source='ai'):
    # AI 提的新叫法先放「待审核」，审核通过前不对齐、不进联想；种子 / 迁移来的直接生效
    a = normalize_dish(alias)
    if a and a != canonical_key:
        status = 'pending' if source == 'ai' else 'active'
        conn.execute('INSERT OR IGNORE INTO dish_aliases (alias_key, canonical_key, source, status) VALUES (?, ?, ?, ?)',
                     (a, canonical_key, source, status))


def alias_map(conn):
    # 联想、对齐用的别名：只有已生效的
    return {r[0]: r[1] for r in conn.execute("SELECT alias_key, canonical_key FROM dish_aliases WHERE status = 'active'")}


def pending_aliases(conn):
    # 待审核的别名：[(叫法, 指向的标准名, 来源, 时间)]
    return [tuple(r) for r in conn.execute(
        "SELECT alias_key, canonical_key, source, created_at FROM dish_aliases WHERE status = 'pending' ORDER BY created_at, alias_key")]


def review_alias(conn, alias, approve=True):
    # 审核一条待审核别名：通过 → active；不通过 → 删掉。返回是否改到了
    a = normalize_dish(alias)
    if approve:
        cur = conn.execute("UPDATE dish_aliases SET status = 'active' WHERE alias_key = ? AND status = 'pending'", (a,))
    else:
        cur = conn.execute("DELETE FROM dish_aliases WHERE alias_key = ? AND status = 'pending'", (a,))
    conn.commit()
    return cur.rowcount > 0


def cached_names(conn):
    return [r[0] for r in conn.execute('SELECT canonical_name FROM dish_breakdowns ORDER BY id')]


def _env_int(name, default):
    # 读一个非负整数的环境变量；没设或写错就用默认值，0 表示关掉
    try:
        return max(int(os.environ.get(name, default)), 0)
    except ValueError:
        return default


def daily_cap():
    return _env_int('DISH_AI_DAILY_CAP', DEFAULT_DAILY_CAP)


def per_ip_daily():
    # 注意：这里 0 表示「每个 IP 不限次数」（跟全站上限的 0 = 关掉 AI 不一样）
    return _env_int('DISH_AI_PER_IP_DAILY', DEFAULT_PER_IP_DAILY)


def visitor_id(ip, salt):
    return hashlib.sha256(f'{salt}|{ip or "unknown"}'.encode('utf-8')).hexdigest()[:32]


def find_record(conn, canonical_key):
    # 按标准名找记录：返回 (id, 标准名, AI 初稿 dict) 或 None
    row = conn.execute('SELECT id, canonical_name, result_json FROM dish_breakdowns WHERE canonical_key = ?',
                       (canonical_key,)).fetchone()
    if not row:
        return None
    try:
        return row[0], row[1], json.loads(row[2])
    except ValueError:
        return None


def touch(conn, record_id):
    conn.execute("UPDATE dish_breakdowns SET updated_at = datetime('now') WHERE id = ?", (record_id,))
    conn.commit()


def limit_reason(conn, visitor, day=None):
    # 能不能再调一次 AI：能就返回 None，不能就返回给页面看的一句话（两种限额都按伦敦日期算）
    day = day or london_day()
    if conn.execute('SELECT COUNT(*) FROM dish_ai_calls WHERE day = ?', (day,)).fetchone()[0] >= daily_cap():
        return '今天全站的 AI 次数已用完，先用稳厨经验库'
    limit = per_ip_daily()
    if limit and conn.execute('SELECT COUNT(*) FROM dish_ai_calls WHERE day = ? AND visitor = ?', (day, visitor)).fetchone()[0] >= limit:
        return f'你今天的 {limit} 次 AI 已用完，先用稳厨经验库（明天再来）'
    return None


def log_call(conn, visitor, day=None):
    # 发请求前先记一笔（并发时也不会超额太多），返回这条的 id，拿到结果后再标成功
    cur = conn.execute('INSERT INTO dish_ai_calls (visitor, day) VALUES (?, ?)', (visitor, day or london_day()))
    conn.commit()
    return cur.lastrowid


def mark_ok(conn, call_id):
    conn.execute('UPDATE dish_ai_calls SET ok = 1 WHERE id = ?', (call_id,))
    conn.commit()


def save_breakdown(conn, canonical_name, result, model, usage=None, api_model=None):
    # 存一条标准记录；同一个标准名已经有了就不存（一个标准名 = 一条记录），返回 (记录 id, 是否新存)
    u = usage if isinstance(usage, dict) else {}

    def num(k):
        v = u.get(k)
        return v if isinstance(v, int) else None

    key = normalize_dish(canonical_name)
    cur = conn.execute('''INSERT OR IGNORE INTO dish_breakdowns (canonical_key, canonical_name, result_json, mode, model, api_model,
                          prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens, total_tokens)
                          VALUES (?, ?, ?, 'AI+规则', ?, ?, ?, ?, ?, ?, ?)''',
                       (key, canonical_name, json.dumps(result, ensure_ascii=False), model,
                        api_model if isinstance(api_model, str) else None, num('prompt_tokens'),
                        num('completion_tokens'), num('prompt_cache_hit_tokens'), num('prompt_cache_miss_tokens'),
                        num('total_tokens')))
    conn.commit()
    if cur.rowcount:
        return cur.lastrowid, True
    return conn.execute('SELECT id FROM dish_breakdowns WHERE canonical_key = ?', (key,)).fetchone()[0], False
