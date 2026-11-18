"""手机优先改版的测试：导航按用户意图、首页大输入框、逛菜谱合并、拍照认菜（假的 AI）、分享菜谱照片、PWA、老网址。

不连网：DeepSeek 全部用假的代替。用法（在项目根目录）：
    python tests/test_mobile.py
"""
import base64
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DB = os.path.join(ROOT, '厨房数据库.sqlite3')
TMP = tempfile.mkdtemp(prefix='wenchu-mobile-')
TEST_DB = os.path.join(TMP, 'test.sqlite3')
UPLOADS = os.path.join(TMP, 'uploads')
shutil.copy(REAL_DB, TEST_DB)
os.environ['WENCHU_DB'] = TEST_DB
os.environ['WENCHU_UPLOAD_DIR'] = UPLOADS
os.environ.pop('DEEPSEEK_API_KEY', None)
os.environ.pop('DISH_AI_DAILY_CAP', None)
os.environ.pop('DISH_AI_PER_IP_DAILY', None)
sys.path.insert(0, ROOT)
real_db_hash = hashlib.md5(open(REAL_DB, 'rb').read()).hexdigest()

import app as wenchu  # noqa: E402
import dish_ai  # noqa: E402
import dish_store  # noqa: E402
import dish_vision  # noqa: E402

app = wenchu.app
app.config['TESTING'] = True
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

passed = 0
failed = []


def check(name, ok, detail=''):
    global passed
    if ok:
        passed += 1
        print(f'  [通过] {name}')
    else:
        failed.append(name)
        print(f'  [失败] {name} {detail}')


def text(r):
    return r.get_data(as_text=True)


def db():
    con = sqlite3.connect(TEST_DB)
    con.row_factory = sqlite3.Row
    return con


def jpeg_with_gps(w=2000, h=1500):
    im = Image.new('RGB', (w, h), (200, 120, 40))
    ex = im.getexif()
    ex[0x010F] = 'TestMake'
    ex[0x8825] = {1: 'N', 2: (51.0, 30.0, 0.0), 3: 'W', 4: (0.0, 7.0, 0.0)}
    buf = io.BytesIO()
    im.save(buf, 'JPEG', exif=ex.tobytes())
    return buf.getvalue()


def png_size(data):
    return struct.unpack('>II', data[16:24]) if data[:8] == b'\x89PNG\r\n\x1a\n' else None


def db_dump():
    # 整个库的文字内容（查照片有没有被存进去）
    con = sqlite3.connect(TEST_DB)
    out = []
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        for row in con.execute(f'SELECT * FROM "{t}"'):
            out.extend(v if isinstance(v, (str, bytes)) else str(v) for v in row)
    con.close()
    return out


def nav_part(html):
    m = re.search(r'<header class="topbar">.*?<nav class="bottom-nav">.*?</nav>', html, re.S)
    return m.group(0) if m else ''


class LogCatcher(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


try:
    c = app.test_client()
    anon = app.test_client()

    print('1. 导航：按用户想干什么分成 4 个')
    for url in ['/', '/recipes', '/all', '/recipe/1', '/profile', '/dish-ai', '/upload', '/questions', '/starter', '/recommend']:
        nav = nav_part(text(anon.get(url)))
        top = re.findall(r'<nav class="top-links">(.*?)</nav>', nav, re.S)
        top_links = re.findall(r'<a [^>]*>([^<]+)</a>', top[0]) if top else []
        bottom = re.findall(r'<nav class="bottom-nav">(.*?)</nav>', nav, re.S)
        tabs = re.findall(r'<a ', bottom[0]) if bottom else []
        ok = (top_links == ['问怎么做', '逛菜谱', '我的厨房'] and '＋ 分享我的菜谱' in nav and len(tabs) == 4
              and all(w in bottom[0] for w in ['问怎么做', '逛菜谱', '我的厨房', '分享我的菜谱'])
              and not any(w in nav for w in ['放心菜谱', '全部菜谱', '为我推荐', 'AI 拆菜', '拆菜', '入门备厨', '质疑区']))
        check(f'{url}：顶栏 3 个 + 分享按钮，底栏 4 格，旧名字都不在导航里', ok, (top_links, len(tabs)))
    h = text(anon.get('/recipes'))
    check('逛菜谱页：顶栏「逛菜谱」高亮', re.search(r'href="/recipes" class="active">逛菜谱', h) is not None)
    check('详情页也算逛菜谱', re.search(r'href="/recipes" class="active">逛菜谱', text(anon.get('/recipe/1'))) is not None)
    check('推荐页、入门备厨算我的厨房', all(re.search(r'href="/profile" class="active">我的厨房', text(anon.get(u))) for u in ['/recommend', '/starter']))

    print('2. 首页：今天想做什么菜？')
    h = text(anon.get('/'))
    check('大标题和一个菜名输入框（POST 到 /dish-ai）', '今天想做什么菜？' in h and h.count('name="dish"') == 1
          and 'method="post" action="/dish-ai"' in h and '这道菜怎么做 →' in h)
    check('📷拍照：accept=image/* + capture=environment', re.search(r'<input type="file" name="photo" id="photo-camera" accept="image/\*" capture="environment"', h) is not None)
    check('🖼相册：accept=image/*，不带 capture', re.search(r'<input type="file" name="photo" id="photo-album" accept="image/\*" class', h) is not None)
    check('拍照 / 相册按钮紧挨着输入框', h.index('id="dish-input"') < h.index('for="photo-camera"') < h.index('for="photo-album"') < h.index('id="ai-submit"'))
    check('照片表单 multipart POST 到 /dish-ai/photo，不开 JS 也能提交', 'action="/dish-ai/photo" enctype="multipart/form-data"' in h and '<noscript>' in h)
    check('写明照片发给 DeepSeek 认菜、不保存', 'DeepSeek' in h and '不保存' in h)
    check('输入联想脚本', '/static/ask.js' in h and 'id="dish-suggest"' in h)
    check('快捷入口：我家的锅能做啥 / 30元以内 / 15分钟 / 先买哪口锅，接到现有功能',
          all(x in h for x in ['href="/recommend"', 'href="/recipes?budget=30"', 'href="/recipes?time=15%E5%88%86%E9%92%9F%E4%BB%A5%E5%86%85"', 'href="/starter"'])
          and all(w in h for w in ['我家的锅能做啥', '30元以内', '15分钟', '先买哪口锅']))
    check('今日推荐：左右滑一排，带 👍👎，不再弹窗', 'swipe-row' in h and 'data-vote="like"' in h and 'data-vote="dislike"' in h
          and 'recommend-popup' not in h and '/static/vote.js' in h)
    check('没填锅：推全部放心菜（12 道里取 8 道）并提示去填锅', h.count('class="pick"') == 8 and '填一下锅具' in h)
    c.post('/profile', data={'nickname': '手机测试', 'cookware': ['炒锅']})
    h = text(c.get('/'))
    ids = re.findall(r'<li class="pick">\s*<a href="/recipe/(\d+)"', h)
    con = db()
    can = [str(r['id']) for r in con.execute('SELECT * FROM recipes ORDER BY id')
           if set(wenchu.shop.pots_needed(wenchu.shop.recipe_tools_text(r, con.execute('SELECT tools FROM recipe_steps WHERE recipe_id = ?', (r['id'],)).fetchall()))) <= {'炒锅'}]
    con.close()
    check('填了锅（只有炒锅）：只推能做的菜，标题写按你家的锅', ids and set(ids) <= set(can) and '按你家的锅' in h, (ids, can))
    check('同一天刷新，推荐顺序不变', re.findall(r'<li class="pick">\s*<a href="/recipe/(\d+)"', text(c.get('/'))) == ids)
    check('今日推荐接口和点赞照旧能用', c.get('/daily_recommend').status_code == 200
          and c.post('/vote', json={'recipe_id': int(ids[0]), 'vote': 'like'}).get_json()['ok'])
    check('首页三张卡：逛菜谱 / 分享我的菜谱 / 大家的疑问', all(x in h for x in ['href="/recipes"', 'href="/upload"', 'href="/questions"', '大家的疑问']))
    check('页脚：大家的疑问、先买哪口锅、数据口径（演示）→ /stats', 'class="site-foot"' in h and 'href="/stats">📊 数据口径（演示）' in h)

    print('3. 逛菜谱：放心菜谱 + 全部菜谱合成一页')
    h = text(anon.get('/recipes'))
    check('/recipes 标题是逛菜谱，「只看放心菜」开关默认打开，点了去 /all', '<h1>逛菜谱</h1>' in h and 'class="switch on" href="/all?' in h and 'aria-checked="true"' in h)
    h = text(anon.get('/all'))
    check('/all 同一页，开关关着，点了回 /recipes', '<h1>逛菜谱</h1>' in h and 'class="switch" href="/recipes?' in h and 'aria-checked="false"' in h)
    h = text(anon.get('/recipes?budget=30&q=蛋'))
    check('切换开关保留搜索和预算', re.search(r'href="/all\?q=%E8%9B%8B&(amp;)?budget=30"', h) is not None)
    c.post('/question', data={'recipe_id': 3, 'question_text': '烤箱温度好像不对'})
    check('被质疑的菜：开关开着看不到，关掉能看到', 'href="/recipe/3"' not in text(anon.get('/recipes')) and 'href="/recipe/3"' in text(anon.get('/all')))
    h = text(anon.get('/questions'))
    check('质疑区改名「大家的疑问」，列出刚提的疑问', '<h1>大家的疑问</h1>' in h and '烤箱温度好像不对' in h)
    check('逛菜谱页能点到大家的疑问', '/questions' in text(anon.get('/recipes')))

    print('4. 老网址一个不少')
    qid = db().execute('SELECT MAX(id) FROM questions').fetchone()[0]
    urls = ['/', '/recipes', '/all', '/recipe/1', '/recommend', '/starter', '/stats', '/profile', '/questions', f'/question/{qid}',
            '/upload', '/dish-ai', '/dish-ai/suggest?q=宫爆', '/daily_recommend', '/manifest.webmanifest', '/apple-touch-icon.png',
            '/static/icons/icon-192.png', '/static/icons/icon-512.png', '/static/ask.js']
    bad = [u for u in urls if c.get(u).status_code != 200]
    check('所有页面都还是 200', not bad, bad)
    h = text(c.get('/profile'))
    check('我的厨房里有「为我推荐」和「先买哪口锅（入门备厨）」', 'href="/recommend"' in h and 'href="/starter"' in h)

    print('5. 联想：站内菜直接去菜谱')
    items = anon.get('/dish-ai/suggest?q=蛋炒').get_json()['items']
    egg = next((i for i in items if i['name'] == '蛋炒饭'), None)
    check('联想到站内菜「蛋炒饭」→ /recipe/12', egg is not None and egg['url'] == '/recipe/12', items)
    items = anon.get('/dish-ai/suggest?q=宫爆').get_json()['items']
    gb = next((i for i in items if i['name'] == '宫保鸡丁'), None)
    check('联想到经验库的「宫保鸡丁」→ 现成结果（零 AI）', gb is not None and gb['url'].startswith('/dish-ai?known=1&dish='), items)

    print('6. 「这道菜怎么做」结果页：卡片竖排')
    h = text(anon.post('/dish-ai', data={'dish': '蛋炒饭'}))
    check('标题「蛋炒饭怎么做」，四张卡：食材 / 锅 / 还缺什么 / 步骤', '蛋炒饭怎么做' in h and all(x in h for x in ['🥬 要买的食材', '🍳 要用的锅', '🧾 你家还缺什么', '👣 步骤']))
    con = db()
    first_step = con.execute('SELECT action FROM recipe_steps WHERE recipe_id = 12 ORDER BY step_no').fetchone()[0]
    con.close()
    check('站内菜的步骤直接用菜谱里的', first_step in h and 'href="/recipe/12"' in h)
    check('页面上不出现「拆菜」字样（模式标签照旧写 AI+规则 / 稳厨菜谱）', '拆菜' not in h and '稳厨菜谱' in h)
    orig_deep = dish_ai.call_deepseek
    dish_ai.call_deepseek = lambda dish, desc: dish_ai.AIReply(json.dumps({
        'recognized': True, 'canonical_name': '红烧茄子', 'main': ['茄子'], 'side': ['蒜'], 'season': ['生抽'], 'methods': ['烧'],
        'cookware': [{'name': '炒锅', 'reason': '烧'}], 'tips': '茄子先煎', 'steps': ['茄子切条', '1. 煎软', '加酱汁烧入味']},
        ensure_ascii=False), {'total_tokens': 1}, 'deepseek-flash')
    try:
        h = text(anon.post('/dish-ai', data={'dish': '红烧茄子'}))
    finally:
        dish_ai.call_deepseek = orig_deep
    check('AI 的菜：显示 AI 给的步骤（去掉序号）和 AI+规则 标签', 'AI+规则' in h and '<li>煎软</li>' in h and '茄子切条' in h and '步骤由 AI 生成' in h)

    print('7. 拍照认菜（假的 AI）')
    check('上传的文件只放内存（不写临时文件）', app.request_class is wenchu.InMemoryRequest
          and isinstance(app.request_class._get_file_stream(None, 0, 'image/jpeg'), io.BytesIO))
    sent = []

    def fake_vision(reply):
        def f(b64, mime, **kw):
            sent.append((b64, mime))
            if isinstance(reply, Exception):
                raise reply
            return dish_ai.AIReply(reply, {'prompt_tokens': 261, 'completion_tokens': 29, 'total_tokens': 290}, 'deepseek-flash')
        return f
    orig_vision = dish_vision.call_vision
    text_calls = []
    dish_ai.call_deepseek = lambda *a, **k: text_calls.append(a) or (_ for _ in ()).throw(dish_ai.AIError('不该调'))
    catcher = LogCatcher()
    logging.getLogger().addHandler(catcher)
    logging.getLogger().setLevel(logging.DEBUG)
    try:
        photo = jpeg_with_gps() if Image else open(os.path.join(ROOT, 'static', 'dishes', 'recipe-12.webp'), 'rb').read()
        before_files = sorted(os.listdir(UPLOADS)) if os.path.isdir(UPLOADS) else []
        con = db()
        n_calls = con.execute('SELECT COUNT(*) FROM dish_ai_calls').fetchone()[0]
        n_rec = con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0]
        con.close()
        dish_vision.call_vision = fake_vision('{"dish_name": "蛋炒饭", "confidence": 0.98}')
        r = anon.post('/dish-ai/photo', data={'photo': [(io.BytesIO(b''), ''), (io.BytesIO(photo), 'IMG_0001.jpg')]},
                      content_type='multipart/form-data')
        h = text(r)
        check('认出站内菜：显示「看起来像 蛋炒饭」+ 把握高', r.status_code == 200 and '看起来像' in h and '蛋炒饭' in h and '把握：高' in h)
        check('必须先确认：有「对，就是它」和「不对，我来改」，「对」直接去菜谱', '对，就是它' in h and '不对，我来改' in h and 'href="/recipe/12"' in h)
        check('页面写明照片发给 DeepSeek 认菜、认完就丢、不保存', 'DeepSeek' in h and '认完就丢' in h and '不保存' in h)
        check('相册 / 拍照两个同名框：取选了文件的那个', len(sent) == 1)
        b64, mime = sent[0]
        if Image:
            im = Image.open(io.BytesIO(base64.b64decode(b64)))
            check('发给 AI 前先缩小（最长边 ≤1024），并去掉 EXIF（含 GPS）', max(im.size) <= 1024 and mime == 'image/jpeg'
                  and not im.getexif().get(0x010F) and not dict(im.getexif().get_ifd(0x8825)))
        after_files = sorted(os.listdir(UPLOADS)) if os.path.isdir(UPLOADS) else []
        dump = db_dump()
        check('照片没写进上传目录', after_files == before_files)
        check('照片没进数据库（库里找不到照片内容）', not any((isinstance(v, bytes) and len(v) > 1000) or (isinstance(v, str) and (b64[:40] in v or 'base64' in v)) for v in dump))
        con = db()
        row = con.execute('SELECT ok FROM dish_ai_calls ORDER BY id DESC LIMIT 1').fetchone()
        check('算进全站 AI 次数（记一笔、标成功），不新存菜谱记录', con.execute('SELECT COUNT(*) FROM dish_ai_calls').fetchone()[0] == n_calls + 1
              and row['ok'] == 1 and con.execute('SELECT COUNT(*) FROM dish_breakdowns').fetchone()[0] == n_rec)
        con.close()
        check('日志里没有照片内容', not any(b64[:40] in m for m in catcher.records))
        check('认菜这一步不调文字 AI', text_calls == [])

        dish_vision.call_vision = fake_vision('{"dish_name": "宫保鸡丁", "confidence": 0.6}')
        h = text(anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(photo), 'a.jpg')}, content_type='multipart/form-data'))
        check('不是站内菜：「对，就是它」把菜名交给「这道菜怎么做」（POST）', 'name="dish" value="宫保鸡丁"' in h and 'action="/dish-ai"' in h and '把握：中' in h)
        check('「不对，我来改」：有可以改菜名的输入框', 'id="fix"' in h and 'placeholder="比如 扬州炒饭"' in h)

        for label, reply, word in [('AI 出错', dish_ai.AIError('连不上 AI 服务或超时'), '连不上'),
                                   ('AI 回的不是 JSON', 'not json', '不是合格 JSON'),
                                   ('AI 没给把握', '{"dish_name": "蛋炒饭"}', '把握'),
                                   ('把握太低', '{"dish_name": "蛋炒饭", "confidence": 0.05}', '没认出'),
                                   ('看不出是菜', '{"dish_name": "", "confidence": 0.9}', '没认出')]:
            dish_vision.call_vision = fake_vision(reply)
            r = anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(photo), 'a.jpg')}, content_type='multipart/form-data')
            h = text(r)
            check(f'失败（{label}）：退回「请直接打菜名」', r.status_code == 422 and '请直接打菜名' in h and word in h
                  and 'name="dish"' in h and 'action="/dish-ai"' in h)
        n = len(sent)
        r = anon.post('/dish-ai/photo', data={}, content_type='multipart/form-data')
        check('没选照片：提示，不调 AI', r.status_code == 422 and '没收到照片' in text(r) and len(sent) == n)
        heic = b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic' + b'\x00' * 100
        r = anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(heic), 'IMG.HEIC')}, content_type='multipart/form-data')
        check('HEIC：友好提示怎么办，不调 AI', r.status_code == 422 and 'HEIC' in text(r) and '兼容性最佳' in text(r) and len(sent) == n)
        r = anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(b'GIF89a' + b'\x00' * 50), 'a.gif')}, content_type='multipart/form-data')
        check('GIF / 其他格式：提示只支持 JPG、PNG、WebP', r.status_code == 422 and '只支持 JPG、PNG、WebP' in text(r) and len(sent) == n)
        r = anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(b'\xff\xd8\xff' + b'\x00' * (5 * 1024 * 1024 + 10)), 'big.jpg')},
                      content_type='multipart/form-data')
        check('超过 5MB：中文提示换小图，不调 AI', r.status_code == 413 and '5MB' in text(r) and len(sent) == n)
        check('坏图片：提示打不开', '打不开' in text(anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(b'\xff\xd8\xff\xe0garbage'), 'x.jpg')},
                                                              content_type='multipart/form-data')) if Image else True)

        con = db()
        today = con.execute('SELECT COUNT(*) FROM dish_ai_calls WHERE day = ?', (dish_store.london_day(),)).fetchone()[0]
        con.close()
        os.environ['DISH_AI_DAILY_CAP'] = str(today)
        dish_vision.call_vision = fake_vision('{"dish_name": "蛋炒饭", "confidence": 0.98}')
        r = anon.post('/dish-ai/photo', data={'photo': (io.BytesIO(photo), 'a.jpg')}, content_type='multipart/form-data')
        check('全站每天上限到了：不调 AI，提示今天次数用完、请直接打菜名', r.status_code == 422 and len(sent) == n
              and '今天全站的 AI 次数已用完' in text(r) and '请直接打菜名' in text(r))
        os.environ.pop('DISH_AI_DAILY_CAP')
    finally:
        dish_vision.call_vision = orig_vision
        dish_ai.call_deepseek = orig_deep
        logging.getLogger().removeHandler(catcher)

    captured = {}

    class FakeResp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        captured['body'] = json.loads(req.data.decode('utf-8'))
        return FakeResp(json.dumps({'model': 'deepseek-flash', 'usage': {}, 'choices': [{'message': {'content': '{"dish_name":"蛋炒饭","confidence":0.9}'}}]}).encode())
    reply = dish_vision.call_vision('QUJD', 'image/jpeg', api_key='sk-test-not-real', opener=opener)
    body = captured['body']
    part = body['messages'][1]['content'][1]
    check('按官方看图格式发：model=deepseek-v4-flash、image_url 带 data URL、detail=low、只要 JSON',
          body['model'] == 'deepseek-v4-flash' and part['type'] == 'image_url' and part['image_url']['url'] == 'data:image/jpeg;base64,QUJD'
          and part['image_url']['detail'] == 'low' and body['response_format'] == {'type': 'json_object'})
    check('解析严格：{dish_name, confidence}', dish_vision.parse_guess(reply) == {'dish_name': '蛋炒饭', 'confidence': 0.9})
    try:
        dish_vision.call_vision('QUJD', 'image/jpeg', api_key='')
        check('没配密钥：报「没配置 AI 密钥」', False)
    except dish_ai.AIError as e:
        check('没配密钥：报「没配置 AI 密钥」，不连网', '没配置' in str(e))
    src = open(os.path.join(ROOT, 'dish_vision.py'), encoding='utf-8').read()
    check('代码里没有 pro 模型、不写死密钥、不打印 / 不写日志', 'v4-pro' not in src and 'sk-' not in src and 'print(' not in src and 'logging' not in src)

    print('8. 分享我的菜谱：照片优先，勾了同意才存')
    h = text(anon.get('/upload'))
    check('照片区在最前面：📷拍成品照（capture）+ 🖼从相册选', h.index('class="photo-first"') < h.index('name="name"')
          and re.search(r'name="image" id="image-camera" accept="image/\*" capture="environment"', h) and 'id="image-album" accept="image/*"' in h)
    check('有「同意公开这张照片」勾选，写明不发给 AI', 'name="photo_consent"' in h and '同意把这张照片作为菜谱图公开展示' in h and '不会发给 AI' in h)
    check('标题改成「分享我的菜谱」', '<h1>分享我的菜谱</h1>' in h)
    sent.clear()
    dish_vision.call_vision = fake_vision('{"dish_name": "x", "confidence": 1}')
    deep_calls = []
    dish_ai.call_deepseek = lambda *a, **k: deep_calls.append(a)
    try:
        img = jpeg_with_gps(800, 600) if Image else b'\xff\xd8\xff' + b'\x00' * 100
        base = {'template_id': '3', 'step_action': ['炒']}
        r = c.post('/upload', data=dict(base, name='没勾同意', image=(io.BytesIO(img), 'a.jpg')), content_type='multipart/form-data', follow_redirects=True)
        con = db()
        row = con.execute("SELECT image FROM recipes WHERE name = '没勾同意'").fetchone()
        con.close()
        check('没勾同意：菜照样发出去，但照片不存，并提示', row is not None and row['image'] is None and '没勾「同意公开这张照片」' in text(r))
        r = c.post('/upload', data=dict(base, name='勾了同意', photo_consent='1', image=[(io.BytesIO(b''), ''), (io.BytesIO(img), 'b.jpg')]),
                   content_type='multipart/form-data')
        con = db()
        row = con.execute("SELECT image FROM recipes WHERE name = '勾了同意'").fetchone()
        con.close()
        check('勾了同意：照片存下（随机文件名）', row is not None and re.match(r'^/uploads/[0-9a-f]{32}\.jpg$', row['image'] or ''))
        if Image and row and row['image']:
            saved = Image.open(os.path.join(UPLOADS, os.path.basename(row['image'])))
            check('存下的照片没有 EXIF / GPS', not saved.getexif().get(0x010F) and not dict(saved.getexif().get_ifd(0x8825)))
        check('分享的照片不发给 AI', sent == [] and deep_calls == [])
        r = c.post('/upload', data=dict(base, name='苹果照片', photo_consent='1', image=(io.BytesIO(b'\x00' * 50), 'IMG_1.HEIC')),
                   content_type='multipart/form-data')
        check('HEIC 照片：友好提示，不 500', r.status_code == 400 and 'HEIC' in text(r))
    finally:
        dish_vision.call_vision = orig_vision
        dish_ai.call_deepseek = orig_deep

    print('9. 添加到主屏幕（PWA）')
    r = anon.get('/manifest.webmanifest')
    m = json.loads(r.get_data(as_text=True))
    sizes = {i['sizes'] for i in m['icons']}
    check('manifest：类型对、有名字、启动页、standalone、主题色', r.mimetype == 'application/manifest+json' and m['short_name'] == '稳厨'
          and m['name'] and m['start_url'].startswith('/') and m['display'] == 'standalone' and m['theme_color'] and m['background_color'])
    check('manifest：有 192 和 512 图标，没有 prefer_related_applications', {'192x192', '512x512'} <= sizes and not m.get('prefer_related_applications'))
    check('图标真的是对应尺寸的 PNG', png_size(anon.get('/static/icons/icon-192.png').data) == (192, 192)
          and png_size(anon.get('/static/icons/icon-512.png').data) == (512, 512))
    check('苹果图标 180×180', png_size(anon.get('/apple-touch-icon.png').data) == (180, 180))
    h = text(anon.get('/recipes'))
    check('每页都引用 manifest、苹果图标、主题色', 'rel="manifest" href="/manifest.webmanifest"' in h and 'rel="apple-touch-icon"' in h
          and 'name="theme-color"' in h and 'apple-mobile-web-app-title' in h)
    js = ''.join(open(os.path.join(ROOT, 'static', f), encoding='utf-8').read() for f in os.listdir(os.path.join(ROOT, 'static')) if f.endswith('.js'))
    tpl = ''.join(open(os.path.join(ROOT, 'templates', f), encoding='utf-8').read() for f in os.listdir(os.path.join(ROOT, 'templates')))
    check('不注册 service worker（不做离线缓存、不推送）', 'serviceWorker' not in js + tpl)

    print('10. 收尾')
    check('交付库一个字节都没变', hashlib.md5(open(REAL_DB, 'rb').read()).hexdigest() == real_db_hash)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print(f'通过 {passed} 项，失败 {len(failed)} 项')
if failed:
    print('失败的项：' + '；'.join(failed))
sys.exit(1 if failed else 0)
