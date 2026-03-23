// 音频播放模块
import BlockingQueue from './blocking-queue.js';
import { createStreamingContext } from './stream-context.js';

// 音频播放器类
export class AudioPlayer {
    constructor() {
        // 音频参数
        this.SAMPLE_RATE = 16000;
        this.CHANNELS = 1;
        this.FRAME_SIZE = 960;
        this.MIN_AUDIO_DURATION = 0.12;

        // 状态
        this.audioContext = null;
        this.opusDecoder = null;
        this.streamingContext = null;
        this.queue = new BlockingQueue();
        this.isPlaying = false;
    }

    // 获取或创建AudioContext
    getAudioContext() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.SAMPLE_RATE,
                latencyHint: 'interactive'
            });
            console.log('创建音频上下文，采样率：' + this.SAMPLE_RATE + 'Hz');
        }
        return this.audioContext;
    }

    // 初始化Opus解码器
    async initOpusDecoder() {
        if (this.opusDecoder) return this.opusDecoder;

        try {
            if (typeof window.ModuleInstance === 'undefined') {
                if (typeof Module !== 'undefined') {
                    window.ModuleInstance = Module;
                    console.log('使用全局 Module 作为 ModuleInstance');
                } else {
                    throw new Error('Opus库未加载，ModuleInstance和Module对象都不存在');
                }
            }

            const mod = window.ModuleInstance;

            this.opusDecoder = {
                channels: this.CHANNELS,
                rate: this.SAMPLE_RATE,
                frameSize: this.FRAME_SIZE,
                module: mod,
                decoderPtr: null,

                init: function () {
                    if (this.decoderPtr) return true;

                    const decoderSize = mod._opus_decoder_get_size(this.channels);
                    console.log(`Opus 解码器大小：${decoderSize}字节`);

                    this.decoderPtr = mod._malloc(decoderSize);
                    if (!this.decoderPtr) {
                        throw new Error("无法分配解码器内存");
                    }

                    const err = mod._opus_decoder_init(
                        this.decoderPtr,
                        this.rate,
                        this.channels
                    );

                    if (err < 0) {
                        this.destroy();
                        throw new Error(`Opus解码器初始化失败: ${err}`);
                    }

                    console.log("Opus 解码器初始化成功");
                    return true;
                },

                decode: function (opusData) {
                    if (!this.decoderPtr) {
                        if (!this.init()) {
                            throw new Error("解码器未初始化且无法初始化");
                        }
                    }

                    try {
                        const mod = this.module;

                        const opusPtr = mod._malloc(opusData.length);
                        mod.HEAPU8.set(opusData, opusPtr);

                        const pcmPtr = mod._malloc(this.frameSize * 2);

                        const decodedSamples = mod._opus_decode(
                            this.decoderPtr,
                            opusPtr,
                            opusData.length,
                            pcmPtr,
                            this.frameSize,
                            0
                        );

                        if (decodedSamples < 0) {
                            mod._free(opusPtr);
                            mod._free(pcmPtr);
                            throw new Error(`Opus解码失败: ${decodedSamples}`);
                        }

                        const decodedData = new Int16Array(decodedSamples);
                        for (let i = 0; i < decodedSamples; i++) {
                            decodedData[i] = mod.HEAP16[(pcmPtr >> 1) + i];
                        }

                        mod._free(opusPtr);
                        mod._free(pcmPtr);

                        return decodedData;
                    } catch (error) {
                        console.error(`Opus 解码错误：${error.message}`);
                        return new Int16Array(0);
                    }
                },

                destroy: function () {
                    if (this.decoderPtr) {
                        this.module._free(this.decoderPtr);
                        this.decoderPtr = null;
                    }
                }
            };

            if (!this.opusDecoder.init()) {
                throw new Error("Opus解码器初始化失败");
            }

            return this.opusDecoder;

        } catch (error) {
            console.error(`Opus 解码器初始化失败：${error.message}`);
            this.opusDecoder = null;
            throw error;
        }
    }

    // 启动音频缓冲
    async startAudioBuffering() {
        console.log("开始音频缓冲...");

        this.initOpusDecoder().catch(error => {
            console.error(`预初始化 Opus 解码器失败：${error.message}`);
        });

        const timeout = 400;
        while (true) {
            const packets = await this.queue.dequeue(
                6,
                timeout,
                (count) => {
                    console.log(`缓冲超时，当前缓冲包数：${count}，开始播放`);
                }
            );
            if (packets.length) {
                console.log(`已缓冲 ${packets.length} 个音频包，开始播放`);
                this.streamingContext.pushAudioBuffer(packets);
            }

            while (true) {
                const data = await this.queue.dequeue(99, 30);
                if (data.length) {
                    this.streamingContext.pushAudioBuffer(data);
                } else {
                    break;
                }
            }
        }
    }

    // 播放已缓冲的音频
    async playBufferedAudio() {
        try {
            this.audioContext = this.getAudioContext();

            if (!this.opusDecoder) {
                console.log('初始化 Opus 解码器...');
                try {
                    this.opusDecoder = await this.initOpusDecoder();
                    if (!this.opusDecoder) {
                        throw new Error('解码器初始化失败');
                    }
                    console.log("Opus 解码器初始化成功");
                } catch (error) {
                    console.error('Opus 解码器初始化失败：' + error.message);
                    this.isPlaying = false;
                    return;
                }
            }

            if (!this.streamingContext) {
                this.streamingContext = createStreamingContext(
                    this.opusDecoder,
                    this.audioContext,
                    this.SAMPLE_RATE,
                    this.CHANNELS,
                    this.MIN_AUDIO_DURATION
                );
            }

            this.streamingContext.decodeOpusFrames();
            this.streamingContext.startPlaying();

        } catch (error) {
            console.error(`播放已缓冲的音频出错：${error.message}`);
            this.isPlaying = false;
            this.streamingContext = null;
        }
    }

    // 添加音频数据到队列
    enqueueAudioData(opusData) {
        if (opusData.length > 0) {
            this.queue.enqueue(opusData);
        } else {
            console.warn('收到空音频数据帧，可能是结束标志');
            if (this.isPlaying && this.streamingContext) {
                this.streamingContext.endOfStream = true;
            }
        }
    }

    // 预加载解码器
    async preload() {
        console.log('预加载 Opus 解码器...');
        try {
            await this.initOpusDecoder();
            console.log('Opus 解码器预加载成功');
        } catch (error) {
            console.error(`Opus 解码器预加载失败：${error.message}，将在需要时重试`);
        }
    }

    // 启动播放系统
    async start() {
        await this.preload();
        this.playBufferedAudio();
        this.startAudioBuffering();
    }

    // 获取音频包统计信息
    getAudioStats() {
        if (!this.streamingContext) {
            return {
                pendingDecode: 0,
                pendingPlay: 0,
                totalPending: 0
            };
        }

        const pendingDecode = this.streamingContext.getPendingDecodeCount();
        const pendingPlay = this.streamingContext.getPendingPlayCount();

        return {
            pendingDecode,  // 待解码包数
            pendingPlay,    // 待播放包数
            totalPending: pendingDecode + pendingPlay  // 总待处理包数
        };
    }

    // 清空所有音频缓冲并停止播放
    clearAllAudio() {
        console.log('AudioPlayer: 清空所有音频');

        // 清空接收队列（使用clear方法保持对象引用）
        this.queue.clear();

        // 清空流上下文的所有缓冲
        if (this.streamingContext) {
            this.streamingContext.clearAllBuffers();
        }

        console.log('AudioPlayer: 音频已清空');
    }
}

// 创建单例
let audioPlayerInstance = null;

export function getAudioPlayer() {
    if (!audioPlayerInstance) {
        audioPlayerInstance = new AudioPlayer();
    }
    return audioPlayerInstance;
}
