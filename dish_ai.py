# AI 拆菜 · 第一层「AI 初稿」+ 合并：DeepSeek 先拆，稳厨经验库（dish_rules）核对、补齐
# 密钥只从环境变量 DEEPSEEK_API_KEY 读，只在服务器端用；不打印、不写日志、不进页面
import json
import os
import re
import urllib.error
import urllib.request

import dish_rules
import shop

API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-flash'  # 只用这个模型，别换成 pro 或其他
TIMEOUT = 20  # 秒；超时就走规则兜底，页面不会一直转圈
MAX_ITEMS = 10
MAX_NAME = 20

SYSTEM_PROMPT = (
    '你是家常菜拆解助手。用户给一道菜名（可能附简短描述），你只输出一个 JSON 对象，不要输出任何别的文字。'
    '字段：{"recognized": true/false（是否认得这道菜）, '
    '"main": ["主料名", ...], "side": ["辅料名", ...], "season": ["调味料名", ...], '
    '"methods": ["做法", ...], "cookware": [{"name": "锅具名", "reason": "为什么要用（15字内）"}], '
    '"tips": "给新手的一句提醒（30字内）"}。'
    '规则：食材只写名字不写用量，每类最多 8 个；methods 只能从这些里选：' + '、'.join(dish_rules.METHOD_NAMES) + '；'
    'cookware 尽量用这些叫法：炒锅、平底锅、蒸锅、电饭煲、空气炸锅、微波炉、小汤锅、锅盖、锅铲、刀、案板、打蛋器、油温计、漏勺；'
    '不要写价格；不认得这道菜就把 recognized 设为 false，其他字段给空数组。'
)


class AIError(Exception):
    """AI 这一层任何问题（没密钥、网络、超时、返回不是合格 JSON）都抛这个，外面统一走规则兜底"""


def call_deepseek(dish, description, api_key=None, timeout=TIMEOUT, opener=None):
    # 调 DeepSeek（OpenAI 兼容的 chat completions），要求只回 JSON；返回模型回的那段文字
    key = api_key if api_key is not None else os.environ.get('DEEPSEEK_API_KEY', '')
    if not key.strip():
        raise AIError('没配置 AI 密钥')
    user_msg = f'菜名：{dish}' + (f'\n描述：{description}' if description else '')
    body = {
        'model': MODEL,
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user_msg}],
        'response_format': {'type': 'json_object'},
        'thinking': {'type': 'disabled'},
        'temperature': 0.2,
        'max_tokens': 800,
        'stream': False,
    }
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key.strip()})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:  # 只记状态码，不带请求头（里面有密钥）
        raise AIError('密钥无效或已失效' if e.code in (401, 403) else f'AI 服务返回 {e.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AIError('连不上 AI 服务或超时') from None
    except ValueError:
        raise AIError('AI 返回的不是 JSON') from None
    try:
        return payload['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        raise AIError('AI 返回格式不对') from None


def _clean_name(x):
    # 一个食材/做法/锅具名：只要字符串，去掉标签符号和括号说明，限制长度
    if not isinstance(x, str):
        return ''
    x = re.sub(r'[<>{}\[\]"`\\]', '', x)
    x = shop.strip_brackets(x)
    x = re.sub(r'\s+', ' ', x).strip(' ，,。、;；:：')
    return x[:MAX_NAME]


def _clean_list(v):
    out = []
    if not isinstance(v, list):
        return out
    for x in v:
        if isinstance(x, dict):  # 有的模型会回 {"name": "...", "amount": "..."}
            x = x.get('name')
        n = _clean_name(x)
        if n and n not in out:
            out.append(n)
        if len(out) >= MAX_ITEMS:
            break
    return out


def parse_ai_json(text):
    # 校验 + 清洗 AI 的 JSON。不合格（不是 JSON、不认得、主料和做法都空）就抛 AIError
    if not isinstance(text, str) or not text.strip():
        raise AIError('AI 没有返回内容')
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)  # 万一包了 ``` 代码块
    try:
        data = json.loads(t)
    except ValueError:
        raise AIError('AI 返回的不是合格 JSON') from None
    if not isinstance(data, dict):
        raise AIError('AI 返回的不是 JSON 对象')
    if data.get('recognized') is False:
        raise AIError('AI 没认出这道菜')
    methods = []
    for m in _clean_list(data.get('methods')):
        c = dish_rules.canonical_method(m)  # 只收规则库认识的做法
        if c and c not in methods:
            methods.append(c)
    cookware = []
    raw_tools = data.get('cookware') if isinstance(data.get('cookware'), list) else []
    for t_ in raw_tools[:MAX_ITEMS]:
        if isinstance(t_, str):
            t_ = {'name': t_}
        if not isinstance(t_, dict):
            continue
        name = _clean_name(t_.get('name'))
        reason = t_.get('reason') if isinstance(t_.get('reason'), str) else ''
        reason = re.sub(r'[<>{}\[\]"`\\]', '', reason).strip()[:40]
        if name:
            cookware.append({'name': name, 'reason': reason})
    tips = data.get('tips') if isinstance(data.get('tips'), str) else ''
    result = {
        'main': _clean_list(data.get('main')),
        'side': _clean_list(data.get('side')),
        'season': _clean_list(data.get('season')),
        'methods': methods,
        'cookware': cookware,
        'tips': re.sub(r'[<>{}\[\]"`\\]', '', tips).strip()[:60],
    }
    if not result['main'] or not result['methods']:
        raise AIError('AI 返回缺主料或做法')
    return result


def analyze(dish, description, owned, know_pots, known_recipes, catalog, use_ai=True, caller=None):
    # 主流程：先试 AI，再让规则拍板锅具；AI 不可用就纯规则。返回页面要的全部数据
    dish = _clean_name(dish)
    description = (description or '').strip()[:100]
    ai, ai_error = None, '' if use_ai else '已选只用稳厨经验库'
    rules = dish_rules.rule_draft(dish, description, known_recipes)
    if rules['site_id']:  # 站内已有这道菜：直接用菜谱里的食材、做法、锅具，花费跟列表页一致，不调 AI
        use_ai = False
    if use_ai:
        try:
            ai = parse_ai_json((caller or call_deepseek)(dish, description))
        except AIError as e:
            ai_error = str(e)
    if rules['site_id']:
        mode = '稳厨菜谱'
        main, side, season = rules['main'], rules['side'], rules['season']
        methods = rules['methods']
        cookware, dropped = dish_rules.build_site_cookware(methods, rules['site_tools']), []
        tips = ''
    elif ai:
        mode = 'AI+规则'
        main, side, season = ai['main'], ai['side'], ai['season']
        # 做法：AI 的为主，菜名里明写的做法规则也要算上（例如名字带「清蒸」AI 却漏了）
        methods = list(ai['methods'])
        for m in dish_rules.methods_from_text(dish):
            if m not in methods:
                methods.append(m)
        cookware, dropped = dish_rules.build_cookware(methods, ai['cookware'], rules['site_tools'])
        tips = ai['tips']
    else:
        mode = '规则兜底'
        main, side, season = rules['main'], rules['side'], rules['season']
        methods = rules['methods']
        cookware, dropped = dish_rules.build_cookware(methods, None, rules['site_tools'])
        tips = ''
    pot_names = [c['name'] for c in cookware if c['name'] in shop.POTS]
    for c in cookware:
        c['is_pot'] = c['name'] in shop.POTS
        c['have'] = c['is_pot'] and c['name'] in owned
        item = catalog['cookware'].get(c['name']) or catalog['tools'].get(c['name'])
        c['price'] = item['price'] if item else None  # 示例价；配置里没有就不写价格
    # 花费沿用全站的 meal_cost：食材按采购清单算（调味料不算），锅只算画像里还缺的
    buy = main + side
    recipe = {'ingredients_list': '、'.join(buy), 'tools_list': '、'.join(pot_names)}
    if rules['site_id']:  # 站内菜：花费直接按原菜谱的食材清单算，跟列表页「补齐约」一模一样
        recipe['ingredients_list'] = rules['ingredients_list']
    cost = shop.meal_cost(recipe, [], owned, catalog, know_pots=know_pots) if buy or pot_names else None
    rows = shop.shopping_list(recipe['ingredients_list'], catalog) if buy else []
    return {
        'dish': dish, 'description': description, 'mode': mode, 'ai_error': ai_error,
        'matched': rules['matched'], 'site_id': rules['site_id'], 'main': main, 'side': side, 'season': season, 'methods': methods,
        'cookware': cookware, 'dropped': [d for d in dropped if d], 'tips': tips,
        'have': [p for p in pot_names if p in owned], 'missing': [p for p in pot_names if p not in owned],
        'know_pots': know_pots, 'cost': cost, 'rows': rows,
        'empty': not main and not methods,
    }
