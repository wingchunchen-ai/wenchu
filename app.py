from flask import Flask, render_template, request, session, redirect, flash, send_from_directory#引入网站和显示页面的功能，flash 用来给下一页带一句提示
import os#拼路径、读环境变量
import uuid#给上传的图片起一个不会重名的文件名
import sqlite3#引入sql数据库
# 数据库文件：默认就是和 app.py 放在一起的 厨房数据库.sqlite3
# 也可以用环境变量 WENCHU_DB 指定别的路径（测试时用临时库副本，不弄脏交付库）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('WENCHU_DB', os.path.join(BASE_DIR, '厨房数据库.sqlite3'))
# 上传的菜品图存这里（默认 static/uploads），网址统一是 /uploads/文件名
UPLOAD_DIR = os.environ.get('WENCHU_UPLOAD_DIR', os.path.join(BASE_DIR, 'static', 'uploads'))
# 现成的 12 道菜：标记成官方菜，网页上不能被删掉
OFFICIAL_NAMES = ['可乐鸡翅', '芥末虾球', '巧克力慕斯蛋糕', '干锅花菜', '熔岩吐司', '生啫鱿鱼',
                  '秘制土豆鸡腿饭', '龙虾面', '赛螃蟹', '爆炒猪肝', '奶油蘑菇意面', '蛋炒饭']
def get_db():#定义函数get_db
    conn = sqlite3.connect(DB_PATH, timeout=10)#连接sqlite3，最多等 10 秒，别一碰就“库被锁”
    conn.row_factory = sqlite3.Row#按照列名取数据
    return conn#返回conn
# 建表函数：启动时自动建好需要的表，已经建过的表不会重复建
def init_db():
    # 连库
    conn = get_db()
    try:
        # users 表：存昵称、锅具清单和头像
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            cookware TEXT,
            avatar TEXT
        )''')
        # 旧库的 users 表可能没有 avatar 列（线上画像保存 500 就是这个原因），没有就补上
        user_cols = [r['name'] for r in conn.execute('PRAGMA table_info(users)')]
        if 'avatar' not in user_cols:
            conn.execute('ALTER TABLE users ADD COLUMN avatar TEXT')
        # recipes 表是作者提前建好的；旧库可能缺后来加的列，缺哪列补哪列
        recipe_cols = [r['name'] for r in conn.execute('PRAGMA table_info(recipes)')]
        for col, col_type in [('time_minutes', 'INTEGER'), ('image', 'TEXT'), ('user_id', 'INTEGER'),
                              ('tools_list', 'TEXT'), ('ingredients_list', 'TEXT'),
                              ('is_official', 'INTEGER DEFAULT 0')]:
            if recipe_cols and col not in recipe_cols:
                conn.execute(f'ALTER TABLE recipes ADD COLUMN {col} {col_type}')
                if col == 'is_official':  # 第一次加这列时，把现成的 12 道菜标成官方菜
                    marks = ','.join('?' for _ in OFFICIAL_NAMES)
                    conn.execute(f'UPDATE recipes SET is_official = 1 WHERE name IN ({marks})', OFFICIAL_NAMES)
        # questions 表：存对菜谱的质疑
        # recipe_id 是被质疑的菜，user_id 是提问的人，question_text 是质疑内容
        # created_at 是提问时间，建表时自动填现在时间，插入时不用写这一列
        conn.execute('''CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            question_text TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )''')
        # verdicts 表：存别人对质疑的裁决
        conn.execute('''CREATE TABLE IF NOT EXISTS verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL REFERENCES questions(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            verdict TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )''')
        # recommend_votes 表：存点赞点踩，一个人对一道菜只算一票（原来代码在用，但没写建表）
        conn.execute('''CREATE TABLE IF NOT EXISTS recommend_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote TEXT NOT NULL CHECK (vote IN ('like', 'dislike')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (recipe_id, user_id)
        )''')
        # 提交建表
        conn.commit()
    finally:
        conn.close()#不管成没成功都关库
app = Flask(__name__)#创建flask应用
# 密钥：线上请在环境变量 SECRET_KEY 里设一个长的随机字符串；没设就用演示用的固定字符串
app.secret_key = os.environ.get('SECRET_KEY', 'wenchu')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 上传最大 5MB，再大就提示换小图
ALLOWED_IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
# 时间三档，列表页和筛选共用
TIME_FILTERS = ['15分钟以内', '15到30分钟', '30分钟以上']
def current_user():
    # 取当前登录的人（填过画像才有），没有就返回 None
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = get_db()
    try:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    finally:
        conn.close()
    if user is None:
        session.pop('user_id', None)  # 浏览器记着的人在库里已经没了（比如换过库），当成没登录
    return user
def user_cookware(user):
    # 把存的锅具文本按逗号拆成列表，没存过就是空列表
    if not user or not user['cookware']:
        return []
    return [c.strip() for c in user['cookware'].split(',') if c.strip()]
@app.context_processor
def inject_user():
    # 每个模板都能用 me（当前用户），底部导航、提示语要用；查库出错也不要连错误页都打不开
    try:
        return {'me': current_user()}
    except sqlite3.Error:
        return {'me': None}
def vote_stats(conn):
    # 取每道菜的点赞点踩数，返回 {菜id: {'likes':赞数, 'total':总票数, 'rate':好评率}}
    rows = conn.execute(
        "SELECT recipe_id, SUM(CASE WHEN vote = 'like' THEN 1 ELSE 0 END) AS likes, COUNT(*) AS total FROM recommend_votes GROUP BY recipe_id"
    ).fetchall()
    stats = {}
    for r in rows:
        stats[r['recipe_id']] = {
            'likes': r['likes'], 'total': r['total'],
            'rate': round(r['likes'] / r['total'] * 100) if r['total'] else None,
        }
    return stats
@app.route('/')#首页地址
def home():#定义home函数
    return render_template('index.html')
def list_recipes(only_normal, base_path, title):
    # 总菜谱和正常菜谱共用：都能搜索、按分类、按时间筛，不用先填画像
    # only_normal=True 时只显示没被质疑的菜
    category = request.args.get('category', '')  # 分类名
    time_filter = request.args.get('time', '')  # 时间档
    q = request.args.get('q', '').strip()  # 搜索框里的关键词
    query = '''SELECT recipes.id, recipes.name, recipes.description, recipes.time_minutes, recipes.image,
               cooking_categories.category AS category
               FROM recipes LEFT JOIN cooking_categories ON recipes.template_id = cooking_categories.template_id'''
    conditions = []
    params = []
    if q:  # 菜名里带这个词的才留下来
        conditions.append('recipes.name LIKE ?')
        params.append('%' + q + '%')
    if only_normal:  # 只显示没有被质疑的菜（有质疑的去质疑区）
        conditions.append('recipes.id NOT IN (SELECT recipe_id FROM questions)')
    if category:
        conditions.append('cooking_categories.category = ?')
        params.append(category)
    if time_filter == '15分钟以内':
        conditions.append('recipes.time_minutes <= 15')
    elif time_filter == '15到30分钟':
        conditions.append('recipes.time_minutes BETWEEN 16 AND 30')
    elif time_filter == '30分钟以上':
        conditions.append('recipes.time_minutes > 30')
    if conditions:  # 多个条件用 AND 连起来（必须同时满足）
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY recipes.id'  # 按 id 排序，保证列表顺序固定
    conn = get_db()
    try:
        recipes_list = [dict(r) for r in conn.execute(query, params).fetchall()]
        stats = vote_stats(conn)
        categories = [r['category'] for r in conn.execute('SELECT category FROM cooking_categories ORDER BY template_id')]
    finally:
        conn.close()
    for r in recipes_list:  # 把好评率和人数挂到每道菜上
        v = stats.get(r['id'], {'likes': 0, 'total': 0, 'rate': None})
        r.update(v)
    return render_template('recipes.html', recipes=recipes_list, base_path=base_path, title=title,
                           categories=categories, time_filters=TIME_FILTERS,
                           q=q, category=category, time_filter=time_filter)
# 总表：全部菜谱，不管有没有被质疑
@app.route('/all')
def all_recipes():
    return list_recipes(False, '/all', '总菜谱')
# 正常菜谱：没被质疑的菜，也能搜索和分类筛选；不再要求先填画像
@app.route('/recipes')
def recipes():
    return list_recipes(True, '/recipes', '正常菜谱')
# 菜谱详情路由：网址是 /recipe/1、/recipe/2 这样，数字就是菜的 id
@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    conn = get_db()
    try:
        recipe = conn.execute('''SELECT recipes.*, cooking_categories.category AS category FROM recipes
            LEFT JOIN cooking_categories ON recipes.template_id = cooking_categories.template_id
            WHERE recipes.id = ?''', (recipe_id,)).fetchone()
        steps = conn.execute('SELECT * FROM recipe_steps WHERE recipe_id = ? ORDER BY step_no', (recipe_id,)).fetchall()
        # 这道菜已经有的质疑，详情页上列出来，能点进去站队
        questions = conn.execute('''SELECT q.id, q.question_text, q.created_at, u.nickname
            FROM questions q LEFT JOIN users u ON q.user_id = u.id
            WHERE q.recipe_id = ? ORDER BY q.id DESC''', (recipe_id,)).fetchall()
        stats = vote_stats(conn).get(recipe_id, {'likes': 0, 'total': 0, 'rate': None})
    finally:
        conn.close()
    if recipe is None:
        return render_template('error.html', message='这道菜不存在，可能已经被删掉了。'), 404
    return render_template('recipe_detail.html', recipe=recipe, steps=steps, questions=questions, stats=stats)
# 存质疑的路由
@app.route('/question', methods=['POST'])
def ask_question():
    recipe_id = request.form.get('recipe_id', type=int)
    question_text = (request.form.get('question_text') or '').strip()
    if not recipe_id:
        return render_template('error.html', message='没找到要质疑的菜。'), 400
    # 没填过画像不能提问，但不把人踢走：回到这道菜，告诉他原因
    if not current_user():
        flash('请先保存厨房画像，再来提交质疑。')
        return redirect(f'/recipe/{recipe_id}')
    if not question_text:
        flash('质疑内容不能是空的。')
        return redirect(f'/recipe/{recipe_id}')
    conn = get_db()
    try:
        if conn.execute('SELECT id FROM recipes WHERE id = ?', (recipe_id,)).fetchone() is None:
            return render_template('error.html', message='这道菜不存在，可能已经被删掉了。'), 404
        cursor = conn.execute('INSERT INTO questions (recipe_id, user_id, question_text) VALUES (?, ?, ?)',
                              (recipe_id, session['user_id'], question_text))
        question_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    flash('质疑已提交，大家可以来站队了。')
    return redirect(f'/question/{question_id}')  # 存完直接去这条质疑的站队页
# 质疑区列表路由
@app.route('/questions')
def question_list():
    conn = get_db()
    try:
        # 查所有质疑，按提问时间从新到旧排；用 LEFT JOIN，提问人被删了也不丢质疑
        questions = conn.execute('''SELECT q.id, q.question_text, q.created_at, q.recipe_id,
            r.name AS recipe_name, u.nickname
            FROM questions q
            JOIN recipes r ON q.recipe_id = r.id
            LEFT JOIN users u ON q.user_id = u.id
            ORDER BY q.created_at DESC, q.id DESC''').fetchall()
    finally:
        conn.close()
    return render_template('questions.html', questions=questions)
# 质疑详情路由
@app.route('/question/<int:question_id>')
def question_detail(question_id):
    conn = get_db()
    try:
        question = conn.execute('''SELECT q.id, q.question_text, q.created_at, q.recipe_id,
            r.name AS recipe_name, u.nickname
            FROM questions q
            JOIN recipes r ON q.recipe_id = r.id
            LEFT JOIN users u ON q.user_id = u.id
            WHERE q.id = ?''', (question_id,)).fetchone()
        # 查这条质疑的票数：确实有错多少票、质疑不对多少票
        counts = conn.execute('''SELECT verdict, COUNT(*) AS num
            FROM verdicts WHERE question_id = ? GROUP BY verdict''',
            (question_id,)).fetchall()
    finally:
        conn.close()
    if question is None:
        return render_template('error.html', message='这条质疑不存在。'), 404
    return render_template('question_detail.html', question=question, counts=counts)
VERDICTS = ('确实有错', '质疑不对')
# 存裁决的路由
@app.route('/verdict', methods=['POST'])
def save_verdict():
    question_id = request.form.get('question_id', type=int)
    verdict = request.form.get('verdict')
    if not question_id or verdict not in VERDICTS:
        return render_template('error.html', message='站队信息不完整，请回到质疑页重新点一次。'), 400
    if not current_user():
        flash('请先保存厨房画像，再来站队。')
        return redirect(f'/question/{question_id}')
    user_id = session['user_id']
    conn = get_db()
    try:
        if conn.execute('SELECT id FROM questions WHERE id = ?', (question_id,)).fetchone() is None:
            return render_template('error.html', message='这条质疑不存在。'), 404
        # 先查这个人之前给这条质疑投过没有，没投过就是 None
        old = conn.execute('SELECT verdict FROM verdicts WHERE question_id = ? AND user_id = ?',
                           (question_id, user_id)).fetchone()
        conn.execute('DELETE FROM verdicts WHERE question_id = ? AND user_id = ?', (question_id, user_id))
        if old is not None and old['verdict'] == verdict:
            msg = '已撤回你的站队。'  # 点了和上次一样的按钮，就是撤回
        else:
            conn.execute('INSERT INTO verdicts (question_id, user_id, verdict) VALUES (?, ?, ?)',
                         (question_id, user_id, verdict))
            msg = f'已记下你的站队：{verdict}。'
        conn.commit()
    finally:
        conn.close()
    flash(msg)
    return redirect(f'/question/{question_id}')
AVATARS = ['🍳', '👨‍🍳', '👩‍🍳', '🐱', '🐶', '🦊', '🐼', '🎃']
POTS = ['炒锅', '电饭煲', '微波炉', '空气炸锅', '蒸锅', '平底锅']  # 画像页能选、推荐要检查的六种锅
@app.route('/profile', methods=['GET', 'POST'])  # 画像页，GET 显示，POST 保存
def profile():  # 处理画像的函数
    if request.method == 'POST':  # 保存
        nickname = (request.form.get('nickname') or '').strip()  # 取昵称输入框的值
        if not nickname:
            flash('请先填写昵称。')
            return redirect('/profile?edit=1')
        cookware_list = [c for c in request.form.getlist('cookware') if c in POTS]  # 取所有勾上的锅具
        cookware_str = ','.join(cookware_list)  # 拼成逗号隔开的文本，存进数据库
        avatar = request.form.get('avatar') or '🍳'  # 取选中的头像，没选就默认
        if avatar not in AVATARS:
            avatar = '🍳'
        conn = get_db()
        try:
            user_id = session.get('user_id')
            updated = 0
            if user_id:  # 老用户改画像，更新这一行
                updated = conn.execute('UPDATE users SET nickname=?, cookware=?, avatar=? WHERE id=?',
                                       (nickname, cookware_str, avatar, user_id)).rowcount
            if not updated:  # 新用户（或库里已经找不到这个人），插入一行
                cursor = conn.execute('INSERT INTO users (nickname, cookware, avatar) VALUES (?, ?, ?)',
                                      (nickname, cookware_str, avatar))
                session['user_id'] = cursor.lastrowid  # 把用户 id 写进 session，浏览器会记住
            conn.commit()
        except sqlite3.Error:
            flash('保存失败，请稍后再试。')
            return redirect('/profile?edit=1')
        finally:
            conn.close()
        if cookware_list:
            flash('画像已保存。')
        else:
            flash('画像已保存。还没选锅具的话，推荐会不准，可以随时回来补选。')
        return redirect('/profile')  # 保存完回画像页，看保存好的样子
    # GET：读出当前用户的数据，传给模板显示
    user = current_user()
    edit = request.args.get('edit') == '1'  # 网址里有 ?edit=1 就是点更改进来的
    return render_template('profile.html', user=user, edit=edit, user_cookware=user_cookware(user),
                           avatars=AVATARS)
@app.route('/recommend')  # 推荐页的网址
def recommend():  # 处理推荐页的函数
    user = current_user()
    my_cookware = user_cookware(user)
    if not user or not my_cookware:  # 没填画像或没选锅具：不跳走，页面上说明一下
        return render_template('recommend.html', need_profile=True, can_make=[], cannot_make=[], user_cookware=my_cookware)
    conn = get_db()
    try:
        recipes = conn.execute('SELECT * FROM recipes ORDER BY id').fetchall()
        can_make = []  # 能做的菜，放这里
        cannot_make = []  # 做不了的菜，放这里
        for recipe in recipes:  # 一道一道过所有菜
            steps = conn.execute('SELECT tools FROM recipe_steps WHERE recipe_id = ?', (recipe['id'],)).fetchall()
            tools_text = ' '.join(s['tools'] for s in steps if s['tools'])  # 把这道菜所有步骤的工具拼起来
            if recipe['tools_list']:
                tools_text += ' ' + recipe['tools_list']
            missing = [pot for pot in POTS if pot in tools_text and pot not in my_cookware]  # 这道菜提到了、但用户没有的锅
            if missing:
                cannot_make.append((recipe, missing))
            else:
                can_make.append(recipe)
    finally:
        conn.close()
    return render_template('recommend.html', need_profile=False, can_make=can_make, cannot_make=cannot_make, user_cookware=my_cookware)
def get_categories():
    # 从数据库读 8 个分类，上传和编辑的下拉框用
    conn = get_db()
    try:
        return conn.execute('SELECT template_id, category FROM cooking_categories ORDER BY template_id').fetchall()
    finally:
        conn.close()
def read_recipe_form():
    # 把上传 / 编辑表单读成 (菜的信息, 步骤列表, 出错原因列表)，两边共用一套检查
    f = request.form
    data = {
        'name': (f.get('name') or '').strip(),
        'description': (f.get('description') or '').strip(),
        'template_id': f.get('template_id', type=int),
        'time_minutes': (f.get('time_minutes') or '').strip(),
        'ingredients_list': (f.get('ingredients_list') or '').strip(),
        'tools_list': (f.get('tools_list') or '').strip(),
        'summary_safety_tip': (f.get('summary_safety_tip') or '').strip(),
    }
    titles = f.getlist('step_title')
    actions = f.getlist('step_action')
    tools = f.getlist('step_tools')
    usages = f.getlist('step_tool_usage')
    tips = f.getlist('step_safety_tip')
    steps = []
    for i in range(max(len(titles), len(actions), len(tools), len(usages), len(tips))):
        def pick(lst):
            return (lst[i] if i < len(lst) else '').strip()
        step = {'title': pick(titles), 'action': pick(actions), 'tools': pick(tools),
                'tool_usage': pick(usages), 'safety_tip': pick(tips)}
        if any(step.values()):  # 整步都空着的就当没写
            steps.append(step)
    errors = []
    if not data['name']:
        errors.append('请填写菜名')
    elif len(data['name']) > 40:
        errors.append('菜名最多 40 个字')
    valid_ids = [c['template_id'] for c in get_categories()]
    if data['template_id'] not in valid_ids:
        errors.append('请选一个分类')
    if data['time_minutes']:
        if not data['time_minutes'].isdigit() or not (1 <= int(data['time_minutes']) <= 1440):
            errors.append('大概时间请填 1 到 1440 之间的整数（分钟）')
    if not steps:
        errors.append('至少写一步做法')
    elif any(not st['action'] for st in steps):
        errors.append('每一步都要写「做什么」')
    data['time_minutes'] = int(data['time_minutes']) if data['time_minutes'].isdigit() else None
    if not data['summary_safety_tip']:  # 没写整体安全提示，就用第一步的安全提示
        data['summary_safety_tip'] = next((st['safety_tip'] for st in steps if st['safety_tip']), '')
    return data, steps, errors
def save_image(image_file):
    # 存上传的菜品图，返回 (网址, 出错原因)。没传图返回 (None, None)
    if not image_file or not image_file.filename:
        return None, None
    ext = os.path.splitext(image_file.filename)[1].lower()  # 中文文件名也能拿到后缀
    if ext not in ALLOWED_IMAGE_EXT:
        return None, '图片只支持 jpg、png、webp、gif'
    head = image_file.stream.read(16)  # 看文件开头几个字节，确认真的是图片
    image_file.stream.seek(0)
    is_image = (head.startswith(b'\xff\xd8\xff') or head.startswith(b'\x89PNG') or
                head.startswith(b'GIF8') or (head[:4] == b'RIFF' and head[8:12] == b'WEBP'))
    if not is_image:
        return None, '这个文件看起来不是图片，请换一张'
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = uuid.uuid4().hex + ('.jpg' if ext == '.jpeg' else ext)  # 随机文件名，不会互相覆盖
    image_file.save(os.path.join(UPLOAD_DIR, filename))
    return '/uploads/' + filename, None
def remove_image(image_path):
    # 删掉之前上传的图片文件（只删 /uploads/ 下的，别的不动）
    if image_path and image_path.startswith('/uploads/'):
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(image_path)))
        except OSError:
            pass
def insert_steps(conn, recipe_id, steps):
    # 按顺序写入步骤，step_no 从 1 开始
    for i, st in enumerate(steps, start=1):
        conn.execute('INSERT INTO recipe_steps (recipe_id, step_no, title, action, tools, tool_usage, safety_tip) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (recipe_id, i, st['title'] or f'第{i}步', st['action'], st['tools'], st['tool_usage'], st['safety_tip']))
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # 把上传的图片发给浏览器
    return send_from_directory(UPLOAD_DIR, filename)
@app.route('/upload', methods=['GET', 'POST'])  # 上传页的网址，GET 显示表单，POST 保存
def upload():  # 函数
    if request.method == 'POST':  # 如果是提交表单（点上传）
        data, steps, errors = read_recipe_form()  # 后台再检查一次，不能只靠浏览器拦
        image_path, image_error = (None, None)
        if not errors:
            image_path, image_error = save_image(request.files.get('image'))
        if image_error:
            errors.append(image_error)
        if errors:
            flash('没能上传：' + '；'.join(errors) + '。')
            return render_template('upload.html', form=request.form, steps=steps, categories=get_categories()), 400
        conn = get_db()
        try:
            cursor = conn.execute(
                '''INSERT INTO recipes (name, description, template_id, summary_safety_tip, image, user_id,
                   time_minutes, ingredients_list, tools_list, is_official)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''',
                (data['name'], data['description'], data['template_id'], data['summary_safety_tip'], image_path,
                 session.get('user_id'), data['time_minutes'], data['ingredients_list'], data['tools_list']))
            recipe_id = cursor.lastrowid  # 拿到刚插入的这道菜的 id
            insert_steps(conn, recipe_id, steps)
            conn.commit()
        except sqlite3.IntegrityError:  # 菜名和已有的重复了
            conn.rollback()
            remove_image(image_path)
            flash('没能上传：这个菜名已经存在，请换一个。')
            return render_template('upload.html', form=request.form, steps=steps, categories=get_categories()), 400
        finally:
            conn.close()
        if session.get('user_id'):
            flash('上传成功！')
        else:
            flash('上传成功！先保存厨房画像再上传，以后就能自己修改和删除这道菜。')
        return redirect(f'/recipe/{recipe_id}')  # 保存完跳到刚传的这道菜
    return render_template('upload.html', form={}, steps=[], categories=get_categories())  # GET 就显示空表单
@app.route('/delete/<int:recipe_id>', methods=['POST'])  # 删除菜的路由，只接受 POST
def delete_recipe(recipe_id):  # 函数，recipe_id 是要删的菜的 id
    if not current_user():
        flash('请先保存厨房画像。')
        return redirect(f'/recipe/{recipe_id}')
    conn = get_db()
    try:
        recipe = conn.execute('SELECT user_id, is_official, image FROM recipes WHERE id = ?', (recipe_id,)).fetchone()  # 查这道菜是谁传的
        if not recipe:
            flash('这道菜已经不在了。')
            return redirect('/all')
        if recipe['is_official']:  # 现成的官方菜不能在网页上删
            return render_template('error.html', message='这是稳厨自带的菜谱，不能删除。'), 403
        if recipe['user_id'] != session['user_id']:  # 不是发布者本人
            return render_template('error.html', message='只有发布者能删这道菜。'), 403
        conn.execute('DELETE FROM verdicts WHERE question_id IN (SELECT id FROM questions WHERE recipe_id = ?)', (recipe_id,))
        conn.execute('DELETE FROM questions WHERE recipe_id = ?', (recipe_id,))
        conn.execute('DELETE FROM recommend_votes WHERE recipe_id = ?', (recipe_id,))
        conn.execute('DELETE FROM recipe_steps WHERE recipe_id = ?', (recipe_id,))
        conn.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
        conn.commit()
    finally:
        conn.close()
    remove_image(recipe['image'])
    flash('已删除。')
    return redirect('/all')
@app.route('/edit/<int:recipe_id>', methods=['GET', 'POST'])  # 修改菜的路由，能改的内容和上传一样
def edit_recipe(recipe_id):  # 函数
    if not current_user():
        flash('请先保存厨房画像。')
        return redirect(f'/recipe/{recipe_id}')
    conn = get_db()
    try:
        recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
        if not recipe:
            return render_template('error.html', message='这道菜不存在，可能已经被删掉了。'), 404
        if recipe['user_id'] != session['user_id']:  # 不是发布者本人
            return render_template('error.html', message='只有发布者能改这道菜。'), 403
        if request.method == 'POST':
            data, steps, errors = read_recipe_form()
            image_path, image_error = (None, None)
            if not errors:
                image_path, image_error = save_image(request.files.get('image'))
            if image_error:
                errors.append(image_error)
            if errors:
                flash('没能保存：' + '；'.join(errors) + '。')
                return render_template('edit.html', recipe=recipe, form=request.form, steps=steps, categories=get_categories()), 400
            try:
                conn.execute('''UPDATE recipes SET name = ?, description = ?, template_id = ?, summary_safety_tip = ?,
                    time_minutes = ?, ingredients_list = ?, tools_list = ?, image = COALESCE(?, image) WHERE id = ?''',
                    (data['name'], data['description'], data['template_id'], data['summary_safety_tip'],
                     data['time_minutes'], data['ingredients_list'], data['tools_list'], image_path, recipe_id))
                conn.execute('DELETE FROM recipe_steps WHERE recipe_id = ?', (recipe_id,))  # 步骤整组换掉
                insert_steps(conn, recipe_id, steps)
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                remove_image(image_path)
                flash('没能保存：这个菜名已经存在，请换一个。')
                return render_template('edit.html', recipe=recipe, form=request.form, steps=steps, categories=get_categories()), 400
            if image_path:
                remove_image(recipe['image'])  # 换了新图，旧图删掉
            flash('修改已保存。')
            return redirect(f'/recipe/{recipe_id}')
        steps = [dict(r) for r in conn.execute('SELECT title, action, tools, tool_usage, safety_tip FROM recipe_steps WHERE recipe_id = ? ORDER BY step_no', (recipe_id,))]
    finally:
        conn.close()
    form = dict(recipe)
    form['time_minutes'] = recipe['time_minutes'] or ''
    return render_template('edit.html', recipe=recipe, form=form, steps=steps, categories=get_categories())
@app.route('/daily_recommend')
def daily_recommend():
    # 没登录或没填锅具，返回空列表加 need_profile 标记，让弹窗显示引导语
    my_cookware = user_cookware(current_user())
    if not my_cookware:
        return {'recipes': [], 'need_profile': True}
    # 只找步骤里用了这些锅具的菜，排除被质疑的，随机取最多 3 道
    conditions = ' OR '.join('tools LIKE ?' for _ in my_cookware)
    like_params = ['%' + c + '%' for c in my_cookware]
    conn = get_db()
    try:
        rows = conn.execute(
            f'''SELECT DISTINCT recipes.id, recipes.name FROM recipes
            WHERE recipes.id NOT IN (SELECT recipe_id FROM questions)
            AND recipes.id IN (SELECT recipe_id FROM recipe_steps WHERE {conditions})
            ORDER BY RANDOM() LIMIT 3''',
            like_params
        ).fetchall()
    finally:
        conn.close()
    return {'recipes': [{'id': r['id'], 'name': r['name']} for r in rows], 'need_profile': False}
@app.route('/vote', methods=['POST'])
def vote():
    if not current_user():
        return {'ok': False, 'message': '请先保存厨房画像，再来点赞。'}, 401
    data = request.get_json(silent=True) or {}
    try:
        recipe_id = int(data.get('recipe_id'))
    except (TypeError, ValueError):
        return {'ok': False, 'message': '没找到这道菜。'}, 400
    v = data.get('vote')
    if v not in ('like', 'dislike'):
        return {'ok': False, 'message': '只能点「好吃」或「不好吃」。'}, 400
    conn = get_db()
    try:
        if conn.execute('SELECT id FROM recipes WHERE id = ?', (recipe_id,)).fetchone() is None:
            return {'ok': False, 'message': '这道菜不存在。'}, 404
        conn.execute(
            'INSERT INTO recommend_votes (recipe_id, user_id, vote) VALUES (?, ?, ?) '
            'ON CONFLICT(recipe_id, user_id) DO UPDATE SET vote = ?',
            (recipe_id, session['user_id'], v, v)
        )
        conn.commit()
        stats = vote_stats(conn).get(recipe_id)
    finally:
        conn.close()
    return {'ok': True, 'message': '已记下你的评价，谢谢！', 'stats': stats}
# 出错时给中文页面，不要让评委看到英文报错
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', message='这个页面不存在。'), 404
@app.errorhandler(413)
def too_large(e):
    return render_template('error.html', message='上传的图片太大了，请换一张小于 5MB 的图片。'), 413
@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', message='服务器出了点问题，请稍后再试。'), 500
init_db()
if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 5001)))
