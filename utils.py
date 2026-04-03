"""
工具函数模块
"""

import wave
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def save_audio_buffer(
    audio_buffer: List[bytes],
    output_dir: Path,
    sample_rate: int = 16000,
    channels: int = 1
) -> Optional[str]:
    """
    保存音频缓冲区到文件（同时保存.raw和.wav格式）
    
    Args:
        audio_buffer: 音频数据缓冲区（bytes列表）
        output_dir: 输出目录
        sample_rate: 采样率（默认16000）
        channels: 声道数（默认1）
        
    Returns:
        保存的时间戳字符串，失败返回None
    """
    if not audio_buffer or not output_dir:
        return None
    
    try:
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%H%M%S')
        
        # 合并所有音频数据
        combined_audio = b''.join(audio_buffer)
        
        # 1. 保存原始PCM文件
        raw_file = output_dir / f"audio_{timestamp}.raw"
        with open(raw_file, 'wb') as f:
            f.write(combined_audio)
        
        # 2. 保存WAV文件（添加头部）
        wav_file = output_dir / f"audio_{timestamp}.wav"
        save_as_wav(combined_audio, wav_file, sample_rate, channels)
        
        logger.info(f"保存音频: {raw_file.name}, {wav_file.name}")
        return timestamp

    except Exception as e:
        logger.error(f"保存音频失败: {e}")
        return None


def save_as_wav(
    audio_data: bytes,
    output_path: Path,
    sample_rate: int = 16000,
    channels: int = 1
) -> bool:
    """
    将PCM数据保存为WAV格式
    
    Args:
        audio_data: PCM音频数据（bytes）
        output_path: 输出文件路径
        sample_rate: 采样率（默认16000）
        channels: 声道数（默认1）
        
    Returns:
        是否成功
    """
    try:
        with wave.open(str(output_path), 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 16位 = 2字节
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data)
        return True
    except Exception as e:
        logger.error(f"保存WAV文件失败: {e}")
        return False