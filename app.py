from flask import Flask, render_template, request, session, redirect#引入网站和显示页面的功能
import sqlite3#引入sql数据库
def get_db():#定义函数get_db
    conn = sqlite3.connect('厨房数据库.sqlite3')#连接sqlite3
    conn.row_factory = sqlite3.Row#按照列名取数据
    return conn#返回conn
# 建表函数：启动时自动建好需要的表，已经建过的表不会重复建
def init_db():
    # 连库
    conn = get_db()
    # users 表：存昵称和锅具清单
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT NOT NULL,
        cookware TEXT
    )''')
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
    # question_id 是被裁决的质疑，user_id 是投票的人，verdict 是裁决结果
    # created_at 是投票时间，建表时自动填现在时间，插入时不用写这一列
    conn.execute('''CREATE TABLE IF NOT EXISTS verdicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL REFERENCES questions(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        verdict TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )''')
    # 提交建表，关库
    conn.commit()
    conn.close()
app = Flask(__name__)#创建flask应用
app.secret_key = 'wenchu'  # 设置密钥，用固定字符串演示
@app.route('/')#首页地址
def home():#定义home函数
    return render_template('index.html')
# 总表：全部菜谱，不管有没有被质疑
@app.route('/all')
def all_recipes():
    conn = sqlite3.connect('厨房数据库.sqlite3')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, name, description, time_minutes, image FROM recipes ORDER BY id')
    recipes_list = c.fetchall()
    # 取每道菜的点赞点踩数
    vote_rows = c.execute(
        'SELECT recipe_id, SUM(CASE WHEN vote = \'like\' THEN 1 ELSE 0 END) as likes, COUNT(*) as total FROM recommend_votes GROUP BY recipe_id'
    ).fetchall()
    vote_map = {r['recipe_id']: {'likes': r['likes'], 'total': r['total']} for r in vote_rows}
    # 把好评率和人数挂到每道菜上
    recipes_list = [dict(r) for r in recipes_list]
    for r in recipes_list:
        v = vote_map.get(r['id'], {'likes': 0, 'total': 0})
        r['likes'] = v['likes']
        r['total'] = v['total']
        r['rate'] = round(v['likes'] / v['total'] * 100) if v['total'] > 0 else None
    conn.close()
    return render_template('recipes.html', recipes=recipes_list)
#分类筛选和时间筛选
@app.route('/recipes')
def recipes():# 取网址里的筛选条件，没有就返回 None
    # 如果没填画像，先跳去画像页
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/profile')
    conn = sqlite3.connect('厨房数据库.sqlite3')
    c = conn.cursor()
    c.execute('SELECT cookware FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return redirect('/profile')
    category = request.args.get('category')  # 分类名
    time_filter = request.args.get('time')  # 时间档
    # 基础查询
    query = 'SELECT recipes.id, recipes.name, recipes.description, recipes.time_minutes, recipes.image FROM recipes JOIN cooking_categories ON recipes.template_id = cooking_categories.template_id'
    #按顺序一一对应
    conditions = []
    params = []
    q = request.args.get('q', '')  # 取搜索框里的关键词
    if q:  # 如果输了关键词
        conditions.append('recipes.name LIKE ?')  # 菜名里带这个词的才留下来
        params.append('%' + q + '%')  # 前后加 %，表示模糊匹配
    # 只显示没有被质疑的菜（有质疑的去质疑区）
    conditions.append('recipes.id NOT IN (SELECT recipe_id FROM questions)')
    # 如果网址里有 category，就加一条分类条件
    if category:
        conditions.append('cooking_categories.category = ?')
        params.append(category)
    # 如果网址里有 time，就按三档加一条时间条件
    if time_filter == '15分钟以内':
        conditions.append('recipes.time_minutes <= 15')
    elif time_filter == '15到30分钟':
        conditions.append('recipes.time_minutes BETWEEN 16 AND 30')
    elif time_filter == '30分钟以上':
        conditions.append('recipes.time_minutes > 30')
    # 如果有任何条件，就拼上 WHERE，多个条件用 AND 连起来（必须同时满足）
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    # 按 id 排序，保证列表顺序固定（1 到 40，不乱）
    query += ' ORDER BY recipes.id'
    # 连库、查、关库，拿到菜列表
    conn = get_db()
    recipes_list = conn.execute(query, params).fetchall()
    # 取每道菜的点赞点踩数
    vote_rows = conn.execute(
        'SELECT recipe_id, SUM(CASE WHEN vote = \'like\' THEN 1 ELSE 0 END) as likes, COUNT(*) as total FROM recommend_votes GROUP BY recipe_id'
    ).fetchall()
    vote_map = {r['recipe_id']: {'likes': r['likes'], 'total': r['total']} for r in vote_rows}
    # 把好评率和人数挂到每道菜上
    recipes_list = [dict(r) for r in recipes_list]
    for r in recipes_list:
        v = vote_map.get(r['id'], {'likes': 0, 'total': 0})
        r['likes'] = v['likes']
        r['total'] = v['total']
        r['rate'] = round(v['likes'] / v['total'] * 100) if v['total'] > 0 else None
        conn.close()
        # 把菜列表传给 recipes.html 模板去显示
    return render_template('recipes.html', recipes=recipes_list)
# 菜谱详情路由：网址是 /recipe/1、/recipe/2 这样，数字就是菜的 id
@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    # 连库
    conn = get_db()
    # 查这一道菜（按 id 查，只取一行）
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    # 查这道菜的所有步骤
    steps = conn.execute('SELECT * FROM recipe_steps WHERE recipe_id = ? ORDER BY step_no', (recipe_id,)).fetchall()
    # 关库
    conn.close()
    # 如果查不到这道菜（id 不存在），返回“菜不存在”加 404 状态码
    if recipe is None:
        return '菜不存在', 404
    # 把菜和步骤传给 recipe_detail.html 模板去显示
    return render_template('recipe_detail.html', recipe=recipe, steps=steps)
# 存质疑的路由
@app.route('/question', methods=['POST'])
def ask_question():
    # 从表单拿数据
    recipe_id = request.form.get('recipe_id')
    question_text = request.form.get('question_text')
    # 从 session 拿当前登录用户的 id，没填过画像就是 None
    user_id = session.get('user_id')
    # 没登录就先去填画像页，登录了才能提问
    if not user_id:
        return redirect('/profile')
    # 连库
    conn = get_db()
    # 把质疑插进 questions 表，created_at 不用写，建表时设了自动填现在时间
    conn.execute('INSERT INTO questions (recipe_id, user_id, question_text) VALUES (?, ?, ?)',
                 (recipe_id, user_id, question_text))
    # 提交插入，关库
    conn.commit()
    conn.close()
    # 存完跳回这道菜的详情页
    return redirect(f'/recipe/{recipe_id}')
# 质疑区列表路由
@app.route('/questions')
def question_list():
    # 连库
    conn = get_db()
    # 查所有质疑，按提问时间从新到旧排
    # 两张表
    questions = conn.execute('''SELECT q.id, q.question_text, q.created_at, q.recipe_id,
        r.name AS recipe_name, u.nickname
        FROM questions q
        JOIN recipes r ON q.recipe_id = r.id
        JOIN users u ON q.user_id = u.id
        ORDER BY q.created_at DESC''').fetchall()
    # 关库
    conn.close()
    # 把查到的质疑列表交给模板显示
    return render_template('questions.html', questions=questions)
# 质疑详情路由
@app.route('/question/<int:question_id>')
def question_detail(question_id):
    # 连库
    conn = get_db()
    # 查这一条质疑：JOIN 两张表，拿被质疑的菜名和提问人的昵称
    question = conn.execute('''SELECT q.id, q.question_text, q.created_at, q.recipe_id,
        r.name AS recipe_name, u.nickname
        FROM questions q
        JOIN recipes r ON q.recipe_id = r.id
        JOIN users u ON q.user_id = u.id
        WHERE q.id = ?''', (question_id,)).fetchone()
    # 查这条质疑的票数：按裁决结果分组数，确实有错多少票、质疑不对多少票
    counts = conn.execute('''SELECT verdict, COUNT(*) AS num
        FROM verdicts WHERE question_id = ? GROUP BY verdict''',
        (question_id,)).fetchall()
    # 关库
    conn.close()
    # 把质疑和票数交给模板显示
    return render_template('question_detail.html', question=question, counts=counts)
# 存裁决的路由
@app.route('/verdict', methods=['POST'])
def save_verdict():
    # 从表单拿数据
    question_id = request.form.get('question_id')
    verdict = request.form.get('verdict')
    # 从 session 拿当前登录用户的 id，没填过画像就是 None
    user_id = session.get('user_id')
    # 没登录就先去填画像页，登录了才能站队
    if not user_id:
        return redirect('/profile')
    # 连库
    conn = get_db()
    # 先查这个人之前给这条质疑投过没有，没投过就是 None
    old = conn.execute('SELECT verdict FROM verdicts WHERE question_id = ? AND user_id = ?',
                       (question_id, user_id)).fetchone()
    if old is None:
        # 没投过，插一行新票
        conn.execute('INSERT INTO verdicts (question_id, user_id, verdict) VALUES (?, ?, ?)',
                     (question_id, user_id, verdict))
    elif old['verdict'] == verdict:
        # 点了和上次一样的按钮，就是撤回，删掉他这条质疑上的票
        conn.execute('DELETE FROM verdicts WHERE question_id = ? AND user_id = ?',
                     (question_id, user_id))
    else:
        # 点了另一个按钮，就是改票：先删掉旧票，再插一行新票
        conn.execute('DELETE FROM verdicts WHERE question_id = ? AND user_id = ?',
                     (question_id, user_id))
        conn.execute('INSERT INTO verdicts (question_id, user_id, verdict) VALUES (?, ?, ?)',
                     (question_id, user_id, verdict))
    # 提交，关库
    conn.commit()
    conn.close()
    # 存完跳回这条质疑的详情页，就能看到票数变了
    return redirect(f'/question/{question_id}')
@app.route('/profile', methods=['GET', 'POST'])  # 画像页，GET 显示，POST 保存
def profile():  # 处理画像的函数
    if request.method == 'POST':  # 保存
        nickname = request.form['nickname']  # 取昵称输入框的值
        cookware_list = request.form.getlist('cookware')  # 取所有勾上的锅具，返回一个列表
        cookware_str = ','.join(cookware_list)  # 把列表拼成逗号隔开的文本，存进数据库
        avatar = request.form.get('avatar', '🍳')  # 取选中的头像，没选就默认
        conn = get_db()  # 连接
        user_id = session.get('user_id')  # 看看浏览器里有没有存用户 id
        if user_id:  # 老用户改画像，更新这一行
            conn.execute('UPDATE users SET nickname=?, cookware=?, avatar=? WHERE id=?', (nickname, cookware_str, avatar, user_id))
        else:  # 新用户，插入一行
            cursor = conn.execute('INSERT INTO users (nickname, cookware, avatar) VALUES (?, ?, ?)', (nickname, cookware_str, avatar))
            user_id = cursor.lastrowid  # 拿到刚插入的这行的 id
            session['user_id'] = user_id  # 把用户 id 写进 session，浏览器会记住
        conn.commit()  # 提交保存
        conn.close()  # 关掉连接
        return redirect('/profile')  # 保存完回画像页，看保存好的样子
    # GET：读出当前用户的数据，传给模板显示
    user_id = session.get('user_id')
    user = None
    if user_id:
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        conn.close()
    edit = request.args.get('edit') == '1'  # 网址里有 ?edit=1 就是点更改进来的
    return render_template('profile.html', user=user, edit=edit)
@app.route('/recommend')  # 推荐页的网址
def recommend():  # 处理推荐页的函数
    user_id = session.get('user_id')  # 在简介中取用户，没填过画像就没有
    if not user_id:  # 如果没填过画像
        return redirect('/profile')  # 先去填画像
    conn = get_db()  # 拿数据库连接
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()  # 查这个用户的id与内容
    user_cookware = user['cookware'].split(',') if user['cookware'] else []  # 把存的锅具文本按逗号拆成列表，没存过就是空列表
    recipes = conn.execute('SELECT * FROM recipes').fetchall()  # 显示所有
    pots = ['炒锅', '电饭煲', '微波炉', '空气炸锅', '蒸锅', '平底锅']  # 要检查的六种锅
    can_make = []  # 能做的菜，放这里
    cannot_make = []  # 做不了的菜，放这里
    for recipe in recipes:  # 一道一道过所有菜
        steps = conn.execute('SELECT tools FROM recipe_steps WHERE recipe_id = ?', (recipe['id'],)).fetchall()  # 查这道菜所有步骤的工具
        tools_text = ''  # 先准备一个空文本，用来拼这道菜的所有工具
        for s in steps:  # 一步一步过
            if s['tools']:  # 如果这步有工具
                tools_text += s['tools'] + ' '  # 就把工具拼进文本
        missing = []  # 这道菜缺的锅，放这里
        for pot in pots:  # 六种锅一个一个对
            if pot in tools_text and pot not in user_cookware:  # 如果这道菜提到了这个锅，但用户没有
                missing.append(pot)  # 就记下来，缺这个锅
        if missing:  # 如果有缺的锅
            cannot_make.append((recipe, missing))  # 就放进做不了的列表（菜+缺的锅一起存）
        else:  # 如果一个都不缺
            can_make.append(recipe)  # 就放进能做的列表
    conn.close()  # 关掉连接
    return render_template('recommend.html', can_make=can_make, cannot_make=cannot_make, user_cookware=user_cookware)  # 把三个东西交给推荐模板显示
@app.route('/upload', methods=['GET', 'POST'])  # 上传页的网址，GET 显示表单，POST 保存
def upload():  # 函数
    if request.method == 'POST':  # 如果是提交表单（点上传）
        name = request.form['name']  # 取菜名输入框的值
        description = request.form['description']  # 取简介输入框的值
        step_title = request.form['step_title']  # 取第一步标题输入框的值
        action = request.form['action']  # 取第一步做什么输入框的值
        tools = request.form['tools']  # 取第一步工具输入框的值
        tool_usage = request.form['tool_usage']  # 取工具怎么用输入框的值
        safety_tip = request.form['safety_tip']  # 取安全提示输入框的值
        # 处理上传的片图
        image_file = request.files.get('image')  # 取传上来的图，没传就是 None
        image_path = None  # 默认没图
        if image_file and image_file.filename:  # 如果传了图
            import os  # 用来拼路径和建文件夹
            from werkzeug.utils import secure_filename  # 把文件名弄安全
            upload_dir = 'static/uploads'  # 图存到 static/uploads 文件夹
            os.makedirs(upload_dir, exist_ok=True)  # 文件夹不存在就建一个
            filename = secure_filename(image_file.filename)  # 安全文件名
            filepath = os.path.join(upload_dir, filename)  # 拼完整路径
            image_file.save(filepath)  # 把图存下来
            image_path = '/' + filepath  # 存进数据库的路径
        conn = get_db()  # 拿数据库连接
        cursor = conn.execute('INSERT INTO recipes (name, description, template_id, summary_safety_tip, image) VALUES (?, ?, ?, ?, ?)', (name, description, 1, safety_tip, image_path))  
        recipe_id = cursor.lastrowid  # 拿到刚插入的这道菜的 id
        conn.execute('INSERT INTO recipe_steps (recipe_id, step_no, title, action, tools, tool_usage, safety_tip) VALUES (?, ?, ?, ?, ?, ?, ?)', (recipe_id, 1, step_title, action, tools, tool_usage, safety_tip))  # 插入这道菜的第一步，step_no 是 1
        conn.commit()  # 提交保存
        conn.close()  # 关掉连接
        return redirect('/recipes')  # 保存完跳到菜谱列表页
    return render_template('upload.html')  # 如果是 GET（直接打开），就显示表单
@app.route('/delete/<int:recipe_id>', methods=['POST'])  # 删除菜的路由，只接受 POST
def delete_recipe(recipe_id):  # 函数，recipe_id 是要删的菜的 id
    user_id = session.get('user_id')  # 取当前登录人的 id
    if not user_id:  # 没登录
        return redirect('/profile')  # 先去填画像
    conn = get_db()  # 拿数据库连接
    recipe = conn.execute('SELECT user_id FROM recipes WHERE id = ?', (recipe_id,)).fetchone()  # 查这道菜是谁传的
    if not recipe:  # 菜不存在
        conn.close()  # 关掉连接
        return redirect('/recipes')  # 回菜谱列表
    if recipe['user_id'] != user_id:  # 不是发布者本人
        conn.close()  # 关掉连接
        return '只有发布者能删这道菜', 403  # 403 禁止
    conn.execute('DELETE FROM verdicts WHERE question_id IN (SELECT id FROM questions WHERE recipe_id = ?)', (recipe_id,))  # 先清掉这道菜的质疑的裁决
    conn.execute('DELETE FROM questions WHERE recipe_id = ?', (recipe_id,))  # 再清掉这道菜的质疑
    conn.execute('DELETE FROM recipe_steps WHERE recipe_id = ?', (recipe_id,))  # 再删步骤
    conn.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))  # 最后删菜本身
    conn.commit()  # 提交保存
    conn.close()  # 关掉连接
    return redirect('/recipes')  # 删完回菜谱列表
# 建表函数：启动时自动建好需要的表，已经建过的表不会重复建
@app.route('/edit/<int:recipe_id>', methods=['GET', 'POST'])  # 修改菜的路由
def edit_recipe(recipe_id):  # 函数
    user_id = session.get('user_id')  # 取当前登录人的 id
    if not user_id:  # 没登录
        return redirect('/profile')  # 先去填画像
    conn = get_db()  # 拿数据库连接
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()  # 查这道菜
    if not recipe:  # 菜不存在
        conn.close()  # 关掉连接
        return redirect('/recipes')  # 回菜谱列表
    if recipe['user_id'] != user_id:  # 不是发布者本人
        conn.close()  # 关掉连接
        return '只有发布者能改这道菜', 403  # 403 禁止
    if request.method == 'POST':  # 如果是提交修改
        name = request.form['name']  # 取新菜名
        description = request.form['description']  # 取新简介
        conn.execute('UPDATE recipes SET name = ?, description = ? WHERE id = ?', (name, description, recipe_id))  # 更新菜名和简介
        conn.commit()  # 提交保存
        conn.close()  # 关掉连接
        return redirect(f'/recipe/{recipe_id}')  # 改完回详情页
    conn.close()  # 关掉连接
    return render_template('edit.html', recipe=recipe)  # GET 就显示修改表单
@app.route('/daily_recommend')
def daily_recommend():
    # # 没登录或没填画像，返回空列表加 need_profile 标记，让弹窗显示引导语
    user_id = session.get('user_id')
    if not user_id:
        return {'recipes': [], 'need_profile': True}
    db = get_db()
    user = db.execute('SELECT cookware FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user or not user['cookware']:
        return {'recipes': [], 'need_profile': True}
    # 用户的锅具列表
    my_cookware = [c.strip() for c in user['cookware'].split(',') if c.strip()]
    # 只找步骤里用了这些锅具的菜，排除被质疑的，随机取最多 3 道
    # 不够 3 道就返回实际有的几道，不会报错
    conditions = ' OR '.join('tools LIKE ?' for _ in my_cookware)
    like_params = ['%' + c + '%' for c in my_cookware]
    rows = db.execute(
        f'''SELECT DISTINCT recipes.id, recipes.name FROM recipes
        WHERE recipes.id NOT IN (SELECT recipe_id FROM questions)
        AND recipes.id IN (SELECT recipe_id FROM recipe_steps WHERE {conditions})
        ORDER BY RANDOM() LIMIT 3''',
        like_params
    ).fetchall()
    return {'recipes': [{'id': r['id'], 'name': r['name']} for r in rows]}
@app.route('/vote', methods=['POST'])
def vote():
    user_id = session.get('user_id')
    if not user_id:
        return {'ok': False}, 401
    data = request.get_json()
    recipe_id = data.get('recipe_id')
    v = data.get('vote')
    if v not in ('like', 'dislike'):
        return {'ok': False}, 400
    db = get_db()
    db.execute(
        'INSERT INTO recommend_votes (recipe_id, user_id, vote) VALUES (?, ?, ?) '
        'ON CONFLICT(recipe_id, user_id) DO UPDATE SET vote = ?',
        (recipe_id, user_id, v, v)
    )
    db.commit()
    return {'ok': True} 
init_db()
if __name__ == '__main__':
    app.run(port=5001)