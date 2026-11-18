# AI 拆菜的「账本」：拆过的菜存成可复用的记录（也当缓存），外加 AI 调用次数的限额
#
# 表 dish_breakdowns —— 每一次成功的 AI 拆菜一条，将来是「菜谱库」和 skill 的素材
#   id                 自增主键
#   dish_key           归一化后的菜名（去空格、标点，全角转半角，英文小写），查缓存用
#   dish_name          用户输入的菜名（清洗后，原样显示用）
#   description        用户写的补充说明；空字符串表示没写。只有空说明的记录会被当缓存复用
#   result_json        AI 返回并经过 dish_ai.parse_ai_json 校验清洗后的 JSON：
#                      {"main": [...], "side": [...], "season": [...], "methods": [...],
#                       "cookware": [{"name", "reason"}], "tips": "..."}
#                      注意存的是「AI 初稿」，锅具最终以 dish_rules 规则核对为准（每次展示时重新核对）
#   mode               这条记录怎么来的，目前固定 'AI+规则'
#   model              调用时用的模型名（deepseek-v4-flash）；api_model 是接口回报的实际模型名
#   prompt_tokens / completion_tokens / cache_hit_tokens / cache_miss_tokens / total_tokens
#                      这次调用的用量（接口的 prompt_cache_hit_tokens / prompt_cache_miss_tokens；没给就是 NULL），算成本用
#   created_at         UTC 时间
#
# 表 dish_ai_calls —— 每一次真正发出去的 AI 请求一条（缓存命中不记），限额就数这张表
#   visitor   访客 IP 的哈希（不存原始 IP）
#   day       伦敦日期（YYYY-MM-DD）；「每天」的限额都按这一列算，过了伦敦午夜就重新计
#   ok        1 = 拿到合格结果，0 = 出错 / 超时 / 返回不合格
#   created_at UTC 时间
#
# 提醒：Render 免费版的 SQLite 在每次重新部署后会清空，这两张表也一样。
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_PER_IP_DAILY = 5    # 每个 IP 每天（伦敦日期）最多真正调几次 AI，环境变量 DISH_AI_PER_IP_DAILY
DEFAULT_DAILY_CAP = 200     # 全站每天最多真正调几次 AI，环境变量 DISH_AI_DAILY_CAP
LONDON = ZoneInfo('Europe/London')


def london_day(now=None):
    return (now or datetime.now(LONDON)).astimezone(LONDON).strftime('%Y-%m-%d')


def init_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS dish_breakdowns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dish_key TEXT NOT NULL,
        dish_name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        result_json TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'AI+规则',
        model TEXT NOT NULL,
        api_model TEXT,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        cache_hit_tokens INTEGER,
        cache_miss_tokens INTEGER,
        total_tokens INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )''')
    cols = [r[1] for r in conn.execute('PRAGMA table_info(dish_breakdowns)')]
    if 'cache_miss_tokens' not in cols:  # 早期建的表没有这一列，补上
        conn.execute('ALTER TABLE dish_breakdowns ADD COLUMN cache_miss_tokens INTEGER')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dish_breakdowns_key ON dish_breakdowns (dish_key, description)')
    conn.execute('''CREATE TABLE IF NOT EXISTS dish_ai_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor TEXT NOT NULL,
        day TEXT NOT NULL,
        ok INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dish_ai_calls_day ON dish_ai_calls (day, visitor)')


def normalize_dish(name):
    # 「宫保 鸡丁」「宫保鸡丁！」「宫保鸡丁 」都算同一道菜
    s = unicodedata.normalize('NFKC', name or '').lower()
    return re.sub(r'[\s\W_]+', '', s)


def _env_int(name, default):
    # 读一个非负整数的环境变量；没设或写错就用默认值，0 表示关掉
    try:
        return max(int(os.environ.get(name, default)), 0)
    except ValueError:
        return default


def daily_cap():
    return _env_int('DISH_AI_DAILY_CAP', DEFAULT_DAILY_CAP)


def per_ip_daily():
    return _env_int('DISH_AI_PER_IP_DAILY', DEFAULT_PER_IP_DAILY)


def visitor_id(ip, salt):
    return hashlib.sha256(f'{salt}|{ip or "unknown"}'.encode('utf-8')).hexdigest()[:32]


def find_cached(conn, dish):
    # 同一道菜（归一化后）、没写补充说明 → 返回最近一条记录的 AI 初稿；没有返回 None
    row = conn.execute('''SELECT id, result_json FROM dish_breakdowns WHERE dish_key = ? AND description = ''
                          ORDER BY id DESC LIMIT 1''', (normalize_dish(dish),)).fetchone()
    if not row:
        return None
    try:
        return row['id'], json.loads(row['result_json'])
    except ValueError:
        return None


def limit_reason(conn, visitor, day=None):
    # 能不能再调一次 AI：能就返回 None，不能就返回给页面看的一句话（两种限额都按伦敦日期算）
    day = day or london_day()
    if conn.execute('SELECT COUNT(*) FROM dish_ai_calls WHERE day = ?', (day,)).fetchone()[0] >= daily_cap():
        return '今天全站的 AI 次数已用完，先用稳厨经验库'
    limit = per_ip_daily()
    if conn.execute('SELECT COUNT(*) FROM dish_ai_calls WHERE day = ? AND visitor = ?', (day, visitor)).fetchone()[0] >= limit:
        return f'你今天的 {limit} 次 AI 拆菜已用完，先用稳厨经验库（明天再来）'
    return None


def log_call(conn, visitor, day=None):
    # 发请求前先记一笔（并发时也不会超额太多），返回这条的 id，拿到结果后再标成功
    cur = conn.execute('INSERT INTO dish_ai_calls (visitor, day) VALUES (?, ?)', (visitor, day or london_day()))
    conn.commit()
    return cur.lastrowid


def mark_ok(conn, call_id):
    conn.execute('UPDATE dish_ai_calls SET ok = 1 WHERE id = ?', (call_id,))
    conn.commit()


def save_breakdown(conn, dish, description, result, model, usage=None, api_model=None):
    u = usage if isinstance(usage, dict) else {}

    def num(k):
        v = u.get(k)
        return v if isinstance(v, int) else None

    cur = conn.execute('''INSERT INTO dish_breakdowns (dish_key, dish_name, description, result_json, mode, model, api_model,
                          prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens, total_tokens)
                          VALUES (?, ?, ?, ?, 'AI+规则', ?, ?, ?, ?, ?, ?, ?)''',
                       (normalize_dish(dish), dish, description or '', json.dumps(result, ensure_ascii=False), model,
                        api_model if isinstance(api_model, str) else None, num('prompt_tokens'),
                        num('completion_tokens'), num('prompt_cache_hit_tokens'), num('prompt_cache_miss_tokens'),
                        num('total_tokens')))
    conn.commit()
    return cur.lastrowid
