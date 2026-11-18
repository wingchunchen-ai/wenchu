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
    check('AI 拆菜页能打开，有菜名输入框', 'name="dish"' in h and 'AI 拆菜' in h)
    check('导航里有 AI 拆菜', 'href="/dish-ai"' in c.get('/recipes').get_data(as_text=True))
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
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print(f'通过 {passed} 项，失败 {len(failed)} 项')
if failed:
    print('失败的项：' + '；'.join(failed))
sys.exit(1 if failed else 0)
