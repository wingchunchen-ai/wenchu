"""AI 拆菜测试：规则库、JSON 校验、AI 不可用时的规则兜底、页面。不连网（DeepSeek 全部用假的代替）。

用法（在项目根目录）：
    python tests/test_dish_ai.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='wenchu-ai-test-')
TEST_DB = os.path.join(TMP, 'test.sqlite3')
shutil.copy(os.path.join(ROOT, '厨房数据库.sqlite3'), TEST_DB)
os.environ['WENCHU_DB'] = TEST_DB
os.environ['WENCHU_UPLOAD_DIR'] = os.path.join(TMP, 'uploads')
os.environ.pop('DEEPSEEK_API_KEY', None)  # 测试里绝不用真密钥
sys.path.insert(0, ROOT)

import app as wenchu  # noqa: E402
import dish_ai  # noqa: E402
import dish_rules  # noqa: E402
import shop  # noqa: E402

passed, failed = 0, []


def check(name, ok, detail=''):
    global passed
    if ok:
        passed += 1
        print(f'  [通过] {name}')
    else:
        failed.append(name)
        print(f'  [失败] {name} {detail}')


def names(cookware):
    return [c['name'] for c in cookware]


GOOD = json.dumps({
    'recognized': True, 'main': ['鸡胸肉', '花生米'], 'side': ['干辣椒', '葱'], 'season': ['生抽', '醋'],
    'methods': ['爆炒'], 'cookware': [{'name': '铁锅', 'reason': '大火快炒'}, {'name': '料理机', 'reason': '没用'}],
    'tips': '花生米最后放',
}, ensure_ascii=False)


def fake_ok(text):
    return lambda dish, desc: text


def fake_fail(dish, desc):
    raise dish_ai.AIError('连不上 AI 服务或超时')


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


try:
    catalog = shop.load_shop()
    conn = wenchu.get_db()
    known = wenchu.known_recipes_for_rules(conn)
    conn.close()

    print('1. 规则库：做法 → 锅具')
    cases = {'炒': '炒锅', '清蒸': '蒸锅', '油炸': '油温计', '炖煲': '电饭煲', '烤': '空气炸锅', '煎': '平底锅', '水煮': '小汤锅'}
    for m, pot in cases.items():
        cw, _ = dish_rules.build_cookware([m])
        check(f'{m} 一定要 {pot}', pot in names(cw), names(cw))
    cw, _ = dish_rules.build_cookware(['油炸'])
    check('油炸：深锅（炒锅）+ 油温计 + 漏勺', {'炒锅', '油温计', '漏勺'} <= set(names(cw)))
    check('每道菜都带刀和案板', {'刀', '案板'} <= set(names(dish_rules.build_cookware([])[0])))
    known_names = set(shop.POTS) | set(catalog['tools']) | {'油温计', '漏勺'}
    all_rule_tools = {n for rules in dish_rules.RULES.values() for n, _, _ in rules} | {n for n, _, _ in dish_rules.BASIC}
    check('规则里的锅具名都跟全站一致（画像六口锅 / 商品表小工具 / 油温计漏勺）', all_rule_tools <= known_names, all_rule_tools - known_names)
    check('每条规则都写了原因', all(r for rules in dish_rules.RULES.values() for _, r, _ in rules))
    check('别名归一：铁锅→炒锅、砧板→案板、烤箱→空气炸锅、砂锅→电饭煲',
          [dish_rules.canonical_tool(x) for x in ['铁锅', '砧板', '烤箱', '砂锅']] == ['炒锅', '案板', '空气炸锅', '电饭煲'])
    check('认不出的锅具返回 None', dish_rules.canonical_tool('料理机') is None)
    check('菜名找做法：清蒸鲈鱼→清蒸', dish_rules.methods_from_text('清蒸鲈鱼') == ['清蒸'])
    check('「空气炸锅鸡翅」不会被当成油炸', '油炸' not in dish_rules.methods_from_text('空气炸锅鸡翅'))
    check('红烧茄子→红烧', dish_rules.methods_from_text('红烧茄子') == ['红烧'])

    print('2. JSON 校验 / 清洗')
    d = dish_ai.parse_ai_json(GOOD)
    check('合格 JSON 能解析', d['main'] == ['鸡胸肉', '花生米'] and d['methods'] == ['炒'])
    check('包在 ``` 代码块里也能解析', dish_ai.parse_ai_json('```json\n' + GOOD + '\n```')['methods'] == ['炒'])
    for bad, why in [('不是JSON', '不是 JSON'), ('[1,2]', '不是对象'), ('', '空'),
                     ('{"recognized": false}', '不认得'), ('{"main": ["鸡"], "methods": []}', '没做法'),
                     ('{"main": [], "methods": ["爆炒"]}', '没主料'), ('{"main": ["鸡"], "methods": ["量子烹饪"]}', '做法不在规则库')]:
        try:
            dish_ai.parse_ai_json(bad)
            check(f'坏 JSON（{why}）会被拒', False)
        except dish_ai.AIError:
            check(f'坏 JSON（{why}）会被拒', True)
    d = dish_ai.parse_ai_json(json.dumps({'main': ['<script>alert(1)</script>鸡', 123, '鸡（去皮）', '超长' * 30],
                                          'methods': ['大火爆炒', '爆炒'], 'cookware': ['平底锅', 5],
                                          'tips': '<b>小心</b>'}, ensure_ascii=False))
    check('清洗：去掉尖括号、非字符串、括号说明，限制长度',
          all('<' not in x and len(x) <= dish_ai.MAX_NAME for x in d['main']) and '鸡' in d['main'] and 123 not in d['main'], d['main'])
    check('清洗：做法归一并去重（大火爆炒、爆炒 → 炒）', d['methods'] == ['炒'], d['methods'])
    check('清洗：锅具可以是字符串，非法项丢掉', [c['name'] for c in d['cookware']] == ['平底锅'])
    check('清洗：提醒里没有尖括号', '<' not in d['tips'])
    many = json.dumps({'main': [f'料{i}' for i in range(50)], 'methods': ['煎']}, ensure_ascii=False)
    check('每类最多 10 个', len(dish_ai.parse_ai_json(many)['main']) == dish_ai.MAX_ITEMS)

    print('3. AI+规则：规则核对 AI 的锅具')
    r = dish_ai.analyze('宫保鸡丁', '', ['平底锅'], True, known, catalog, caller=fake_ok(GOOD))
    check('模式是 AI+规则', r['mode'] == 'AI+规则')
    cw = {c['name']: c for c in r['cookware']}
    check('AI 说的「铁锅」归成炒锅，且规则确认', cw.get('炒锅', {}).get('source') == 'both')
    check('规则补上 AI 漏掉的锅铲、刀、案板', all(cw.get(n, {}).get('source') == 'rule' for n in ['锅铲', '刀', '案板']))
    check('规则库不认识的「料理机」不列出，单独说明', '料理机' not in cw and r['dropped'] == ['料理机'])
    check('对照画像：有平底锅、缺炒锅', r['missing'] == ['炒锅'] and r['have'] == [])
    exp = shop.meal_cost({'ingredients_list': '鸡胸肉、花生米、干辣椒、葱', 'tools_list': '炒锅'}, [], ['平底锅'], catalog)
    check('花费沿用 meal_cost（食材+缺的锅，调味料不算）', r['cost'] == exp and r['cost']['cookware'] == catalog['cookware']['炒锅']['price'], r['cost'])
    r = dish_ai.analyze('清蒸鲈鱼', '', [], False, known, catalog,
                        caller=fake_ok('{"main": ["鲈鱼"], "methods": ["煮"], "cookware": [{"name": "汤锅"}]}'))
    check('菜名写了清蒸、AI 漏了，规则补上蒸锅', '蒸锅' in names(r['cookware']) and '清蒸' in r['methods'])
    check('没填画像：锅具不算钱', r['cost']['cookware'] == 0 and r['know_pots'] is False)

    print('4. 规则兜底')
    r = dish_ai.analyze('宫保鸡丁', '', [], False, known, catalog, caller=fake_fail)
    check('AI 失败 → 规则兜底，并说明原因', r['mode'] == '规则兜底' and '超时' in r['ai_error'])
    check('兜底用经验库的宫保鸡丁：主料鸡胸肉、做法炒、要炒锅',
          r['main'] == ['鸡胸肉'] and r['methods'] == ['炒'] and '炒锅' in names(r['cookware']))
    r = dish_ai.analyze('宫保鸡丁', '', [], False, known, catalog, caller=fake_ok('乱七八糟'))
    check('AI 返回坏 JSON → 规则兜底', r['mode'] == '规则兜底' and r['main'] == ['鸡胸肉'])
    r = dish_ai.analyze('宫保鸡丁', '', [], False, known, catalog)  # 环境里没有密钥
    check('没配密钥 → 规则兜底，提示没配置', r['mode'] == '规则兜底' and '没配置' in r['ai_error'])
    print('4b. 站内 12 道菜：做法看菜名和步骤，锅具、花费跟原菜谱一模一样')
    expect_methods = {'可乐鸡翅': ['水煮', '煎', '炖煲'], '芥末虾球': ['油炸'], '巧克力慕斯蛋糕': ['打发'], '干锅花菜': ['炒'],
                      '熔岩吐司': ['烤'], '生啫鱿鱼': ['红烧', '炒'], '秘制土豆鸡腿饭': ['炖煲', '煎'],
                      '龙虾面': ['炒', '炖煲', '水煮'], '赛螃蟹': ['炒'], '爆炒猪肝': ['炒'], '奶油蘑菇意面': ['水煮', '炒'], '蛋炒饭': ['炒']}
    con = wenchu.get_db()
    bad_methods, bad_cost, bad_tools = [], [], []
    for owned in ([], ['炒锅'], ['平底锅', '小汤锅']):
        for rec in con.execute('SELECT * FROM recipes WHERE is_official = 1 ORDER BY id').fetchall():
            steps = con.execute('SELECT tools FROM recipe_steps WHERE recipe_id=?', (rec['id'],)).fetchall()
            r = dish_ai.analyze(rec['name'], '', owned, bool(owned), known, catalog, caller=fake_ok(GOOD))
            orig = shop.meal_cost(rec, steps, owned, catalog, know_pots=bool(owned))
            if r['methods'] != expect_methods[rec['name']]:
                bad_methods.append((rec['name'], r['methods']))
            if r['cost'] != orig or r['missing'] != (orig['missing_pots'] if owned else r['missing']):
                bad_cost.append((rec['name'], owned, r['cost']['total'], orig['total']))
            need = set(shop.pots_needed(shop.recipe_tools_text(rec, steps)))
            if {c['name'] for c in r['cookware'] if c['is_pot']} != need or r['mode'] != '稳厨菜谱':
                bad_tools.append(rec['name'])
    con.close()
    check('12 道菜的做法都对得上菜名和步骤（蛋炒饭是炒，不是煎）', not bad_methods, bad_methods)
    check('12 道菜 × 3 种厨房：补齐花费和缺的锅跟列表页完全一样', not bad_cost, bad_cost)
    check('12 道菜的锅跟原菜谱一样，不多不少；不调 AI，标「稳厨菜谱」', not bad_tools, bad_tools)
    r = dish_ai.analyze('蛋炒饭', '', ['炒锅'], True, known, catalog, use_ai=False)
    check('蛋炒饭：做法炒，用平底锅，不会多出炒锅', r['methods'] == ['炒'] and '平底锅' in names(r['cookware']) and '炒锅' not in names(r['cookware']))
    check('蛋炒饭：锅具原因里不再出现「煎」', '煎' not in ''.join(c['reason'] for c in r['cookware']))
    r = dish_ai.analyze('可乐鸡翅', '', [], False, known, catalog, use_ai=False)
    check('站内菜：「腌制」「拌饭」「搅拌」不会被当成凉拌', all('凉拌' not in dish_ai.analyze(n, '', [], False, known, catalog, use_ai=False)['methods'] for n in expect_methods))
    check('站内菜：调味料和「可选」算家里已有', '料酒' in r['season'] and '鸡翅' in r['main'])
    check('站内菜：页面给出完整菜谱链接', r['site_id'] == 1)
    r = dish_ai.analyze('胡萝卜鸡蛋炒饭', '', [], False, known, catalog, use_ai=False)
    check('多了食材的菜（胡萝卜鸡蛋炒饭）不直接套用蛋炒饭，也不丢胡萝卜', not r.get('site_id') and '胡萝卜' in r['main'] and '鸡' not in r['main'])
    r = dish_ai.analyze('家常蛋炒饭', '', [], False, known, catalog, use_ai=False)
    check('只多了修饰词（家常蛋炒饭）仍用站内蛋炒饭', r.get('site_id') and r['mode'] == '稳厨菜谱')
    r = dish_ai.analyze('红烧茄子', '', [], False, known, catalog, use_ai=False)
    check('没收录的菜：按菜名猜出茄子 + 红烧 → 炒锅、锅盖', r['main'] == ['茄子'] and {'炒锅', '锅盖'} <= set(names(r['cookware'])))
    r = dish_ai.analyze('神秘料理', '', [], False, known, catalog, use_ai=False)
    check('完全认不出时老实说认不出，不编', r['empty'] and r['cost'] is None)

    print('5. 调 DeepSeek 的那一层（假的网络）')
    seen = {}

    def opener_ok(req, timeout):
        seen['body'] = json.loads(req.data.decode('utf-8'))
        seen['timeout'] = timeout
        seen['url'] = req.full_url
        return FakeResp(json.dumps({'choices': [{'message': {'content': GOOD}}]}).encode('utf-8'))

    out = dish_ai.call_deepseek('宫保鸡丁', '', api_key='sk-test-not-real', opener=opener_ok)
    check('只用 deepseek-v4-flash 模型', seen['body']['model'] == 'deepseek-v4-flash')
    check('要求 JSON 输出', seen['body']['response_format'] == {'type': 'json_object'})
    check('超时 20 秒以内', seen['timeout'] <= 20)
    check('请求发到 DeepSeek 官方地址', seen['url'] == 'https://api.deepseek.com/chat/completions')
    check('返回模型给的内容', out == GOOD)

    def opener_401(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, None)

    def opener_timeout(req, timeout):
        raise TimeoutError()

    for op, word in [(opener_401, '密钥'), (opener_timeout, '超时')]:
        try:
            dish_ai.call_deepseek('x', '', api_key='sk-test-not-real', opener=op)
            check(f'出错（{word}）抛 AIError', False)
        except dish_ai.AIError as e:
            check(f'出错（{word}）抛 AIError，且信息里不含密钥', word in str(e) and 'sk-test' not in str(e))
    src = open(os.path.join(ROOT, 'dish_ai.py'), encoding='utf-8').read()
    check('代码里只从环境变量读密钥，不写死', "os.environ.get('DEEPSEEK_API_KEY'" in src and 'sk-' not in src)
    check('代码里没有 pro 模型', 'v4-pro' not in src)

    print('6. 页面')
    c = wenchu.app.test_client()
    h = c.get('/dish-ai').get_data(as_text=True)
    check('「这道菜怎么做」页能打开，有菜名输入框，页面不再叫「AI 拆菜」', 'name="dish"' in h and '这道菜怎么做' in h and '拆菜' not in h)
    nav = c.get('/recipes').get_data(as_text=True)
    check('导航按用户意图：问怎么做 / 逛菜谱 / 我的厨房 / 分享我的菜谱', all(w in nav for w in ['问怎么做', '逛菜谱', '我的厨房', '分享我的菜谱']) and 'AI 拆菜' not in nav)
    r = c.post('/dish-ai', data={'dish': ''}, follow_redirects=True)
    check('没写菜名会提示', '请先写上菜名' in r.get_data(as_text=True))
    orig = dish_ai.call_deepseek
    dish_ai.call_deepseek = fake_ok(GOOD)
    try:
        h = c.post('/dish-ai', data={'dish': '宫保鸡丁'}).get_data(as_text=True)
        check('AI 模式：页面写明 AI+规则', 'AI+规则' in h and '鸡胸肉' in h and 'AI 提出 · 规则确认' in h)
        check('页面写明示例价和合作声明', '示例价' in h and catalog['disclaimer'] in h)
        h = c.post('/dish-ai', data={'dish': '宫保鸡丁', 'rules_only': '1'}).get_data(as_text=True)
        check('勾「只用经验库」：不调 AI，写明规则兜底', '规则兜底' in h and 'AI 提出' not in h)
        h = c.post('/dish-ai', data={'dish': '蛋炒饭', 'rules_only': '1'}).get_data(as_text=True)
        check('蛋炒饭页面：标「稳厨菜谱」、做法显示炒、有菜谱链接', '稳厨菜谱' in h and '<span class="chip red">炒</span>' in h and 'href="/recipe/12"' in h)
    finally:
        dish_ai.call_deepseek = orig
    dish_ai.call_deepseek = fake_fail
    try:
        resp = c.post('/dish-ai', data={'dish': '清蒸鲈鱼'})
        h = resp.get_data(as_text=True)
        check('AI 挂了：页面照样出结果，写明规则兜底', resp.status_code == 200 and '规则兜底' in h and '蒸锅' in h)
    finally:
        dish_ai.call_deepseek = orig
    h = c.post('/dish-ai', data={'dish': '<script>x</script>'}).get_data(as_text=True)
    check('菜名里的标签不会原样出现在页面上', '<script>x</script>' not in h)
    print('7. 限额 / 缓存 / 拆菜记录')
    import sqlite3
    from datetime import datetime, timezone
    import dish_store
    os.environ.pop('DISH_AI_DAILY_CAP', None)
    os.environ.pop('DISH_AI_PER_IP_DAILY', None)
    calls = []
    USAGE = {'prompt_tokens': 420, 'completion_tokens': 180, 'total_tokens': 600, 'prompt_cache_hit_tokens': 384, 'prompt_cache_miss_tokens': 36}

    def fake_api(dish, desc):
        calls.append(dish)
        return dish_ai.AIReply(GOOD, USAGE, 'deepseek-v4-flash')

    def db():
        con = sqlite3.connect(TEST_DB)
        con.row_factory = sqlite3.Row
        return con

    def post(dish, ip, desc='', **kw):
        return c.post('/dish-ai', data={'dish': dish, 'description': desc, **kw},
                      headers={'X-Forwarded-For': ip}).get_data(as_text=True)

    check('菜名归一：空格、标点、全角都算同一道菜',
          dish_store.normalize_dish(' 宫保 鸡丁！') == dish_store.normalize_dish('宫保鸡丁') == dish_store.normalize_dish('宫保鸡丁 '))
    check('默认限额：每 IP 不限（0）、全站每天 200 次', dish_store.per_ip_daily() == 0 and dish_store.daily_cap() == 200)
    os.environ['DISH_AI_DAILY_CAP'] = 'abc'
    os.environ['DISH_AI_PER_IP_DAILY'] = '-3'
    check('环境变量写错用默认值，负数当 0', dish_store.daily_cap() == 200 and dish_store.per_ip_daily() == 0)
    os.environ['DISH_AI_DAILY_CAP'] = '7'
    os.environ['DISH_AI_PER_IP_DAILY'] = '3'
    check('环境变量能改限额', dish_store.daily_cap() == 7 and dish_store.per_ip_daily() == 3)
    os.environ.pop('DISH_AI_DAILY_CAP')
    os.environ.pop('DISH_AI_PER_IP_DAILY')
    check('「每天」按伦敦日期：夏令时 6/30 23:30 UTC 已经是伦敦 7/1',
          dish_store.london_day(datetime(2026, 6, 30, 23, 30, tzinfo=timezone.utc)) == '2026-07-01')
    check('冬令时 11/18 23:30 UTC 还是伦敦 11/18',
          dish_store.london_day(datetime(2026, 11, 18, 23, 30, tzinfo=timezone.utc)) == '2026-11-18')
    con = db()
    cols = [r['name'] for r in con.execute('PRAGMA table_info(dish_breakdowns)')]
    cols2 = [r['name'] for r in con.execute('PRAGMA table_info(dish_ai_calls)')]
    con.close()
    check('dish_breakdowns 表字段齐全，没有补充说明列', cols == dish_store.BREAKDOWN_COLS and 'description' not in cols, cols)
    check('dish_ai_calls 表字段齐全（存 IP 哈希和伦敦日期）', cols2 == ['id', 'visitor', 'day', 'ok', 'created_at'], cols2)

    con = db()
    con.execute('DELETE FROM dish_breakdowns')  # 前面页面测试留下的记录先清掉，从零开始数
    con.execute('DELETE FROM dish_ai_calls')
    con.commit()
    con.close()
    orig = dish_ai.call_deepseek
    dish_ai.call_deepseek = fake_api
    try:
        h = post('宫保鸡丁', '1.1.1.1')
        check('第一次：真调 AI，标 AI+规则', len(calls) == 1 and 'AI+规则' in h and '没再调 AI' not in h)
        con = db()
        rec = con.execute('SELECT * FROM dish_breakdowns').fetchall()
        con.close()
        check('成功的拆菜存成一条记录', len(rec) == 1)
        r0 = rec[0]
        check('记录：标准名、模式、模型', r0['canonical_key'] == '宫保鸡丁' and r0['canonical_name'] == '宫保鸡丁'
              and r0['mode'] == 'AI+规则' and r0['model'] == 'deepseek-v4-flash')
        check('记录：用量都存了', (r0['prompt_tokens'], r0['completion_tokens'], r0['cache_hit_tokens'], r0['cache_miss_tokens'], r0['total_tokens']) == (420, 180, 384, 36, 600))
        stored = json.loads(r0['result_json'])
        check('记录：存的是清洗后的 JSON（AI 初稿，结构固定）', set(stored) == {'canonical_name', 'main', 'side', 'season', 'methods', 'cookware', 'tips', 'steps'}
              and stored['methods'] == ['炒'])
        check('记录有创建和更新时间', bool(r0['created_at']) and bool(r0['updated_at']))
        h = post('宫保鸡丁', '1.1.1.1')
        check('同一道菜再拆：用存下的结果，不调 AI，页面写明', len(calls) == 1 and 'AI+规则' in h and '没再调 AI' in h)
        post(' 宫保 鸡丁！', '9.9.9.9')
        check('写法不同（空格、标点）也命中缓存', len(calls) == 1)
        con = db()
        n_calls = con.execute('SELECT COUNT(*) FROM dish_ai_calls').fetchone()[0]
        n_rec = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        con.close()
        check('缓存命中不算次数、不重复存记录', n_calls == 1 and n_rec == 1)
        h = post('宫保鸡丁', '1.1.1.1', desc='不要太辣')
        check('只是口味要求：照样用存下的结果，不调 AI，页面提醒自己调口味', len(calls) == 1 and '没再调 AI' in h and '自己调口味' in h)
        calls.append('占位')  # 保持后面计数和原来一致

        n = len(calls)
        for i in range(7):
            post(f'不限测试{i}', '1.2.3.4')
        check('默认每 IP 不限：同一个 IP 调 7 次都真调 AI', len(calls) == n + 7)
        os.environ['DISH_AI_PER_IP_DAILY'] = '5'  # 下面测「打开每 IP 限额」的情况
        before = len(calls)
        for i in range(5):
            post(f'测试菜{i}', '2.2.2.2')
        check('每个 IP 每天 5 次以内都真调 AI', len(calls) == before + 5)
        h = post('测试菜99', '2.2.2.2')
        check('第 6 次：不调 AI，规则兜底并写明今天次数用完', len(calls) == before + 5 and '规则兜底' in h and '今天的 5 次 AI 已用完' in h)
        h = post('宫保鸡丁', '2.2.2.2')
        check('次数用完的人，拆过的菜照样能用（缓存不占次数）', 'AI+规则' in h and '没再调 AI' in h and len(calls) == before + 5)
        post('测试菜100', '3.3.3.3, 10.0.0.1')
        check('换一个 IP 照样能用', len(calls) == before + 6)
        post('测试菜101', '3.3.3.3, 10.0.0.2')
        con = db()
        vs = {r[0] for r in con.execute("SELECT visitor FROM dish_ai_calls ORDER BY id DESC LIMIT 2")}
        con.close()
        check('X-Forwarded-For 只认第一个 IP（后面的代理不同也算同一人）', len(vs) == 1)
        con = db()
        raw_ip = con.execute("SELECT COUNT(*) FROM dish_ai_calls WHERE visitor LIKE '%3.3.3.3%'").fetchone()[0]
        con.close()
        check('不存原始 IP，只存哈希', raw_ip == 0)
        os.environ['DISH_AI_PER_IP_DAILY'] = '7'
        post('测试菜102', '2.2.2.2')
        check('把 DISH_AI_PER_IP_DAILY 调大，同一个 IP 又能用', len(calls) == before + 8)
        os.environ['DISH_AI_PER_IP_DAILY'] = '0'
        post('测试菜103', '2.2.2.2')
        check('DISH_AI_PER_IP_DAILY=0：不限，同一个 IP 继续能用', len(calls) == before + 9)
        os.environ['DISH_AI_PER_IP_DAILY'] = '5'

        con = db()
        v4 = dish_store.visitor_id('4.4.4.4', wenchu.app.secret_key)
        for _ in range(5):
            con.execute("INSERT INTO dish_ai_calls (visitor, day, ok) VALUES (?, '2000-01-01', 1)", (v4,))
        con.commit()
        con.close()
        n = len(calls)
        post('测试菜200', '4.4.4.4')
        check('昨天（以前）的次数不算今天的', len(calls) == n + 1)

        con = db()
        today_total = con.execute('SELECT COUNT(*) FROM dish_ai_calls WHERE day = ?', (dish_store.london_day(),)).fetchone()[0]
        con.close()
        os.environ['DISH_AI_DAILY_CAP'] = str(today_total)
        n = len(calls)
        h = post('测试菜300', '5.5.5.5')
        check('全站每天上限到了：新访客也不调 AI，写明全站次数用完', len(calls) == n and '今天全站的 AI 次数已用完' in h)
        h = post('宫保鸡丁', '5.5.5.5')
        check('全站上限到了，拆过的菜照样能用', '没再调 AI' in h and len(calls) == n)
        os.environ['DISH_AI_DAILY_CAP'] = '0'
        post('测试菜301', '6.6.6.6')
        check('DISH_AI_DAILY_CAP=0 等于关掉 AI', len(calls) == n)
        os.environ.pop('DISH_AI_DAILY_CAP')

        dish_ai.call_deepseek = lambda d, x: (calls.append(d), dish_ai.AIReply('乱七八糟', USAGE))[1]
        con = db()
        n_rec = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        n_call = con.execute('SELECT COUNT(*) FROM dish_ai_calls').fetchone()[0]
        con.close()
        h = post('测试菜400', '7.7.7.7')
        con = db()
        row = con.execute('SELECT ok FROM dish_ai_calls ORDER BY id DESC LIMIT 1').fetchone()
        n_rec2 = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        n_call2 = con.execute('SELECT COUNT(*) FROM dish_ai_calls').fetchone()[0]
        con.close()
        check('AI 回了坏 JSON：算一次调用（标失败），不存记录，页面规则兜底',
              n_call2 == n_call + 1 and row['ok'] == 0 and n_rec2 == n_rec and '规则兜底' in h)
        dish_ai.call_deepseek = fake_fail
        post('测试菜401', '7.7.7.7')
        con = db()
        n_call3 = con.execute('SELECT COUNT(*) FROM dish_ai_calls').fetchone()[0]
        con.close()
        check('AI 超时也算一次真实请求', n_call3 == n_call2 + 1)
        dish_ai.call_deepseek = fake_api
        n = len(calls)
        post('蛋炒饭', '8.8.8.8')
        check('站内菜不调 AI，也不占次数', len(calls) == n)
        h = c.get('/dish-ai').get_data(as_text=True)
        check('打开每 IP 限额时，页面写明每人每天 5 次', '每人每天 5 次' in h and '不占次数' in h)
        os.environ.pop('DISH_AI_PER_IP_DAILY')
        h = c.get('/dish-ai').get_data(as_text=True)
        check('默认不限每人次数：页面不写「每人每天」，只写拆过的菜不占次数', '每人每天' not in h and '不占次数' in h)
    finally:
        dish_ai.call_deepseek = orig
    print('8. 菜名对齐：别名 / 联想 / 标准名去重 / 个性化条件 / 隐私')
    import dish_match
    os.environ.pop('DISH_AI_PER_IP_DAILY', None)
    os.environ.pop('DISH_AI_DAILY_CAP', None)
    con = db()
    con.execute('DELETE FROM dish_breakdowns')
    con.execute("DELETE FROM dish_aliases WHERE source != 'seed'")
    con.execute('DELETE FROM dish_ai_calls')
    con.commit()
    check('别名种子：宫爆鸡丁 → 宫保鸡丁、西红柿炒鸡蛋 → 番茄炒蛋、鸡蛋炒饭 → 蛋炒饭',
          [dish_store.resolve_alias(con, x) for x in ['宫爆鸡丁', '西红柿炒鸡蛋', ' 鸡蛋炒饭！']] == ['宫保鸡丁', '番茄炒蛋', '蛋炒饭'])
    check('别名表里没有的叫法：标准名就是它自己', dish_store.resolve_alias(con, '火星炒饭') == '火星炒饭')
    con.close()
    check('种子别名指向的标准名都是「稳厨已有」的菜（站内 12 道或经验库）',
          all(v in dish_rules.COMMON_DISHES or v in expect_methods for v in dish_match.SEED_ALIASES.values()))
    cands = {'宫保鸡丁': 'cached', '蛋炒饭': 'site', '番茄炒蛋': 'common', '爆炒猪肝': 'site'}
    al = {dish_match.normalize(k): dish_match.normalize(v) for k, v in dish_match.SEED_ALIASES.items()}
    top = lambda q: [n for n, _, _ in dish_match.suggest(q, cands, al)]
    check('联想：打「宫爆」出宫保鸡丁', top('宫爆')[:1] == ['宫保鸡丁'], top('宫爆'))
    check('联想：打「西红柿」出番茄炒蛋（别名 + 近似字）', '番茄炒蛋' in top('西红柿'))
    check('联想：打「炒饭」出蛋炒饭（包含）', '蛋炒饭' in top('炒饭'))
    check('联想：字序不同但字大多一样也能对上（「猪肝爆炒」→ 爆炒猪肝）', '爆炒猪肝' in top('猪肝爆炒'))
    check('联想：完全不相干的不出', top('提拉米苏') == [])
    check('联想：同一道菜只出一次', len(top('宫保')) == len(set(top('宫保'))))

    calls.clear()
    dish_ai.call_deepseek = fake_api
    try:
        con = db()
        con.execute('''INSERT INTO dish_breakdowns (canonical_key, canonical_name, result_json, model)
                       VALUES ('宫保鸡丁', '宫保鸡丁', ?, 'deepseek-v4-flash')''', (GOOD,))
        con.commit()
        con.close()
        r = c.get('/dish-ai/suggest?q=' + '宫爆')
        items = r.get_json()['items']
        check('联想接口：宫爆 → 宫保鸡丁（拆过），链接是零 AI 的已有结果', r.status_code == 200 and items
              and items[0]['name'] == '宫保鸡丁' and 'known=1' in items[0]['url'], items)
        r = c.get('/dish-ai/suggest?q=' + '炒饭').get_json()['items']
        check('联想接口：站内菜标「稳厨菜谱」', any(i['name'] == '蛋炒饭' and i['label'] == '稳厨菜谱' for i in r), r)
        check('联想接口：空的输入返回空列表', c.get('/dish-ai/suggest?q=').get_json() == {'items': []})
        h = c.get('/dish-ai?known=1&dish=' + '番茄炒蛋', headers={'X-Forwarded-For': '8.1.1.1'}).get_data(as_text=True)
        check('点联想里的经验库菜（没拆过）：零 AI，用经验库', calls == [] and '规则兜底' in h and '没调 AI' in h)
        h = c.get('/dish-ai?known=1&dish=' + '蛋炒饭').get_data(as_text=True)
        check('点联想里的站内菜：零 AI，用稳厨菜谱', calls == [] and '稳厨菜谱' in h)

        h = post('宫爆鸡丁', '8.2.2.2')
        check('输入别名「宫爆鸡丁」：对到宫保鸡丁的记录，不调 AI，页面说明', calls == [] and '就是「宫保鸡丁」' in h and '没再调 AI' in h)
        h = post('鸡蛋炒饭', '8.2.2.2')
        check('输入站内菜的别名「鸡蛋炒饭」：直接用蛋炒饭菜谱，不调 AI', calls == [] and '稳厨菜谱' in h and '就是「蛋炒饭」' in h)

        def fake_canon(name):
            def f(dish, desc):
                calls.append((dish, desc))
                return dish_ai.AIReply(json.dumps(dict(json.loads(GOOD), canonical_name=name), ensure_ascii=False), USAGE, 'deepseek-flash')
            return f
        dish_ai.call_deepseek = fake_canon('宫保鸡丁')
        h = post('川味宫保鸡块', '8.3.3.3')
        con = db()
        n_rec = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        alias = con.execute("SELECT canonical_key, source, status FROM dish_aliases WHERE alias_key = '川味宫保鸡块'").fetchone()
        con.close()
        check('AI 说新叫法的标准名是宫保鸡丁：调了 1 次 AI，但不新存记录', len(calls) == 1 and n_rec == 1)
        check('新叫法记成别名，指向宫保鸡丁（来源 ai，待审核）', alias is not None and tuple(alias) == ('宫保鸡丁', 'ai', 'pending'))
        check('页面说明「稳厨之前问过，直接用那一份」、叫法待审核', '稳厨之前问过' in h and '宫保鸡丁' in h and '审核' in h)
        check('待审核的别名不进联想、不用来对齐', '川味宫保鸡块' not in dish_store.alias_map(db())
              and dish_store.resolve_alias(db(), '川味宫保鸡块') == '川味宫保鸡块'
              and all(it['name'] != '川味宫保鸡块' for it in c.get('/dish-ai/suggest?q=川味宫保鸡块').get_json()['items']))
        post('川味宫保鸡块', '8.3.3.3')
        con = db()
        n_rec2 = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        con.close()
        check('审核前同一新叫法再来：会再问一次 AI，但照样去重、不新存', len(calls) == 2 and n_rec2 == n_rec)
        con = db()
        check('待审核列表里有它；审核通过后变成生效', ('川味宫保鸡块', '宫保鸡丁') in [p[:2] for p in dish_store.pending_aliases(con)]
              and dish_store.review_alias(con, '川味宫保鸡块', approve=True))
        con.close()
        post('川味宫保鸡块', '8.3.3.3')
        check('审核通过后：靠别名直接命中，不再调 AI', len(calls) == 2)
        con = db()
        dish_store.add_alias(con, '宫保鸡块块', '宫保鸡丁', 'ai')
        con.commit()
        check('审核不通过：直接删掉', dish_store.review_alias(con, '宫保鸡块块', approve=False)
              and con.execute("SELECT COUNT(*) FROM dish_aliases WHERE alias_key = '宫保鸡块块'").fetchone()[0] == 0)
        check('种子别名默认生效', con.execute("SELECT COUNT(*) FROM dish_aliases WHERE source = 'seed' AND status != 'active'").fetchone()[0] == 0)
        con.close()

        dish_ai.call_deepseek = fake_canon('地三鲜')
        calls.clear()
        post('东北地三鲜', '8.4.4.4')
        con = db()
        rec = con.execute("SELECT canonical_name FROM dish_breakdowns WHERE canonical_key = '地三鲜'").fetchone()
        con.close()
        check('全新的菜：按 AI 给的标准名「地三鲜」存一条，用户的叫法记成待审核别名', rec is not None and rec[0] == '地三鲜'
              and ('东北地三鲜', '地三鲜') in [p[:2] for p in dish_store.pending_aliases(db())]
              and dish_store.resolve_alias(db(), '东北地三鲜') == '东北地三鲜')
        post('地三鲜', '8.4.4.4')
        check('之后直接打标准名也命中，不调 AI', len(calls) == 1)
        dish_ai.call_deepseek = fake_canon('蛋炒饭')
        h = post('黄金炒饭', '8.4.4.4')
        con = db()
        n_site = con.execute("SELECT COUNT(*) FROM dish_breakdowns WHERE canonical_key = '蛋炒饭'").fetchone()[0]
        con.close()
        con = db()
        approved = dish_store.review_alias(con, '黄金炒饭')
        con.close()
        check('AI 认出是站内菜：不另存记录，叫法待审核；审核后直接用菜谱', n_site == 0 and approved
              and dish_store.resolve_alias(db(), '黄金炒饭') == '蛋炒饭' and '稳厨菜谱里的「蛋炒饭」' in h)

        dish_ai.call_deepseek = fake_canon('宫保鸡丁')
        calls.clear()
        con = db()
        n_before = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        con.close()
        h = post('宫保鸡丁', '8.5.5.5', desc='家里没有炒锅，只有平底锅')
        con = db()
        n_after = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        con.close()
        check('个性化条件（没有炒锅）：不复用记录，带着说明单独调 AI', len(calls) == 1 and '没有炒锅' in calls[0][1])
        check('个性化结果不存进菜谱库', n_after == n_before)
        check('页面说明按条件单独拆、不存', '单独请 AI 查了一次' in h and '不存进菜谱库' in h)
        h = post('蛋炒饭', '8.5.5.5', desc='想用空气炸锅')
        check('站内菜 + 个性化条件：也不套菜谱，单独调 AI', len(calls) == 2 and '稳厨菜谱：站内' not in h)
        calls.clear()
        h = post('宫保鸡丁', '8.5.5.5', desc='少放点盐')
        check('口味要求（少放盐）：复用记录，不调 AI', calls == [] and '没再调 AI' in h)
        check('个性化判断：没有炒锅 / 用空气炸锅 / 不油炸 / 素食 算；不要太辣 / 甜一点 不算',
              all(dish_match.personal_reason(d) for d in ['没有炒锅', '想用空气炸锅', '不要油炸', '我吃素食'])
              and not any(dish_match.personal_reason(d) for d in ['不要太辣', '甜一点', '少放盐', '']))

        con = db()
        texts = ' '.join(str(v) for row in con.execute('SELECT * FROM dish_breakdowns') for v in row)
        texts += ' '.join(str(v) for row in con.execute('SELECT * FROM dish_aliases') for v in row)
        con.close()
        check('隐私：补充说明（没有炒锅、少放点盐、不要太辣）一个字都没存进库',
              all(w not in texts for w in ['没有炒锅', '少放点盐', '不要太辣', '空气炸锅']))
    finally:
        dish_ai.call_deepseek = orig

    print('9. 旧表迁移（按说明存的旧记录 → 一个标准名一条、不存说明）')
    mig = sqlite3.connect(':memory:')
    mig.row_factory = sqlite3.Row
    mig.execute('''CREATE TABLE dish_breakdowns (id INTEGER PRIMARY KEY AUTOINCREMENT, dish_key TEXT, dish_name TEXT,
                   description TEXT, result_json TEXT, mode TEXT, model TEXT, api_model TEXT, prompt_tokens INTEGER,
                   completion_tokens INTEGER, cache_hit_tokens INTEGER, cache_miss_tokens INTEGER, total_tokens INTEGER,
                   created_at TEXT DEFAULT (datetime('now')))''')
    for key, name, desc in [('宫保鸡丁', '宫保鸡丁', ''), ('宫爆鸡丁', '宫爆鸡丁', ''), ('番茄炒蛋', '番茄炒蛋', '想少放油，做给小朋友吃'),
                            ('红烧肉', '红烧肉', '')]:
        mig.execute("INSERT INTO dish_breakdowns (dish_key, dish_name, description, result_json, mode, model, prompt_tokens) "
                    "VALUES (?, ?, ?, ?, 'AI+规则', 'deepseek-v4-flash', 300)", (key, name, desc, GOOD))
    dish_store.init_tables(mig)
    dish_store.init_tables(mig)  # 再跑一次也不出错
    cols = [r[1] for r in mig.execute('PRAGMA table_info(dish_breakdowns)')]
    names_ = sorted(r[0] for r in mig.execute('SELECT canonical_name FROM dish_breakdowns'))
    check('迁移后是新表结构，没有说明列', cols == dish_store.BREAKDOWN_COLS)
    check('写了说明的旧记录丢掉；宫爆鸡丁并进宫保鸡丁，一个标准名一条', names_ == ['宫保鸡丁', '红烧肉'], names_)
    check('迁移保留用量', mig.execute("SELECT prompt_tokens FROM dish_breakdowns WHERE canonical_key='红烧肉'").fetchone()[0] == 300)
    mig.close()

    print('10. 页面：只有一个输入框')
    h = c.get('/dish-ai').get_data(as_text=True)
    check('只有一个菜名输入框，带联想', h.count('name="dish"') == 1 and 'id="dish-suggest"' in h and '/static/ask.js' in h
          and '/dish-ai/suggest' in open(os.path.join(ROOT, 'static', 'ask.js'), encoding='utf-8').read())
    check('没有单独的「选稳厨已验证的菜」入口', '选稳厨已验证' not in h)
    check('不开 JS 也能提交：普通表单 POST', 'method="post" action="/dish-ai"' in h)
    h = post('宫保鸡块饭', '8.6.6.6', rules_only='1')
    check('没对上已有菜时，页面列出相近的已有菜（不靠 JS）', '相近的稳厨已有菜' in h and '宫保鸡丁' in h)
    reply = dish_ai.call_deepseek('x', '', api_key='sk-test-not-real', opener=lambda req, timeout: FakeResp(json.dumps(
        {'model': 'deepseek-v4-flash', 'usage': USAGE, 'choices': [{'message': {'content': GOOD}}]}).encode('utf-8')))
    check('调 DeepSeek 时把 usage 和模型名带回来', reply.usage == USAGE and reply.model == 'deepseek-v4-flash' and reply == GOOD)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print(f'通过 {passed} 项，失败 {len(failed)} 项')
if failed:
    print('失败的项：' + '；'.join(failed))
sys.exit(1 if failed else 0)
