<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits(['upload-image', 'upload-audio', 'upload-file'])

const imageInput = ref<HTMLInputElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const audioInput = ref<HTMLInputElement | null>(null)
const isRecording = ref(false)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])

const triggerImageUpload = () => {
  imageInput.value?.click()
}

const triggerFileUpload = () => {
  fileInput.value?.click()
}

const triggerAudioUpload = () => {
  audioInput.value?.click()
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

const handleAudioUpload = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      emit('upload-audio', {
        data: e.target?.result as string,
        type: file.type
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
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder.value = new MediaRecorder(stream)
    audioChunks.value = []

    mediaRecorder.value.ondataavailable = (event) => {
      audioChunks.value.push(event.data)
    }

    mediaRecorder.value.onstop = () => {
      const audioBlob = new Blob(audioChunks.value, { type: 'audio/webm' })
      const reader = new FileReader()
      reader.onload = (e) => {
        emit('upload-audio', {
          data: e.target?.result as string,
          type: 'audio/webm',
          isRecording: true
        })
      }
      reader.readAsDataURL(audioBlob)
    }

    mediaRecorder.value.start()
    isRecording.value = true
  } catch (error) {
    console.error('Error accessing microphone:', error)
  }
}

const stopRecording = () => {
  if (mediaRecorder.value && isRecording.value) {
    mediaRecorder.value.stop()
    isRecording.value = false

    // Stop all tracks
    mediaRecorder.value.stream.getTracks().forEach(track => track.stop())
  }
}
</script>

<template>
  <div class="flex items-center space-x-2">
    <!-- Image Upload -->
    <input ref="imageInput" type="file" accept="image/*" class="hidden" @change="handleImageUpload" />
    <button @click="triggerImageUpload" class="nes-btn is-primary p-2 rounded transition-colors" title="Upload Image">
      📷
    </button>

    <!-- File Upload -->
    <input ref="fileInput" type="file" class="hidden" @change="handleFileUpload" />
    <button @click="triggerFileUpload" class="nes-btn is-primary p-2 rounded transition-colors" title="Upload File">
      📎
    </button>

    <!-- Voice Recording -->
    <button @click="isRecording ? stopRecording() : startRecording()" class="nes-btn"
      :class="isRecording ? 'is-danger' : 'is-primary'" :title="isRecording ? 'Stop Recording' : 'Start Recording'">
      {{ isRecording ? '⏹️' : '🎙️' }}
    </button>
  </div>
</template>
