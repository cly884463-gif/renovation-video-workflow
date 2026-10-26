# 发布与验收

## 本地发布检查

1. 确认版本、README 和 CHANGELOG 一致。
2. 运行单元测试和继承的路径/部署回归。
3. 运行技术媒体烟雾测试；它验证真实 FFmpeg 渲染、字幕标黄、首帧封面、短叠化与解码，不代表真实配音或语义审核。
4. 运行 `python scripts/release_check.py`。扫描仅针对公开目录的固定风险模式，是自动辅助，不保证发现所有隐私/许可问题。
5. 检查 manifest 差异、公开压缩包内容；明确选择 LICENSE、仓库名、可见性后再上传。

引擎维护者修改 engine 后用 `python scripts/release_check.py --refresh-manifest` 更新发布清单，再重新测试。运行时修改配置应放 engine 外；不通过重建清单掩盖未知篡改。

```powershell
python engine/scripts/test_source_paths.py --out local/test-source-paths
python engine/scripts/test_deployment.py --out local/test-deployment
python tests/media_smoke.py --out local/media-smoke --font YOUR_FONT.ttf
python scripts/release_check.py
```

输出目录必须是新目录，失败记录保留用于诊断。媒体烟雾测试使用纯色卡和合成音调，不产生可发布业务片，也不伪造审核通过。模型实测需自行提供权重和参考音频，完成短样、全文听审及一条完整真实素材片。

## GitHub

CI 运行基础单元测试和发布扫描，不自动上传素材或发布成片。建议先私有仓库审查发布文件；确认后再公开。本地候选不包含 Git 远端、个人身份或访问令牌。

上传前仍需确认：仓库所有者/名称、公开或私有、代码许可证。仓库内 `local/`、`private/`、模型及媒体文件均不进入版本库。`.gitignore` 不是秘密扫描器，不能清除已提交历史。

## 故障排查

| 问题 | 处理 |
|---|---|
| package-check 清单变化 | 核对源码改动；维护者重新验证后更新清单 |
| 无品牌资源/缺字 | 提供合法字体与 Logo，运行 setup_brand 并检查字符表 |
| TTS 超时 | 查已有服务任务和 request_status，不盲目重发 |
| 音轨漏首句/断句异常 | 原音实际听审、按完整语义修订，新版重新对齐 |
| 共享目录离线 | 恢复连接再查库存；不认定全部缺片 |
| 审核记录过期 | 重新生成受影响证据并审当前版本 |
| 同名不同 SHA | 保留旧文件，由操作者核准版本处理 |
| .copying 残留 | 检查复制任务与哈希，先保留证据，不自动删除 |

当前公开版未提供无人值守编排器、自动素材语义分类器或一键模型安装器。批次库存、制作、审核与交付通过明确命令衔接。
