# 广韵字音数据（韵典网整理本，瘦身抽取）

来源：https://github.com/BYVoid/ytenx （ytenx.org 韵典网数据文件）
- guangyun_chars.tsv：字→小韵号（自 kyonh/Dzih.txt 去释义瘦身）
- guangyun_syllables.tsv：小韵号/代表字/声母/韵目等/韵系/反切（自 kyonh/SieuxYonh.txt）

《广韵》（1008）原典属公有领域；本抽取仅含音韵结构字段，不含释义文本。
声调由韵目名判定（206 韵四声韵目名互不重复，见 hermes_poetry/extract/phonology.py
内嵌规范表，构建时对未覆盖韵目响亮报错）。
