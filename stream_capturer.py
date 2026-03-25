"""
直播流捕获器
从FLV/HLS直播流中提取音频数据
"""

import os
import io
import re
import logging
import threading
import subprocess
import queue
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import requests

logger = logging.getLogger(__name__)


class StreamStatus(Enum):
    """直播流状态"""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AudioChunk:
    """音频数据块"""
    data: bytes
    timestamp: float
    duration: float  # 秒
    sample_rate: int
    channels: int


class StreamCapturer:
    """
    直播流捕获器
    
    支持从FLV/HLS直播流中提取音频，使用FFmpeg进行解码
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        buffer_size: int = 5,
        timeout: int = 30,
        reconnect_interval: int = 3,
        max_reconnect_attempts: int = 10,
        ffmpeg_path: str = None
    ):
        """
        初始化捕获器
        
        Args:
            sample_rate: 音频采样率
            channels: 音频通道数
            buffer_size: 音频缓冲区大小（秒）
            timeout: 流请求超时时间
            reconnect_interval: 断线重连间隔
            max_reconnect_attempts: 最大重连次数
            ffmpeg_path: FFmpeg可执行文件路径（None则自动查找）
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        
        # 自动查找ffmpeg
        if ffmpeg_path:
            self.ffmpeg_path = ffmpeg_path
        else:
            self.ffmpeg_path = self._find_ffmpeg()
        
        # 状态
        self._status = StreamStatus.IDLE
        self._stream_url: Optional[str] = None
        self._stream_info: Optional[Dict] = None
        
        # FFmpeg进程
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        
        # 音频队列
        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        
        # 控制标志
        self._stop_event = threading.Event()
        self._stream_thread: Optional[threading.Thread] = None
        
        # 回调函数
        self._on_audio_chunk: Optional[Callable[[AudioChunk], None]] = None
        self._on_status_change: Optional[Callable[[StreamStatus], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        
        # 统计信息
        self._stats = {
            'total_duration': 0.0,
            'chunks_received': 0,
            'bytes_received': 0,
            'start_time': None,
            'last_chunk_time': None,
        }
    
    def _find_ffmpeg(self) -> str:
        """查找FFmpeg可执行文件"""
        # 1. 首先检查项目目录
        project_dir = os.path.dirname(os.path.abspath(__file__))
        local_ffmpeg = os.path.join(project_dir, 'ffmpeg.exe')
        if os.path.exists(local_ffmpeg):
            logger.info(f"使用本地FFmpeg: {local_ffmpeg}")
            return local_ffmpeg
        
        # 2. 检查系统PATH
        import shutil
        ffmpeg_in_path = shutil.which('ffmpeg')
        if ffmpeg_in_path:
            return ffmpeg_in_path
        
        # 3. 返回默认值（会在后续报错）
        return "ffmpeg"
    
    @property
    def status(self) -> StreamStatus:
        """获取当前状态"""
        return self._status
    
    @property
    def stream_url(self) -> Optional[str]:
        """获取当前流URL"""
        return self._stream_url
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    def _set_status(self, status: StreamStatus):
        """设置状态并触发回调"""
        if self._status != status:
            self._status = status
            logger.info(f"流捕获器状态变更: {status.value}")
            if self._on_status_change:
                try:
                    self._on_status_change(status)
                except Exception as e:
                    logger.error(f"状态回调执行错误: {e}")
    
    def on_audio_chunk(self, callback: Callable[[AudioChunk], None]):
        """设置音频数据回调"""
        self._on_audio_chunk = callback
    
    def on_status_change(self, callback: Callable[[StreamStatus], None]):
        """设置状态变更回调"""
        self._on_status_change = callback
    
    def on_error(self, callback: Callable[[str], None]):
        """设置错误回调"""
        self._on_error = callback
    
    def start(self, stream_info: Dict) -> bool:
        """
        开始捕获直播流
        
        Args:
            stream_info: 直播流信息，包含flv_url或hls_url
            
        Returns:
            是否成功启动
        """
        if self._status not in [StreamStatus.IDLE, StreamStatus.STOPPED, StreamStatus.ERROR]:
            logger.warning(f"当前状态 {self._status.value} 不允许启动")
            return False
        
        self._stream_info = stream_info
        self._stream_url = stream_info.get('flv_url') or stream_info.get('hls_url')
        
        if not self._stream_url:
            error_msg = "没有找到可用的直播流URL"
            logger.error(error_msg)
            if self._on_error:
                self._on_error(error_msg)
            return False
        
        logger.info(f"开始捕获直播流: {self._stream_url}")
        
        # 重置状态
        self._stop_event.clear()
        self._stats = {
            'total_duration': 0.0,
            'chunks_received': 0,
            'bytes_received': 0,
            'start_time': time.time(),
            'last_chunk_time': None,
        }
        
        # 启动流处理线程
        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            daemon=True
        )
        self._stream_thread.start()
        
        return True
    
    def stop(self):
        """停止捕获"""
        logger.info("停止捕获直播流")
        self._stop_event.set()
        self._set_status(StreamStatus.STOPPED)
        
        # 停止FFmpeg进程
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"停止FFmpeg进程时出错: {e}")
                try:
                    self._ffmpeg_process.kill()
                except:
                    pass
            self._ffmpeg_process = None
        
        # 等待线程结束
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=5)
        
        # 清空队列
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
    
    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[AudioChunk]:
        """
        从队列获取音频数据块
        
        Args:
            timeout: 超时时间
            
        Returns:
            音频数据块或None
        """
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _stream_worker(self):
        """流处理工作线程"""
        reconnect_count = 0
        
        while not self._stop_event.is_set():
            try:
                self._set_status(StreamStatus.CONNECTING)
                
                # 使用FFmpeg捕获流
                success = self._capture_with_ffmpeg()
                
                if self._stop_event.is_set():
                    break
                
                if not success:
                    reconnect_count += 1
                    if reconnect_count > self.max_reconnect_attempts:
                        error_msg = f"重连次数超过最大限制 ({self.max_reconnect_attempts})"
                        logger.error(error_msg)
                        self._set_status(StreamStatus.ERROR)
                        if self._on_error:
                            self._on_error(error_msg)
                        break
                    
                    logger.info(f"将在 {self.reconnect_interval} 秒后重连 (第 {reconnect_count} 次)")
                    self._set_status(StreamStatus.RECONNECTING)
                    
                    # 等待重连
                    for _ in range(int(self.reconnect_interval * 10)):
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.1)
                else:
                    # 正常结束
                    break
                    
            except Exception as e:
                logger.error(f"流处理线程错误: {e}")
                if not self._stop_event.is_set():
                    reconnect_count += 1
                    if reconnect_count <= self.max_reconnect_attempts:
                        time.sleep(self.reconnect_interval)
                    else:
                        self._set_status(StreamStatus.ERROR)
                        if self._on_error:
                            self._on_error(str(e))
                        break
    
    def _capture_with_ffmpeg(self) -> bool:
        """
        使用FFmpeg捕获直播流并提取音频
        
        Returns:
            是否正常结束（非断流）
        """
        # FFmpeg命令
        # -i: 输入URL
        # -vn: 不处理视频
        # -acodec pcm_s16le: 输出16位PCM
        # -ar: 采样率
        # -ac: 声道数
        # -f s16le: 输出格式为原始PCM
        # -flush_packets 1: 立即刷新数据包
        # -reconnect 1: 自动重连（对于HTTP流）
        
        ffmpeg_cmd = [
            self.ffmpeg_path,
            '-i', self._stream_url,
            '-vn',  # 不处理视频
            '-acodec', 'pcm_s16le',  # 16位PCM编码
            '-ar', str(self.sample_rate),  # 采样率
            '-ac', str(self.channels),  # 声道数
            '-f', 's16le',  # 原始PCM格式
            '-flush_packets', '1',
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-timeout', str(self.timeout * 1000000),  # 微秒
            '-',  # 输出到stdout
        ]
        
        logger.info(f"启动FFmpeg: {' '.join(ffmpeg_cmd[:5])}...")
        
        try:
            self._ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            self._set_status(StreamStatus.CONNECTED)
            
            # 启动stderr读取线程（用于调试）
            stderr_thread = threading.Thread(
                target=self._read_ffmpeg_stderr,
                daemon=True
            )
            stderr_thread.start()
            
            # 计算每次读取的字节数（对应buffer_size秒的音频）
            bytes_per_chunk = self.sample_rate * self.channels * 2 * self.buffer_size
            
            logger.info(f"开始读取音频数据，每次读取 {bytes_per_chunk} 字节 ({self.buffer_size}秒)")
            
            while not self._stop_event.is_set():
                # 读取音频数据
                audio_data = self._ffmpeg_process.stdout.read(bytes_per_chunk)
                
                if not audio_data:
                    # 检查进程是否结束
                    if self._ffmpeg_process.poll() is not None:
                        logger.warning("FFmpeg进程已结束")
                        return False
                    time.sleep(0.1)
                    continue
                
                self._set_status(StreamStatus.STREAMING)
                
                # 创建音频块
                chunk = AudioChunk(
                    data=audio_data,
                    timestamp=time.time(),
                    duration=self.buffer_size,
                    sample_rate=self.sample_rate,
                    channels=self.channels
                )
                
                # 更新统计
                self._stats['chunks_received'] += 1
                self._stats['bytes_received'] += len(audio_data)
                self._stats['total_duration'] += self.buffer_size
                self._stats['last_chunk_time'] = time.time()
                
                # 放入队列
                try:
                    self._audio_queue.put_nowait(chunk)
                except queue.Full:
                    # 队列满，丢弃最旧的数据
                    try:
                        self._audio_queue.get_nowait()
                        self._audio_queue.put_nowait(chunk)
                        logger.debug("队列已满，丢弃旧数据")
                    except queue.Empty:
                        pass
                
                # 触发回调
                if self._on_audio_chunk:
                    try:
                        self._on_audio_chunk(chunk)
                    except Exception as e:
                        logger.error(f"音频回调执行错误: {e}")
                        
            return True
            
        except FileNotFoundError:
            error_msg = f"找不到FFmpeg，请确保已安装并添加到PATH: {self.ffmpeg_path}"
            logger.error(error_msg)
            if self._on_error:
                self._on_error(error_msg)
            return False
        except Exception as e:
            logger.error(f"FFmpeg捕获错误: {e}")
            if self._on_error:
                self._on_error(str(e))
            return False
        finally:
            if self._ffmpeg_process:
                try:
                    self._ffmpeg_process.terminate()
                    self._ffmpeg_process.wait(timeout=2)
                except:
                    try:
                        self._ffmpeg_process.kill()
                    except:
                        pass
                self._ffmpeg_process = None
    
    def _read_ffmpeg_stderr(self):
        """读取FFmpeg的stderr输出（用于调试）"""
        if not self._ffmpeg_process:
            return
            
        try:
            while True:
                line = self._ffmpeg_process.stderr.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    # 只记录重要信息
                    if any(x in line_str.lower() for x in ['error', 'warning', 'invalid']):
                        logger.warning(f"FFmpeg: {line_str}")
                    else:
                        logger.debug(f"FFmpeg: {line_str}")
        except Exception as e:
            logger.debug(f"读取FFmpeg stderr错误: {e}")
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._status in [StreamStatus.CONNECTING, StreamStatus.CONNECTED, 
                                StreamStatus.STREAMING, StreamStatus.RECONNECTING]
    
    def save_audio_to_file(self, output_path: str, duration: Optional[float] = None) -> bool:
        """
        直接将流保存到音频文件
        
        Args:
            output_path: 输出文件路径
            duration: 录制时长（秒），None表示一直录制直到手动停止
            
        Returns:
            是否成功
        """
        if not self._stream_url:
            logger.error("没有设置流URL")
            return False
        
        # 构建FFmpeg命令
        ffmpeg_cmd = [
            self.ffmpeg_path,
            '-i', self._stream_url,
            '-vn',
            '-acodec', 'libmp3lame' if output_path.endswith('.mp3') else 'pcm_s16le',
            '-ar', str(self.sample_rate),
            '-ac', str(self.channels),
        ]
        
        if duration:
            ffmpeg_cmd.extend(['-t', str(duration)])
        
        ffmpeg_cmd.extend([
            '-y',  # 覆盖输出文件
            output_path
        ])
        
        try:
            logger.info(f"开始录制到文件: {output_path}")
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 等待完成或超时
            if duration:
                process.wait(timeout=duration + 10)
            else:
                process.wait()
            
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"保存音频文件失败: {e}")
            return False


class StreamCapturerWithRetry:
    """
    带自动重试的流捕获器
    封装StreamCapturer，提供更稳定的连接
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.capturer = StreamCapturer(
            sample_rate=self.config.get('sample_rate', 16000),
            channels=self.config.get('channels', 1),
            buffer_size=self.config.get('buffer_size', 5),
            timeout=self.config.get('flv_timeout', 30),
            reconnect_interval=self.config.get('reconnect_interval', 3),
            max_reconnect_attempts=self.config.get('max_reconnect_attempts', 10),
        )
    
    def start(self, stream_info: Dict) -> bool:
        """启动捕获"""
        return self.capturer.start(stream_info)
    
    def stop(self):
        """停止捕获"""
        self.capturer.stop()
    
    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[AudioChunk]:
        """获取音频块"""
        return self.capturer.get_audio_chunk(timeout)
    
    def on_audio_chunk(self, callback):
        """设置音频回调"""
        self.capturer.on_audio_chunk(callback)
    
    def on_status_change(self, callback):
        """设置状态回调"""
        self.capturer.on_status_change(callback)
    
    def on_error(self, callback):
        """设置错误回调"""
        self.capturer.on_error(callback)
    
    @property
    def status(self) -> StreamStatus:
        return self.capturer.status
    
    @property
    def stats(self) -> Dict[str, Any]:
        return self.capturer.stats
    
    def is_running(self) -> bool:
        return self.capturer.is_running()


if __name__ == "__main__":
    # 测试代码
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 测试流URL（需要替换为实际的）
    test_stream_url = "https://example.com/live/stream.flv"
    
    capturer = StreamCapturer(
        sample_rate=16000,
        channels=1,
        buffer_size=3,
    )
    
    def on_audio(chunk: AudioChunk):
        print(f"收到音频块: {len(chunk.data)} 字节, {chunk.duration} 秒")
    
    def on_status(status: StreamStatus):
        print(f"状态变更: {status.value}")
    
    capturer.on_audio_chunk(on_audio)
    capturer.on_status_change(on_status)
    
    # 测试启动（需要实际的流URL）
    # capturer.start({'flv_url': test_stream_url})
    
    print("StreamCapturer 模块测试完成")