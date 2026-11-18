# AI 拆菜 · 菜名对齐：别名表（把各种叫法归到一个标准名）、输入时的联想、「个性化条件」判断
# 全部是规则，不调 AI。数据库读写在 dish_store.py，这里只放纯函数和种子数据
import re
import unicodedata

import dish_rules


def normalize(name):
    # 「宫保 鸡丁」「宫保鸡丁！」「宫保鸡丁 」都算同一个；全角转半角、英文小写、去掉空格和标点
    s = unicodedata.normalize('NFKC', name or '').lower()
    return re.sub(r'[\s\W_]+', '', s)


# 种子别名：常见写法 / 错别字 → 标准名。标准名要么是站内 12 道菜，要么是 dish_rules.COMMON_DISHES 里的菜
SEED_ALIASES = {
    # 常见菜
    '宫爆鸡丁': '宫保鸡丁', '宫保鸡': '宫保鸡丁', '宫爆鸡': '宫保鸡丁', '公保鸡丁': '宫保鸡丁', '宫保鸡肉丁': '宫保鸡丁',
    '西红柿炒鸡蛋': '番茄炒蛋', '西红柿炒蛋': '番茄炒蛋', '番茄炒鸡蛋': '番茄炒蛋', '蕃茄炒蛋': '番茄炒蛋', '鸡蛋炒番茄': '番茄炒蛋',
    '西红柿鸡蛋汤': '番茄蛋汤', '番茄鸡蛋汤': '番茄蛋汤', '西红柿蛋汤': '番茄蛋汤',
    '蒸蛋': '鸡蛋羹', '水蒸蛋': '鸡蛋羹', '蒸水蛋': '鸡蛋羹', '蒸鸡蛋': '鸡蛋羹', '炖蛋': '鸡蛋羹',
    '红烧五花肉': '红烧肉', '毛氏红烧肉': '红烧肉',
    '麻婆豆府': '麻婆豆腐', '麻辣豆腐': '麻婆豆腐',
    '渔香肉丝': '鱼香肉丝',
    '糖醋小排': '糖醋排骨', '糖醋排条': '糖醋排骨',
    '醋溜土豆丝': '酸辣土豆丝', '炒土豆丝': '酸辣土豆丝',
    '土豆烧牛肉': '土豆炖牛肉', '牛肉炖土豆': '土豆炖牛肉',
    '水煮虾': '白灼虾', '凉拌黄瓜': '拍黄瓜',
    '蒸鲈鱼': '清蒸鲈鱼', '清蒸鱼': '清蒸鲈鱼',
    '牛排': '煎牛排', '炸鸡中翅': '炸鸡翅', '烤翅': '烤鸡翅', '奥尔良烤翅': '烤鸡翅', '回锅肉片': '回锅肉',
    # 站内 12 道菜的常见叫法
    '可乐鸡中翅': '可乐鸡翅', '可乐鸡翼': '可乐鸡翅',
    '芥末虾仁': '芥末虾球', '芥末虾': '芥末虾球',
    '巧克力慕斯': '巧克力慕斯蛋糕', '慕斯蛋糕': '巧克力慕斯蛋糕',
    '干锅菜花': '干锅花菜', '干锅花椰菜': '干锅花菜',
    '岩浆吐司': '熔岩吐司', '熔岩面包': '熔岩吐司',
    '啫啫鱿鱼': '生啫鱿鱼',
    '土豆鸡腿饭': '秘制土豆鸡腿饭', '鸡腿土豆饭': '秘制土豆鸡腿饭',
    '龙虾伊面': '龙虾面',
    '炒猪肝': '爆炒猪肝', '熘肝尖': '爆炒猪肝',
    '奶油蘑菇面': '奶油蘑菇意面', '奶油蘑菇意大利面': '奶油蘑菇意面',
    '鸡蛋炒饭': '蛋炒饭', '蛋炒米饭': '蛋炒饭',
}

# 联想时的「近似字」：两边都换成同一个字再比，「宫爆」就能对上「宫保」。只用于联想，不改存的名字
FUZZY_SWAPS = [('西红柿', '番茄'), ('菜花', '花菜'), ('鸡中翅', '鸡翅'), ('爆', '保'), ('公', '宫'), ('蕃', '番'),
               ('渔', '鱼'), ('府', '腐'), ('翼', '翅')]


def fuzzy_form(s):
    s = normalize(s)
    for a, b in FUZZY_SWAPS:
        s = s.replace(a, b)
    return s


def score(q, name):
    # q 跟一个名字有多像：0 = 不像；越大越像。只用字符串比较
    qn, nn = fuzzy_form(q), fuzzy_form(name)
    if not qn or not nn:
        return 0
    if qn == nn:
        return 100
    if nn.startswith(qn):
        return 90
    if qn in nn:
        return 80
    if len(nn) >= 2 and nn in qn:
        return 70
    common = len(set(qn) & set(nn))
    if len(qn) >= 2 and common >= 2 and common / len(set(qn)) >= 0.6:
        return 40 + int(20 * common / len(set(qn)))
    return 0


def suggest(q, candidates, aliases, limit=6):
    # candidates: {标准名: 'site' | 'cached' | 'common'}；aliases: {别名(归一): 标准名(归一)}
    # 返回 [(标准名, 类型, 分数)]，同一个标准名只出现一次，按分数排
    by_key = {normalize(n): n for n in candidates}
    best = {}
    for name in candidates:
        best[name] = score(q, name)
    for alias, canon_key in aliases.items():
        name = by_key.get(canon_key)
        if name:
            best[name] = max(best[name], score(q, alias) - 1)  # 别名命中比正名略低一点
    rank = {'site': 0, 'cached': 1, 'common': 2}
    hits = [(n, candidates[n], s) for n, s in best.items() if s > 0]
    hits.sort(key=lambda x: (-x[2], rank.get(x[1], 9), x[0]))
    return hits[:limit]


# 个性化条件：补充说明里出现这些，说明会改变锅具或做法 → 不复用标准拆法，单独调 AI，结果也不存进菜谱库
# 只是口味（不要太辣、少放盐、甜一点）不算，照样用标准拆法，页面提醒「口味自己调」
PERSONAL_WORDS = ['没有', '家里没', '没锅', '不用', '不要用', '别用', '换成', '改用', '只有', '只用', '用烤箱', '用空气炸锅',
                  '素食', '吃素', '素的', '纯素', '不吃肉', '不吃荤', '过敏', '忌口', '清真', '不炸', '不油炸', '不要油炸',
                  '无油', '不放油', '免油']


def personal_reason(description):
    # 返回触发的那个词（页面上告诉用户为什么单独拆）；不是个性化条件返回 ''
    d = normalize(description)
    if not d:
        return ''
    for w in PERSONAL_WORDS:
        if w in d:
            return w
    tools = sorted({w for ws in dish_rules.ALIASES.values() for w in ws if len(w) >= 2}, key=len, reverse=True)
    for w in tools:  # 说明里点名了某件锅具（「想用电饭煲」「蒸锅做」），也会改变锅具
        if w in d:
            return w
    return ''
