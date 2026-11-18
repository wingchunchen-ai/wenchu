# 拍照认菜：把一张菜的照片交给 DeepSeek（只用 deepseek-v4-flash，官方看图格式，detail=low）认出菜名
#
# 隐私：照片只在内存里处理——不写硬盘、不进数据库、不写日志；认完就丢。
# 官方文档：https://api-docs.deepseek.com/guides/vision （flash 支持看图；pro 不支持，也不许用）
import base64
import io
import json
import re
import urllib.error
import urllib.request

import dish_ai

MAX_BYTES = 5 * 1024 * 1024       # 超过 5MB 直接拒绝（网站整体上传上限也是 5MB）
MAX_SIDE = 1024                   # 有 Pillow 时先缩到最长边 1024 像素再发，省流量；detail=low 服务器还会再缩
TIMEOUT = 20

SYSTEM_PROMPT = (
    '你是菜品识别助手。用户发来一张照片，判断照片里是哪道菜（优先中式家常菜的叫法）。'
    '只输出一个 JSON 对象，不要输出别的文字：{"dish_name": "最通用的中文菜名，20字以内；看不出是菜就写空字符串", '
    '"confidence": 0到1之间的小数，表示有多大把握}'
)

try:  # Pillow 可选：有就先缩图、顺便去掉 EXIF（含拍摄地点）；没有就按原图发
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None


class PhotoError(Exception):
    """照片本身的问题（太大、格式不支持、打不开），给用户看的一句话"""


def sniff(data):
    # 看文件开头判断格式：返回 'jpeg' / 'png' / 'webp' / 'heic' / 'gif' / None
    head = data[:16]
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head.startswith(b'\x89PNG'):
        return 'png'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    if head.startswith(b'GIF8'):
        return 'gif'
    if head[4:8] == b'ftyp' and head[8:12] in (b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1', b'avif'):
        return 'heic'
    return None


def prepare(data):
    # 校验 + 缩图，返回 (base64 字符串, mime)。不合格抛 PhotoError
    if not data:
        raise PhotoError('没收到照片，请再拍一张或从相册选一张')
    if len(data) > MAX_BYTES:
        raise PhotoError('照片超过 5MB，请换一张小一点的')
    kind = sniff(data)
    if kind == 'heic':
        raise PhotoError('这是苹果的 HEIC 格式，暂时认不了：可以截个屏再传，或在「设置 → 相机 → 格式」选「兼容性最佳」')
    if kind not in ('jpeg', 'png', 'webp'):
        raise PhotoError('只支持 JPG、PNG、WebP 格式的照片')
    if Image is None:
        return base64.b64encode(data).decode('ascii'), 'image/' + kind
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)  # 按 EXIF 方向摆正，然后只存像素：EXIF（含位置）不会带出去
            im = im.convert('RGB')
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=85)
    except Exception:  # 图片坏了 / 解不开
        raise PhotoError('这张照片打不开，请换一张') from None
    return base64.b64encode(buf.getvalue()).decode('ascii'), 'image/jpeg'


def call_vision(b64, mime, api_key=None, timeout=TIMEOUT, opener=None):
    # 发给 DeepSeek 看图；返回 dish_ai.AIReply（模型回的文字 + 用量）
    import os
    key = api_key if api_key is not None else os.environ.get('DEEPSEEK_API_KEY', '')
    if not key.strip():
        raise dish_ai.AIError('没配置 AI 密钥')
    if 'pro' in dish_ai.MODEL:  # 保险：pro 不支持看图，也不许用
        raise dish_ai.AIError('模型配置不对')
    body = {
        'model': dish_ai.MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': '这张照片是什么菜？只输出 json。'},
                {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}', 'detail': 'low'}},
            ]},
        ],
        'response_format': {'type': 'json_object'},
        'thinking': {'type': 'disabled'},
        'temperature': 0,
        'max_tokens': 100,
        'stream': False,
    }
    req = urllib.request.Request(dish_ai.API_URL, data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key.strip()})
    body = None  # 照片的 base64 只留在请求里，不再引用
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:  # 只看状态码；不带请求内容（里面有密钥和照片）
        raise dish_ai.AIError('密钥无效或已失效' if e.code in (401, 403) else f'AI 服务返回 {e.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise dish_ai.AIError('连不上 AI 服务或超时') from None
    except ValueError:
        raise dish_ai.AIError('AI 返回的不是 JSON') from None
    try:
        return dish_ai.AIReply(payload['choices'][0]['message']['content'], payload.get('usage'), payload.get('model'))
    except (KeyError, IndexError, TypeError):
        raise dish_ai.AIError('AI 返回格式不对') from None


def parse_guess(text):
    # 严格校验 {"dish_name": "...", "confidence": 0~1}；不合格或没认出来抛 AIError
    if not isinstance(text, str) or not text.strip():
        raise dish_ai.AIError('AI 没有返回内容')
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    try:
        data = json.loads(t)
    except ValueError:
        raise dish_ai.AIError('AI 返回的不是合格 JSON') from None
    if not isinstance(data, dict):
        raise dish_ai.AIError('AI 返回的不是 JSON 对象')
    name = dish_ai._clean_name(data.get('dish_name'))
    conf = data.get('confidence')
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        raise dish_ai.AIError('AI 没给出把握程度')
    conf = min(max(float(conf), 0.0), 1.0)
    if not name or conf < 0.2:
        raise dish_ai.AIError('没认出照片里是哪道菜')
    return {'dish_name': name, 'confidence': conf}


def confidence_label(conf):
    return '高' if conf >= 0.8 else ('中' if conf >= 0.5 else '低')
