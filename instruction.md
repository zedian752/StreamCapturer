# 小红书直播流捕获器 - 详细使用指引

## 目录

1. [项目概述](#项目概述)
2. [系统要求](#系统要求)
3. [安装步骤](#安装步骤)
4. [配置说明](#配置说明)
5. [使用方法](#使用方法)
6. [工作流程详解](#工作流程详解)
7. [输出文件说明](#输出文件说明)
8. [语音识别引擎选择](#语音识别引擎选择)
9. [测试方法](#测试方法)
10. [常见问题](#常见问题)
11. [注意事项](#注意事项)

---

## 项目概述

本项目是一个运行在 Windows 平台的工具，用于：

1. **获取小红书直播流** - 通过短链接或直播间链接获取 FLV 直播流地址
2. **提取音频数据** - 从直播流中实时提取 PCM 音频
3. **语音识别转文字** - 使用本地 AI 模型将音频转换为文字
4. **保存结果** - 自动保存识别文本和对应的音频文件

### 核心特性

- ✅ 支持小红书短链接自动转换
- ✅ 使用 Chrome CDP 协议自动捕获直播流地址
- ✅ 支持多种语音识别引擎（Whisper、SenseVoice）
- ✅ 本地运行，无需联网识别
- ✅ 自动重连机制
- ✅ 识别成功后才保存音频（避免无效数据）

---

## 系统要求

### 必需环境

| 组件 | 要求 | 说明 |
|------|------|------|
| 操作系统 | Windows 10/11 | 仅支持 Windows |
| Python | 3.8+ | 推荐 3.10 |
| Chrome | 最新版 | 用于 CDP 协议捕获 |
| FFmpeg | 任意版本 | 用于音频处理 |
| 内存 | 8GB+ | 语音识别需要 |
| 磁盘 | 5GB+ | 模型和音频文件 |

### 硬件建议

- **CPU 识别**: 可运行，但速度较慢
- **GPU (CUDA)**: 推荐用于实时识别，速度快 10 倍以上

---

## 安装步骤

### 第一步：获取项目代码

```bash
cd d:\xhs_stream_capturer
```

### 第二步：创建虚拟环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate
```

### 第三步：安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 第四步：安装 FFmpeg

1. 下载 FFmpeg: https://www.gyan.dev/ffmpeg/builds/
2. 解压到任意目录（如 `C:\ffmpeg`）
3. 将 `bin` 目录添加到系统 PATH

**验证安装：**
```bash
ffmpeg -version
```

### 第五步：下载语音识别模型

**SenseVoice 模型（推荐，中文效果好）：**
```bash
# 模型会自动从 ModelScope 下载
# 首次运行时会自动下载约 1GB 的模型文件
```

**Whisper 模型：**
```bash
# 模型会在首次使用时自动下载
# base 模型约 150MB
```

---

## 配置说明

### 配置文件：`config.yaml`

#### 1. 直播流配置（推荐）

**推荐方式：直接指定流地址，跳过链接解析**

```yaml
# 取消注释并填入实际地址
stream_url: "https://live-source-play.xhscdn.com/live/570200729166651969_hcv5402.flv?userId=xxx"
room_id: "570200729166651969"
```

**获取流地址方法：**
```bash
# 运行网络捕获工具
python capture_network_cdp.py

# 输出示例：
# 找到直播流: https://live-source-play.xhscdn.com/live/xxx.flv?userId=xxx
```

#### 2. 流捕获配置

```yaml
stream:
  sample_rate: 16000      # 音频采样率（不要修改）
  channels: 1             # 声道数（不要修改）
  buffer_size: 5          # 音频缓冲区大小（秒）
  flv_timeout: 30         # 流请求超时时间（秒）
  reconnect_interval: 3   # 断线重连间隔（秒）
  max_reconnect_attempts: 10  # 最大重连次数
```

#### 3. 语音识别配置

```yaml
speech_recognition:
  # 选择引擎: whisper 或 sensevoice
  engine: "sensevoice"
  
  # Whisper 配置
  whisper:
    model: "base"         # tiny/base/small/medium/large
    language: "zh"
    device: "cpu"         # cpu 或 cuda
  
  # SenseVoice 配置（中文推荐）
  sensevoice:
    model: "./models/SenseVoiceSmall"
    vad_model: "./models/speech_fsmn_vad_zh-cn-16k-common-pytorch"
    language: "auto"
    device: "cpu"
```

#### 4. 输出配置

```yaml
output:
  save_dir: "./output"    # 输出目录
  save_audio: true        # 保存音频文件
  save_text: true         # 保存识别文本
  text_format: "txt"      # txt/json/srt
```

#### 5. 日志配置

```yaml
logging:
  level: "INFO"           # DEBUG/INFO/WARNING/ERROR
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: ""                # 日志文件路径（留空不保存）
```

---

## 使用方法

### 方式一：使用配置文件（推荐）

**第一步：获取直播流地址**

```bash
# 修改 capture_network_cdp.py 中的 test_url
python capture_network_cdp.py
```

**第二步：编辑配置文件**

编辑 `config.yaml`，填入获取到的流地址：

```yaml
stream_url: "https://live-source-play.xhscdn.com/live/xxx.flv?userId=xxx"
room_id: "570200729166651969"
```

**第三步：运行主程序**

```bash
python main.py -c config.yaml
```

### 方式二：命令行直接指定流地址

```bash
python main.py -s "https://live-source-play.xhscdn.com/live/xxx.flv?userId=xxx"
```

### 方式三：使用短链接（需要 Chrome）

```bash
python main.py http://xhslink.com/m/AZKB2inRqtk
```

### 方式四：使用直播间链接（需要 Chrome）

```bash
python main.py https://www.xiaohongshu.com/livestream/dynpathkeF6dmRm/570200151527099270
```

### 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `url` | 短链接或直播间 URL | `http://xhslink.com/xxx` |
| `-c, --config` | 配置文件路径 | `-c config.yaml` |
| `-s, --stream-url` | 直接指定流 URL | `-s "https://..."` |
| `-v, --verbose` | 详细日志模式 | `-v` |

---

## 工作流程详解

### 整体流程图

```
短链接/直播间URL
       ↓
[Chrome CDP] 捕获网络请求
       ↓
提取 FLV 流地址
       ↓
[FFmpeg] 下载 FLV 流
       ↓
提取 PCM 音频数据
       ↓
[语音识别引擎] Whisper/SenseVoice
       ↓
识别出文本？
   ├── 是 → 保存文本 + 音频文件
   └── 否 → 丢弃音频，继续处理
       ↓
循环处理，直到直播结束或用户中断
```

### 关键流程说明

#### 1. 音频缓冲和识别

```
音频数据进入 → 累积到缓冲区（3-30秒）→ 发送到识别引擎
                                                    ↓
                                            识别出文本？
                                           ├── 是 → 保存
                                           └── 否 → 丢弃
```

#### 2. 识别触发保存

- **之前**：每 60 秒保存一次音频（不管有没有识别出文本）
- **现在**：只有识别出文本后，才保存对应的音频文件

这样可以避免保存大量无效的静音或噪音数据。

---

## 输出文件说明

### 输出目录结构

```
output/
└── room_{房间ID}_{日期}_{时间}/
    ├── transcript.txt           # 识别文本（追加以时间戳）
    ├── audio_{时间1}.raw        # 原始 PCM 音频
    ├── audio_{时间1}.wav        # WAV 格式音频
    ├── audio_{时间2}.raw
    ├── audio_{时间2}.wav
    └── ...
```

### 文件说明

| 文件 | 格式 | 说明 |
|------|------|------|
| `transcript.txt` | 文本 | 识别出的所有文本，格式：`[HH:MM:SS] 文本内容` |
| `audio_*.raw` | PCM | 原始音频数据，16kHz, 16bit, 单声道 |
| `audio_*.wav` | WAV | 带 WAV 头部的音频文件，可直接播放 |

### 音频文件对应关系

每个音频文件对应一次成功的识别结果：

```
[14:30:15] 大家好，欢迎来到直播间    → audio_143015.raw + audio_143015.wav
[14:30:25] 今天给大家分享一个好物    → audio_143025.raw + audio_143025.wav
```

---

## 语音识别引擎选择

### Whisper vs SenseVoice

| 特性 | Whisper | SenseVoice |
|------|---------|------------|
| 开发者 | OpenAI | 阿里达摩院 |
| 中文效果 | 良好 | 优秀 |
| 情感识别 | 不支持 | 支持 |
| 模型大小 | 75MB-3GB | ~1GB |
| 运行速度 | 较慢 | 较快 |
| VAD 支持 | 内置 | 独立 VAD 模型 |

### 推荐选择

- **中文直播**：推荐 **SenseVoice**，中文识别效果更好
- **多语言场景**：推荐 **Whisper**
- **GPU 加速**：两者都支持，设置 `device: "cuda"`

### Whisper 模型大小对比

| 模型 | 参数量 | 英文速度 | 多语言速度 | 磁盘空间 |
|------|--------|----------|------------|----------|
| tiny | 39M | ~32x | ~32x | ~75MB |
| base | 74M | ~16x | ~16x | ~150MB |
| small | 244M | ~6x | ~6x | ~500MB |
| medium | 769M | ~2x | ~2x | ~1.5GB |
| large | 1550M | 1x | 1x | ~3GB |

---

## 测试方法

### 测试语音识别模型

**测试 Whisper：**
```bash
cd d:\xhs_stream_capturer
python test\test_whisper.py
```

修改 `test/test_whisper.py` 中的音频文件路径：
```python
TEST_AUDIO_FILE = "./test_audio/live_audio_30s.wav"
```

**测试 SenseVoice：**
```python
# 创建类似的测试脚本
from speech_recognizer import SenseVoiceRecognizer

recognizer = SenseVoiceRecognizer(
    model="./models/SenseVoiceSmall",
    vad_model="./models/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    device="cpu"
)
recognizer.initialize()

# 读取音频文件并识别
with open("test_audio/live_audio_30s.wav", "rb") as f:
    audio_data = f.read()

result = recognizer.recognize(audio_data)
print(result.text)
```

### 测试网络捕获

```bash
python capture_network_cdp.py
```

---

## 常见问题

### Q1: 无法获取直播流地址

**可能原因：**
- Chrome 浏览器未正确安装
- 直播间未开播
- 网络连接问题

**解决方案：**
1. 确认 Chrome 浏览器已安装
2. 手动访问直播间确认是否在直播
3. 使用 `capture_network_cdp.py` 工具捕获

### Q2: 语音识别初始化很慢

**原因：** 首次运行需要下载模型文件

**解决方案：**
- SenseVoice 模型约 1GB，耐心等待
- 可预先下载模型到 `./models/` 目录

### Q3: 识别效果不好

**可能原因：**
- 音频质量差
- 背景噪音大
- 模型选择不当

**解决方案：**
1. 尝试使用更大的模型（如 `medium`）
2. 切换到 SenseVoice 引擎
3. 使用 GPU 加速

### Q4: FFmpeg 未找到

**错误信息：** `'ffmpeg' is not recognized as an internal or external command`

**解决方案：**
1. 下载 FFmpeg: https://www.gyan.dev/ffmpeg/builds/
2. 将 `ffmpeg.exe` 所在目录添加到系统 PATH

### Q5: 运行时内存不足

**解决方案：**
1. 使用更小的模型（如 `tiny` 或 `base`）
2. 关闭其他应用程序
3. 增加虚拟内存

---

## 注意事项

### 法律和道德

1. ⚠️ **本工具仅供学习研究使用**
2. ⚠️ **请遵守小红书用户协议**
3. ⚠️ **不要用于商业用途**
4. ⚠️ **尊重主播隐私，不要录制敏感内容**
5. ⚠️ **录制的音频和文字不得用于非法用途**

### 技术限制

1. 需要直播正在进行的直播间
2. 部分直播间可能有地区限制
3. 音频质量取决于网络状况
4. 实时识别需要较好的硬件配置

### 最佳实践

1. **推荐使用配置文件方式运行**，避免每次启动 Chrome
2. **使用 GPU 加速**可大幅提升识别速度
3. **定期清理 output 目录**，避免磁盘占用过多
4. **使用 SenseVoice 引擎**获得更好的中文识别效果

---

## 项目文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序入口 |
| `config.yaml` | 配置文件 |
| `link_converter.py` | 链接转换模块 |
| `stream_capturer.py` | 流捕获和音频提取 |
| `speech_recognizer.py` | 语音识别模块 |
| `utils.py` | 工具函数（音频保存等） |
| `capture_network_cdp.py` | Chrome CDP 网络捕获工具 |
| `requirements.txt` | Python 依赖列表 |
| `README.md` | 项目说明文档 |
| `instruction.md` | 本指引文档 |

---

## 更新日志

### v1.0
- 初始版本
- 支持短链接转换
- 支持 Whisper 语音识别
- 支持 FLV 流捕获

### v1.1
- 添加 SenseVoice 语音识别支持
- 优化音频保存逻辑（识别成功后才保存）
- 添加 WAV 格式输出
- 模块化代码结构

---

如有问题，请查看项目 README.md 或提交 Issue。