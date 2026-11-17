-- 稳厨：给 recipes 加一列 tools_list（整道菜要用的全部厨具）
-- 用途：详情页在第一步之前显示，让人一眼看清，不会做到一半发现缺东西
-- 内容就是整理版里每道菜的“锅具·工具”那一栏，一字没改
-- 只跑一次就行

ALTER TABLE recipes ADD COLUMN tools_list TEXT;

UPDATE recipes SET tools_list = '小汤锅（蒸锅拿掉上面的蒸笼就行）、平底锅、锅盖、案板、刀、厨房纸、夹子、碗、勺子' WHERE id = 1;
UPDATE recipes SET tools_list = '炒锅、小刀、小碗、装盘的碗、木筷子、漏勺' WHERE id = 2;
UPDATE recipes SET tools_list = '能融化巧克力和黄油的锅子、模具、打蛋器、塑料袋、碗、保鲜膜、冰箱' WHERE id = 3;
UPDATE recipes SET tools_list = '炒锅、刀、碗、锅铲' WHERE id = 4;
UPDATE recipes SET tools_list = '空气炸锅、空气炸锅纸、勺子、盘子' WHERE id = 5;
UPDATE recipes SET tools_list = '炒锅、锅盖、刀、剪刀、小碗、锅铲' WHERE id = 6;
UPDATE recipes SET tools_list = '平底锅、锅盖、刀、碗、勺子、锅铲' WHERE id = 7;
UPDATE recipes SET tools_list = '平底锅、小汤锅（蒸锅拿掉上面的蒸笼就行）、刀、叉子、小碗、锅铲、盘子' WHERE id = 8;
UPDATE recipes SET tools_list = '炒锅、大碗、小碗、锅铲、盘子' WHERE id = 9;
UPDATE recipes SET tools_list = '炒锅、大碗、刀、锅铲' WHERE id = 10;
UPDATE recipes SET tools_list = '平底锅、小汤锅（蒸锅拿掉上面的蒸笼就行）、刀、剪刀、锅铲' WHERE id = 11;
UPDATE recipes SET tools_list = '平底锅、小碗、筷子、锅铲' WHERE id = 12;
