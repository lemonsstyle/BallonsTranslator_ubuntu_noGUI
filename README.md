# BallonsTranslator (macOS 使用说明)

本文档只针对 macOS（Apple Silicon）下的命令行批处理模式。

核心运行命令：

```bash
QT_QPA_PLATFORM=offscreen python launch.py --frozen --headless --exec_dirs "待翻译图片目录"
```

## 1. 创建并激活虚拟环境

推荐使用 conda 独立环境。

```bash
conda create -n pc python=3.14 -y
conda activate pc
```

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 下载并放置模型文件

1. 从[网盘](https://www.alipan.com/s/vbuTbH5bER6)下载 `data.zip`。
2. 解压得到 `data/` 目录。
3. 把 `data/` 放到项目根目录（和 `launch.py` 同级）。

结构示例：

```text
BallonsTranslator_ubuntu_noGUI-AI_trans/
├── data/
├── config/
├── launch.py
└── ...
```

## 4. 配置翻译参数

编辑 [config/config.json](config/config.json)：

1. `module.translator` 使用 `LLM_API_Translator`
2. 在 `module.translator_params.LLM_API_Translator` 中填写：
   - `system_prompt`
   - `override model`
   - `endpoint`（OpenRouter 建议填 `https://openrouter.ai/api/v1`）
3. 如需给模型额外背景设定，可在命令行使用 `--reference ./comic_ref.md`

建议：

1. 建议把 `apikey` 留空，运行前通过环境变量提供真实密钥。
2. 先把 `enable_book_context` 设为 `false`，可减少额外请求。

## 5. 准备待翻译图片目录

例如 `ces/`：

```text
ces/
├── 1.png
├── 2.png
└── 3.png
```

## 6. 运行翻译

```bash
conda activate pc
export BA_API_KEY="你的真实密钥"
QT_QPA_PLATFORM=offscreen python launch.py --frozen --headless --exec_dirs "ces/"
```

带参考文档运行：

```bash
conda activate pc
export BA_API_KEY="你的真实密钥"
QT_QPA_PLATFORM=offscreen python launch.py --frozen --headless --exec_dirs "ces/" --reference ./comic_ref.md
```

多个目录可用逗号分隔：

```bash
QT_QPA_PLATFORM=offscreen python launch.py --frozen --headless --exec_dirs "ces/,book2/,book3/"
```

## 7. 输出结果

在每个项目目录下生成：

1. `mask/`：文本区域掩码
2. `inpainted/`：修复后的底图
3. `result/`：绘制译文后的结果图
4. `imgtrans_.json`：工程状态与中间结果

## 8. 常见问题

### 8.1 运行看起来“卡住”

1. 先看日志卡在 `Inpaint` 还是 `Translation`。
2. 如果日志显示 `Inpainter set to lama_large_512px`，速度会很慢；可改为 `opencv-tela`。
3. 如果卡在 `Translation`，通常是 API 网络/鉴权问题，先用脚本自测。

### 8.2 OpenRouter 连通性自测

```bash
conda activate pc
python scripts/openrouter_smoketest.py
```

在脚本顶部填好 `endpoint`、`api key`、`prompt`、`text` 后运行。

也可以直接：

```bash
export BA_API_KEY="你的真实密钥"
python scripts/openrouter_smoketest.py
```
