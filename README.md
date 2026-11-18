# 稳厨

按家里有的锅具，找到能稳稳做成的菜。Flask + SQLite。

## 本地运行

```bash
pip install -r requirements.txt
python app.py            # 默认 http://127.0.0.1:5001 ，可用环境变量 PORT 改端口
```

`厨房数据库.sqlite3` 要和 `app.py` 放在同一个文件夹。启动时会自动补齐旧库缺的列（如 users.avatar）。

可选环境变量：

- `SECRET_KEY`：登录状态加密用的密钥，线上一定要设成一长串随机字符
- `WENCHU_DB`：数据库文件路径（默认是项目里的 厨房数据库.sqlite3）
- `WENCHU_UPLOAD_DIR`：上传图片存放的文件夹（默认 static/uploads）

## 测试

```bash
python tests/test_main_path.py
```

会把数据库复制到临时文件夹再测，不会改动项目里的数据库。全部通过时显示「失败 0 项」。

## 部署（Render）

- Build Command：`pip install -r requirements.txt`
- Start Command：`gunicorn app:app`
- 环境变量：`SECRET_KEY`

## 导购演示（商业模式）

- 商品数据在 `shop_items.json`：现在全部是示例商品，链接是各平台公开搜索页。换成真实联盟推广链接时，只改这个文件里的 `url`、`price`、`is_sample`。
- 页面：菜谱详情里的「做这道菜的锅」「一键备齐食材」、`/starter` 入门备厨、`/stats` 导购点击统计。
- 现成 12 道菜的菜品图在 `static/dishes/`，由 AI（即梦）生成；`菜品图-写入数据库.sql` 可以把图片路径写进别的数据库。
