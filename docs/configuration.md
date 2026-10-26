# 配置与迁移

## 三份配置

- `machine.json`：实际工作目录、FFmpeg、素材库、配音和 ASR 环境。
- `brand.json`：字体、Logo、字符表和资源哈希；使用 `setup_brand.py` 从使用者资源生成。
- `schedule.json`：发布根目录、批次工作目录、账号名称与星期排期。

机器配置内的 `workspace`、`approvals`、`brand_config` 及模型路径相对机器配置文件解析；`history` 相对 workspace。批次配置的目录相对批次配置文件。CLI 文件参数相对当前命令目录，`--out` 相对工作目录，建议正式操作传完整路径。

```json
{
  "source_roots": {"shared": ["./materials"]},
  "material_roots": ["@shared/footage"],
  "copy_root": "@shared/copy",
  "brand_config": "./brand.json"
}
```

`@library/库ID/路径` 支持多库，同一库多个入口必须确实是同一内容；不凭目录名继承其他用户审批。初始 approvals 和 history 都为空，绝不导入开发者的真实审批记录。

## 配音

默认 `tts.api=local`。填写已有 CosyVoice3 仓库、模型目录、该环境 Python、获准参考音频和准确参考原话；`reference_authorized` 按实际情况填写。工具不安装依赖、不下载权重、不终止其他服务、不自动切换音色。

`http` 模式仅用于实现 `POST /api/tts` 契约的服务，不能把任意 WebUI URL 当作兼容接口。原速请求后本机仅执行一次 1.21 倍处理。失败保留状态及错误，先查服务任务，避免重复提交。凭据通过私有配置管理，禁止进入仓库。

ASR 使用已有 FunASR/Paraformer 环境；默认不启用兼容适配器。保留的 `astra_funasr_1_3_14` 名称是历史接口标识，仅在确认同版本时间戳问题时使用，不表示任何远程依赖。

## 审核数据

`engine/configs/job.example.json` 是待填写草稿，不是可直接交付的样片。每镜记录：source、source_start、source_duration、scene_id、intent、人物/材料依据、规范化文件及来源收据。审核必须绑定准确版本，替换镜头或音轨后重建受影响证据。

初始 `engine/data/approvals.json` 的 presenters/materials 对象为空。每条获准源需 `source`（稳定库路径）、`scope: exact`、`status: approved`、`basis` 和 `authority`。真实性由审核人核对，软件只验证记录结构和绑定关系。

## 依赖与服务恢复

基础 Python 与模型 Python 可分离；基础 requirements 不包含 PyTorch、CosyVoice 或模型权重。安装模型依照所选模型版本官方说明。本工作流不管理模型服务生命周期，因此没有自动关闭/恢复服务。旧工程中临时释放内存的人工操作不进入公开版默认流程。
