"""稳厨主路径测试：可以反复跑，不会弄脏交付库。

用法（在项目根目录）：
    pip install -r requirements.txt
    python tests/test_main_path.py

做法：把 厨房数据库.sqlite3 复制到临时文件夹，用环境变量 WENCHU_DB 指向副本，
上传的图片也存到临时文件夹；跑完自动删掉。全部通过时退出码为 0。
"""
import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from io import BytesIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DB = os.path.join(ROOT, '厨房数据库.sqlite3')
TMP = tempfile.mkdtemp(prefix='wenchu-test-')
TEST_DB = os.path.join(TMP, 'test.sqlite3')
shutil.copy(REAL_DB, TEST_DB)
os.environ['WENCHU_DB'] = TEST_DB
os.environ['WENCHU_UPLOAD_DIR'] = os.path.join(TMP, 'uploads')
sys.path.insert(0, ROOT)

real_db_hash = hashlib.md5(open(REAL_DB, 'rb').read()).hexdigest()

import app as wenchu  # noqa: E402  导入时会对临时库跑 init_db

app = wenchu.app
app.config['TESTING'] = True

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


def text(resp):
    return resp.get_data(as_text=True)


def recipe_links(html):
    return re.findall(r'href="/recipe/(\d+)">', html)


PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64

try:
    c = app.test_client()

    print('1. 看菜谱（没填画像也能看）')
    r = c.get('/')
    check('首页能打开且有标题', r.status_code == 200 and '<title>稳厨' in text(r))
    r = c.get('/all')
    check('全部菜谱 200，12 道现成菜都在', r.status_code == 200 and len(set(recipe_links(text(r)))) == 12)
    r = c.get('/recipes')
    check('放心菜谱不再跳去画像页', r.status_code == 200 and len(set(recipe_links(text(r)))) == 12, r.status_code)

    print('2. 搜索 / 分类 / 时间')
    r = c.get('/recipes?q=鸡')
    ids = set(recipe_links(text(r)))
    check('搜「鸡」只出带鸡的菜', r.status_code == 200 and ids and ids <= {'1', '7'}, ids)
    r = c.get('/all?category=快手小炒')
    check('全部菜谱也能按分类筛（快手小炒 6 道）', r.status_code == 200 and len(set(recipe_links(text(r)))) == 6)
    r = c.get('/recipes?time=15分钟以内')
    check('按时间筛 15 分钟以内', r.status_code == 200 and set(recipe_links(text(r))) == {'5', '9', '12'}, set(recipe_links(text(r))))
    r = c.get('/recipes?q=不存在的菜')
    check('搜不到时有空状态提示', '没有找到符合条件的菜谱' in text(r))

    print('3. 详情')
    r = c.get('/recipe/1')
    h = text(r)
    check('详情 200，含时间/食材/厨具/步骤', r.status_code == 200 and '30 分钟' in h and '要用的食材' in h and '要用的厨具' in h and '改刀备料' in h)
    check('详情没有 None、没有开发注释', 'None' not in h and '<!--' not in h)
    r = c.get('/recipe/9999')
    check('不存在的菜给中文 404', r.status_code == 404 and '不存在' in text(r))

    print('4. 没画像时点赞 / 质疑给中文原因')
    r = c.post('/vote', json={'recipe_id': 1, 'vote': 'like'})
    check('未登录点赞 401 + 中文提示', r.status_code == 401 and '画像' in r.get_json()['message'])
    r = c.post('/question', data={'recipe_id': 1, 'question_text': '测试'}, follow_redirects=True)
    check('未登录质疑回到详情并提示', r.status_code == 200 and '请先保存厨房画像' in text(r))

    print('5. 画像保存 + 推荐')
    r = c.post('/profile', data={'nickname': '', 'cookware': ['炒锅']}, follow_redirects=True)
    check('昵称为空不保存并提示', '请先填写昵称' in text(r))
    r = c.post('/profile', data={'nickname': '审读测试', 'cookware': ['炒锅', '平底锅'], 'avatar': '🐱'}, follow_redirects=True)
    h = text(r)
    check('画像保存成功并提示', r.status_code == 200 and '画像已保存' in h and '审读测试' in h and '🐱' in h)
    check('画像页有「去看适合我的菜」入口', '/recommend' in h and '去看适合我的菜' in h)
    r = c.get('/profile?edit=1')
    check('再进编辑页，锅具保持勾选', text(r).count('checked') >= 3)
    r = c.get('/recommend')
    h = text(r)
    check('推荐页显示能做 / 缺锅具', r.status_code == 200 and '能做的' in h and '缺锅具' in h and '蛋炒饭' in h)
    r = c.get('/daily_recommend')
    data = r.get_json()
    check('首页今日推荐接口有菜', r.status_code == 200 and len(data['recipes']) > 0 and not data['need_profile'])

    print('6. 上传：空表单 / 重名 / 坏图片 都不 500')
    r = c.post('/upload', data={'name': '', 'step_action': ''})
    check('空表单被拦下（400 + 中文原因）', r.status_code == 400 and '请填写菜名' in text(r))
    r = c.post('/upload', data={'name': '蛋炒饭', 'template_id': '3', 'step_action': ['炒']})
    check('和现成菜重名被拦下', r.status_code == 400 and '已经存在' in text(r))
    r = c.post('/upload', data={'name': '坏图测试', 'template_id': '3', 'step_action': ['炒'],
                                'image': (BytesIO(b'not an image'), 'a.jpg')}, content_type='multipart/form-data')
    check('不是图片的文件被拦下', r.status_code == 400 and '不是图片' in text(r))
    r = c.post('/upload', data={'name': '时间乱填', 'template_id': '3', 'step_action': ['炒'], 'time_minutes': 'abc'})
    check('时间不是数字被拦下', r.status_code == 400 and '整数' in text(r))
    r = c.post('/upload', data={'name': '漏写做什么', 'template_id': '3', 'step_title': ['一', '二'], 'step_action': ['炒', '']})
    check('有一步没写「做什么」被拦下', r.status_code == 400 and '做什么' in text(r))
    con = sqlite3.connect(TEST_DB)
    check('以上失败上传都没写进库', con.execute('SELECT COUNT(*) FROM recipes').fetchone()[0] == 12)
    con.close()

    print('7. 上传一道完整的菜')
    form = {
        'name': '番茄炒蛋（测试）', 'description': '酸甜下饭的家常菜', 'template_id': '3', 'time_minutes': '12',
        'ingredients_list': '番茄 2 个、鸡蛋 3 个、盐、糖、油', 'tools_list': '平底锅、碗、锅铲',
        'summary_safety_tip': '热油下锅时手离远一点',
        'step_title': ['打蛋', '炒蛋', '炒番茄'],
        'step_action': ['鸡蛋打散加一点盐', '热锅下油，倒蛋液炒到凝固盛出', '番茄炒出汁，倒回鸡蛋翻匀'],
        'step_tools': ['碗、筷子', '平底锅、锅铲', '平底锅、锅铲'],
        'step_tool_usage': ['顺一个方向搅', '中火', '中小火'],
        'step_safety_tip': ['', '油热了再下蛋，小心溅油', '番茄出汁会溅，盖一下锅盖'],
        'image': (BytesIO(PNG), '番茄炒蛋.png'),
    }
    r = c.post('/upload', data=form, content_type='multipart/form-data')
    loc = r.headers.get('Location', '')
    check('上传成功跳到新菜详情', r.status_code == 302 and loc.startswith('/recipe/'), (r.status_code, loc))
    new_id = loc.rsplit('/', 1)[-1]
    r = c.get(loc)
    h = text(r)
    check('详情显示「上传成功」', '上传成功' in h)
    check('详情有 3 步、时间、食材、厨具、分类', all(k in h for k in ['炒番茄', '12 分钟', '番茄 2 个', '平底锅、碗、锅铲', '快手小炒']))
    img = re.search(r'src="(/uploads/[0-9a-f]{32}\.png)"', h)
    check('图片用随机文件名保存并在详情显示', bool(img))
    if img:
        check('图片网址能打开', c.get(img.group(1)).status_code == 200)
    check('上传者能看到编辑入口', f'/edit/{new_id}' in h)
    r = c.get('/recipes?category=快手小炒')
    check('新菜出现在所选分类里', new_id in recipe_links(text(r)))
    r = c.get('/recipes?time=15分钟以内')
    check('新菜能被时间筛选到', new_id in recipe_links(text(r)))

    print('8. 编辑自己的菜')
    r = c.get(f'/edit/{new_id}')
    check('编辑页带出原来的步骤', r.status_code == 200 and '炒番茄' in text(r))
    edit_form = dict(form)
    edit_form.pop('image')
    edit_form['time_minutes'] = '15'
    edit_form['step_title'] = ['打蛋', '一起炒']
    edit_form['step_action'] = ['鸡蛋打散', '先炒蛋再炒番茄']
    for k in ['step_tools', 'step_tool_usage', 'step_safety_tip']:
        edit_form[k] = ['', '']
    r = c.post(f'/edit/{new_id}', data=edit_form, content_type='multipart/form-data', follow_redirects=True)
    h = text(r)
    check('编辑保存成功，步骤换成 2 步，旧图保留', '修改已保存' in h and '<h3>一起炒</h3>' in h and '<h3>炒番茄</h3>' not in h and '15 分钟' in h and '/uploads/' in h)

    print('9. 点赞 / 质疑 / 站队')
    r = c.post('/vote', json={'recipe_id': 1, 'vote': 'like'})
    check('点赞成功', r.status_code == 200 and r.get_json()['ok'])
    check('列表显示好评率', '好评率 100%（1人评价）' in text(c.get('/all')))
    r = c.post('/vote', json={'recipe_id': 'abc', 'vote': 'like'})
    check('乱传菜 id 不 500', r.status_code == 400)
    r = c.post('/question', data={'recipe_id': 1, 'question_text': ''}, follow_redirects=True)
    check('空质疑被拦下', '不能是空的' in text(r))
    r = c.post('/question', data={'recipe_id': 1, 'question_text': '可乐加太多会溢锅吗？'})
    qloc = r.headers.get('Location', '')
    check('质疑提交后跳到站队页', r.status_code == 302 and qloc.startswith('/question/'))
    r = c.get('/questions')
    check('质疑区能点进站队页', qloc in text(r))
    check('放心菜谱里不再有被质疑的菜', '1' not in recipe_links(text(c.get('/recipes'))))
    check('详情页列出已有质疑', qloc in text(c.get('/recipe/1')))
    qid = qloc.rsplit('/', 1)[-1]
    r = c.post('/verdict', data={'question_id': qid, 'verdict': '确实有错'}, follow_redirects=True)
    check('站队成功并显示票数', '确实有错：1票' in text(r) and '已记下你的站队' in text(r))
    r = c.post('/verdict', data={'question_id': qid, 'verdict': '确实有错'}, follow_redirects=True)
    check('再点一次撤回', '已撤回' in text(r) and '还没有人表态' in text(r))
    r = c.post('/verdict', data={'question_id': qid, 'verdict': '乱写'})
    check('乱写站队值不 500', r.status_code == 400)

    print('10. 安全：XSS 与权限')
    xss = '<img src=x onerror=alert(1)>'
    r = c.post('/upload', data={'name': xss, 'template_id': '3', 'step_action': ['炒'], 'step_tools': ['炒锅']})
    xid = r.headers['Location'].rsplit('/', 1)[-1]
    h = text(c.get(f'/recipe/{xid}'))
    check('详情里菜名被转义', xss not in h and '&lt;img' in h)
    idx = open(os.path.join(ROOT, 'templates', 'index.html'), encoding='utf-8').read()
    check('首页推荐不再用 innerHTML 拼菜名', "'</a>" not in idx and 'a.textContent = r.name' in idx)
    names = [x['name'] for x in c.get('/daily_recommend').get_json()['recipes']]
    check('推荐接口原样返回菜名（由前端当文字显示）', all(isinstance(n, str) for n in names))
    other = app.test_client()
    other.post('/profile', data={'nickname': '路人', 'cookware': ['炒锅']})
    check('别人不能改我的菜', other.get(f'/edit/{new_id}').status_code == 403)
    check('别人不能删我的菜', other.post(f'/delete/{new_id}').status_code == 403)
    owner = app.test_client()
    with owner.session_transaction() as s:
        s['user_id'] = 5  # 现成菜在库里记在 5 号用户名下
    r = owner.post('/delete/1')
    check('现成菜连原发布者也删不掉', r.status_code == 403 and '不能删除' in text(r))
    r = c.post(f'/delete/{xid}', follow_redirects=True)
    check('自己能删自己的菜', '已删除' in text(r) and c.get(f'/recipe/{xid}').status_code == 404)

    print('11. 旧库兼容：users 没有 avatar 列也能保存画像')
    old_db = os.path.join(TMP, 'old.sqlite3')
    shutil.copy(REAL_DB, old_db)
    con = sqlite3.connect(old_db)
    con.execute('ALTER TABLE users DROP COLUMN avatar')
    con.execute('ALTER TABLE recipes DROP COLUMN is_official')
    con.commit()
    con.close()
    saved_path = wenchu.DB_PATH
    wenchu.DB_PATH = old_db
    try:
        wenchu.init_db()
        c2 = app.test_client()
        r = c2.post('/profile', data={'nickname': '旧库用户', 'cookware': ['蒸锅'], 'avatar': '🐼'}, follow_redirects=True)
        check('旧库启动后自动补列，画像保存成功', r.status_code == 200 and '画像已保存' in text(r))
        con = sqlite3.connect(old_db)
        check('旧库现成菜自动标成官方菜', con.execute('SELECT SUM(is_official) FROM recipes').fetchone()[0] == 12)
        con.close()
    finally:
        wenchu.DB_PATH = saved_path

    print('12. 导购演示：缺的锅 / 一键备齐食材 / 入门备厨 / 点击统计')
    import json
    import shop as shopmod
    cfg = json.load(open(os.path.join(ROOT, 'shop_items.json'), encoding='utf-8'))
    allowed = tuple(p['search_url'].split('{kw}')[0] for p in cfg['platforms'].values())
    offers = [o for group in ('cookware', 'tools') for it in cfg[group].values() for o in it['offers']]
    check('六种锅都有推荐款', all(p in cfg['cookware'] for p in shopmod.POTS))
    check('每个商品都有平台、链接、参考价、是否示例',
          all(o['platform'] in cfg['platforms'] and o['url'] and o['price'] > 0 and 'is_sample' in o for o in offers))
    check('现在全部标成示例商品', all(o['is_sample'] for o in offers) and all(e['is_sample'] for e in cfg['ingredients']))
    check('链接都是平台公开搜索页（没有编造商品页）', all(o['url'].startswith(allowed) for o in offers))
    anon = app.test_client()
    r = anon.get('/recipe/5')
    h = text(r)
    check('未填画像：详情不拦人，只提示填锅具', r.status_code == 200 and '填一下家里的锅具，就能看到缺什么' in h and '还缺' not in h)
    check('未填画像也能看采购清单', '一键备齐食材' in h and '示例商品、价格仅供参考' in h)
    shopper = app.test_client()
    shopper.post('/profile', data={'nickname': '只有炒锅', 'cookware': ['炒锅']})
    h = text(shopper.get('/recipe/5'))
    check('缺空气炸锅：显示还缺 + 推荐款 + 示例标记',
          '还缺：空气炸锅' in h and '可视窗空气炸锅' in h and '示例商品' in h and '为什么适合小白' in h and '/go?kind=cookware' in h)
    h = text(shopper.get('/recipe/4'))
    check('锅都有：显示你家已有、可以直接开做', '你家已有：炒锅' in h and '都有' in h and '还缺' not in h)
    h = text(shopper.get('/recipe/1'))
    check('括号里的「蒸锅拿掉蒸笼」不算要蒸锅', '还缺：平底锅' in h and '还缺：平底锅、蒸锅' not in h)
    h = text(shopper.get('/recipe/12'))
    rows = re.findall(r'class="shop-row( done)?" data-price="(\d+)" data-name="([^"]+)"', h)
    names = [n for _, _, n in rows]
    check('采购清单列出蛋炒饭的 4 样食材', len(rows) == 4 and '鸡蛋' in names and '生抽' in names, names)
    check('调味料默认勾上「家里已有」', any(d and n == '生抽' for d, _, n in rows) and any(not d and n == '鸡蛋' for d, _, n in rows))
    check('有估算总价和去买按钮', '估算' in h and 'kind=ingredient' in h and '复制采购清单' in h)
    r = shopper.get('/go?kind=cookware&key=空气炸锅&platform=jd&from=detail&recipe=5')
    check('购买按钮跳到京东搜索页', r.status_code == 302 and r.headers['Location'].startswith('https://search.jd.com/Search?keyword='))
    r = shopper.get('/go?kind=ingredient&key=鸡蛋&platform=pdd&from=list&recipe=12')
    check('食材去买跳到拼多多搜索页', r.status_code == 302 and r.headers['Location'].startswith('https://mobile.yangkeduo.com/search_result.html?search_key='))
    r = shopper.get('/go?kind=tool&key=锅铲&platform=taobao&from=tool&recipe=4')
    check('小工具跳到淘宝搜索页', r.status_code == 302 and r.headers['Location'].startswith('https://s.taobao.com/search?q='))
    check('不存在的商品 404', shopper.get('/go?kind=cookware&key=不存在&platform=jd&from=detail').status_code == 404)
    check('乱填平台 / 入口 400', shopper.get('/go?kind=cookware&key=炒锅&platform=evil&from=detail').status_code == 400
          and shopper.get('/go?kind=cookware&key=炒锅&platform=jd&from=evil').status_code == 400)
    r = shopper.get('/go?kind=cookware&key=炒锅&platform=jd&from=detail&url=https://evil.example')
    check('不能借跳转去别的网站', r.status_code == 302 and 'evil' not in r.headers['Location'])
    r = shopper.get('/starter')
    h = text(r)
    # 前面测试上传了一道用平底锅的菜，所以按库里实际菜数来判断
    m = re.search(r'补一口(\S+?)：多做 (\d+) 道', h)
    check('入门备厨：补平底锅解锁最多且排第一', r.status_code == 200 and m and m.group(1) == '平底锅' and int(m.group(2)) >= 5
          and h.find('补一口平底锅') < h.find('补一口空气炸锅'), m and m.groups())
    m = re.search(r'只买这三件：<strong>([^<]+)</strong>，就能做稳厨里 <strong>(\d+)</strong> / (\d+) 道', h)
    check('入门三件套（炒锅、平底锅、空气炸锅）能做全部菜', m and set(m.group(1).split('、')) == {'炒锅', '平底锅', '空气炸锅'} and m.group(2) == m.group(3), m and m.groups())
    m = re.search(r'没有炒锅也能做的菜（(\d+) 道）', h)
    check('没有炒锅也能做至少 7 道', m and int(m.group(1)) >= 7, m and m.groups())
    check('入门备厨未填画像也能看', anon.get('/starter').status_code == 200 and '还没填锅具' in text(anon.get('/starter')))
    check('画像页和推荐页有入门备厨入口', '/starter' in text(shopper.get('/profile')) and '/starter' in text(shopper.get('/recommend')))
    r = shopper.get('/stats')
    h = text(r)
    check('统计页显示点击次数和点击率', r.status_code == 200 and '全部购买点击' in h and '点击率' in h and '演示数据' in h)
    con = sqlite3.connect(TEST_DB)
    check('点击记进库（4 次有效点击）', con.execute('SELECT COUNT(*) FROM shop_clicks').fetchone()[0] == 4)
    check('详情浏览也记进库', con.execute('SELECT COUNT(*) FROM recipe_views').fetchone()[0] > 0)
    con.close()

    print('13. 菜品图（AI 生成，已压缩）')
    con = sqlite3.connect(TEST_DB)
    imgs = con.execute("SELECT id, image FROM recipes WHERE is_official = 1 ORDER BY id").fetchall()
    con.close()
    check('12 道现成菜都有菜品图', len(imgs) == 12 and all(i and i.startswith('/static/dishes/') for _, i in imgs))
    sizes = [os.path.getsize(os.path.join(ROOT, i.lstrip('/'))) for _, i in imgs]
    check('图片文件都在且单张不超过 150KB', all(sz <= 150 * 1024 for sz in sizes), sizes)
    check('图片网址能打开', all(anon.get(i).status_code == 200 for _, i in imgs))
    h = text(anon.get('/all'))
    check('列表页显示菜品图', h.count('src="/static/dishes/') >= 12)
    check('详情页显示菜品图', 'src="/static/dishes/recipe-12.webp"' in text(anon.get('/recipe/12')))
    recs = shopper.get('/daily_recommend').get_json()['recipes']
    check('首页推荐带图片地址', recs and all((x['image'] or '').startswith('/static/dishes/') for x in recs if x['id'] <= 12))
    check('首页推荐弹窗会显示小图', 'rec-thumb' in open(os.path.join(ROOT, 'templates', 'index.html'), encoding='utf-8').read())

    print('14. 收尾')
    check('交付库一个字节都没变', hashlib.md5(open(REAL_DB, 'rb').read()).hexdigest() == real_db_hash)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print(f'通过 {passed} 项，失败 {len(failed)} 项')
if failed:
    print('失败的项：' + '；'.join(failed))
sys.exit(1 if failed else 0)
