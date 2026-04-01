"""
SenseVoice 模型测试脚本
使用示例音频文件测试 SenseVoice 语音识别功能
"""

import os
import sys
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sensevoice():
    """测试 SenseVoice 模型"""
    
    print("=" * 60)
    print("SenseVoice 模型测试")
    print("=" * 60)
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 音频文件路径
    audio_file = os.path.join(
        project_root,
        "models", "SenseVoiceSmall", "example", "yue.mp3"
    )
    
    if not os.path.exists(audio_file):
        print(f"错误: 音频文件不存在: {audio_file}")
        print("请确保已下载 SenseVoice 模型到 models/SenseVoiceSmall 目录")
        return False
    
    print(f"音频文件: {audio_file}")
    print("正在加载模型...")
    
    # 模型路径（使用绝对路径）
    model_path = os.path.join(project_root, "models", "SenseVoiceSmall")  
    model_py_path = os.path.join(project_root, "model.py")
    vad_model_path = os.path.join(project_root, "models", "speech_fsmn_vad_zh-cn-16k-common-pytorch")  

    # 加载模型
    model = AutoModel(
        model=model_path,  # model(str): model name in the Model Repository, or a model path on local disk.
        
        trust_remote_code=True,
        remote_code=model_py_path,
        vad_model=vad_model_path,
        vad_kwargs={"max_single_segment_time": 30000},
        device="cpu",
        disable_pbar=False,  # 是否禁用进度条
        disable_update=True,
    )
    
    print("模型加载完成！")
    print("正在进行语音识别...")
    
    # 进行识别
    res = model.generate(
        input=audio_file,
        cache={}, # 用于存储推理过程中的中间状态。对于单次文件识别，传空字典即可；如果是流式识别（一边说话一边出字），这个参数非常关键，用于保存上一段语音的上下文。
        language="auto",
        use_itn=True,  # ITN (Inverse Text Normalization) 负责把“二零二四年”转成“2024年”，把“百分之五十”转成“50%”。开启后文字可读性更高。
        batch_size_s=60, # 一次性处理多少秒
        merge_vad=True, # 是否合并 VAD 切分后的短句。VAD 有时会把一句话因为语气停顿切得太碎，开启此项能把太短的片段拼起来。
        merge_length_s=15, # 配合上面参数merge_vad。表示尽量将短片段拼接成 15 秒左右的一段话再交给模型。这能显著提升准确率，因为模型在长一点的上下文中识别效果更好。
    )
    
    # 后处理并输出结果
    if res and len(res) > 0:
        text = rich_transcription_postprocess(res[0]["text"])
        print("=" * 60)
        print(f"识别结果: {text}")
        print("=" * 60)
        return True
    else:
        print("识别失败: 无结果")
        return False


def simplest_test_sensevoice():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_model_path = os.path.join(project_root, "models", "SenseVoiceSmall")  
    vad_model_path = os.path.join(project_root, "models", "speech_fsmn_vad_zh-cn-16k-common-pytorch")  
    model = AutoModel(
        model=base_model_path,
        disable_update=True,
        device="cpu",
        vad_model=vad_model_path,
        vad_kwargs={"max_single_segment_time": 30000},
        )

    
    # 音频文件路径
    #audio_file = os.path.join(project_root, "models", "SenseVoiceSmall", "example", "yue.mp3")
    
    audio_file_list = []
    audio_file_list.append(os.path.join(project_root, "models", "SenseVoiceSmall", "example", "yue.mp3"))
    audio_file_list.append(os.path.join(project_root, "models", "SenseVoiceSmall", "example", "zh.mp3"))

    # loop processing
    for audio_file in audio_file_list:
        res = model.generate(input=audio_file)
        print(rich_transcription_postprocess(res))


def read_wav_to_bytes(wav_file: str) -> bytes:
    """
    读取 WAV 文件并返回音频数据（不含头部）的 bytes
    
    Args:
        wav_file: WAV 文件路径
        
    Returns:
        音频数据的 bytes（16位PCM，单声道，16kHz）
    """
    import wave
    
    with wave.open(wav_file, 'rb') as wf:
        # 读取WAV文件信息
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        
        print(f"WAV信息: {n_channels}声道, {sample_width}位. {framerate}Hz. {n_frames}帧")
        
        # 读取所有音频帧
        audio_data = wf.readframes(n_frames)
        
        return audio_data


    
def test_wav_bytes(wav_filename: str):
    """
    读取 test_audio 目录下的 wav 文件（转bytes）并使用 SenseVoice 进行识别
    
    Args:
        wav_filename: wav文件名，默认为 live_audio_30s.wav
    """
    import numpy as np
    
    print("=" * 60)
    print("WAV Bytes 语音识别测试")
    print("=" * 60)
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # wav 文件路径
    wav_file = os.path.join(project_root, "test_audio", wav_filename)
    
    if not os.path.exists(wav_file):
        print(f"错误: WAV文件不存在: {wav_file}")
        print("请先运行 test_capture_audio.py 录制音频")
        return False
    
    # 读取wav文件为bytes
    audio_bytes = read_wav_to_bytes(wav_file)
    print(f"音频数据大小: {len(audio_bytes)} 字节")
    print("正在加载模型...")
    
    # 模型路径
    model_path = os.path.join(project_root, "models", "SenseVoiceSmall")
    model_py_path = os.path.join(project_root, "model.py")
    vad_model_path = os.path.join(project_root, "models", "speech_fsmn_vad_zh-cn-16k-common-pytorch")
    
    # 加载模型
    model = AutoModel(
        model=model_path,
        trust_remote_code=False,
        vad_model=vad_model_path,
        vad_kwargs={"max_single_segment_time": 30000},
        device="cpu",
        disable_pbar=False,
        disable_update=True,
    )
    
    print("模型加载完成！")
    print("正在进行语音识别（使用bytes输入）...")
    
    # 将bytes转换为numpy数组（float32）
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
    audio_float = audio_array.astype(np.float32) / 32768.0
    
    # 进行识别（使用numpy数组作为输入）
    res = model.generate(
        input=audio_float,
        cache={},
        language="auto",
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=15,
    )
    
    # 后处理并输出结果
    if res and len(res) > 0:
        text = rich_transcription_postprocess(res[0]["text"])
        print("=" * 60)
        print(f"识别结果: {text}")
        print("=" * 60)
        return True
    else:
        print("识别失败: 无结果")
        return False


    
    
def test_wav_file(wav_filename: str = "live_audio_30s.wav"):
    """
    读取 test_audio 目录下的 wav 文件并使用 SenseVoice 进行识别
    （直接传入文件路径）
    
    Args:
        wav_filename: wav文件名，默认为 live_audio_30s.wav
    """
    print("=" * 60)
    print("WAV 文件语音识别测试（文件路径输入）")
    print("=" * 60)
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # wav 文件路径
    wav_file = os.path.join(project_root, "test_audio", wav_filename)
    
    if not os.path.exists(wav_file):
        print(f"错误: WAV文件不存在: {wav_file}")
        print("请先运行 test_capture_audio.py 录制音频")
        return False
    
    print(f"WAV文件: {wav_file}")
    file_size = os.path.getsize(wav_file)
    print(f"文件大小: {file_size / 1024:.1f} KB")
    print("正在加载模型...")
    
    # 模型路径
    model_path = os.path.join(project_root, "models", "SenseVoiceSmall")
    model_py_path = os.path.join(project_root, "model.py")
    vad_model_path = os.path.join(project_root, "models", "speech_fsmn_vad_zh-cn-16k-common-pytorch")
    
    # 加载模型
    model = AutoModel(
        model=model_path,
        trust_remote_code=False,
        vad_model=vad_model_path,
        vad_kwargs={"max_single_segment_time": 30000},
        device="cpu",
        disable_pbar=False,
        disable_update=True,
    )
    
    print("模型加载完成！")
    print("正在进行语音识别...")
    
    # 进行识别
    res = model.generate(
        input=wav_file,
        cache={},
        language="auto",
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=15,
    )
    
    # 后处理并输出结果
    if res and len(res) > 0:
        text = rich_transcription_postprocess(res[0]["text"])
        print("=" * 60)
        print(f"识别结果: {text}")
        print("=" * 60)
        return True
    else:
        print("识别失败: 无结果")
        return False


if __name__ == "__main__":
    # 测试模型示例音频
    # test_sensevoice()
    
    # 测试录制的 wav 文件（直接传入文件路径）
    #test_wav_file("live_audio_30s.wav")
    
    # 测试录制的 wav 文件（转换为bytes后传入）
    test_wav_bytes("live_audio_30s.wav")
