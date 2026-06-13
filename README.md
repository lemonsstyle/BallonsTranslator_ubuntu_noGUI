# 漫画批量翻译工具

English version: [README_EN.md](README_EN.md)

这是一个基于 BallonsTranslator 的漫画翻译项目，当前重点是无界面批量处理漫画目录。它会按配置自动完成文字检测、OCR、翻译、原文擦除和结果图导出。

## 功能

- 批量处理一个或多个漫画图片目录。
- 自动检测气泡/文字区域并识别原文。
- 使用配置的翻译器生成目标语言文本，支持 `LLM_API_Translator` 等 AI 接口。
- 可选启用全书 OCR 上下文预分析，让 LLM 先总结角色、术语和语气，再逐页翻译。
- 自动修复原文字区域并导出嵌字后的结果图。

## 使用方法

先在 `config/config.json` 中确认模块和翻译器配置，尤其是：

- `module.translator`
- `module.translate_source`
- `module.translate_target`
- `module.translator_params`
- `module.enable_detect`
- `module.enable_ocr`
- `module.enable_translate`
- `module.enable_inpaint`

### 使用其他 AI 服务

如果你想接入自己配置的第三方 AI 站点，确认该站点提供 OpenAI 兼容接口后，主要改 `config/config.json` 里的三个字段：

- `module.translator_params.LLM_API_Translator.endpoint`：填写服务商提供的 Base URL，例如 `https://example.com/v1`。不要填写完整的 `/chat/completions` 路径。
- `module.translator_params.LLM_API_Translator.override model`：填写服务商实际模型名，例如 `deepseek-chat`、`qwen-plus` 或 `provider/model-name`。
- `module.translator_params.LLM_API_Translator.apikey`：填写服务商 API Key。不要把真实 Key 提交到公开仓库。

最小示例：

```json
{
  "module": {
    "translator": "LLM_API_Translator",
    "translator_params": {
      "LLM_API_Translator": {
        "endpoint": "https://example.com/v1",
        "override model": "provider/model-name",
        "apikey": "YOUR_API_KEY"
      }
    }
  }
}
```

批量运行：

```bash
python launch.py --headless --exec_dirs "/path/to/chapter1,/path/to/chapter2"
```

注意：

- `exec_dirs` 使用英文逗号分隔目录。
- 逗号后不要加空格。
- 每个目录会生成或复用 `imgtrans_<目录名>.json` 工程文件。
- 最终图片输出到对应目录的 `result/`。
- 如需传入术语表或参考文档，可使用：

```bash
python launch.py --headless --exec_dirs "/path/to/chapter1" --reference "/path/to/reference.md"
```

## 文件结构

- `launch.py`：启动入口，负责解析命令行参数、加载配置、初始化环境。
- `config/config.json`：主配置文件，控制模块、语言、API、模型和运行开关。
- `modules/`：核心处理模块，包括检测、OCR、翻译和修复。
- `modules/translators/`：翻译器实现，`trans_llm_api.py` 是通用 LLM API 翻译器。
- `ui/`：主流程和 Qt 界面代码；headless 模式也复用这里的流程控制。
- `utils/`：项目文件、图片读写、配置、日志等基础工具。
- `data/`：模型、缓存或运行数据目录。
- `logs/`：运行日志目录。

## 执行流程

1. `launch.py` 加载配置并进入 headless 模式。
2. `MainWindow.run_batch()` 解析 `exec_dirs`，逐个打开漫画目录。
3. 项目目录不存在工程 JSON 时，自动扫描图片并创建工程。
4. 流水线逐页执行文字检测、OCR、mask 保存和图像修复。
5. 如果启用 `LLM_API_Translator.enable_book_context`，会先收集全书 OCR 文本，调用一次 LLM 生成上下文摘要。
6. 翻译器逐页或分批翻译文本块，并把结果写回工程。
7. 每页完成后保存工程 JSON，并渲染最终图片到 `result/`。

## AI 的作用

- 检测/OCR/修复模型负责图像侧自动化处理。
- LLM 翻译器负责把 OCR 文本翻译为目标语言。
- 启用全书上下文后，LLM 会额外生成一份摘要，用于统一人名、术语、口吻和世界观设定。
