# 小红书直播流捕获器

Windows平台下持续获取小红书直播流的音频信息，并通过语音识别将音频实时转换为文字。

## 功能特点

- **短链接自动转换**: 支持小红书分享的短链接，自动转换为直播间链接
- **直播流自动获取**: 使用Chrome CDP协议自动捕获直播流地址
- **音频提取**: 从FLV直播流中提取音频数据
- **语音识别**: 使用OpenAI Whisper进行本地语音识别（支持中文）
- **自动重连**: 支持网络断开后自动重连
- **结果保存**: 自动保存识别文字和音频数据

## 系统要求

- Windows 10/11
- Python 3.8+
- Chrome浏览器
- FFmpeg（用于音频处理）

## 安装

### 1. 克隆或下载项目

```bash
cd d:\xhs_stream_capturer
```

### 2. 创建虚拟环境

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 安装FFmpeg

下载FFmpeg: https://www.gyan.dev/ffmpeg/builds/
将 `ffmpeg.exe` 添加到系统PATH或放在项目目录下。

## 使用方法

### 推荐方式：先获取流地址，配置后运行

**第一步：获取直播流地址**

运行网络捕获工具，获取直播流URL：

```bash
# 修改 capture_network_cdp.py 中的 test_url 为短链接
python capture_network_cdp.py

# 输出中会显示捕获到的直播流地址：
# 找到直播流: https://live-source-play.xhscdn.com/live/570200729166651969_hcv5402.flv?userId=xxx
```

**第二步：配置流地址**

编辑 `config.yaml`，填入获取到的流地址：

```yaml
# 取消注释并填入实际地址
stream_url: "https://live-source-play.xhscdn.com/live/570200729166651969_hcv5402.flv?userId=xxx"
room_id: "570200729166651969"
```

**第三步：运行主程序**

```bash
python main.py -c config.yaml
```

这样每次运行时跳过CDP获取步骤，启动更快更稳定！

### 其他使用方式

```bash
# 直接指定流URL（跳过链接解析）
python main.py -s "https://live-source-play.xhscdn.com/live/xxx.flv?userId=xxx"

# 使用短链接（会自动启动Chrome获取流地址）
python main.py http://xhslink.com/m/AZKB2inRqtk

# 使用完整直播间链接
python main.py https://www.xiaohongshu.com/livestream/dynpathkeF6dmRm/570200151527099270

# 详细日志模式
python main.py -v http://xhslink.com/xxx
```

## 项目结构

```
xhs_stream_capturer/
├── main.py                 # 主程序入口
├── link_converter.py       # 链接转换和流地址获取
├── stream_capturer.py      # FLV流捕获和音频提取
├── speech_recognizer.py    # 语音识别管理
├── capture_network_cdp.py  # Chrome CDP网络捕获工具
├── config.yaml             # 配置文件
├── requirements.txt        # Python依赖
├── README.md               # 说明文档
├── output/                 # 输出目录
│   └── room_{id}_{time}/   # 按房间和时间分组
│       ├── transcript.txt  # 识别文字
│       └── audio_*.raw     # 音频文件
└── chrome_temp_profile/    # Chrome临时配置
```

## 工作原理

### 1. 获取直播流地址

使用Chrome DevTools Protocol (CDP) 自动捕获直播流地址：

1. 启动带有远程调试的Chrome浏览器
2. 访问小红书直播间页面
3. 监听网络请求，捕获 `live-source-play.xhscdn.com` 的FLV流地址
4. 提取流地址用于后续处理

直播流URL格式：
```
https://live-source-play.xhscdn.com/live/{room_id}_orig.flv?userId=xxx
```

### 2. 音频提取

使用FFmpeg从FLV流中提取音频：

```bash
ffmpeg -i <flv_url> -vn -acodec pcm_s16le -ar 16000 -ac 1 -f s16le -
```

### 3. 语音识别

使用OpenAI Whisper进行本地语音识别：

- 支持多种模型大小（tiny/base/small/medium/large）
- 默认使用base模型，平衡速度和准确率
- 支持中文识别

## 配置说明

`config.yaml` 配置文件：

```yaml
stream:
  sample_rate: 16000    # 音频采样率
  channels: 1           # 声道数
  buffer_size: 5        # 缓冲区大小（秒）
  flv_timeout: 30       # 流超时时间
  reconnect_interval: 3 # 重连间隔
  max_reconnect_attempts: 10  # 最大重连次数

speech_recognition:
  engine: whisper
  whisper:
    model: base         # 模型大小: tiny/base/small/medium/large
    language: zh        # 语言
    device: cpu         # 设备: cpu/cuda

output:
  save_dir: ./output    # 输出目录
  save_audio: true      # 是否保存音频
  save_text: true       # 是否保存文字
```

## 测试工具

### 网络请求捕获工具

用于分析和调试直播流地址：

```bash
python capture_network_cdp.py
```

修改脚本中的 `test_url` 变量来测试不同的直播间。

## 常见问题

### 1. 无法获取直播流地址

- 确保Chrome浏览器已安装
- 检查直播间是否正在直播
- 尝试增加等待时间

### 2. 语音识别初始化慢

首次运行会下载Whisper模型（约150MB），请耐心等待。

### 3. FFmpeg未找到

确保FFmpeg已安装并添加到系统PATH。

## 注意事项

1. 本工具仅供学习研究使用
2. 请遵守小红书用户协议
3. 不要用于商业用途
4. 尊重主播隐私，不要录制敏感内容

## 许可证

MIT License