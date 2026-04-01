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
        cache={},
        language="auto",
        use_itn=True,
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


if __name__ == "__main__":
    test_sensevoice()
    #simplest_test_sensevoice()