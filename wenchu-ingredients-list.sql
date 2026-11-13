-- 稳厨：给 recipes 加一列 ingredients_list（整道菜要用的全部食材）
-- 用途：详情页在第一步之前显示，和厨具清单放一起，让人一眼看清
-- 内容就是整理版里每道菜的“食材”那一栏，一字没改
-- 只跑一次就行

ALTER TABLE recipes ADD COLUMN ingredients_list TEXT;

UPDATE recipes SET ingredients_list = '鸡翅、可乐（300ml 一罐）、料酒、葱、姜、生抽、老抽、蚝油、油（不要用亚麻籽油、橄榄油或芝麻油）' WHERE id = 1;
UPDATE recipes SET ingredients_list = '虾仁（建议买处理好的开背虾仁）、玉米淀粉、盐、胡椒粉、鸡蛋 1 个（用蛋黄）、芥末蛋黄酱、沙拉酱、葱、姜、大量油（不要用亚麻籽油、橄榄油或芝麻油）' WHERE id = 2;
UPDATE recipes SET ingredients_list = '奥利奥碎 100g、黄油 50g、黑巧 180g（可按喜好加牛奶巧克力，越多越甜）、牛奶 120g、吉利丁片 3 片、淡奶油 200g、白糖、巧克力粉（撒面用）' WHERE id = 3;
UPDATE recipes SET ingredients_list = '半颗花菜、五花肉、豆瓣酱、小米辣（可选）、姜、蒜、料酒、盐（泡花菜的盐水）、油（不要用亚麻籽油、橄榄油或芝麻油）' WHERE id = 4;
UPDATE recipes SET ingredients_list = '吐司 2 片、奶酪棒 2 个、巧克力（黑巧＋牛奶巧克力交叉放）' WHERE id = 5;
UPDATE recipes SET ingredients_list = '鱿鱼（新手可直接买处理好的鱿鱼腿）、胡椒粉、盐、糖、味精、鸡粉、料酒、生抽、姜、蒜头 3 颗、干葱 2 颗、油（不要用亚麻籽油、橄榄油或芝麻油）' WHERE id = 6;
UPDATE recipes SET ingredients_list = '土豆、鸡腿肉（可直接买切好的）、米饭、生抽、老抽、糖/蜂蜜、油' WHERE id = 7;
UPDATE recipes SET ingredients_list = '龙虾 2 只（建议买处理好的）、伊面（买不到用通心粉）、黄油、生姜、油（不要用亚麻籽油、橄榄油或芝麻油）、提前烧好的开水、芝士片 2 片、淡奶油 50ml、玉米淀粉、洋葱（可选）、蒜、盐' WHERE id = 8;
UPDATE recipes SET ingredients_list = '鸡蛋 5 个、姜末、蟹醋、油' WHERE id = 9;
UPDATE recipes SET ingredients_list = '猪肝 1 块、面粉、盐、胡椒粉、白糖、生抽、淀粉、食用油、葱、姜 2-3 片、蒜 2-3 颗、蔬菜（可选，喜欢的）' WHERE id = 10;
UPDATE recipes SET ingredients_list = '意面 60g（一人份）、淡奶油 100ml、牛奶 100ml、培根 75g、蒜 2-3 颗、黄油 50g、蘑菇 2-3 个、盐' WHERE id = 11;
UPDATE recipes SET ingredients_list = '鸡蛋 3 个、米饭、生抽、食用油' WHERE id = 12;
