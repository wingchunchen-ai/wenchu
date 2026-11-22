# AI 拆菜 · 第二层「稳厨经验库」：做法 → 锅具 的规则，外加常见菜的兜底资料
# 规则永远说了算：AI 给的锅具要过这里核对，缺的必备锅具由规则补上并写明原因
# 锅具名字跟全站一致：画像六口锅见 shop.POTS，小工具见 shop_items.json 的 tools
import re

import shop

# 做法词典：标准做法名 → 同义词（菜名或 AI 输出里出现任意一个就算）
# 顺序有讲究：长词、特征词在前，避免「清蒸」被「蒸」以外的词抢走
METHODS = [
    ('油炸', ['油炸', '炸', '酥炸', '干炸', '软炸', '过油']),
    ('清蒸', ['清蒸', '蒸', '隔水']),
    ('炖煲', ['炖', '煲', '煨', '卤', '焖煮', '慢炖', '熬']),
    ('红烧', ['红烧', '焖', '烧', '烩', '收汁']),
    ('烤', ['烤', '焗', '烘']),
    ('煎', ['煎', '铁板', '香煎']),
    ('炒', ['爆炒', '炒', '煸', '干锅', '熘', '滑炒', '小炒', '爆香', '爆']),
    ('水煮', ['水煮', '煮', '焯', '汆', '涮', '汤', '面条', '白灼']),
    ('微波', ['微波', '叮']),
    ('焖饭', ['焖饭', '煮饭', '煲仔饭', '蒸饭']),
    ('凉拌', ['凉拌', '拌', '腌', '冷盘']),
    ('打发', ['打发', '慕斯', '蛋糕', '奶油霜']),
]
METHOD_NAMES = [m for m, _ in METHODS]

# 每种做法要什么锅具、为什么。name 必须是全站用的名字；alt 是「家里有这个也行」的替代说法
# 画像里没有的东西（油温计、漏勺、砂锅…）只列出来提醒，不在示例价里，花费不计
RULES = {
    '炒': [('炒锅', '大火快炒要锅深、受热快，翻炒时菜不容易溢出来', ''), ('锅铲', '翻炒、出锅都要用', '')],
    '清蒸': [('蒸锅', '隔水蒸要有蒸屉和锅盖，把蒸汽锁住才熟得均匀', '或炒锅里放蒸架')],
    '油炸': [('炒锅', '炸东西要锅深，油不容易溅出来；稳厨用深一点的炒锅当炸锅', '或深一点的小汤锅'),
             ('油温计', '看准油温再下锅，油太热容易起火、太凉会吸油', ''),
             ('漏勺', '炸好的东西要快速捞出、沥干油', '')],
    '炖煲': [('电饭煲', '炖、煲要小火长时间，电饭煲的煲汤档不用守着火', '或砂锅、炖锅'), ],
    '红烧': [('炒锅', '先煸炒上色再加水焖，锅要够深', ''), ('锅盖', '焖的时候要盖上，食材才焖得透、入味', '')],
    '烤': [('空气炸锅', '定好温度和时间就能烤，小份量比烤箱省事', '或烤箱')],
    '煎': [('平底锅', '锅底平、受热均匀，煎出来两面金黄不粘锅', ''), ('锅铲', '翻面要用', '')],
    '水煮': [('小汤锅', '煮、焯水要一锅开水，小汤锅够深', '或蒸锅拿掉蒸笼')],
    '微波': [('微波炉', '直接叮热或叮熟，不用开火', '')],
    '焖饭': [('电饭煲', '米饭、焖饭交给电饭煲最稳', '')],
    '凉拌': [],
    '打发': [('打蛋器', '奶油、蛋清要打发到起泡变稠', '')],
}
# 画像六口锅 → 它对应的典型做法（站内菜谱按锅反推做法用）
POT_METHOD = {'炒锅': '炒', '平底锅': '煎', '蒸锅': '清蒸', '空气炸锅': '烤', '电饭煲': '焖饭', '微波炉': '微波', '小汤锅': '水煮'}
# 不管什么菜，切配都要这两样
BASIC = [('刀', '切配食材', ''), ('案板', '切菜、切肉要垫着', '')]

# 锅具别名：AI 说的各种叫法 → 全站名字；对不上的一律不收（规则库不认识就不列）
ALIASES = {
    '炒锅': ['炒锅', '铁锅', '中式炒锅', '不粘炒锅', '炒菜锅', '深炒锅', '炒勺'],
    '平底锅': ['平底锅', '煎锅', '平底不粘锅', '牛排锅'],
    '蒸锅': ['蒸锅', '蒸笼', '蒸架', '蒸屉', '蒸格'],
    '电饭煲': ['电饭煲', '电饭锅', '砂锅', '炖锅', '电炖锅', '煲', '瓦煲', '高压锅', '压力锅'],
    '空气炸锅': ['空气炸锅', '烤箱', '电烤箱'],
    '微波炉': ['微波炉'],
    '小汤锅': ['小汤锅', '汤锅', '奶锅', '深锅', '煮锅'],
    '锅盖': ['锅盖'],
    '锅铲': ['锅铲', '铲子', '炒勺铲'],
    '刀': ['刀', '菜刀', '厨刀'],
    '案板': ['案板', '砧板', '菜板'],
    '打蛋器': ['打蛋器', '电动打蛋器'],
    '空气炸锅纸': ['空气炸锅纸', '油纸', '烘焙纸'],
    '油温计': ['油温计', '温度计'],
    '漏勺': ['漏勺', '笊篱', '沥油勺'],
}


def canonical_tool(name):
    # 把一个锅具叫法归到全站名字；认不出返回 None
    n = re.sub(r'\s+', '', shop.strip_brackets(name or ''))
    if not n:
        return None
    for canon, words in ALIASES.items():
        if n in words:
            return canon
    for canon, words in ALIASES.items():  # 再宽松一点：叫法里包含别名（如「不粘平底锅 26cm」）
        if any(len(w) >= 2 and w in n for w in words):
            return canon
    return None


def canonical_method(text):
    # 把一个做法说法归到标准做法名；认不出返回 None
    t = (text or '').strip()
    if t in METHOD_NAMES:
        return t
    for name, words in METHODS:
        if any(w in t for w in words):
            return name
    return None


def methods_from_text(text):
    # 从菜名/描述里找出做法（可能有多个，例如「红烧」+「炖」）
    found = []
    t = text or ''
    # 先把锅具名字抹掉，免得「空气炸锅」被当成油炸、「电饭煲」被当成炖煲、「汤锅」被当成煮汤
    for w in sorted({w for ws in ALIASES.values() for w in ws}, key=len, reverse=True):
        if len(w) >= 2:
            t = t.replace(w, ' ')
    # 「清蒸」「油炸」这类关键字优先；「炒饭」算炒，不算焖饭
    for name, words in METHODS:
        if any(w in t for w in words) and name not in found:
            found.append(name)
    if '炒饭' in t and '焖饭' in found:
        found.remove('焖饭')
    if '红烧' in found and '炖煲' in found and '炖' not in t and '煲' not in t:
        found.remove('炖煲')
    return found[:4]


# 常见菜兜底资料（稳厨经验库）：没接上 AI 时按菜名对上这里。只写食材和做法，不写价格
COMMON_DISHES = {
    '宫保鸡丁': {'main': ['鸡胸肉'], 'side': ['花生米', '干辣椒', '葱', '姜', '蒜'],
             'season': ['花椒', '生抽', '醋', '糖', '淀粉', '料酒'], 'methods': ['炒']},
    '清蒸鲈鱼': {'main': ['鲈鱼'], 'side': ['葱', '姜'], 'season': ['蒸鱼豉油', '料酒', '油'], 'methods': ['清蒸']},
    '番茄炒蛋': {'main': ['番茄', '鸡蛋'], 'side': ['葱'], 'season': ['盐', '糖', '油'], 'methods': ['炒']},
    '西红柿炒鸡蛋': {'main': ['番茄', '鸡蛋'], 'side': ['葱'], 'season': ['盐', '糖', '油'], 'methods': ['炒']},
    '红烧肉': {'main': ['五花肉'], 'side': ['葱', '姜'], 'season': ['冰糖', '生抽', '老抽', '料酒', '八角'], 'methods': ['红烧']},
    '麻婆豆腐': {'main': ['豆腐'], 'side': ['牛肉末', '蒜', '葱'], 'season': ['豆瓣酱', '花椒', '淀粉', '生抽', '油'], 'methods': ['炒', '红烧']},
    '鱼香肉丝': {'main': ['猪里脊'], 'side': ['木耳', '胡萝卜', '青椒', '葱', '姜', '蒜'],
             'season': ['豆瓣酱', '醋', '糖', '生抽', '淀粉'], 'methods': ['炒']},
    '回锅肉': {'main': ['五花肉'], 'side': ['青蒜', '青椒'], 'season': ['豆瓣酱', '甜面酱', '料酒'], 'methods': ['水煮', '炒']},
    '糖醋排骨': {'main': ['排骨'], 'side': ['姜'], 'season': ['醋', '糖', '生抽', '料酒', '油'], 'methods': ['油炸', '红烧']},
    '酸辣土豆丝': {'main': ['土豆'], 'side': ['干辣椒', '蒜'], 'season': ['醋', '盐', '油'], 'methods': ['炒']},
    '鸡蛋羹': {'main': ['鸡蛋'], 'side': ['葱'], 'season': ['盐', '生抽'], 'methods': ['清蒸']},
    '蒸蛋': {'main': ['鸡蛋'], 'side': ['葱'], 'season': ['盐', '生抽'], 'methods': ['清蒸']},
    '炸鸡翅': {'main': ['鸡翅'], 'side': ['面粉', '鸡蛋'], 'season': ['盐', '胡椒粉', '料酒', '油'], 'methods': ['油炸']},
    '烤鸡翅': {'main': ['鸡翅'], 'side': ['蒜'], 'season': ['生抽', '蜂蜜', '料酒'], 'methods': ['烤']},
    '煎牛排': {'main': ['牛排'], 'side': ['黄油', '蒜'], 'season': ['盐', '黑胡椒'], 'methods': ['煎']},
    '土豆炖牛肉': {'main': ['牛腩', '土豆'], 'side': ['胡萝卜', '葱', '姜'], 'season': ['生抽', '老抽', '八角', '料酒'], 'methods': ['炖煲']},
    '番茄蛋汤': {'main': ['番茄', '鸡蛋'], 'side': ['葱'], 'season': ['盐', '油'], 'methods': ['水煮']},
    '白灼虾': {'main': ['鲜虾'], 'side': ['姜', '葱'], 'season': ['生抽', '料酒'], 'methods': ['水煮']},
    '拍黄瓜': {'main': ['黄瓜'], 'side': ['蒜'], 'season': ['醋', '生抽', '盐', '香油'], 'methods': ['凉拌']},
}

# 菜名里常见的食材字眼，兜底时用来猜主料（只认菜名里明明白白写着的）
FOOD_WORDS = ['鸡翅', '鸡腿', '鸡胸', '鸡', '鸭', '鹅', '牛排', '牛肉', '牛腩', '羊肉', '排骨', '五花肉', '里脊', '猪肝', '猪肉',
              '肉丝', '肉片', '鲈鱼', '鱼', '虾仁', '虾', '蟹', '鱿鱼', '豆腐', '鸡蛋', '蛋', '茄子', '胡萝卜', '玉米', '火腿', '青豆', '土豆', '番茄', '西红柿',
              '白菜', '青菜', '花菜', '西兰花', '黄瓜', '冬瓜', '南瓜', '蘑菇', '香菇', '木耳', '豆角', '青椒', '洋葱',
              '米饭', '饭', '面条', '意面', '面', '吐司', '年糕']


def _norm(name):
    return re.sub(r'\s+', '', name or '')


# 菜名多出来的字只是这些修饰词时，才算同一道菜（「家常蛋炒饭」= 蛋炒饭）；
# 多了食材（「胡萝卜鸡蛋炒饭」）就是另一道菜，不能直接套用，免得把胡萝卜丢掉
SAME_DISH_EXTRA = re.compile(r'^(家常|简单|简易|快手|懒人|经典|正宗|自制|好吃的|美味|版|的|做法)*$')


def _same_dish(known, d):
    return known == d or (len(known) >= 3 and known in d and SAME_DISH_EXTRA.match(d.replace(known, '', 1)))


def match_known(dish, known_recipes):
    # 先对站内 12 道菜（和用户上传的菜），再对常见菜资料；返回 (来源, 资料) 或 (None, None)
    d = _norm(dish)
    for r in known_recipes or []:
        rn = _norm(r.get('name'))
        if rn and _same_dish(rn, d):
            return 'site', r
    for name, info in COMMON_DISHES.items():
        if _same_dish(name, d):
            return 'common', dict(info, name=name)
    return None, None


def pots_from_tools_text(text):
    # 站内菜谱的厨具清单 → 全站锅具名（去括号说明后匹配别名）
    found = []
    for item in shop.split_list(shop.strip_brackets(text or '')):
        c = canonical_tool(item)
        if c and c not in found:
            found.append(c)
    return found


def build_cookware(methods, ai_tools=None, site_tools=None):
    # 规则拍板：做法要求的锅具必须在；AI 提的、规则库认得的作为补充；认不出的丢掉并计数
    # 返回 (锅具列表, 被丢掉的 AI 叫法)
    items, order = {}, []

    def add(name, reason, alt, source):
        if name in items:
            if source == 'ai' and items[name]['source'] == 'rule':
                items[name]['source'] = 'both'
            return
        items[name] = {'name': name, 'reason': reason, 'alt': alt, 'source': source}
        order.append(name)

    for m in methods:
        for name, reason, alt in RULES.get(m, []):
            add(name, f'{m}：{reason}', alt, 'rule')
    for name in site_tools or []:  # 站内菜谱自己写的厨具，同样当规则
        add(name, '稳厨菜谱里这道菜就用它', '', 'rule')
    for name, reason, alt in BASIC:
        add(name, reason, alt, 'rule')
    dropped = []
    for t in ai_tools or []:
        canon = canonical_tool(t.get('name'))
        if not canon:
            dropped.append(t.get('name'))
            continue
        add(canon, t.get('reason') or 'AI 建议', '', 'ai')
    return [items[n] for n in order], dropped


def rule_draft(dish, description, known_recipes):
    # 规则兜底：不靠 AI，只靠菜名/描述 + 站内菜谱 + 常见菜资料
    text = f'{dish} {description or ""}'
    src, info = match_known(dish, known_recipes)
    site_tools = []
    if src == 'site':
        # 食材按原菜谱的清单，跟采购清单同一套判断：调味料、可选的算家里已有
        # 主料：清单里带肉、蛋、菜、主食字眼的（最多 3 样）；一个都没有就取第一样
        main, side, season = [], [], []
        for row in shop.shopping_list(info.get('ingredients_list') or '', shop.load_shop()):
            x = re.sub(r'\s*\d.*$', '', shop.strip_brackets(row['raw'])).strip() or row['name']
            if row['at_home']:
                season.append(x + ('（可选）' if row['optional'] else ''))
            elif len(main) < 3 and any(w in x for w in FOOD_WORDS) and not re.search(r'(酱|醋|粉|油)$', x):
                main.append(x)
            else:
                side.append(x)
        if not main and side:
            main.append(side.pop(0))
        site_tools = pots_from_tools_text(info.get('tools_list'))
        # 做法看菜名和每一步的标题（「煎鸡翅」「炸虾球」「炒饭调味」），步骤正文里「烧开水」「搅拌」这类词容易误判，不看
        # 都看不出来时才按锅反推
        methods = site_methods(info) or list(dict.fromkeys(POT_METHOD[p] for p in POT_METHOD if p in site_tools))
        matched = f'稳厨菜谱「{info["name"]}」'
    elif src == 'common':
        main, side, season = list(info['main']), list(info['side']), list(info['season'])
        methods = list(info['methods'])
        matched = f'稳厨经验库「{info["name"]}」'
    else:
        # 长词先认、认过的字划掉：「鸡蛋」不会再被拆出一个「鸡」；按菜名里的先后排
        rest, found = dish, []
        for w in sorted(FOOD_WORDS, key=len, reverse=True):
            if w in rest:
                found.append((dish.find(w), w))
                rest = rest.replace(w, '\0' * len(w))
        main = [w for _, w in sorted(found)]
        main, side, season = main[:3], [], []
        methods = methods_from_text(text)
        matched = ''
    return {'main': main, 'side': side, 'season': season, 'methods': methods,
            'site_tools': site_tools, 'matched': matched, 'tips': '',
            'site_id': info.get('id') if src == 'site' else None,
            'ingredients_list': info.get('ingredients_list') if src == 'site' else None}


# 步骤标题里不算做法的说法：「拌面」「拌饭」是出锅前拌一拌，「腌制」是备料，不是凉拌
STEP_IGNORE = ['搅拌', '拌面', '拌饭', '抓拌', '拌匀', '拌好', '腌制', '调酱', '酱汁',
               '烧至', '烧开', '烧热', '烧油', '烧到', '烧好', '热水', '水蒸气', '融化', '炸至', '收汁']


def site_methods(info):
    # 站内菜的做法：菜名 + 步骤标题，按出现先后排
    parts = [info.get('name') or ''] + list(info.get('step_titles') or [])
    found = []
    for part in parts:
        for w in STEP_IGNORE:
            part = part.replace(w, ' ')
        for m in methods_from_text(part):
            if m not in found:
                found.append(m)
    # 菜谱用到的锅，如果上面的做法都解释不了（比如意面的平底锅是用来炒酱的），再看用这口锅那几步的正文
    covered = {n for m in found for n, _, _ in RULES.get(m, [])}
    for pot in pots_from_tools_text(info.get('tools_list')):
        if pot not in POT_METHOD or pot in covered:
            continue
        for st in info.get('steps') or []:
            if pot not in (st.get('tools') or ''):
                continue
            text = st.get('action') or ''
            for w in STEP_IGNORE:
                text = text.replace(w, ' ')
            for m in methods_from_text(text):
                if m not in found and m not in ('凉拌', '打发'):
                    found.append(m)
    return found[:4]


def build_site_cookware(methods, site_tools):
    # 站内菜：锅具一件不多一件不少，就是菜谱里写的（加上刀、案板）；原因能对上规则就用规则的话
    reasons = {}
    for m in methods:
        for name, reason, alt in RULES.get(m, []):
            reasons.setdefault(name, (f'{m}：{reason}', alt))
    items = []
    for name in list(site_tools) + [n for n, _, _ in BASIC if n not in site_tools]:
        basic = next((r for n, r, _ in BASIC if n == name), None)
        reason, alt = reasons.get(name, (basic or '稳厨菜谱里这道菜就用它', ''))
        items.append({'name': name, 'reason': reason, 'alt': alt, 'source': 'rule'})
    return items


# 步骤标题里不算做法的说法：「拌面」「拌饭」是出锅前拌一拌，「腌制」是备料，不是凉拌
STEP_IGNORE = ['搅拌', '拌面', '拌饭', '抓拌', '拌匀', '拌好', '腌制', '调酱', '酱汁',
               '烧至', '烧开', '烧热', '烧油', '烧到', '烧好', '热水', '水蒸气', '融化', '炸至', '收汁']


def site_methods(info):
    # 站内菜的做法：菜名 + 步骤标题，按出现先后排
    parts = [info.get('name') or ''] + list(info.get('step_titles') or [])
    found = []
    for part in parts:
        for w in STEP_IGNORE:
            part = part.replace(w, ' ')
        for m in methods_from_text(part):
            if m not in found:
                found.append(m)
    # 菜谱用到的锅，如果上面的做法都解释不了（比如意面的平底锅是用来炒酱的），再看用这口锅那几步的正文
    covered = {n for m in found for n, _, _ in RULES.get(m, [])}
    for pot in pots_from_tools_text(info.get('tools_list')):
        if pot not in POT_METHOD or pot in covered:
            continue
        for st in info.get('steps') or []:
            if pot not in (st.get('tools') or ''):
                continue
            text = st.get('action') or ''
            for w in STEP_IGNORE:
                text = text.replace(w, ' ')
            for m in methods_from_text(text):
                if m not in found and m not in ('凉拌', '打发'):
                    found.append(m)
    return found[:4]


def build_site_cookware(methods, site_tools):
    # 站内菜：锅具一件不多一件不少，就是菜谱里写的（加上刀、案板）；原因能对上规则就用规则的话
    reasons = {}
    for m in methods:
        for name, reason, alt in RULES.get(m, []):
            reasons.setdefault(name, (f'{m}：{reason}', alt))
    items = []
    for name in list(site_tools) + [n for n, _, _ in BASIC if n not in site_tools]:
        basic = next((r for n, r, _ in BASIC if n == name), None)
        reason, alt = reasons.get(name, (basic or '稳厨菜谱里这道菜就用它', ''))
        items.append({'name': name, 'reason': reason, 'alt': alt, 'source': 'rule'})
    return items


def _pantry_words():
    words = []
    for e in shop.load_shop()['ingredients']:
        if e.get('pantry'):
            words += e['match']
    return words + ['胡椒粉', '豆瓣酱', '淀粉', '醋']
