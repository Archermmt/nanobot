<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { mdiImage, mdiFileUploadOutline, mdiChat, mdiStop } from '@mdi/js'

interface Props {
  disabled?: boolean
  isOnlineChatOn?: boolean
  enableASR?: boolean // Track if audio input handler is enabled
  msgHandlers?: string[]
}

const props = defineProps<Props>()
const emit = defineEmits(['upload-image', 'upload-audio', 'upload-file', 'recording-start'])

const imageInput = ref<HTMLInputElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isRecording = ref(false)
const showRecordingDialog = ref(false)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const audioContext = ref<AudioContext | null>(null)
const analyser = ref<AnalyserNode | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const animationFrameId = ref<number | null>(null)

const triggerImageUpload = () => {
  if (props.disabled) return
  imageInput.value?.click()
}

const triggerFileUpload = () => {
  if (props.disabled) return
  fileInput.value?.click()
}

const handleImageUpload = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      emit('upload-image', {
        data: e.target?.result as string,
        type: file.type,
        name: file.name
      })
    }
    reader.readAsDataURL(file)
  }
}

const handleFileUpload = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      emit('upload-file', {
        data: e.target?.result as string,
        type: file.type,
        name: file.name
      })
    }
    reader.readAsDataURL(file)
  }
}

const startRecording = async () => {
  if (props.disabled) return

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000,
        channelCount: 1
      }
    })
    mediaRecorder.value = new MediaRecorder(stream)
    audioChunks.value = []

    // Setup audio analysis for volume visualization
    audioContext.value = new (window.AudioContext || (window as any).webkitAudioContext)()
    analyser.value = audioContext.value.createAnalyser()
    analyser.value.fftSize = 256
    const source = audioContext.value.createMediaStreamSource(stream)
    source.connect(analyser.value)

    mediaRecorder.value.ondataavailable = (event) => {
      audioChunks.value.push(event.data)
    }

    mediaRecorder.value.onstop = () => {
      const audioBlob = new Blob(audioChunks.value, { type: 'audio/webm' })
      const reader = new FileReader()
      reader.onload = (e) => {
        // Emit audio data in the same format as image upload
        emit('upload-audio', {
          data: e.target?.result as string,
          type: 'audio/webm',
          name: `recording_${Date.now()}.webm`,
          isRecording: true
        })
      }
      reader.readAsDataURL(audioBlob)

      // Cleanup audio context
      if (animationFrameId.value) {
        cancelAnimationFrame(animationFrameId.value)
      }
      if (audioContext.value) {
        audioContext.value.close()
      }
    }

    mediaRecorder.value.start()
    isRecording.value = true
    showRecordingDialog.value = true
    emit('recording-start')

    // Wait for dialog to render, then start visualization
    await nextTick()
    setTimeout(() => {
      monitorVolume()
    }, 100)
  } catch (error) {
    console.error('Error accessing microphone:', error)
  }
}

const stopRecording = () => {
  if (mediaRecorder.value && isRecording.value) {
    mediaRecorder.value.stop()
    isRecording.value = false
    showRecordingDialog.value = false
    // Stop all tracks
    mediaRecorder.value.stream.getTracks().forEach(track => track.stop())
  }
}

const monitorVolume = () => {
  if (!analyser.value || !canvasRef.value) {
    console.log('Canvas or analyser not ready:', {
      analyser: !!analyser.value,
      canvas: !!canvasRef.value
    })
    return
  }

  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    console.log('Could not get 2D context')
    return
  }

  console.log('Starting linear spectrum visualization')
  console.log('Canvas size:', canvas.width, 'x', canvas.height)
  console.log('Analyser fftSize:', analyser.value.fftSize)

  const bufferLength = analyser.value.frequencyBinCount
  const dataArray = new Uint8Array(bufferLength)

  console.log('Buffer length:', bufferLength)

  const drawLinearSpectrum = () => {
    if (!analyser.value || !canvasRef.value) return

    analyser.value.getByteFrequencyData(dataArray)

    const width = canvas.width
    const height = canvas.height
    const centerY = height / 2

    // Clear canvas
    ctx.fillStyle = 'rgb(17, 24, 39)' // bg-gray-900
    ctx.fillRect(0, 0, width, height)

    // Draw center line
    ctx.strokeStyle = 'rgba(75, 85, 99, 0.5)' // gray-600 with opacity
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, centerY)
    ctx.lineTo(width, centerY)
    ctx.stroke()

    // Draw waveform from frequency data
    ctx.lineWidth = 2
    ctx.strokeStyle = '#ef4444' // red-500
    ctx.beginPath()

    const sliceWidth = width / bufferLength
    let x = 0

    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0
      const y = centerY + (v - 1) * (height / 2)

      if (i === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }

      x += sliceWidth
    }

    ctx.lineTo(canvas.width, centerY)
    ctx.stroke()

    animationFrameId.value = requestAnimationFrame(drawLinearSpectrum)
  }

  drawLinearSpectrum()
}

const handleDialogClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (target.classList.contains('recording-dialog-overlay')) {
    stopRecording()
  }
}

const hasASRHandler = () => props.msgHandlers?.includes('asr') || false

</script>

<template>
  <div class="flex items-center space-x-2">
    <!-- Image Upload -->
    <input ref="imageInput" type="file" accept="image/*" class="hidden" @change="handleImageUpload" />
    <button @click="triggerImageUpload" :disabled="props.disabled"
      class="nes-btn is-primary p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      title="Upload Image">
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path :d="mdiImage" />
      </svg>
    </button>

    <!-- File Upload -->
    <input ref="fileInput" type="file" class="hidden" @change="handleFileUpload" />
    <button @click="triggerFileUpload" :disabled="props.disabled"
      class="nes-btn is-primary p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      title="Upload File">
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path :d="mdiFileUploadOutline" />
      </svg>
    </button>

    <!-- Voice Recording -->
    <button @click="startRecording()" :disabled="props.disabled || isOnlineChatOn || !hasASRHandler()"
      class="nes-btn p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      :class="isRecording ? 'is-danger' : 'is-primary'" :title="isRecording ? '停止录音' : '开始录音'">
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path :d="isRecording ? mdiStop : mdiChat" />
      </svg>
    </button>

    <!-- Recording Dialog Overlay -->
    <div v-if="showRecordingDialog"
      class="recording-dialog-overlay fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      @click="handleDialogClick">
      <div class="bg-gray-800 border-4 border-gray-600 rounded-lg p-6 shadow-2xl text-center max-w-sm mx-4">
        <div class="mb-4">
          <svg class="w-16 h-16 mx-auto text-red-500 animate-pulse" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
            <path
              d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
          </svg>
        </div>
        <h3 class="text-white text-lg font-bold mb-2">正在录音...</h3>
        <p class="text-gray-400 text-xs mb-4">点击任意空白处停止录音</p>

        <!-- Linear Spectrum Visualizer -->
        <div class="bg-gray-900 rounded-lg p-4 mb-4">
          <canvas ref="canvasRef" width="400" height="100" class="w-full rounded"></canvas>
        </div>

        <button @click.stop="stopRecording()" class="nes-btn is-error w-full py-2">
          <svg class="btn-icon inline-block w-4 h-4 mr-2" viewBox="0 0 24 24" fill="currentColor">
            <path :d="mdiStop" />
          </svg>
          停止录音
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.recording-dialog-overlay {
  backdrop-filter: blur(2px);
}
</style>
