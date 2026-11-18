# 导购功能：读商品配置、算「缺哪些锅」、把食材变成采购清单
# 商品数据都在 shop_items.json 里，换成真实联盟链接只改那个文件，不用改代码
import json
import os
import re
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHOP_FILE = os.environ.get('WENCHU_SHOP_FILE', os.path.join(BASE_DIR, 'shop_items.json'))
POTS = ['炒锅', '电饭煲', '微波炉', '空气炸锅', '蒸锅', '平底锅']  # 画像能选的六种锅


def load_shop():
    # 每次调用都重新读，改了配置不用重启也能看到（文件很小，不影响速度）
    with open(SHOP_FILE, encoding='utf-8') as f:
        return json.load(f)


def strip_brackets(text):
    # 去掉括号里的补充说明，例如「小汤锅（蒸锅拿掉上面的蒸笼就行）」只算小汤锅，不算蒸锅
    return re.sub(r'[（(][^）)]*[）)]', '', text or '')


def split_list(text):
    # 按顿号拆清单，括号里的顿号不拆
    items, buf, depth = [], '', 0
    for ch in text or '':
        if ch in '（(':
            depth += 1
        elif ch in '）)':
            depth = max(0, depth - 1)
        if ch == '、' and depth == 0:
            if buf.strip():
                items.append(buf.strip())
            buf = ''
        else:
            buf += ch
    if buf.strip():
        items.append(buf.strip())
    return items


def recipe_tools_text(recipe, steps):
    # 把整道菜的厨具清单和每一步的工具拼起来（去掉括号说明）
    parts = [strip_brackets(recipe['tools_list'] or '')]
    parts += [strip_brackets(s['tools'] or '') for s in steps]
    return ' '.join(parts)


def pots_needed(tools_text):
    # 这道菜要用到六种锅里的哪几种
    return [p for p in POTS if p in tools_text]


def other_tools(recipe):
    # 厨具清单里除了六种锅以外的工具（画像里没记录，只列出来让人自己对照）
    result = []
    for t in split_list(recipe['tools_list'] or ''):
        name = strip_brackets(t).strip()
        if name and not any(p in name for p in POTS):
            result.append(name)
    return result


def tool_item(shop, name):
    # 小工具有推荐款就返回 (键, 商品)，没有返回 (None, None)
    for key, item in shop['tools'].items():
        if key == name or key in name:
            return key, item
    return None, None


def search_url(shop, platform, keyword):
    tpl = shop['platforms'][platform]['search_url']
    return tpl.format(kw=quote(keyword))


def shopping_list(ingredients_text, shop):
    # 把食材清单变成采购清单：每样食材配上名称、规格、示例估价，调味料默认算「家里已有」
    rows = []
    for raw in split_list(ingredients_text):
        base = strip_brackets(raw).strip()
        optional = '可选' in raw
        entry = next((e for e in shop['ingredients'] if any(m in base for m in e['match'])), None)
        if entry:
            name, unit, price, pantry = entry['name'], entry['unit'], entry['price'], entry['pantry']
        else:
            name = re.sub(r'\s*\d.*$', '', base).strip() or base
            unit, price, pantry = '', shop['ingredient_default_price'], False
        rows.append({
            'raw': raw, 'name': name, 'unit': unit, 'price': price,
            'optional': optional, 'matched': entry is not None,
            'at_home': pantry or optional,  # 调味料、可选的默认勾上「家里已有 / 先不买」
        })
    return rows


def best_unlock(recipes_pots, owned):
    # recipes_pots: [(菜, [要的锅])]；owned: 用户已有的锅
    # 返回每种没有的锅「补上它能多做几道菜」，从多到少排
    owned = set(owned)
    ranking = []
    for pot in POTS:
        if pot in owned:
            continue
        unlocked = [r for r, need in recipes_pots if pot in need and set(need) - owned == {pot}]
        ranking.append((pot, unlocked))
    ranking.sort(key=lambda x: (-len(x[1]), POTS.index(x[0])))
    return ranking


def starter_set(recipes_pots, size=3):
    # 按菜谱算「入门 N 件套」：每次挑能让可做菜最多的那口锅
    chosen = []
    for _ in range(size):
        best, best_count = None, -1
        for pot in POTS:
            if pot in chosen:
                continue
            count = sum(1 for _, need in recipes_pots if set(need) <= set(chosen + [pot]))
            if count > best_count:
                best, best_count = pot, count
        chosen.append(best)
    covered = [r for r, need in recipes_pots if set(need) <= set(chosen)]
    return chosen, covered


# 本餐预算：列表页和推荐页可以按「补齐要花多少钱」筛选
BUDGETS = [30, 50, 100]  # 页面上的档位，另外还有「不限」


def parse_budget(value):
    # 网址里的 budget 只认上面几档，其他一律当「不限」（返回 None）
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value in BUDGETS else None


def meal_cost(recipe, steps, owned, catalog, know_pots=True):
    # 估算做这道菜还要花多少钱 = 还缺的食材 + 还缺的锅（价格都是 shop_items.json 里的示例价）
    # 食材沿用采购清单的算法：调味料、可选的算「家里已有」，不计入
    # know_pots=False（没填厨房画像）时不知道家里有什么锅，锅具先不算，页面上会说明
    ingredients = sum(r['price'] for r in shopping_list(recipe['ingredients_list'], catalog) if not r['at_home'])
    missing = [p for p in pots_needed(recipe_tools_text(recipe, steps)) if p not in owned] if know_pots else []
    cookware = sum(catalog['cookware'][p]['price'] for p in missing if p in catalog['cookware'])
    return {'ingredients': ingredients, 'cookware': cookware, 'total': ingredients + cookware,
            'missing_pots': missing, 'counted_pots': know_pots}


def within_budget(items, budget):
    # items: [(菜, 花费)]；有预算就只留不超预算的，并按花费从少到多排；不限就原样返回
    if budget is None:
        return items
    kept = [x for x in items if x[1]['total'] <= budget]
    return sorted(kept, key=lambda x: x[1]['total'])
