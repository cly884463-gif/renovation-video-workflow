# 完整制作流程

以下 `PROJECT` 指私有项目绝对路径，`WORK` 指 machine.json 的 workspace。命令从仓库根运行。每个输出目录只使用一次，返修使用 v2/v3 等新目录。

## 1. 库存与文案

先执行 batch inventory，读取 available / needs_production / resume_existing / not_scheduled。只处理缺片账号；恢复任务前查已有本地音频、成片、运行进程与审核记录。目录离线先恢复连接，不生成整批替代任务。

从获准文案库选择原稿，保存来源、段落、原文、实际稿及差异。地区/称呼替换单独记录，正文改动需对应授权。同发布日期集中比较去掉地区后的正文、开头、结构与结尾。模板轮换不等于机械换地名。

## 2. 配音和听审

```powershell
.\run.bat voice-check --config PROJECT/machine.json
.\run.bat voice --config PROJECT/machine.json --text PROJECT/approved.txt --out voice_v1
.\run.bat align --config PROJECT/machine.json --audio WORK/voice_v1/narration.wav --text PROJECT/approved.txt --pages PROJECT/pages.json --out alignment_v1
```

pages.json 为 `[{"lines":["完整语义"],"highlights":["关键词"]}]`，显示文字无标点，配音稿保留语义标点。全部音轨完成后统一听审；ASR 仅作漏字、多字、读音及对齐辅助。审核按准确音轨 SHA 留记录。

断句或读音返修保留原音、修订稿和处理记录；只剪静音也要重对齐之后字幕/镜头。多音字提示可放在内部合成稿，但准确展示稿与实际读音核对记录应保留。不能把错误 ASR 字样直接改成正确词后标通过。

## 3. 选镜和审核

从实际画面确认房间、动作、人物与材料，检查源首中尾、运动余量及前后案例关系。镜头长度依完整动作与语义，不强制固定镜头数量，也不为长开头切三个不同人物镜头。

```powershell
.\run.bat material-index --config PROJECT/machine.json --query 厨房 --limit 30
.\run.bat normalize --config PROJECT/machine.json --source SOURCE.mp4 --start 1 --duration 3.2 --out shots/00
.\run.bat new-job --config PROJECT/machine.json --draft PROJECT/draft.json --out task_v1
.\run.bat assemble --config PROJECT/machine.json --draft WORK/task_v1/draft.json --alignment WORK/alignment_v1 --review WORK/evidence_v1/review.json --out plan_v1
.\run.bat evidence --config PROJECT/machine.json --job WORK/plan_v1/job.json --out evidence_v1
```

完善草稿中全部路径、文案、镜头、配乐和封面。对 `review.json` 的每镜实际看图后填状态、审核人、可见事实和语义评分，按准确源匹配人物及材料授权。新旧版本可复用未变图片，但不自动继承审核。

## 4. 渲染与终审

```powershell
.\run.bat validate --config PROJECT/machine.json --job WORK/plan_v1/job.json
.\run.bat preview --config PROJECT/machine.json --job WORK/plan_v1/job.json --out preview_v1
.\run.bat render --config PROJECT/machine.json --job WORK/plan_v1/job.json --out render_v1
.\run.bat qa --config PROJECT/machine.json --job WORK/plan_v1/job.json --video WORK/render_v1/video.mp4 --out qa_v1
.\run.bat align --config PROJECT/machine.json --audio WORK/render_v1/video.mp4 --text PROJECT/approved.txt --pages PROJECT/pages.json --out mix_alignment_v1
```

看完整片并听完整声音，再按实际结果填写 qa.json：visual_review、reviewer、review_note、subjective_listening、listening_note、realtime_playback。检查字幕、封面、语义、房间/材料、曝光、切点、片尾及音乐。图像联系表和完整解码各有用途，都不等于连续听看通过。

```powershell
.\run.bat finalize --config PROJECT/machine.json --job WORK/plan_v1/job.json --qa WORK/qa_v1/qa.json --mix-alignment WORK/mix_alignment_v1/alignment.json --out delivery_v1
```

仅 `reviewed_delivery` 的准确版本可进入 batch deliver。修改后旧批准失效，保留旧文件及历史，重新验证变更部分与完整成片。

## 5. 一起送审和存入文件夹

批次目录创建 review_items.json：

```json
[{"account":"示例账号","kind":"video","file":"city_a/render_v1/video.mp4","sha256":"实际文件SHA256","text":"实际使用稿"}]
```

voice 类型显示音频播放器。所有文件必须在本批目录内，页面生成会校验哈希。批次完成再统一发送页面；不要逐条反复催审。

本机预览可由使用者运行 `python -m http.server 8780 --bind 127.0.0.1 --directory BATCH_DIR`，仅服务本批目录。服务不是自动创建的定时任务。完成审核后执行 README 的 batch deliver 命令；只存 MP4，不将私人文案或审批放进发布目录。
