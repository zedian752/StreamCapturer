"""
语音识别器
将音频数据转换为文字
支持多种语音识别引擎：Whisper（本地）、SenseVoice（本地）
"""

import os
import io
import logging
import threading
import queue
import time
import json
import re
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
    segments: Optional[List[Dict]] = None
    language: str = "zh"
    

class BaseRecognizer(ABC):
    """语音识别器基类"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """初始化识别器"""
        pass
    
    @abstractmethod
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """识别音频数据"""
        pass
    
    @abstractmethod
    def close(self):
        """关闭识别器，释放资源"""
        pass


class WhisperRecognizer(BaseRecognizer):
    """
    OpenAI Whisper 本地语音识别器
    """
    
    def __init__(
        self,
        model_size: str = "base",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "float32"
    ):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        
        self._model = None
        self._use_faster_whisper = False
        self._status = RecognizerStatus.IDLE
    
    @property
    def status(self) -> RecognizerStatus:
        return self._status
    
    def initialize(self) -> bool:
        """加载Whisper模型"""
        try:
            self._status = RecognizerStatus.LOADING
            logger.info(f"正在加载Whisper模型: {self.model_size}")
            
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
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            if self._use_faster_whisper:
                result = self._recognize_faster_whisper(audio_float)
            else:
                result = self._recognize_openai_whisper(audio_float)
            
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
    
    def _recognize_faster_whisper(self, audio: np.ndarray) -> RecognitionResult:
        """使用faster-whisper进行识别"""
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
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
            confidence=getattr(info, 'language_probability', 1.0),
            segments=segment_list,
            language=self.language
        )
    
    def _recognize_openai_whisper(self, audio: np.ndarray) -> RecognitionResult:
        """使用openai-whisper进行识别"""
        result = self._model.transcribe(
            audio,
            language=self.language,
            fp16=False if self.device == "cpu" else True
        )
        
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
        
        if self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except:
                pass
        
        self._status = RecognizerStatus.IDLE
        logger.info("Whisper识别器已关闭")


class SenseVoiceRecognizer(BaseRecognizer):
    """
    SenseVoice 语音识别器
    阿里达摩院开源的语音识别模型，对中文有优秀支持
    使用VAD进行语音活动检测，自动分段处理
    """
    
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
        self.model_name = model
        self.language = language
        self.device = device
        self.vad_model = vad_model
        self.max_single_segment_time = max_single_segment_time
        self.merge_vad = merge_vad
        self.merge_length_s = merge_length_s
        self.batch_size_s = batch_size_s
        
        self._model = None
        self._postprocess_func = None
        self._status = RecognizerStatus.IDLE

        if (self.vad_model is None or not self.vad_model):
            raise RuntimeError('[vad_model] is invalid string')      
    
    @property
    def status(self) -> RecognizerStatus:
        return self._status
    
    def initialize(self) -> bool:
        """加载SenseVoice模型"""
        try:
            self._status = RecognizerStatus.LOADING
            logger.info(f"正在加载SenseVoice模型: {self.model_name}")
            
            from funasr import AutoModel
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            
            # 保存后处理函数引用
            self._postprocess_func = rich_transcription_postprocess
            
            # 设备格式转换：cpu -> cpu, cuda -> cuda:0
            device = self.device
            if device == "cuda":
                device = "cuda:0"
            
            self._model = AutoModel(
                model=self.model_name,
                trust_remote_code=True,
                remote_code="./model.py",
                vad_model=self.vad_model,
                vad_kwargs={"max_single_segment_time": self.max_single_segment_time},
                device=device,
                disable_pbar=True,
            )
            logger.info("使用 funasr 引擎 (SenseVoice + VAD)")
            
            self._status = RecognizerStatus.READY
            logger.info(f"SenseVoice模型加载完成")
            return True
            
        except ImportError as e:
            self._status = RecognizerStatus.ERROR
            logger.error(f"请安装 funasr: pip install funasr modelscope")
            logger.error(f"导入错误: {e}")
            return False
        except Exception as e:
            self._status = RecognizerStatus.ERROR
            logger.error(f"加载SenseVoice模型失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        """识别音频"""
        if self._status != RecognizerStatus.READY:
            raise RuntimeError("识别器未初始化")
        
        self._status = RecognizerStatus.RECOGNIZING
        start_time = time.time()
        
        try:
            # # 将字节数据转换为numpy数组
            # audio_array = np.frombuffer(audio_data, dtype=np.int16)
            # # 归一化为float32
            # audio_float = audio_array.astype(np.float32) / 32768.0
            
            # 使用SenseVoice进行识别
            result = self._model.generate(
                input=audio_data,
                cache={},
                language=self.language,  # "auto", "zh", "en", "yue", "ja", "ko", "nospeech"
                use_itn=True,
                batch_size_s=self.batch_size_s,
                merge_vad=self.merge_vad,
                merge_length_s=self.merge_length_s,
            )
            
            # 提取并后处理识别结果
            text = ""
            if result and len(result) > 0:
                first_result = result[0]
                if isinstance(first_result, dict):
                    raw_text = first_result.get("text", "")
                    if raw_text and self._postprocess_func:
                        text = self._postprocess_func(raw_text)
                    else:
                        text = raw_text
                elif isinstance(first_result, str):
                    if self._postprocess_func:
                        text = self._postprocess_func(first_result)
                    else:
                        text = first_result
            
            # 清理文本
            if text:
                text = text.strip()
            
            return RecognitionResult(
                text=text,
                start_time=start_time,
                end_time=time.time(),
                confidence=1.0,
                language=self._detect_language(text)
            )
            
        except Exception as e:
            logger.error(f"识别失败: {e}")
            import traceback
            traceback.print_exc()
            return RecognitionResult(
                text="",
                start_time=start_time,
                end_time=time.time(),
                confidence=0.0
            )
        finally:
            self._status = RecognizerStatus.READY
    
    def _detect_language(self, text: str) -> str:
        """简单检测文本语言"""
        if not text:
            return "unknown"
        # 简单判断：如果有中文字符返回zh
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return "zh"
        return "auto"
    
    def close(self):
        """释放资源"""
        if self._model:
            del self._model
            self._model = None
        
        self._postprocess_func = None
        
        if self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except:
                pass
        
        self._status = RecognizerStatus.IDLE
        logger.info("SenseVoice识别器已关闭")


class ContinuousSpeechRecognizer:
    """
    连续语音识别器
    """
    
    def __init__(
        self,
        recognizer: BaseRecognizer,
        min_chunk_duration: float = 3.0,
        max_chunk_duration: float = 30.0,
        silence_threshold: float = 0.01
    ):
        self.recognizer = recognizer
        self.min_chunk_duration = min_chunk_duration
        self.max_chunk_duration = max_chunk_duration
        self.silence_threshold = silence_threshold
        
        self._audio_buffer: List[bytes] = []
        self._buffer_duration: float = 0.0
        
        self._stop_event = threading.Event()
        self._recognize_thread: Optional[threading.Thread] = None
        
        self._audio_queue: queue.Queue = queue.Queue()
        
        self._on_result: Optional[Callable[[RecognitionResult], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        
        self._stats = {
            'total_chunks': 0,
            'total_duration': 0.0,
            'total_text_length': 0,
        }
    
    @property
    def stats(self) -> Dict[str, Any]:
        return self._stats.copy()
    
    def on_result(self, callback: Callable[[RecognitionResult], None]):
        self._on_result = callback
    
    def on_error(self, callback: Callable[[str], None]):
        self._on_error = callback
    
    def initialize(self) -> bool:
        return self.recognizer.initialize()
    
    def start(self):
        self._stop_event.clear()
        self._recognize_thread = threading.Thread(
            target=self._recognize_worker,
            daemon=True
        )
        self._recognize_thread.start()
        logger.info("连续语音识别已启动")
    
    def stop(self):
        self._stop_event.set()
        
        if self._recognize_thread and self._recognize_thread.is_alive():
            self._recognize_thread.join(timeout=5)
        
        if self._audio_buffer:
            self._process_buffer()
        
        logger.info("连续语音识别已停止")
    
    def add_audio(self, audio_data: bytes, sample_rate: int = 16000, duration: float = 0):
        if duration == 0:
            duration = len(audio_data) / (sample_rate * 2)
        
        try:
            self._audio_queue.put_nowait((audio_data, sample_rate, duration))
        except queue.Full:
            logger.warning("音频队列已满，丢弃数据")
    # 识别线程
    def _recognize_worker(self):
        while not self._stop_event.is_set():
            try:
                try:
                    audio_data, sample_rate, duration = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    if self._buffer_duration >= self.min_chunk_duration:
                        self._process_buffer()
                    continue
                
                self._audio_buffer.append(audio_data)
                self._buffer_duration += duration
                # 满足时长才开始处理
                if self._buffer_duration >= self.max_chunk_duration:
                    self._process_buffer()
                    
            except Exception as e:
                logger.error(f"识别工作线程错误: {e}")
                if self._on_error:
                    self._on_error(str(e))
    
    def _process_buffer(self):
        if not self._audio_buffer or self._buffer_duration < self.min_chunk_duration:
            return
        # 合并二进制块
        combined_audio = b''.join(self._audio_buffer)
        
        self._audio_buffer = []
        buffer_duration = self._buffer_duration
        self._buffer_duration = 0.0
        
        logger.debug(f"开始识别 {buffer_duration:.1f} 秒的音频")
        
        try:
            result = self.recognizer.recognize(combined_audio)
            
            self._stats['total_chunks'] += 1
            self._stats['total_duration'] += buffer_duration
            self._stats['total_text_length'] += len(result.text)
            
            if self._on_result and result.text:
                logger.info(f"识别结果: {result.text}")
                self._on_result(result) # 处理识别结果
            elif result.text:
                logger.info(f"识别结果: {result.text}")
                
        except Exception as e:
            logger.error(f"识别失败: {e}")
            if self._on_error:
                self._on_error(str(e))
    
    def close(self):
        self.stop()
        self.recognizer.close()


class SpeechRecognizerManager:
    """
    语音识别管理器
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.engine_type = config.get('engine', 'sensevoice')
        
        self._recognizer = self._create_recognizer()
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
        elif self.engine_type == 'sensevoice':
            sensevoice_config = self.config.get('sensevoice', {})
            return SenseVoiceRecognizer(
                model=sensevoice_config.get('model', 'iic/SenseVoiceSmall'),
                language=sensevoice_config.get('language', 'auto'),
                device=sensevoice_config.get('device', 'cpu'),
                vad_model=sensevoice_config.get('vad_model'),
            )
        else:
            raise ValueError(f"不支持的识别引擎: {self.engine_type}")
    
    def initialize(self) -> bool:
        return self._recognizer.initialize()
    
    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> RecognitionResult:
        return self._recognizer.recognize(audio_data, sample_rate)
    
    def create_continuous_recognizer(self) -> ContinuousSpeechRecognizer:
        self._continuous_recognizer = ContinuousSpeechRecognizer(
            recognizer=self._recognizer,
            min_chunk_duration=self.config.get('min_chunk_duration', 3.0),
            max_chunk_duration=self.config.get('max_chunk_duration', 30.0)
        )
        return self._continuous_recognizer
    
    def close(self):
        if self._continuous_recognizer:
            self._continuous_recognizer.close()
            self._continuous_recognizer = None
        self._recognizer.close()


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    config = {
        'engine': 'whisper',
        'whisper': {
            'model': 'base',
            'language': 'zh',
            'device': 'cpu'
        }
    }
    
    manager = SpeechRecognizerManager(config)
    
    print("正在初始化模型...")
    if manager.initialize():
        print("模型加载成功！")
    else:
        print("模型加载失败")