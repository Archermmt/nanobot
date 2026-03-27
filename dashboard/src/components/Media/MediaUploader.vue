<script setup lang="ts">
import { ref } from 'vue'
import { mdiImage, mdiFileUploadOutline, mdiChat, mdiStop } from '@mdi/js'

interface Props {
  disabled?: boolean
  isOnlineChatOn?: boolean
  enableASR?: boolean // Track if audio input handler is enabled
}

const props = defineProps<Props>()
const emit = defineEmits(['upload-image', 'upload-audio', 'upload-file', 'recording-start', 'recording-stop'])

const imageInput = ref<HTMLInputElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isRecording = ref(false)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])

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
    }

    mediaRecorder.value.start()
    isRecording.value = true
    emit('recording-start')
  } catch (error) {
    console.error('Error accessing microphone:', error)
  }
}

const stopRecording = () => {
  if (mediaRecorder.value && isRecording.value) {
    mediaRecorder.value.stop()
    isRecording.value = false
    emit('recording-stop')

    // Stop all tracks
    mediaRecorder.value.stream.getTracks().forEach(track => track.stop())
  }
}

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
    <button @click="isRecording ? stopRecording() : startRecording()" :disabled="props.disabled || isOnlineChatOn"
      class="nes-btn p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      :class="isRecording ? 'is-danger' : 'is-primary'" :title="isRecording ? '停止录音' : '开始录音'">
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path :d="isRecording ? mdiStop : mdiChat" />
      </svg>
    </button>
  </div>
</template>
