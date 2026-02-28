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

const sendMessage = () => {
  if (!input.value.trim() || props.isLoading || props.disabled) return
  emit('send', input.value)
  input.value = ''
}

const handleImageUpload = (imageData: string) => {
  emit('upload-image', imageData)
}

const handleAudioUpload = (audioData: { data: string; type: string; isRecording?: boolean }) => {
  emit('upload-audio', audioData)
}
</script>

<template>
  <div class="border-t bg-white p-4">
    <div class="flex items-center space-x-3">
      <!-- Media Upload Buttons -->
      <MediaUploader
        @upload-image="handleImageUpload"
        @upload-audio="handleAudioUpload"
      />

      <!-- Text Input -->
      <form @submit.prevent="sendMessage" class="flex-1 flex space-x-3">
        <input
          v-model="input"
          type="text"
          :placeholder="props.disabled ? '请先连接 WebSocket' : 'Type a message...'"
          class="flex-1 border border-gray-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-500"
          :disabled="isLoading || props.disabled"
        />
        <button
          type="submit"
          class="bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="isLoading || !input.trim() || props.disabled"
        >
          Send
        </button>
      </form>
    </div>
  </div>
</template>
