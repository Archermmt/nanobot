// Audio clip recording module for streaming transcription
import { initOpusEncoder } from './opus-codec.js';

// Audio clip recorder class for streaming mode
export class AudioClipRecorder {
    constructor() {
        this.isRecording = false;
        this.audioContext = null;
        this.analyser = null;
        this.audioProcessor = null;
        this.audioProcessorType = null;
        this.audioSource = null;
        this.opusEncoder = null;
        this.pcmDataBuffer = new Int16Array();
        this.onChunk = null;
        // Callback functions
        this.onRecordingStart = null;
        this.onRecordingStop = null;
        this.onVisualizerUpdate = null;
    }

    // Set the per-chunk sender. Receives base64-encoded Opus payload.
    setChunkHandler(onChunk) {
        this.onChunk = onChunk;
    }

    // Get AudioContext instance
    getAudioContext() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });
        }
        return this.audioContext;
    }

    // Initialize encoder
    async initEncoder() {
        if (!this.opusEncoder) {
            this.opusEncoder = await initOpusEncoder();
        }
        return this.opusEncoder;
    }

    // PCM processor code for AudioWorklet
    getAudioProcessorCode() {
        return `
            class AudioClipProcessor extends AudioWorkletProcessor {
                constructor() {
                    super();
                    this.buffers = [];
                    this.frameSize = 960;
                    this.buffer = new Int16Array(this.frameSize);
                    this.bufferIndex = 0;
                    this.isRecording = false;
                    this.port.onmessage = (event) => {
                        if (event.data.command === 'start') {
                            this.isRecording = true;
                            this.port.postMessage({ type: 'status', status: 'started' });
                        } else if (event.data.command === 'stop') {
                            this.isRecording = false;
                            if (this.bufferIndex > 0) {
                                const finalBuffer = this.buffer.slice(0, this.bufferIndex);
                                this.port.postMessage({ type: 'buffer', buffer: finalBuffer });
                                this.bufferIndex = 0;
                            }
                            this.port.postMessage({ type: 'status', status: 'stopped' });
                        }
                    };
                }
                process(inputs, outputs, parameters) {
                    if (!this.isRecording) return true;
                    const input = inputs[0][0];
                    if (!input) return true;
                    for (let i = 0; i < input.length; i++) {
                        if (this.bufferIndex >= this.frameSize) {
                            this.port.postMessage({ type: 'buffer', buffer: this.buffer.slice(0) });
                            this.bufferIndex = 0;
                        }
                        this.buffer[this.bufferIndex++] = Math.max(-32768, Math.min(32767, Math.floor(input[i] * 32767)));
                    }
                    return true;
                }
            }
            registerProcessor('audio-clip-processor', AudioClipProcessor);
        `;
    }

    // Create audio processor
    async createAudioProcessor() {
        this.audioContext = this.getAudioContext();
        try {
            if (this.audioContext.audioWorklet) {
                const blob = new Blob([this.getAudioProcessorCode()], { type: 'application/javascript' });
                const url = URL.createObjectURL(blob);
                await this.audioContext.audioWorklet.addModule(url);
                URL.revokeObjectURL(url);
                const audioProcessor = new AudioWorkletNode(this.audioContext, 'audio-clip-processor');
                audioProcessor.port.onmessage = (event) => {
                    if (event.data.type === 'buffer') {
                        this.processPCMBuffer(event.data.buffer);
                    }
                };
                console.log('Using AudioWorklet for audio clip processing');
                const silent = this.audioContext.createGain();
                silent.gain.value = 0;
                audioProcessor.connect(silent);
                silent.connect(this.audioContext.destination);
                return { node: audioProcessor, type: 'worklet' };
            } else {
                console.warn('AudioWorklet not available, using ScriptProcessorNode as fallback');
                return this.createScriptProcessor();
            }
        } catch (error) {
            console.error(`Failed to create audio processor: ${error.message}, trying fallback`);
            return this.createScriptProcessor();
        }
    }

    // Create ScriptProcessor as fallback
    createScriptProcessor() {
        try {
            const frameSize = 4096;
            const scriptProcessor = this.audioContext.createScriptProcessor(frameSize, 1, 1);
            scriptProcessor.onaudioprocess = (event) => {
                if (!this.isRecording) return;
                const input = event.inputBuffer.getChannelData(0);
                const buffer = new Int16Array(input.length);
                for (let i = 0; i < input.length; i++) {
                    buffer[i] = Math.max(-32768, Math.min(32767, Math.floor(input[i] * 32767)));
                }
                this.processPCMBuffer(buffer);
            };
            const silent = this.audioContext.createGain();
            silent.gain.value = 0;
            scriptProcessor.connect(silent);
            silent.connect(this.audioContext.destination);
            console.warn('Using ScriptProcessorNode as fallback successfully');
            return { node: scriptProcessor, type: 'processor' };
        } catch (fallbackError) {
            console.error(`Fallback also failed: ${fallbackError.message}`);
            return null;
        }
    }

    // Process PCM buffer data
    processPCMBuffer(buffer) {
        if (!this.isRecording) return;
        const newBuffer = new Int16Array(this.pcmDataBuffer.length + buffer.length);
        newBuffer.set(this.pcmDataBuffer);
        newBuffer.set(buffer, this.pcmDataBuffer.length);
        this.pcmDataBuffer = newBuffer;
        const samplesPerFrame = 960;
        let frameCount = 0;
        while (this.pcmDataBuffer.length >= samplesPerFrame) {
            const frameData = this.pcmDataBuffer.slice(0, samplesPerFrame);
            this.pcmDataBuffer = this.pcmDataBuffer.slice(samplesPerFrame);
            frameCount++;
            this.encodeAndSendOpus(frameData);
        }
        if (frameCount > 0) {
            // Frames processed
        }
    }

    // Encode and emit Opus chunk via the onChunk callback
    encodeAndSendOpus(pcmData = null) {
        if (!this.opusEncoder) {
            return;
        }
        try {
            if (pcmData) {
                const opusData = this.opusEncoder.encode(pcmData);
                if (opusData && opusData.length > 0) {
                    if (typeof this.onChunk === 'function') {
                        try {
                            const base64Data = btoa(String.fromCharCode(...opusData));
                            this.onChunk(base64Data);
                        } catch (error) {
                            console.error(`Chunk dispatch error: ${error.message}`);
                        }
                    }
                }
            }
        } catch (error) {
            console.error(`Opus encoding error: ${error.message}`);
        }
    }

    // Start recording
    async start() {
        if (this.isRecording) return false;
        try {
            const encoder = await this.initEncoder();
            if (!encoder) {
                console.error('Cannot start recording: Opus encoder initialization failed');
                return false;
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { 
                    echoCancellation: true, 
                    noiseSuppression: true, 
                    sampleRate: 16000, 
                    channelCount: 1 
                } 
            });
            
            this.audioContext = this.getAudioContext();
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            const processorResult = await this.createAudioProcessor();
            if (!processorResult) {
                console.error('Cannot create audio processor');
                return false;
            }
            
            this.audioProcessor = processorResult.node;
            this.audioProcessorType = processorResult.type;
            this.audioSource = this.audioContext.createMediaStreamSource(stream);
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 2048;
            this.audioSource.connect(this.analyser);
            this.audioSource.connect(this.audioProcessor);
            this.pcmDataBuffer = new Int16Array();
            this.isRecording = true;
            
            if (this.audioProcessorType === 'worklet' && this.audioProcessor.port) {
                this.audioProcessor.port.postMessage({ command: 'start' });
            }
            
            // Start visualization
            if (this.onVisualizerUpdate) {
                const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
                this.startVisualization(dataArray);
            }
            
            // Notify recording start
            if (this.onRecordingStart) {
                this.onRecordingStart(0);
            }
            
            console.log('Started PCM streaming recording');
            return true;
        } catch (error) {
            console.error(`Streaming recording start error: ${error.message}`);
            this.isRecording = false;
            return false;
        }
    }

    // Start visualization
    startVisualization(dataArray) {
        const draw = () => {
            this.visualizationRequest = requestAnimationFrame(() => draw());
            if (!this.isRecording) return;
            this.analyser.getByteFrequencyData(dataArray);
            if (this.onVisualizerUpdate) {
                this.onVisualizerUpdate(dataArray);
            }
        };
        draw();
    }

    // Stop recording
    stop() {
        if (!this.isRecording) return false;
        try {
            this.isRecording = false;
            if (this.audioProcessor) {
                if (this.audioProcessorType === 'worklet' && this.audioProcessor.port) {
                    this.audioProcessor.port.postMessage({ command: 'stop' });
                }
                this.audioProcessor.disconnect();
                this.audioProcessor = null;
            }
            if (this.audioSource) {
                this.audioSource.disconnect();
                this.audioSource = null;
            }
            if (this.visualizationRequest) {
                cancelAnimationFrame(this.visualizationRequest);
                this.visualizationRequest = null;
            }

            // Encode and send remaining data
            this.encodeAndSendOpus();

            if (this.onRecordingStop) {
                this.onRecordingStop();
            }

            console.log('Stopped PCM streaming recording');
            return true;
        } catch (error) {
            console.error(`Streaming recording stop error: ${error.message}`);
            return false;
        }
    }

    // Get analyser
    getAnalyser() {
        return this.analyser;
    }
}

// Create singleton instance
let audioClipRecorderInstance = null;

export function getAudioClipRecorder() {
    if (!audioClipRecorderInstance) {
        audioClipRecorderInstance = new AudioClipRecorder();
    }
    return audioClipRecorderInstance;
}
