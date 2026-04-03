"""
测试 Whisper 语音识别模型
"""

import os
import sys
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speech_recognizer import WhisperRecognizer, RecognitionResult

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_whisper_with_wav(wav_file: str, model_size: str = "base", device: str = "cpu"):
    """
    使用 Whisper 模型识别 WAV 文件
    
    Args:
        wav_file: WAV 文件路径
        model_size: 模型大小 (tiny, base, small, medium, large)
        device: 设备 (cpu, cuda)
    """
    import wave
    import numpy as np
    
    # 检查文件是否存在
    if not os.path.exists(wav_file):
        logger.error(f"文件不存在: {wav_file}")
        return None
    
    # 读取 WAV 文件
    logger.info(f"读取音频文件: {wav_file}")
    with wave.open(wav_file, 'rb') as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        num_frames = wf.getnframes()
        duration = num_frames / sample_rate
        
        logger.info(f"音频信息: 采样率={sample_rate}Hz, 声道数={channels}, 时长={duration:.1f}秒")
        
        # 读取音频数据
        audio_data = wf.readframes(num_frames)
    
    # 如果需要重采样到 16kHz
    if sample_rate != 16000:
        logger.info(f"重采样: {sample_rate}Hz -> 16000Hz")
        import subprocess
        import tempfile
        
        # 使用 ffmpeg 重采样
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            subprocess.run([
                'ffmpeg', '-y', '-i', wav_file,
                '-ar', '16000', '-ac', '1', '-f', 'wav',
                tmp_path
            ], check=True, capture_output=True)
            
            with wave.open(tmp_path, 'rb') as wf:
                audio_data = wf.readframes(wf.getnframes())
                sample_rate = 16000
            
            os.unlink(tmp_path)
        except Exception as e:
            logger.warning(f"重采样失败，尝试直接使用原始音频: {e}")
    
    # 创建识别器
    logger.info(f"加载 Whisper 模型: {model_size} (device: {device})")
    recognizer = WhisperRecognizer(
        model_size=model_size,
        language="zh",
        device=device
    )
    
    # 初始化模型
    if not recognizer.initialize():
        logger.error("模型加载失败")
        return None
    
    logger.info("开始识别...")
    
    # 进行识别
    result = recognizer.recognize(audio_data, sample_rate=16000)
    
    # 输出结果
    print("\n" + "=" * 50)
    print("识别结果:")
    print("=" * 50)
    print(f"文本: {result.text}")
    print(f"置信度: {result.confidence:.2f}")
    print(f"语言: {result.language}")
    
    if result.segments:
        print("\n分段信息:")
        for i, seg in enumerate(result.segments):
            print(f"  [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")
    
    print("=" * 50)
    
    # 关闭识别器
    recognizer.close()
    
    return result


def test_whisper_simple(wav_file: str):
    """
    简单测试 - 使用默认参数
    
    Args:
        wav_file: WAV 文件路径
    """
    return test_whisper_with_wav(wav_file, model_size="base", device="cpu")


if __name__ == "__main__":
    # TODO: 修改为你要测试的音频文件路径
    TEST_AUDIO_FILE = "./test_audio/live_audio_30s.wav"
    
    # 也可以使用绝对路径
    # TEST_AUDIO_FILE = r"d:\xhs_stream_capturer\test_audio\live_audio_30s.wav"
    
    # 运行测试
    test_whisper_with_wav(
        wav_file=TEST_AUDIO_FILE,
        model_size="base",  # 可选: tiny, base, small, medium, large
        device="cpu"        # 可选: cpu, cuda
    )