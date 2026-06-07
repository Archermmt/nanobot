// Type declarations for audioClipRecorder.js

export interface AudioClipRecorder {
    isRecording: boolean;
    audioContext: AudioContext | null;
    analyser: AnalyserNode | null;
    onRecordingStart: ((duration: number) => void) | null;
    onRecordingStop: (() => void) | null;
    onVisualizerUpdate: ((dataArray: Uint8Array) => void) | null;
    
    setWebSocket(ws: WebSocket, chatId: string, requestId: string): void;
    getAudioContext(): AudioContext;
    initEncoder(): any;
    createAudioProcessor(): Promise<{ node: AudioWorkletNode | ScriptProcessorNode; type: string } | null>;
    processPCMBuffer(buffer: Int16Array): void;
    encodeAndSendOpus(pcmData?: Int16Array): void;
    start(chatId: string, requestId: string): Promise<boolean>;
    stop(): boolean;
    getAnalyser(): AnalyserNode | null;
}

export function getAudioClipRecorder(): AudioClipRecorder;
