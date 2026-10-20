# 作业批量批改 Skill

给一份评分要求文档 + 全班作业压缩包，自动批量批改：

- 解压并按份处理 `.docx` / `.pdf` 作业
- 按评分点在每题后打分：Word 写红色可编辑文字，PDF 用红色手写笔迹写在页边
- 抽出作业里的截图交给大模型看图判断（运行结果、流程图、界面效果）
- 输出批改后文件、Excel 成绩统计表、全班共性问题汇总

## 安装

一条命令（需要 Node.js）：

```bash
npx skills add poleHansen/homework-helper-skill --skill homework-grader
```

按提示选择要安装到的 agent 即可。也可以直接把 `skills/homework-grader/` 整个目录拷到目标 skills 目录，例如 codex：

- 用户级：`~/.codex/skills/homework-grader/`
- 项目级：`<项目>/.codex/skills/homework-grader/`

运行依赖 Python 3.10+ 与以下库：

```bash
pip install pymupdf python-docx openpyxl pillow
```

## 使用

把评分要求文档和作业压缩包交给 codex或者其他agent，说「批改这批作业」即可，`SKILL.md` 里定义了完整工作流。

手工调用脚本的顺序：

```bash
S=skills/homework-grader/scripts
W=批改结果

# 1. 解压
python $S/prepare.py 全班作业.zip $W

# 2. 读要求文档，写 $W/rubric.json（评分点与分值）

# 3. 逐份抽取文本与图片
python $S/extract.py $W/submissions/张三.docx $W/extracted/张三

# 4. 读 content.md 和 images/ 判分，写 $W/grades/张三.json

# 5. 落笔
python $S/annotate_docx.py $W/grades/张三.json $W/submissions/张三.docx $W/result/张三.docx
python $S/annotate_pdf.py  $W/grades/张三.json $W/submissions/张三.pdf  $W/result/张三.pdf

# 6. 统计表
python $S/make_excel.py $W/grades $W/批改统计.xlsx
```

## 目录结构

```
skills/
  homework-grader/
    SKILL.md              工作流说明（给 Agent 读）
    scripts/
      prepare.py          解压、修中文文件名乱码、生成清单
      extract.py          docx/pdf → content.md + images/
      annotate_docx.py    题末追加红色分数
      annotate_pdf.py     页边手写红笔打分 + 末页总分
      make_excel.py       汇总成绩表
```

## 产出

```
批改结果/
  submissions/     原始作业
  extracted/       每份的文本与图片（中间产物）
  grades/          每份的评分 json
  result/          批改后的作业
  批改统计.xlsx     文件名 / 各评分项 / 总分 / 满分 / 备注
  共性问题.md       全班共性问题与教学建议
```

## 限制

- 只支持 `.docx` / `.pdf`；`.doc`、`.wps` 等旧格式直接跳过并在清单里列出
- 不支持扫描件/图片型 PDF（没有文字层，无法定位题号）
- PDF 打分手写效果依赖系统字体 `STXINGKA.TTF`（华文行楷）与 `Inkfree.ttf`，Windows 自带
- 一次建议不超过 60 份，超过时分批批改，最后合并 `grades/` 再生成统计表

## 致谢
感谢 [linuxdo（linux.do） ](https://linux.do/) 社区的交流、分享与反馈。
