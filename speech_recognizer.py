"""
语音识别器
将音频数据转换为文字
支持多种语音识别引擎：Whisper（本地）、Azure、阿里云、火山引擎
"""

import os
import io
import logging
import threading
import queue
import time
import json
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


class RecognizerStatus(Enum):
    """识别器状态"""
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    RECOGNIZING = "recognizing"
    ERROR = "error"


@dataclass
class RecognitionResult:
    """识别结果"""
    text: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    segments: Optional[List[Dict]] = None  # 分段信息（如果有）
    language: str = "zh"
    

class BaseRecognizer(ABC):
    """语音识别器基类"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """初始化识别器"""
        pass
    
    @abstractmethod
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """
        识别音频数据
        
        Args:
            audio_data: PCM音频数据（16位小端）
            sample_rate: 采样率
            
        Returns:
            识别结果
        """
        pass
    
    @abstractmethod
    def close(self):
        """关闭识别器，释放资源"""
        pass


class WhisperRecognizer(BaseRecognizer):
    """
    OpenAI Whisper 本地语音识别器
    支持多种模型大小，对中文有良好支持
    """
    
    def __init__(
        self,
        model_size: str = "base",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "float32"
    ):
        """
        初始化Whisper识别器
        
        Args:
            model_size: 模型大小 (tiny, base, small, medium, large)
            language: 语言代码
            device: 计算设备 (cpu, cuda)
            compute_type: 计算精度 (float32, float16, int8)
        """
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        
        self._model = None
        self._status = RecognizerStatus.IDLE
    
    @property
    def status(self) -> RecognizerStatus:
        return self._status
    
    def initialize(self) -> bool:
        """加载Whisper模型"""
        try:
            self._status = RecognizerStatus.LOADING
            logger.info(f"正在加载Whisper模型: {self.model_size}")
            
            # 尝试使用faster-whisper（更快）
            try:
                from faster_whisper import WhisperModel
                
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type
                )
                self._use_faster_whisper = True
                logger.info("使用 faster-whisper 引擎")
                
            except ImportError:
                # 回退到openai-whisper
                import whisper
                
                self._model = whisper.load_model(
                    self.model_size,
                    device=self.device
                )
                self._use_faster_whisper = False
                logger.info("使用 openai-whisper 引擎")
            
            self._status = RecognizerStatus.READY
            logger.info(f"Whisper模型加载完成")
            return True
            
        except Exception as e:
            self._status = RecognizerStatus.ERROR
            logger.error(f"加载Whisper模型失败: {e}")
            return False
    
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """识别音频"""
        if self._status != RecognizerStatus.READY:
            raise RuntimeError("识别器未初始化")
        
        self._status = RecognizerStatus.RECOGNIZING
        start_time = time.time()
        
        try:
            # 将PCM字节转换为numpy数组
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            if self._use_faster_whisper:
                result = self._recognize_faster_whisper(audio_float, sample_rate)
            else:
                result = self._recognize_openai_whisper(audio_float, sample_rate)
            
            return result
            
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
    
    def _recognize_faster_whisper(self, audio: np.ndarray, sample_rate: int) -> RecognitionResult:
        """使用faster-whisper进行识别"""
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,  # 语音活动检测
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # 收集所有文本
        text_parts = []
        segment_list = []
        
        for segment in segments:
            text_parts.append(segment.text)
            segment_list.append({
                'start': segment.start,
                'end': segment.end,
                'text': segment.text,
                'confidence': segment.avg_logprob
            })
        
        full_text = ''.join(text_parts).strip()
        
        return RecognitionResult(
            text=full_text,
            start_time=time.time(),
            end_time=time.time(),
            confidence=info.language_probability if hasattr(info, 'language_probability') else 1.0,
            segments=segment_list,
            language=self.language
        )
    
    def _recognize_openai_whisper(self, audio: np.ndarray, sample_rate: int) -> RecognitionResult:
        """使用openai-whisper进行识别"""
        result = self._model.transcribe(
            audio,
            language=self.language,
            fp16=False if self.device == "cpu" else True
        )
        
        # 收集所有文本
        text_parts = []
        segment_list = []
        
        for segment in result.get('segments', []):
            text_parts.append(segment['text'])
            segment_list.append({
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text'],
                'confidence': segment.get('avg_logprob', 1.0)
            })
        
        full_text = result['text'].strip() if result.get('text') else ''.join(text_parts).strip()
        
        return RecognitionResult(
            text=full_text,
            start_time=time.time(),
            end_time=time.time(),
            confidence=1.0,
            segments=segment_list,
            language=self.language
        )
    
    def close(self):
        """释放资源"""
        if self._model:
            del self._model
            self._model = None
        
        # 尝试清理GPU内存
        if self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except:
                pass
        
        self._status = RecognizerStatus.IDLE
        logger.info("Whisper识别器已关闭")


class ContinuousSpeechRecognizer:
    """
    连续语音识别器
    持续从音频队列获取数据并进行识别
    """
    
    def __init__(
        self,
        recognizer: BaseRecognizer,
        min_chunk_duration: float = 3.0,
        max_chunk_duration: float = 30.0,
        silence_threshold: float = 0.01
    ):
        """
        初始化连续识别器
        
        Args:
            recognizer: 底层识别器
            min_chunk_duration: 最小处理块时长（秒）
            max_chunk_duration: 最大处理块时长（秒）
            silence_threshold: 静音阈值
        """
        self.recognizer = recognizer
        self.min_chunk_duration = min_chunk_duration
        self.max_chunk_duration = max_chunk_duration
        self.silence_threshold = silence_threshold
        
        # 音频缓冲
        self._audio_buffer: List[bytes] = []
        self._buffer_duration: float = 0.0
        
        # 控制标志
        self._stop_event = threading.Event()
        self._recognize_thread: Optional[threading.Thread] = None
        
        # 音频队列（不限制大小）
        self._audio_queue: queue.Queue = queue.Queue()
        
        # 回调函数
        self._on_result: Optional[Callable[[RecognitionResult], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        
        # 统计
        self._stats = {
            'total_chunks': 0,
            'total_duration': 0.0,
            'total_text_length': 0,
        }
    
    @property
    def stats(self) -> Dict[str, Any]:
        return self._stats.copy()
    
    def on_result(self, callback: Callable[[RecognitionResult], None]):
        """设置识别结果回调"""
        self._on_result = callback
    
    def on_error(self, callback: Callable[[str], None]):
        """设置错误回调"""
        self._on_error = callback
    
    def initialize(self) -> bool:
        """初始化识别器"""
        return self.recognizer.initialize()
    
    def start(self):
        """开始连续识别"""
        self._stop_event.clear()
        self._recognize_thread = threading.Thread(
            target=self._recognize_worker,
            daemon=True
        )
        self._recognize_thread.start()
        logger.info("连续语音识别已启动")
    
    def stop(self):
        """停止识别"""
        self._stop_event.set()
        
        if self._recognize_thread and self._recognize_thread.is_alive():
            self._recognize_thread.join(timeout=5)
        
        # 处理剩余缓冲
        if self._audio_buffer:
            self._process_buffer()
        
        logger.info("连续语音识别已停止")
    
    def add_audio(self, audio_data: bytes, sample_rate: int = 16000, duration: float = 0):
        """
        添加音频数据到队列
        
        Args:
            audio_data: PCM音频数据
            sample_rate: 采样率
            duration: 音频时长（秒），如果不提供则自动计算
        """
        if duration == 0:
            # 16位PCM，每秒 = sample_rate * 2 字节
            duration = len(audio_data) / (sample_rate * 2)
        
        try:
            self._audio_queue.put_nowait((audio_data, sample_rate, duration))
        except queue.Full:
            logger.warning("音频队列已满，丢弃数据")
    
    def _recognize_worker(self):
        """识别工作线程"""
        while not self._stop_event.is_set():
            try:
                # 从队列获取音频数据
                try:
                    audio_data, sample_rate, duration = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    # 超时，检查是否需要处理缓冲区
                    if self._buffer_duration >= self.min_chunk_duration:
                        self._process_buffer()
                    continue
                
                # 添加到缓冲区
                self._audio_buffer.append(audio_data)
                self._buffer_duration += duration
                
                # 检查是否需要处理
                if self._buffer_duration >= self.max_chunk_duration:
                    self._process_buffer()
                    
            except Exception as e:
                logger.error(f"识别工作线程错误: {e}")
                if self._on_error:
                    self._on_error(str(e))
    
    def _process_buffer(self):
        """处理缓冲区中的音频"""
        if not self._audio_buffer or self._buffer_duration < self.min_chunk_duration:
            return
        
        # 合并音频数据
        combined_audio = b''.join(self._audio_buffer)
        
        # 清空缓冲区
        self._audio_buffer = []
        buffer_duration = self._buffer_duration
        self._buffer_duration = 0.0
        
        logger.debug(f"开始识别 {buffer_duration:.1f} 秒的音频")
        
        try:
            # 调用识别器
            result = self.recognizer.recognize(combined_audio)
            
            # 更新统计
            self._stats['total_chunks'] += 1
            self._stats['total_duration'] += buffer_duration
            self._stats['total_text_length'] += len(result.text)
            
            # 触发回调
            if self._on_result and result.text:
                logger.info(f"识别结果: {result.text}")
                self._on_result(result)
            elif result.text:
                logger.info(f"识别结果: {result.text}")
                
        except Exception as e:
            logger.error(f"识别失败: {e}")
            if self._on_error:
                self._on_error(str(e))
    
    def close(self):
        """关闭识别器"""
        self.stop()
        self.recognizer.close()


class SpeechRecognizerManager:
    """
    语音识别管理器
    提供统一的接口管理语音识别
    """
    
    def __init__(self, config: Dict):
        """
        初始化管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.engine_type = config.get('engine', 'whisper')
        
        # 创建底层识别器
        self._recognizer = self._create_recognizer()
        
        # 创建连续识别器
        self._continuous_recognizer = None
    
    def _create_recognizer(self) -> BaseRecognizer:
        """创建识别器实例"""
        if self.engine_type == 'whisper':
            whisper_config = self.config.get('whisper', {})
            return WhisperRecognizer(
                model_size=whisper_config.get('model', 'base'),
                language=whisper_config.get('language', 'zh'),
                device=whisper_config.get('device', 'cpu'),
            )
        else:
            raise ValueError(f"不支持的识别引擎: {self.engine_type}")
    
    def initialize(self) -> bool:
        """初始化"""
        return self._recognizer.initialize()
    
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """单次识别"""
        return self._recognizer.recognize(audio_data, sample_rate)
    
    def create_continuous_recognizer(self) -> ContinuousSpeechRecognizer:
        """创建连续识别器"""
        self._continuous_recognizer = ContinuousSpeechRecognizer(
            recognizer=self._recognizer,
            min_chunk_duration=self.config.get('min_chunk_duration', 3.0),
            max_chunk_duration=self.config.get('max_chunk_duration', 30.0)
        )
        return self._continuous_recognizer
    
    def close(self):
        """关闭"""
        if self._continuous_recognizer:
            self._continuous_recognizer.close()
            self._continuous_recognizer = None
        self._recognizer.close()


if __name__ == "__main__":
    # 测试代码
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建识别器
    config = {
        'engine': 'whisper',
        'whisper': {
            'model': 'base',
            'language': 'zh',
            'device': 'cpu'
        }
    }
    
    manager = SpeechRecognizerManager(config)
    
    print("正在初始化Whisper模型...")
    if manager.initialize():
        print("模型加载成功！")
        print("SpeechRecognizer 模块测试完成")
    else:
        print("模型加载失败")