-- 稳厨：给现成 12 道菜写入菜品图（图片为 AI（即梦）生成，文件在 static/dishes/）
-- 按菜名匹配，线上库编号不一样也能用；已经有图的菜不会被覆盖。可重复执行。
UPDATE recipes SET image = '/static/dishes/recipe-01.webp' WHERE name = '可乐鸡翅' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-02.webp' WHERE name = '芥末虾球' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-03.webp' WHERE name = '巧克力慕斯蛋糕' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-04.webp' WHERE name = '干锅花菜' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-05.webp' WHERE name = '熔岩吐司' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-06.webp' WHERE name = '生啫鱿鱼' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-07.webp' WHERE name = '秘制土豆鸡腿饭' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-08.webp' WHERE name = '龙虾面' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-09.webp' WHERE name = '赛螃蟹' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-10.webp' WHERE name = '爆炒猪肝' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-11.webp' WHERE name = '奶油蘑菇意面' AND (image IS NULL OR image = '');
UPDATE recipes SET image = '/static/dishes/recipe-12.webp' WHERE name = '蛋炒饭' AND (image IS NULL OR image = '');
