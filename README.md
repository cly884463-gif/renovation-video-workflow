# 旧改视频制作工作流

面向真实实拍素材的中文同城视频工作流。覆盖文案来源记录、本地 CosyVoice3 配音、语音对齐、语义选镜、黄色重点字幕、封面、短叠化、整片审核和按账号交付。

**0.1.0 发布候选。** 这是由命令行工具和人工审核组成的制作工作流；不承诺全自动识别房间、材料、人物或客户关系。真实音色、模型、品牌、素材和业务文案由使用者提供。

## 能做什么

- 按指定发布日期与账号排期检查待发布 MP4，保留缺片和恢复记录。
- 原本地 CosyVoice3，或显式选择兼容 HTTP/Gradio；原速合成后只提速一次 1.21 倍。
- ASR 与字幕绑定准确音轨哈希；保留原音和修订版本。
- 逐镜记录准确来源、时间区间、场景及人物/材料范围；生成审核图。
- 1080×1920、30fps，完整语义分页、多处标黄、首帧封面、直切或 4–6 帧叠化、配乐避让。
- 完整解码、黑帧/峰值检查；听审和成片审核独立记录。
- 按账号存入待发布目录，复制后核对 SHA256，遇到不同版本同名文件停止覆盖。

## 使用边界

素材搜索是文件名索引，语义选镜仍需实看。哈希查重不等于场景和构图去重。ASR 不代替真实听审。库存命令只创建缺片/恢复报告，不会私自启动 TTS、渲染或定时任务。操作者或智能体按报告执行下方完整流程。系统不登录或发布到任何社交平台，也不自动清理旧视频。

## 快速开始

Windows，Python 3.10+，FFmpeg/FFprobe 在 PATH。基础环境需要 Pillow；模型环境独立准备。安装属于使用者主动操作，本仓库没有安装器或自动模型下载。

```powershell
# 在选定的 Python 环境中安装基础依赖
python -m pip install -r requirements.txt
python scripts/release_check.py
.\run.bat package-check

# engine 外创建私有项目；local/ 被 Git 忽略
.\run.bat configure --out local/machine.json
python scripts/setup_brand.py --font YOUR_FONT.ttf --logo YOUR_LOGO.png --out local/brand.json
# 编辑 local/machine.json：素材、品牌、音色参考、模型、已有 Python 路径
.\run.bat init --config local/machine.json
.\run.bat doctor --config local/machine.json --out preflight_v1
```

`doctor` 报缺项是首次配置的正常结果；通过环境检查仍需配音短样和实际样片。字体/Logo 留在私有目录，`setup_brand.py` 只登记资源，不授予任何素材使用权。

完整步骤见 [制作教程](docs/workflow.md)、[配置说明](docs/configuration.md)、[选镜和返修规范](docs/editing.md)、[发布检查](docs/releasing.md)。

## 批次入口

复制 `examples/schedule.example.json` 为 `local/schedule.json`，填写实际账号。周一是 0，周日是 6。所有日期显式输入：如凌晨检查次日，就传当地触发日期加一天，命令不会读取电脑日期替你猜测。

```powershell
.\run.bat batch inventory --config local/schedule.json --date 2026-11-01
.\run.bat batch review --config local/schedule.json --date 2026-11-01
.\run.bat batch deliver --config local/schedule.json --date 2026-11-01 --account city_a --receipt local/work/delivery_v1/delivery.json
```

共享盘离线会停止检查，未配置目录单独报告；已存在本地工作目录的账号标为恢复既有任务，不重复启动。批次锁只防止这些命令并发写记录，外部配音/剪辑进程仍需操作者核对。

## 目录

| 目录 | 内容 |
|---|---|
| `engine/` | 可追溯的配音、对齐、剪辑、审核核心及包清单 |
| `scripts/` | 入口、品牌登记、批次库存/审核/交付、发布检查 |
| `examples/` | 无真实账号和凭据的模板 |
| `docs/` | 操作、规则、发布与排错说明 |
| `tests/` | 可离线执行的回归测试 |
| `local/` | 使用者创建的私有配置、素材和产物；不入版本库 |

## 测试

```powershell
python -m unittest discover -s tests -v
python scripts/release_check.py
```

真实模型需要另做短样与全文听审。CI 不下载权重、不联网调用配音、不包含私人素材。技术样片验证步骤见发布文档。

## 版权与发布状态

本版本为发布候选，代码开源许可证待仓库所有者选择。没有 LICENSE 文件时，不应将其当作已获得开源再分发授权。第三方依赖、模型和使用者素材各自适用其许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。
