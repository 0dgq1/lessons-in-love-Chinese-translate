# Ren'Py 实时中英双语翻译

为可编辑 `game/screens.rpy` 的 Ren'Py 游戏添加英文原文和简体中文译文。已在本地 Ren'Py 8.2.3 游戏环境验证，其他游戏可能需要调整对话界面接入。

## 功能

- 支持 DeepSeek 和 Gemini；先显示英文，后台补上中文。
- 默认速度优先、关闭 DeepSeek 思考模式，提前翻译后续三句并缓存。
- 当前句和预翻译分别使用后台线程；不重复请求正在预翻译的句子。
- 预读遇到分支、菜单、Python 或跳转等边界停止，动态变量句实际显示时处理。
- 尽量沿用原游戏对话框，中英文顺序排版，长文本用滚轮阅读。
- 可选质量提示词和独立术语表。

## 安装

先退出游戏。使用系统 Python 3.10 或更新版本运行：

```powershell
python install.py "E:\path\to\game-root"
```

安装脚本备份修改前的界面文件到 `game/bilingual_backup`，保留已有私有配置；首次安装默认关闭翻译。Windows 上仅在安装电脑本地复制微软雅黑，并导出本机信任的公开 CA 证书供游戏自带 Python 校验 HTTPS。字体和证书不包含在仓库里。其他系统需自行配置中文字体及受信任的 PEM CA 文件。

编辑游戏目录中的 `game/bilingual_config.json`：填写 API 密钥、模型，设置 `enabled: true`，再正常启动游戏。

- DeepSeek：`provider: "deepseek"`，`base_url: "https://api.deepseek.com"`，模型按账户可用名称配置。
- Gemini：`provider: "gemini"`，`base_url: "https://generativelanguage.googleapis.com/v1beta"`，模型按账户可用名称配置。
- `prefetch_lines`：默认 3，0 为关闭，最大 10。
- `quality_mode`：默认 false；true 启用详细本地化提示词及 `bilingual_glossary.json`。
- `font`：相对 `game` 的中文字体路径。
- `ca_bundle`：可选 PEM 文件路径，默认 `bilingual_certs/windows-ca.pem`。始终校验证书和域名。

对白会发送到所选服务并使用 API 配额。提前翻译但最终未阅读的句子也会使用配额。缓存位于 `game/bilingual_cache.json`。更换提示词、术语或模型会使用不同缓存标识。请勿提交自己的配置、缓存、字体、证书、游戏源码或存档。

## 测试与卸载

```powershell
python -m unittest test_bilingual -v
```

17 项模拟测试覆盖接口、证书、缓存、预读边界、去重、取消和速度模式；不调用真实 API。真实联网验证和不同游戏的布局需要本机测试。

卸载时退出游戏，将 `game/bilingual_backup/screens.rpy.original` 恢复为 `game/screens.rpy`，移除本工具的 `.rpy`、对应生成的 `.rpyc`、Python 模块、配置及专用资源目录。若安装后改过界面，需合并撤销，避免覆盖后续修改。不要删除游戏存档。
