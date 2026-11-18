"""审核 AI 提的菜名别名（待审核的不会用来对齐菜名，也不进输入联想）。

用法（在项目根目录）：
  python tools/aliases.py                 列出待审核的别名
  python tools/aliases.py ok 宫爆鸡丁      通过（变成生效）
  python tools/aliases.py no 宫爆鸡丁      不通过（删掉）
数据库默认是 厨房数据库.sqlite3，可以用环境变量 WENCHU_DB 指定。
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import dish_store  # noqa: E402


def main(argv):
    db = os.environ.get('WENCHU_DB', os.path.join(ROOT, '厨房数据库.sqlite3'))
    conn = sqlite3.connect(db)
    try:
        dish_store.init_tables(conn)
        conn.commit()
        if len(argv) >= 2 and argv[0] in ('ok', 'no'):
            done = dish_store.review_alias(conn, argv[1], approve=argv[0] == 'ok')
            print(('已通过：' if argv[0] == 'ok' else '已删除：') + argv[1] if done else '没找到这条待审核别名：' + argv[1])
            return 0 if done else 1
        rows = dish_store.pending_aliases(conn)
        if not rows:
            print('没有待审核的别名。')
        for alias, canon, source, created in rows:
            print(f'{alias} → {canon}（来源 {source}，{created} UTC）')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
