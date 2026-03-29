# Speak Handler 使用指南

## 概述

Speak Handler 用于实现声纹识别（Speaker Verification）功能，通过比对输入音频与参考音频的声纹特征，判断是否为同一说话人。

## 配置

在配置文件中添加以下配置项：

```yaml
bus:
  handlers:
    speak:
      enabled: true           # 启用声纹识别
      handler_type: "wespeaker"  # 使用 WeSpeaker 引擎
      depends_folder: "~/.nanobot/samples"  # 参考音频文件目录
      ref_speaker: "archer.wav"  # 参考说话人音频文件名（相对于 depends_folder）
      threshold: 0.9          # 相似度阈值，>0.9 认为是同一人
```

### 配置参数说明

- **enabled**: 是否启用声纹识别功能
- **handler_type**: 声纹识别引擎类型，目前支持 `wespeaker`
- **depends_folder**: 参考音频文件目录，默认 `~/.nanobot/samples`
- **ref_speaker**: 参考说话人音频文件名（相对于 depends_folder），例如 `"archer.wav"`
- **threshold**: 相似度阈值，范围 0-1，默认 0.9
  - score > threshold: 认为是同一说话人
  - score <= threshold: 认为是不同说话人

## 工作原理

### BaseSpeakHandler

基类处理器，提供以下功能：
- 加载参考说话人音频并提取声纹嵌入向量（embedding）
- 累积输入的音频数据块
- 将 PCM 音频数据转换为 WAV 格式
- 调用子类的验证方法进行声纹比对

### WeSpeakHandler

基于 WeSpeaker 的具体实现：
- 使用 `wespeakerruntime` 库进行声纹特征提取
- 通过余弦相似度计算两个声纹向量的相似程度
- 根据阈值判断是否为同一说话人

## 处理流程

1. **初始化阶段**
   - 加载 `wespeakerruntime` 库
   - 读取参考说话人音频文件
   - 提取参考声纹嵌入向量并缓存

2. **输入处理阶段**
   - 接收音频数据块（audio_clip 类型）
   - 累积多个音频块直到收到最后一个块（`is_last=True`）
   - 将累积的 PCM 数据转换为 WAV 格式

3. **声纹验证阶段**
   - 从 WAV 音频中提取测试声纹嵌入向量
   - 计算与参考声纹的余弦相似度
   - 根据阈值判断是否通过验证

4. **结果处理**
   - **验证通过**（score > threshold）：
     - 保留原始音频内容
     - 设置 metadata：`speaker_verified=True`, `speaker_score=相似度`
   - **验证失败**（score <= threshold）：
     - 清空音频内容和 media
     - 设置 `ret_type=IGNORE` 忽略此消息
     - 设置 metadata：`speaker_verified=False`, `speaker_score=相似度`

## 使用示例

### 准备参考音频

录制一段参考说话人的音频（建议 5-10 秒，清晰无噪音），保存到 `depends_folder` 指定的目录：

```bash
# 保存为 WAV 格式，16kHz 采样率，16bit 位深，单声道
ffmpeg -i input.mp3 -ar 16000 -sample_fmt s16 -ac 1 ~/.nanobot/samples/reference.wav
```

### 配置文件示例

```yaml
bus:
  handlers:
    vad:
      enabled: true
      handler_type: "silero"
      # ... VAD 配置
    asr:
      enabled: true
      handler_type: "funasr"
      # ... ASR 配置
    speak:
      enabled: true
      handler_type: "wespeaker"
      depends_folder: "~/.nanobot/samples"
      ref_speaker: "reference.wav"
      threshold: 0.9
```

### 代码中使用

```python
from nanobot.bus.handlers import WeSpeakHandler
from nanobot.config.schema import SpeakHandlerConfig

# 创建配置
config = SpeakHandlerConfig(
    enabled=True,
    handler_type="wespeaker",
    depends_folder="~/.nanobot/samples",
    ref_speaker="reference.wav",  # 相对路径
    threshold=0.9
)

# 创建处理器实例
handler = WeSpeakHandler(config)

# 处理器会自动在消息总线中处理音频输入
# 验证结果通过 msg.metadata["speaker_verified"] 和 msg.metadata["speaker_score"] 获取
```

## 依赖安装

```bash
pip install wespeakerruntime
```

## 注意事项

1. **音频格式要求**
   - 参考音频和输入音频都应该是 WAV 格式
   - 推荐采样率：16kHz
   - 推荐位深：16-bit
   - 推荐声道：单声道

2. **阈值选择**
   - 阈值越高，验证越严格（误识率降低，拒识率升高）
   - 阈值越低，验证越宽松（误识率升高，拒识率降低）
   - 建议根据实际场景调整，默认值 0.9 适用于大多数情况

3. **环境噪音**
   - 背景噪音会影响声纹识别准确率
   - 建议在相对安静的环境下录制参考音频

4. **音频长度**
   - 参考音频建议至少 5 秒
   - 输入音频建议至少 2 秒
   - 过短的音频可能导致特征提取不准确

## 调试信息

启用日志后可以看到详细的处理过程：

```
INFO - Loaded reference speaker embedding from /path/to/reference.wav
INFO - Speaker verified with score: 0.9523  # 验证通过
# 或
INFO - Speaker verification failed with score: 0.7234  # 验证失败
```

## 故障排除

### 问题：无法加载参考音频

**原因**：文件路径不存在或格式错误
**解决**：检查 `depends_folder` 和 `ref_speaker` 配置是否正确，确保文件存在于 `depends_folder/ref_speaker`

### 问题：验证分数始终很低

**原因**：
- 参考音频和输入音频不是同一人
- 音频质量差（噪音大、失真等）
- 音频太短导致特征不充分

**解决**：
- 重新录制高质量的参考音频
- 改善录音环境
- 增加音频长度

### 问题：导入错误 `No module named 'wespeakerruntime'`

**解决**：
```bash
pip install wespeakerruntime
```
