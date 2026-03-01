<script setup lang="ts">
import { ref } from 'vue'
import MediaUploader from '../Media/MediaUploader.vue'

interface Props {
  isLoading: boolean
  disabled?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits(['send', 'upload-image', 'upload-audio'])

const input = ref('')

const autoResize = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  target.style.height = 'auto'
  target.style.height = target.scrollHeight + 'px'
}

const handleKeydown = (event: KeyboardEvent) => {
  // Send on Enter, but only if Shift is NOT pressed
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

const sendMessage = () => {
  if (!input.value.trim() || props.isLoading || props.disabled) return
  emit('send', input.value)
  input.value = ''
  // Reset height after sending
  const textarea = document.querySelector('textarea')
  if (textarea) {
    textarea.style.height = 'auto'
  }
}

const handleImageUpload = (imageData: string) => {
  emit('upload-image', imageData)
}

const handleAudioUpload = (audioData: { data: string; type: string; isRecording?: boolean }) => {
  emit('upload-audio', audioData)
}
</script>

<template>
  <div class="border-t-4 border-gray-700 bg-gray-800 p-4">
    <div class="flex items-center space-x-3">
      <!-- Media Upload Buttons -->
      <MediaUploader
        @upload-image="handleImageUpload"
        @upload-audio="handleAudioUpload"
      />

      <!-- Text Input -->
      <form @submit.prevent="sendMessage" class="flex-1 flex flex-col space-y-2">
        <textarea
          v-model="input"
          :placeholder="props.disabled ? '请先连接 WebSocket' : '输入消息...'"
          class="flex-1 border-2 border-gray-600 rounded shadow-[inset_2px_2px_4px_rgba(0,0,0,0.3)] px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-700 disabled:text-gray-500 resize-none min-h-[48px] max-h-[200px] overflow-y-auto nes-input text-xs pixel-font"
          :disabled="isLoading || props.disabled"
          rows="1"
          @input="autoResize"
          @keydown="handleKeydown"
        />
        <div class="flex justify-end">
          <button
            type="submit"
            class="nes-btn is-primary px-6 py-2 rounded text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="isLoading || !input.trim() || props.disabled"
          >
            发送
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
