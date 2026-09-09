# -*- coding: utf-8 -*-
"""合并预置诗词数据，供 app.py 初始化时导入"""
from seed_data1 import POEMS_1
from seed_data2 import POEMS_2

ALL_POEMS = POEMS_1 + POEMS_2
