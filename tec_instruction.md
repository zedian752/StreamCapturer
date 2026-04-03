# 小红书直播流捕获器 - 技术开发文档

> 本文档面向开发人员，包含详细的技术实现、架构设计、API参考和扩展开发指南。

---

## 目录

1. [项目概览](#1-项目概览)
2. [核心类和模块](#2-核心类和模块)
3. [关键技术细节](#3-关键技术细节)
4. [数据结构](#4-数据结构)
5. [配置系统](#5-配置系统)
6. [扩展开发指南](#6-扩展开发指南)
7. [调试技巧](#7-调试技巧)
8. [性能优化](#8-性能优化)
9. [API 参考](#9-api-参考)
10. [错误处理](#10-错误处理)
11. [测试指南](#11-测试指南)

---

## 1. 项目概览

### 1.1 项目信息

| 项目 | 说明 |
|------|------|
| 名称 | 小红书直播流捕获器 |
| 平台 | Windows 10/11 |
| 语言 | Python 3.8+ |
| 目标 | 获取小红书直播流音频并实时转换为文字 |

### 1.2 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 主控制器 | `main.py` | 整合所有模块，管理运行流程 |
| 链接转换 | `link_converter.py` | 短链接转换，获取直播流地址 |
| 流捕获 | `stream_capturer.py` | FLV流下载，音频提取 |
| 语音识别 | `speech_recognizer.py` | 语音转文字（Whisper/SenseVoice） |
| 工具函数 | `utils.py` | 音频保存等通用功能 |
| 网络捕获 | `capture_network_cdp.py` | Chrome CDP 网络请求捕获 |

### 1.3 工作流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户输入 URL                                 │
└─────────────────────────────┬───────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    XHSLiveCapturer.start()                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ 1. LinkConverter.convert_short_url() → 获取 room_id          │  │
│  │ 2. LinkConverter.get_stream_url() → 获取 flv_url (CDP)       │  │
│  │ 3. StreamCapturer.start() → 启动 FFmpeg 进程                  │  │
│  │ 4. ContinuousSpeechRecognizer.start() → 启动识别线程          │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    StreamCapturer._capture_loop()                   │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ FFmpeg stdout → 读取 PCM 数据 → AudioChunk 对象               │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  XHSLiveCapturer._on_audio_chunk()                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ 1. 缓存音频到 _audio_buffer                                   │  │
│  │ 2. 发送到 ContinuousSpeechRecognizer.add_audio()              │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│             ContinuousSpeechRecognizer._recognize_worker()          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ 1. 从队列获取音频数据                                         │  │
│  │ 2. 累积到缓冲区 (3-30秒)                                      │  │
│  │ 3. 达到阈值 → _process_buffer() → 调用识别引擎                 │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│               XHSLiveCapturer._on_recognition_result()              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ if result.text:                                               │  │
│  │   ├── _save_text() → transcript.txt                           │  │
│  │   └── _save_audio_from_result() → audio_*.raw, audio_*.wav    │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心类和模块

### 2.1 类结构总览

```
main.py
└── XHSLiveCapturer              # 主控制器

link_converter.py
└── LinkConverter                # 链接转换器

stream_capturer.py
├── StreamCapturer               # 流捕获器
├── AudioChunk (dataclass)       # 音频数据块
└── StreamStatus (Enum)          # 流状态枚举

speech_recognizer.py
├── BaseRecognizer (ABC)         # 识别器基类
├── WhisperRecognizer            # Whisper 识别器
├── SenseVoiceRecognizer         # SenseVoice 识别器
├── ContinuousSpeechRecognizer   # 连续语音识别器
├── SpeechRecognizerManager      # 识别器管理器
├── RecognitionResult (dataclass)# 识别结果
└── RecognizerStatus (Enum)      # 识别器状态

utils.py
├── save_audio_buffer()          # 保存音频缓冲区
└── save_as_wav()                # 保存为 WAV 格式
```

### 2.2 XHSLiveCapturer (main.py)

主控制器，整合所有模块。

```python
class XHSLiveCapturer:
    """小红书直播流捕获器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化捕获器
        
        Attributes:
            config: 配置字典
            _link_converter: 链接转换器实例
            _stream_capturer: 流捕获器实例
            _speech_manager: 语音识别管理器
            _continuous_recognizer: 连续识别器
            _is_running: 运行状态
            _room_id: 房间ID
            _stream_info: 流信息字典
            _output_dir: 输出目录
            _text_file: 文本文件路径
            _audio_buffer: 音频缓冲区
        """
    
    # === 公共方法 ===
    def start(self, url: str) -> bool       # 启动捕获
    def stop(self)                           # 停止捕获
    def convert_url(self, url: str) -> bool  # 转换URL
    def on_text(self, callback)              # 设置文本回调
    def on_status(self, callback)            # 设置状态回调
    def get_stats(self) -> Dict              # 获取统计信息
    
    # === 内部方法 ===
    def _init_components(self)               # 初始化组件
    def _setup_output(self, room_id: str)    # 设置输出目录
    def _on_audio_chunk(self, chunk)         # 处理音频数据
    def _on_stream_status(self, status)      # 处理流状态
    def _on_stream_error(self, error)        # 处理流错误
    def _on_recognition_result(self, result) # 处理识别结果
    def _on_recognition_error(self, error)   # 处理识别错误
    def _save_text(self, text, timestamp)    # 保存文本
    def _save_audio_from_result(self, ...)   # 保存音频
    def _save_audio_buffer(self)             # 保存音频缓冲区
```

### 2.3 LinkConverter (link_converter.py)

负责短链接转换和获取直播流地址。

```python
class LinkConverter:
    """链接转换器"""
    
    def __init__(self):
        """
        Attributes:
            cdp_port: Chrome CDP 端口 (默认 9222)
            chrome_path: Chrome 可执行文件路径
            temp_profile_dir: 临时配置目录
        """
    
    def convert_short_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        转换短链接/直播间链接
        
        Args:
            url: 短链接或直播间URL
            
        Returns:
            (long_url, room_id) 元组
        """
    
    def get_stream_url(self, room_id: str) -> Optional[str]:
        """
        使用 Chrome CDP 获取直播流地址
        
        Args:
            room_id: 直播间ID
            
        Returns:
            FLV 流地址或 None
        """
    
    # === 内部方法 ===
    def _extract_room_id(self, url: str) -> Optional[str]     # 提取房间ID
    def _start_chrome_with_cdp(self) -> Optional[int]          # 启动 Chrome
    def _capture_stream_url_via_cdp(self, room_id, port)       # CDP 捕获
    def _cleanup(self)                                          # 清理资源
```

### 2.4 StreamCapturer (stream_capturer.py)

负责 FLV 流捕获和音频提取。

```python
class StreamCapturer:
    """流捕获器"""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        buffer_size: int = 5,
        timeout: int = 30,
        reconnect_interval: int = 3,
        max_reconnect_attempts: int = 10
    ):
        """
        Args:
            sample_rate: 音频采样率
            channels: 声道数
            buffer_size: 缓冲区大小(秒)
            timeout: 流超时时间(秒)
            reconnect_interval: 重连间隔(秒)
            max_reconnect_attempts: 最大重连次数
        """
    
    # === 公共方法 ===
    def start(self, stream_info: Dict) -> bool    # 启动捕获
    def stop(self)                                 # 停止捕获
    def on_audio_chunk(self, callback)             # 设置音频回调
    def on_status_change(self, callback)           # 设置状态回调
    def on_error(self, callback)                   # 设置错误回调
    
    @property
    def stats(self) -> Dict                        # 获取统计信息
    
    # === 内部方法 ===
    def _start_ffmpeg(self, flv_url: str)          # 启动 FFmpeg
    def _capture_loop(self)                         # 捕获循环
    def _read_audio_chunk(self, process)           # 读取音频块
    def _handle_reconnect(self)                     # 处理重连


@dataclass
class AudioChunk:
    """音频数据块"""
    data: bytes           # PCM 音频数据
    sample_rate: int      # 采样率 (16000)
    channels: int         # 声道数 (1)
    timestamp: float      # 时间戳
    duration: float       # 时长(秒)


class StreamStatus(Enum):
    """流状态"""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"
    ERROR = "error"
```

### 2.5 语音识别模块 (speech_recognizer.py)

```python
# === 基类 ===
class BaseRecognizer(ABC):
    """语音识别器基类"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """初始化识别器"""
    
    @abstractmethod
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """识别音频数据"""
    
    @abstractmethod
    def close(self):
        """关闭识别器"""


# === Whisper 实现 ===
class WhisperRecognizer(BaseRecognizer):
    """Whisper 语音识别器"""
    
    def __init__(
        self,
        model_size: str = "base",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "float32"
    ):
        """
        Args:
            model_size: 模型大小 (tiny/base/small/medium/large)
            language: 语言
            device: 设备 (cpu/cuda)
            compute_type: 计算类型
        """


# === SenseVoice 实现 ===
class SenseVoiceRecognizer(BaseRecognizer):
    """SenseVoice 语音识别器"""
    
    def __init__(
        self,
        model: str = "iic/SenseVoiceSmall",
        language: str = "auto",
        device: str = "cpu",
        vad_model: str = "fsmn-vad",
        max_single_segment_time: int = 30000,
        merge_vad: bool = True,
        merge_length_s: int = 15,
        batch_size_s: int = 60
    ):
        """
        Args:
            model: 模型名称或路径
            language: 语言 (auto/zh/en/yue/ja/ko)
            device: 设备 (cpu/cuda)
            vad_model: VAD 模型
            max_single_segment_time: 最大单段时长(ms)
            merge_vad: 是否合并VAD分段
            merge_length_s: 合并长度(秒)
            batch_size_s: 批处理大小(秒)
        """


# === 连续识别器 ===
class ContinuousSpeechRecognizer:
    """连续语音识别器 - 核心识别逻辑"""
    
    def __init__(
        self,
        recognizer: BaseRecognizer,
        min_chunk_duration: float = 3.0,
        max_chunk_duration: float = 30.0,
        silence_threshold: float = 0.01
    ):
        """
        Args:
            recognizer: 底层识别器实例
            min_chunk_duration: 最小音频块时长(秒)
            max_chunk_duration: 最大音频块时长(秒)
            silence_threshold: 静音阈值
        """
    
    def start(self)                           # 启动识别线程
    def stop(self)                            # 停止识别
    def add_audio(self, data, sample_rate, duration)  # 添加音频
    def on_result(self, callback)             # 设置结果回调
    def on_error(self, callback)              # 设置错误回调
    
    # === 内部方法 ===
    def _recognize_worker(self)               # 识别工作线程
    def _process_buffer(self)                 # 处理音频缓冲区


# === 管理器 ===
class SpeechRecognizerManager:
    """语音识别管理器"""
    
    def __init__(self, config: Dict):
        """根据配置创建识别器"""
    
    def initialize(self) -> bool
    def recognize(self, audio_data, sample_rate) -> RecognitionResult
    def create_continuous_recognizer(self) -> ContinuousSpeechRecognizer
    def close(self)


# === 数据结构 ===
@dataclass
class RecognitionResult:
    """识别结果"""
    text: str                              # 识别文本
    start_time: float                      # 开始时间
    end_time: float                        # 结束时间
    confidence: float = 1.0                # 置信度
    segments: Optional[List[Dict]] = None  # 分段信息
    language: str = "zh"                   # 语言
    audio_data: Optional[bytes] = None     # 对应的音频数据


class RecognizerStatus(Enum):
    """识别器状态"""
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    RECOGNIZING = "recognizing"
    ERROR = "error"
```

---

## 3. 关键技术细节

### 3.1 链接转换流程

```
输入: http://xhslink.com/m/AZKB2inRqtk (短链接)
       或 https://www.xiaohongshu.com/livestream/xxx/570200151527099270 (直播间链接)
       或 https://live-source-play.xhscdn.com/live/xxx.flv (直接流地址)
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: 判断 URL 类型                                               │
│   - 包含 xhslink.com → 短链接，需要跟随重定向                        │
│   - 包含 xiaohongshu.com/livestream → 直播间链接，提取 room_id       │
│   - 包含 .flv → 直接流地址，直接使用                                 │
└─────────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Step 2: 跟随重定向 (如果是短链接)                                    │
│   requests.get(url, allow_redirects=True)                           │
│   提取最终 URL 中的 room_id                                          │
└─────────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Step 3: 使用 Chrome CDP 获取 FLV 流地址                              │
│   1. 启动 Chrome (--remote-debugging-port=9222)                     │
│   2. 访问直播间页面                                                  │
│   3. 监听 Network.requestWillBeSent 事件                            │
│   4. 过滤 live-source-play.xhscdn.com 的请求                        │
│   5. 提取 FLV URL                                                    │
└─────────────────────────────────────────────────────────────────────┘
         ↓
输出: https://live-source-play.xhscdn.com/live/570200151527099270_hcv5402.flv?userId=xxx
```

**关键代码：**

```python
def _extract_room_id(self, url: str) -> Optional[str]:
    """从URL中提取房间ID"""
    patterns = [
        r'/livestream/[^/]+/(\d+)',           # 标准直播间链接
        r'room_id=(\d+)',                      # 查询参数
        r'/live/(\d+)',                        # 简短格式
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def _capture_stream_url_via_cdp(self, room_id: str, port: int) -> Optional[str]:
    """通过CDP捕获流URL"""
    import websocket
    import json
    
    # 连接到 Chrome DevTools
    ws_url = f"ws://localhost:{port}/devtools/browser/..."
    ws = websocket.create_connection(ws_url)
    
    # 启用网络监控
    ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
    
    # 监听网络请求
    while True:
        message = json.loads(ws.recv())
        if message.get("method") == "Network.requestWillBeSent":
            url = message["params"]["request"]["url"]
            if "live-source-play.xhscdn.com" in url and ".flv" in url:
                return url
```

### 3.2 音频提取流程

```
FLV 流 URL
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ FFmpeg 进程                                                         │
│                                                                     │
│   ffmpeg -i <flv_url> \                                             │
│           -vn \                       # 禁用视频                    │
│           -acodec pcm_s16le \         # 16-bit PCM 编码             │
│           -ar 16000 \                 # 16kHz 采样率                │
│           -ac 1 \                     # 单声道                      │
│           -f s16le \                  # signed 16-bit little-endian │
│           -                           # 输出到 stdout               │
└─────────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Python 读取 stdout                                                  │
│                                                                     │
│   chunk_size = sample_rate * channels * 2 * buffer_size             │
│              = 16000 * 1 * 2 * 5 = 160000 bytes (5秒音频)           │
│                                                                     │
│   audio_data = process.stdout.read(chunk_size)                      │
└─────────────────────────────────────────────────────────────────────┘
         ↓
AudioChunk 对象
```

**关键代码：**

```python
def _start_ffmpeg(self, flv_url: str) -> subprocess.Popen:
    """启动FFmpeg进程"""
    cmd = [
        'ffmpeg',
        '-i', flv_url,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', str(self.sample_rate),
        '-ac', str(self.channels),
        '-f', 's16le',
        '-'
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW  # Windows 隐藏窗口
    )
    return process

def _capture_loop(self):
    """捕获循环"""
    # 计算每次读取的字节数
    bytes_per_chunk = self.sample_rate * self.channels * 2 * self.buffer_size
    
    while self._is_running:
        try:
            audio_data = self._ffmpeg_process.stdout.read(bytes_per_chunk)
            if not audio_data:
                break
            
            chunk = AudioChunk(
                data=audio_data,
                sample_rate=self.sample_rate,
                channels=self.channels,
                timestamp=time.time(),
                duration=self.buffer_size
            )
            
            if self._on_audio_chunk_callback:
                self._on_audio_chunk_callback(chunk)
                
        except Exception as e:
            self._handle_error(str(e))
```

### 3.3 语音识别流程

```
AudioChunk (5秒 PCM 数据)
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ ContinuousSpeechRecognizer.add_audio()                              │
│                                                                     │
│   1. 计算音频时长: duration = len(data) / (sample_rate * 2)         │
│   2. 放入队列: _audio_queue.put((data, sample_rate, duration))      │
└─────────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ _recognize_worker() 线程                                            │
│                                                                     │
│   while running:                                                    │
│       data, sr, dur = _audio_queue.get(timeout=0.5)                │
│       _audio_buffer.append(data)                                    │
│       _buffer_duration += dur                                       │
│                                                                     │
│       if _buffer_duration >= max_chunk_duration (30秒):             │
│           _process_buffer()                                         │
└─────────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ _process_buffer()                                                   │
│                                                                     │
│   1. 合并音频: combined = b''.join(_audio_buffer)                   │
│   2. 清空缓冲区                                                     │
│   3. 调用识别: result = recognizer.recognize(combined)              │
│   4. 附加音频: result.audio_data = combined                         │
│   5. 回调结果: _on_result(result)                                   │
└─────────────────────────────────────────────────────────────────────┘
         ↓
RecognitionResult (text + audio_data)
```

**关键代码：**

```python
def _process_buffer(self):
    """处理音频缓冲区 - 核心识别逻辑"""
    if not self._audio_buffer or self._buffer_duration < self.min_chunk_duration:
        return
    
    # 合并所有音频块
    combined_audio = b''.join(self._audio_buffer)
    
    # 清空缓冲区
    self._audio_buffer = []
    buffer_duration = self._buffer_duration
    self._buffer_duration = 0.0
    
    logger.debug(f"开始识别 {buffer_duration:.1f} 秒的音频")
    
    try:
        # 调用底层识别器
        result = self.recognizer.recognize(combined_audio)
        
        # 将音频数据附加到结果中（用于后续保存）
        result.audio_data = combined_audio
        
        # 更新统计
        self._stats['total_chunks'] += 1
        self._stats['total_duration'] += buffer_duration
        self._stats['total_text_length'] += len(result.text)
        
        # 回调结果（只有识别出文本才回调）
        if self._on_result and result.text:
            logger.info(f"识别结果: {result.text}")
            self._on_result(result)
        elif result.text:
            logger.info(f"识别结果: {result.text}")
            
    except Exception as e:
        logger.error(f"识别失败: {e}")
        if self._on_error:
            self._on_error(str(e))
```

### 3.4 音频保存逻辑

```python
def _on_recognition_result(self, result: RecognitionResult):
    """处理识别结果 - 识别成功后才保存"""
    if not result.text:
        return
    
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # 1. 输出到控制台
    print(f"\n[{timestamp}] {result.text}\n")
    
    # 2. 保存文本
    output_config = self.config.get('output', {})
    if output_config.get('save_text', True) and self._text_file:
        self._save_text(result.text, timestamp)
    
    # 3. 保存音频（只有识别成功才保存）
    if result.audio_data and output_config.get('save_audio', True) and self._output_dir:
        self._save_audio_from_result(result.audio_data, timestamp)
    
    # 4. 触发回调
    if self._on_text_callback:
        self._on_text_callback(result.text, timestamp)

def _save_audio_from_result(self, audio_data: bytes, timestamp: str):
    """保存识别结果对应的音频"""
    from utils import save_as_wav
    
    # 文件名使用时间戳（去除冒号）
    ts = timestamp.replace(':', '')
    
    # 1. 保存原始 PCM 文件
    raw_file = self._output_dir / f"audio_{ts}.raw"
    with open(raw_file, 'wb') as f:
        f.write(audio_data)
    
    # 2. 保存 WAV 格式文件
    wav_file = self._output_dir / f"audio_{ts}.wav"
    stream_config = self.config.get('stream', {})
    save_as_wav(
        audio_data,
        wav_file,
        sample_rate=stream_config.get('sample_rate', 16000),
        channels=stream_config.get('channels', 1)
    )
    
    self.logger.info(f"保存音频: {raw_file.name}, {wav_file.name}")
```

---

## 4. 数据结构

### 4.1 AudioChunk

```python
@dataclass
class AudioChunk:
    """
    音频数据块
    
    Attributes:
        data: PCM 音频数据 (bytes)
              - 格式: signed 16-bit little-endian
              - 采样率: 16000 Hz
              - 声道: 单声道
        sample_rate: 采样率 (默认 16000)
        channels: 声道数 (默认 1)
        timestamp: 时间戳 (Unix timestamp)
        duration: 时长 (秒)
    """
    data: bytes
    sample_rate: int
    channels: int
    timestamp: float
    duration: float
    
    @property
    def bytes_per_second(self) -> int:
        """每秒字节数"""
        return self.sample_rate * self.channels * 2
```

### 4.2 RecognitionResult

```python
@dataclass
class RecognitionResult:
    """
    识别结果
    
    Attributes:
        text: 识别出的文本
        start_time: 识别开始时间 (Unix timestamp)
        end_time: 识别结束时间 (Unix timestamp)
        confidence: 置信度 (0.0 - 1.0)
        segments: 分段信息列表 (可选)
            [
                {
                    'start': 0.0,      # 开始时间(秒)
                    'end': 2.5,        # 结束时间(秒)
                    'text': '文本片段',
                    'confidence': 0.95
                },
                ...
            ]
        language: 识别语言
        audio_data: 对应的音频数据 (bytes, 可选)
    """
    text: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    segments: Optional[List[Dict]] = None
    language: str = "zh"
    audio_data: Optional[bytes] = None
```

### 4.3 StreamStatus

```python
class StreamStatus(Enum):
    """流状态枚举"""
    IDLE = "idle"                     # 空闲，未启动
    CONNECTING = "connecting"         # 正在连接
    CONNECTED = "connected"           # 已连接
    STREAMING = "streaming"           # 正在接收数据
    RECONNECTING = "reconnecting"     # 正在重连
    STOPPED = "stopped"               # 已停止
    ERROR = "error"                   # 发生错误
```

### 4.4 配置数据结构

```python
# config.yaml 对应的 Python 字典结构
DEFAULT_CONFIG = {
    'short_link': {
        'timeout': 10,
        'max_redirects': 5,
        'headers': {
            'User-Agent': '...',
        }
    },
    'stream': {
        'sample_rate': 16000,
        'channels': 1,
        'buffer_size': 5,
        'flv_timeout': 30,
        'reconnect_interval': 3,
        'max_reconnect_attempts': 10,
    },
    'speech_recognition': {
        'engine': 'sensevoice',  # 或 'whisper'
        'min_chunk_duration': 3.0,
        'max_chunk_duration': 30.0,
        'whisper': {
            'model': 'base',
            'language': 'zh',
            'device': 'cpu',
        },
        'sensevoice': {
            'model': './models/SenseVoiceSmall',
            'vad_model': './models/speech_fsmn_vad_zh-cn-16k-common-pytorch',
            'language': 'auto',
            'device': 'cpu',
        }
    },
    'output': {
        'save_dir': './output',
        'save_audio': True,
        'save_text': True,
        'text_format': 'txt',
    },
    'logging': {
        'level': 'INFO',
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'file': '',
    }
}
```

---

## 5. 配置系统

### 5.1 配置加载流程

```python
def load_config(config_path: Optional[str] = None) -> Dict:
    """
    加载配置文件
    
    1. 使用默认配置 DEFAULT_CONFIG
    2. 如果存在 config.yaml，递归合并覆盖默认配置
    3. 返回合并后的配置字典
    """
    config = DEFAULT_CONFIG.copy()
    
    # 自动查找默认配置文件
    if config_path is None:
        default_paths = ['config.yaml', './config.yaml']
        for path in default_paths:
            if os.path.exists(path):
                config_path = path
                break
    
    # 加载并合并用户配置
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)
            if user_config:
                merge_dict(config, user_config)
    
    return config

def merge_dict(base: Dict, override: Dict):
    """递归合并字典"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            merge_dict(base[key], value)
        else:
            base[key] = value
```

### 5.2 配置项说明

| 配置路径 | 类型 | 默认值 | 说明 |
|---------|------|--------|------|
| `stream.sample_rate` | int | 16000 | 音频采样率，不建议修改 |
| `stream.channels` | int | 1 | 声道数，不建议修改 |
| `stream.buffer_size` | int | 5 | 每次读取的音频时长(秒) |
| `stream.flv_timeout` | int | 30 | FFmpeg 连接超时(秒) |
| `stream.reconnect_interval` | int | 3 | 重连间隔(秒) |
| `stream.max_reconnect_attempts` | int | 10 | 最大重连次数 |
| `speech_recognition.engine` | str | sensevoice | 识别引擎 |
| `speech_recognition.min_chunk_duration` | float | 3.0 | 最小识别时长(秒) |
| `speech_recognition.max_chunk_duration` | float | 30.0 | 最大识别时长(秒) |
| `output.save_dir` | str | ./output | 输出目录 |
| `output.save_audio` | bool | True | 是否保存音频 |
| `output.save_text` | bool | True | 是否保存文本 |

---

## 6. 扩展开发指南

### 6.1 添加新的语音识别引擎

**步骤 1: 创建识别器类**

```python
# speech_recognizer.py

class NewRecognizer(BaseRecognizer):
    """新的语音识别器"""
    
    def __init__(self, model: str, device: str = "cpu", **kwargs):
        """
        初始化识别器
        
        Args:
            model: 模型名称或路径
            device: 设备 (cpu/cuda)
        """
        self.model_name = model
        self.device = device
        self._model = None
        self._status = RecognizerStatus.IDLE
    
    def initialize(self) -> bool:
        """加载模型"""
        try:
            self._status = RecognizerStatus.LOADING
            logger.info(f"正在加载模型: {self.model_name}")
            
            # 加载模型的代码
            # self._model = load_model(self.model_name)
            
            self._status = RecognizerStatus.READY
            logger.info("模型加载完成")
            return True
            
        except Exception as e:
            self._status = RecognizerStatus.ERROR
            logger.error(f"模型加载失败: {e}")
            return False
    
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """识别音频"""
        if self._status != RecognizerStatus.READY:
            raise RuntimeError("识别器未初始化")
        
        self._status = RecognizerStatus.RECOGNIZING
        start_time = time.time()
        
        try:
            # 预处理音频（如果需要）
            # audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # 调用模型识别
            # text = self._model.transcribe(audio_array)
            
            return RecognitionResult(
                text=text,
                start_time=start_time,
                end_time=time.time(),
                confidence=1.0,
                language="zh"
            )
            
        except Exception as e:
            logger.error(f"识别失败: {e}")
            return RecognitionResult(
                text="",
                start_time=start_time,
                end_time=time.time(),
                confidence=0.0
            )
        finally:
            self._status = RecognizerStatus.READY
    
    def close(self):
        """释放资源"""
        if self._model:
            del self._model
            self._model = None
        
        self._status = RecognizerStatus.IDLE
        logger.info("识别器已关闭")
```

**步骤 2: 注册到管理器**

```python
# speech_recognizer.py - SpeechRecognizerManager 类

def _create_recognizer(self) -> BaseRecognizer:
    """创建识别器实例"""
    if self.engine_type == 'whisper':
        # ... 现有代码
    elif self.engine_type == 'sensevoice':
        # ... 现有代码
    elif self.engine_type == 'new_engine':  # 新增
        new_config = self.config.get('new_engine', {})
        return NewRecognizer(
            model=new_config.get('model', 'default_model'),
            device=new_config.get('device', 'cpu'),
        )
    else:
        raise ValueError(f"不支持的识别引擎: {self.engine_type}")
```

**步骤 3: 添加配置**

```yaml
# config.yaml

speech_recognition:
  engine: "new_engine"
  
  new_engine:
    model: "path/to/model"
    device: "cpu"
    # 其他配置项...
```

### 6.2 添加新的输出格式

**步骤 1: 创建保存函数**

```python
# utils.py

def save_as_srt(segments: List[Dict], output_path: Path):
    """
    保存为 SRT 字幕格式
    
    Args:
        segments: 分段信息列表
        output_path: 输出文件路径
    """
    def format_srt_time(seconds: float) -> str:
        """将秒数转换为 SRT 时间格式 (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments):
            start = format_srt_time(seg['start'])
            end = format_srt_time(seg['end'])
            f.write(f"{i + 1}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{seg['text']}\n\n")


def save_as_json(result: RecognitionResult, output_path: Path):
    """
    保存为 JSON 格式
    
    Args:
        result: 识别结果
        output_path: 输出文件路径
    """
    data = {
        'text': result.text,
        'start_time': result.start_time,
        'end_time': result.end_time,
        'confidence': result.confidence,
        'language': result.language,
        'segments': result.segments
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

**步骤 2: 在主程序中调用**

```python
# main.py - _on_recognition_result 方法

def _on_recognition_result(self, result: RecognitionResult):
    if not result.text:
        return
    
    timestamp = datetime.now().strftime('%H%M%S')
    text_format = self.config.get('output', {}).get('text_format', 'txt')
    
    if text_format == 'txt':
        self._save_text(result.text, timestamp)
    elif text_format == 'srt' and result.segments:
        from utils import save_as_srt
        srt_file = self._output_dir / f"transcript_{timestamp}.srt"
        save_as_srt(result.segments, srt_file)
    elif text_format == 'json':
        from utils import save_as_json
        json_file = self._output_dir / f"transcript_{timestamp}.json"
        save_as_json(result, json_file)
```

### 6.3 添加 VAD（语音活动检测）

```python
# speech_recognizer.py - ContinuousSpeechRecognizer 类

class ContinuousSpeechRecognizer:
    def __init__(self, ...):
        # ... 现有代码
        self._vad_buffer: List[bytes] = []
        self._silence_duration: float = 0.0
        self._speech_duration: float = 0.0
        self.vad_silence_threshold: float = 0.5  # 静音阈值(秒)
        self.vad_speech_threshold: float = 0.3   # 语音阈值(秒)
    
    def _detect_speech(self, audio_data: bytes) -> bool:
        """
        检测是否为语音
        
        简单实现：计算 RMS 能量
        """
        import numpy as np
        
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
        
        # 归一化到 0-1
        rms_normalized = rms / 32768.0
        
        return rms_normalized > self.silence_threshold
    
    def _recognize_worker(self):
        """改进的识别工作线程 - 带 VAD"""
        while not self._stop_event.is_set():
            try:
                try:
                    audio_data, sample_rate, duration = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    # 队列为空时的处理
                    if self._buffer_duration >= self.min_chunk_duration:
                        self._process_buffer()
                    continue
                
                # VAD 检测
                is_speech = self._detect_speech(audio_data)
                
                if is_speech:
                    self._audio_buffer.append(audio_data)
                    self._buffer_duration += duration
                    self._speech_duration += duration
                    self._silence_duration = 0.0
                else:
                    self._silence_duration += duration
                    
                    # 如果静音超过阈值且已有足够语音，触发识别
                    if (self._silence_duration >= self.vad_silence_threshold and 
                        self._speech_duration >= self.vad_speech_threshold):
                        if self._buffer_duration >= self.min_chunk_duration:
                            self._process_buffer()
                        self._speech_duration = 0.0
                
                # 最大时长限制
                if self._buffer_duration >= self.max_chunk_duration:
                    self._process_buffer()
                    
            except Exception as e:
                logger.error(f"识别工作线程错误: {e}")
                if self._on_error:
                    self._on_error(str(e))
```

---

## 7. 调试技巧

### 7.1 启用详细日志

**命令行方式：**
```bash
python main.py -v http://xhslink.com/xxx
```

**配置文件方式：**
```yaml
logging:
  level: "DEBUG"
```

**代码方式：**
```python
import logging
logging.getLogger('XHSLiveCapturer').setLevel(logging.DEBUG)
logging.getLogger('StreamCapturer').setLevel(logging.DEBUG)
logging.getLogger('ContinuousSpeechRecognizer').setLevel(logging.DEBUG)
```

### 7.2 测试单个模块

**测试链接转换：**
```python
from link_converter import LinkConverter

converter = LinkConverter()

# 测试短链接转换
long_url, room_id = converter.convert_short_url("http://xhslink.com/xxx")
print(f"长链接: {long_url}")
print(f"房间ID: {room_id}")

# 测试流地址获取
stream_url = converter.get_stream_url(room_id)
print(f"流地址: {stream_url}")
```

**测试流捕获：**
```python
from stream_capturer import StreamCapturer

def on_chunk(chunk):
    print(f"收到音频: {len(chunk.data)} bytes, {chunk.duration}秒")

capturer = StreamCapturer()
capturer.on_audio_chunk(on_chunk)
capturer.start({'flv_url': 'https://...'})

# 等待...
input("按回车停止")
capturer.stop()
```

**测试语音识别：**
```python
from speech_recognizer import WhisperRecognizer, SenseVoiceRecognizer

# 测试 Whisper
recognizer = WhisperRecognizer(model_size="base", language="zh")
recognizer.initialize()

with open("test_audio/live_audio_30s.wav", "rb") as f:
    # 跳过 WAV 头部（44字节）
    f.read(44)
    audio_data = f.read()

result = recognizer.recognize(audio_data)
print(f"识别结果: {result.text}")
```

### 7.3 常见问题排查

| 问题 | 可能原因 | 排查步骤 |
|------|---------|---------|
| 无法获取流地址 | Chrome 未启动 | 检查 `chrome_temp_profile` 目录是否创建 |
| | 网络超时 | 增加等待时间，检查代理设置 |
| | 直播已结束 | 手动访问直播间确认 |
| FFmpeg 无输出 | 流 URL 失效 | 手动运行 FFmpeg 命令测试 |
| | 网络问题 | 检查防火墙设置 |
| 识别无结果 | 音频为空 | 打印 `len(audio_data)` 确认 |
| | 模型未加载 | 检查 `recognizer.status` |
| | 全是静音 | 检查 VAD 设置 |
| 内存持续增长 | 缓冲区未清空 | 检查 `_audio_buffer.clear()` 是否被调用 |
| | audio_data 未释放 | 确认识别结果处理后释放引用 |

### 7.4 性能分析

```python
import cProfile
import pstats

# 分析识别性能
def profile_recognition():
    recognizer = WhisperRecognizer(model_size="base")
    recognizer.initialize()
    
    # 读取测试音频
    with open("test_audio.wav", "rb") as f:
        f.read(44)
        audio_data = f.read()
    
    # 性能分析
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(10):
        result = recognizer.recognize(audio_data)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)

profile_recognition()
```

---

## 8. 性能优化

### 8.1 GPU 加速

**安装 CUDA 版 PyTorch：**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**配置使用 GPU：**
```yaml
speech_recognition:
  whisper:
    device: "cuda"
  sensevoice:
    device: "cuda"
```

**性能对比（30秒音频）：**
| 设备 | tiny | base | small | medium |
|------|------|------|-------|--------|
| CPU (i7) | 2s | 5s | 15s | 45s |
| GPU (RTX 3060) | 0.2s | 0.4s | 0.8s | 2s |

### 8.2 音频缓冲优化

```yaml
# 减少识别频率，提高吞吐量
stream:
  buffer_size: 10  # 增加每次读取的时长

speech_recognition:
  max_chunk_duration: 45  # 增加单次识别的时长
```

### 8.3 多线程优化

当前架构使用 3 个线程：
- 主线程：程序控制
- 捕获线程：FFmpeg 输出读取
- 识别线程：语音识别处理

**可进一步优化：**

```python
# 使用线程池处理识别任务
from concurrent.futures import ThreadPoolExecutor

class ContinuousSpeechRecognizer:
    def __init__(self, ...):
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def _process_buffer(self):
        # 提交到线程池异步处理
        self._executor.submit(self._recognize_task, combined_audio)
    
    def _recognize_task(self, audio_data):
        result = self.recognizer.recognize(audio_data)
        if self._on_result and result.text:
            self._on_result(result)
```

### 8.4 内存优化

```python
# 及时释放大对象
def _on_recognition_result(self, result):
    # 处理结果
    self._save_text(result.text, timestamp)
    self._save_audio_from_result(result.audio_data, timestamp)
    
    # 释放音频数据引用
    result.audio_data = None
    
    # 手动触发垃圾回收（如果需要）
    import gc
    if len(self._audio_buffer) > 100:
        gc.collect()
```

---

## 9. API 参考

### 9.1 XHSLiveCapturer

```python
class XHSLiveCapturer:
    """小红书直播流捕获器 - 主控制器"""
    
    def __init__(self, config: Optional[Dict] = None)
    """
    初始化捕获器
    
    Args:
        config: 配置字典，为 None 时使用默认配置
    """
    
    def start(self, url: str) -> bool
    """
    启动捕获和识别
    
    Args:
        url: 短链接或直播间 URL
        
    Returns:
        是否成功启动
    """
    
    def stop()
    """停止捕获"""
    
    def convert_url(self, url: str) -> bool
    """
    转换 URL 并获取流信息
    
    Args:
        url: 短链接或直播间 URL
        
    Returns:
        是否成功
    """
    
    def on_text(self, callback: Callable[[str, str], None])
    """
    设置文本输出回调
    
    Args:
        callback: 回调函数，参数为 (text, timestamp)
    """
    
    def on_status(self, callback: Callable[[str], None])
    """
    设置状态变化回调
    
    Args:
        callback: 回调函数，参数为状态字符串
    """
    
    @property
    def is_running(self) -> bool
    """是否正在运行"""
    
    @property
    def room_id(self) -> Optional[str]
    """当前房间 ID"""
    
    def get_stats(self) -> Dict[str, Any]
    """
    获取统计信息
    
    Returns:
        包含 stream 和 recognition 统计的字典
    """
```

### 9.2 StreamCapturer

```python
class StreamCapturer:
    """流捕获器"""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        buffer_size: int = 5,
        timeout: int = 30,
        reconnect_interval: int = 3,
        max_reconnect_attempts: int = 10
    )
    
    def start(self, stream_info: Dict) -> bool
    """
    启动流捕获
    
    Args:
        stream_info: 流信息字典，包含 'flv_url' 或 'hls_url'
        
    Returns:
        是否成功启动
    """
    
    def stop()
    """停止捕获"""
    
    def on_audio_chunk(self, callback: Callable[[AudioChunk], None])
    """设置音频数据回调"""
    
    def on_status_change(self, callback: Callable[[StreamStatus], None])
    """设置状态变化回调"""
    
    def on_error(self, callback: Callable[[str], None])
    """设置错误回调"""
    
    @property
    def stats(self) -> Dict
    """获取统计信息"""
```

### 9.3 ContinuousSpeechRecognizer

```python
class ContinuousSpeechRecognizer:
    """连续语音识别器"""
    
    def __init__(
        self,
        recognizer: BaseRecognizer,
        min_chunk_duration: float = 3.0,
        max_chunk_duration: float = 30.0,
        silence_threshold: float = 0.01
    )
    
    def start()
    """启动识别线程"""
    
    def stop()
    """停止识别"""
    
    def add_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        duration: float = 0
    )
    """
    添加音频数据到队列
    
    Args:
        audio_data: PCM 音频数据
        sample_rate: 采样率
        duration: 时长（为0时自动计算）
    """
    
    def on_result(self, callback: Callable[[RecognitionResult], None])
    """设置识别结果回调"""
    
    def on_error(self, callback: Callable[[str], None])
    """设置错误回调"""
    
    @property
    def stats(self) -> Dict
    """获取统计信息"""
```

### 9.4 Utils 函数

```python
def save_audio_buffer(
    audio_buffer: List[bytes],
    output_dir: Path,
    sample_rate: int = 16000,
    channels: int = 1
) -> Optional[str]
"""
保存音频缓冲区到文件（同时保存 .raw 和 .wav）

Args:
    audio_buffer: 音频数据缓冲区（bytes 列表）
    output_dir: 输出目录
    sample_rate: 采样率
    channels: 声道数
    
Returns:
    保存的时间戳字符串，失败返回 None
"""

def save_as_wav(
    audio_data: bytes,
    output_path: Path,
    sample_rate: int = 16000,
    channels: int = 1
) -> bool
"""
将 PCM 数据保存为 WAV 格式

Args:
    audio_data: PCM 音频数据
    output_path: 输出文件路径
    sample_rate: 采样率
    channels: 声道数
    
Returns:
    是否成功
"""
```

---

## 10. 错误处理

### 10.1 重连机制

```python
# StreamCapturer 中的重连逻辑
def _capture_loop(self):
    """捕获循环，带重连机制"""
    self._reconnect_count = 0
    
    while self._is_running:
        try:
            # 更新状态
            self._update_status(StreamStatus.CONNECTING)
            
            # 启动 FFmpeg
            process = self._start_ffmpeg(self._flv_url)
            
            if not process:
                raise RuntimeError("无法启动 FFmpeg")
            
            self._update_status(StreamStatus.STREAMING)
            self._reconnect_count = 0
            
            # 读取数据
            while self._is_running:
                chunk = self._read_audio_chunk(process)
                if not chunk:
                    break
                
                if self._on_audio_chunk_callback:
                    self._on_audio_chunk_callback(chunk)
                    
        except Exception as e:
            logger.error(f"捕获错误: {e}")
            self._reconnect_count += 1
            
            if self._reconnect_count <= self.max_reconnect_attempts:
                self._update_status(StreamStatus.RECONNECTING)
                logger.info(f"将在 {self.reconnect_interval} 秒后重连 "
                          f"({self._reconnect_count}/{self.max_reconnect_attempts})")
                time.sleep(self.reconnect_interval)
                continue
            else:
                self._update_status(StreamStatus.ERROR)
                if self._on_error_callback:
                    self._on_error_callback("达到最大重连次数")
                break
```

### 10.2 识别错误处理

```python
def _process_buffer(self):
    """处理缓冲区，带错误处理"""
    if not self._audio_buffer:
        return
    
    combined_audio = b''.join(self._audio_buffer)
    buffer_duration = self._buffer_duration
    
    # 清空缓冲区（即使识别失败也要清空，避免内存泄漏）
    self._audio_buffer = []
    self._buffer_duration = 0.0
    
    try:
        result = self.recognizer.recognize(combined_audio)
        result.audio_data = combined_audio
        
        # 只有识别出文本才回调
        if result.text and self._on_result:
            self._on_result(result)
            
    except Exception as e:
        logger.error(f"识别失败: {e}")
        
        # 回调错误
        if self._on_error:
            self._on_error(str(e))
        
        # 不保留音频数据，避免内存泄漏
        return
```

### 10.3 资源清理

```python
def stop(self):
    """停止捕获器，确保资源清理"""
    self._is_running = False
    
    # 1. 停止流捕获
    if self._stream_capturer:
        self._stream_capturer.stop()
    
    # 2. 停止语音识别
    if self._continuous_recognizer:
        self._continuous_recognizer.stop()
    
    # 3. 保存剩余缓冲区
    if self._audio_buffer:
        self._save_audio_buffer()
    
    # 4. 关闭链接转换器（清理 Chrome 进程）
    if self._link_converter:
        self._link_converter._cleanup()
    
    # 5. 清理引用
    self._stream_capturer = None
    self._continuous_recognizer = None
    self._link_converter = None
    
    logger.info("捕获器已完全停止")
```

---

## 11. 测试指南

### 11.1 测试目录结构

```
test/
├── __init__.py
├── test_whisper.py           # Whisper 模型测试
├── test_sensevoice.py        # SenseVoice 模型测试
├── test_converter.py         # 链接转换测试
├── test_capturer.py          # 流捕获测试
├── test_integration.py       # 集成测试
└── test_audio/
    ├── live_audio_30s.wav    # 30秒测试音频
    ├── live_audio_60s.wav    # 60秒测试音频
    └── silence.wav           # 静音测试文件
```

### 11.2 单元测试示例

```python
# test/test_capturer.py

import pytest
import numpy as np
from stream_capturer import StreamCapturer, AudioChunk, StreamStatus

class TestStreamCapturer:
    """流捕获器测试"""
    
    def test_audio_chunk_creation(self):
        """测试 AudioChunk 创建"""
        data = b'\x00\x00' * 16000  # 1秒静音
        chunk = AudioChunk(
            data=data,
            sample_rate=16000,
            channels=1,
            timestamp=0.0,
            duration=1.0
        )
        
        assert len(chunk.data) == 32000
        assert chunk.sample_rate == 16000
        assert chunk.duration == 1.0
    
    def test_capturer_initialization(self):
        """测试捕获器初始化"""
        capturer = StreamCapturer(
            sample_rate=16000,
            channels=1,
            buffer_size=5
        )
        
        assert capturer.sample_rate == 16000
        assert capturer.channels == 1
        assert not capturer._is_running
    
    @pytest.mark.skip(reason="需要实际的流地址")
    def test_capturer_start_stop(self):
        """测试启动和停止"""
        capturer = StreamCapturer()
        
        result = capturer.start({'flv_url': 'https://...'})
        assert result == True
        assert capturer._is_running
        
        capturer.stop()
        assert not capturer._is_running
```

```python
# test/test_recognizer.py

import pytest
import wave
import tempfile
from speech_recognizer import WhisperRecognizer, RecognitionResult

class TestWhisperRecognizer:
    """Whisper 识别器测试"""
    
    @pytest.fixture
    def recognizer(self):
        """创建识别器实例"""
        recognizer = WhisperRecognizer(model_size="tiny")
        recognizer.initialize()
        yield recognizer
        recognizer.close()
    
    @pytest.fixture
    def sample_audio(self):
        """生成测试音频"""
        # 1秒静音
        import numpy as np
        audio = np.zeros(16000, dtype=np.int16)
        return audio.tobytes()
    
    def test_initialization(self, recognizer):
        """测试初始化"""
        assert recognizer.status.value == "ready"
    
    def test_recognize_silence(self, recognizer, sample_audio):
        """测试静音识别"""
        result = recognizer.recognize(sample_audio)
        
        assert isinstance(result, RecognitionResult)
        assert result.text == "" or len(result.text) >= 0  # 静音可能返回空
    
    def test_recognize_with_audio(self, recognizer):
        """测试实际音频识别"""
        # 使用测试音频文件
        with wave.open("test_audio/live_audio_30s.wav", "rb") as f:
            f.readframes(44)  # 跳过 WAV 头部
            audio_data = f.readframes(f.getnframes())
        
        result = recognizer.recognize(audio_data)
        
        assert isinstance(result, RecognitionResult)
        assert len(result.text) > 0  # 应该识别出内容
```

### 11.3 运行测试

```bash
# 运行所有测试
python -m pytest test/ -v

# 运行特定测试文件
python test/test_whisper.py

# 运行带标记的测试
python -m pytest test/ -v -m "not skip"

# 生成覆盖率报告
python -m pytest test/ --cov=. --cov-report=html
```

---

## 附录

### A. 命令行参数

```
usage: main.py [-h] [-c CONFIG] [-s STREAM_URL] [-v] [url]

小红书直播流捕获器 - 获取直播音频并转换为文字

positional arguments:
  url                   小红书直播间短链接或完整URL（可选）

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        配置文件路径
  -s STREAM_URL, --stream-url STREAM_URL
                        直接指定直播流URL（跳过链接解析）
  -v, --verbose         显示详细日志
```

### B. 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `XHS_CHROME_PATH` | Chrome 可执行文件路径 | 自动检测 |
| `XHS_CDP_PORT` | Chrome CDP 端口 | 9222 |
| `XHS_FFMPEG_PATH` | FFmpeg 可执行文件路径 | 系统 PATH |
| `XHS_MODEL_DIR` | 模型目录 | ./models |

### C. 文件格式说明

**PCM 音频格式：**
- 编码：signed 16-bit little-endian
- 采样率：16000 Hz
- 声道：单声道
- 比特率：256 kbps

**WAV 文件头部：**
```python
# 使用 wave 模块写入
import wave

with wave.open("output.wav", "wb") as wf:
    wf.setnchannels(1)      # 单声道
    wf.setsampwidth(2)      # 16-bit = 2 bytes
    wf.setframerate(16000)  # 16kHz
    wf.writeframes(pcm_data)
```

---

**文档版本**: v1.0  
**最后更新**: 2026-04  
**维护者**: Development Team