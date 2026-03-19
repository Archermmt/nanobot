declare module 'opus-decoder' {
  export interface DecodedFrame {
    channelData: Float32Array[]  // Array of channels (left, right for stereo)
    samplesDecoded: number
    sampleRate: number
  }

  export class OpusDecoder {
    ready: Promise<void>  // Promise that resolves when WASM is compiled
    constructor(sampleRate?: number, channels?: number)
    decodeFrame(data: Uint8Array): DecodedFrame | null
    reset(): Promise<void>
    free(): void
  }
}
