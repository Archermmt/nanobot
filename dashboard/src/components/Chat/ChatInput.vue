<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import MediaUploader from '../Media/MediaUploader.vue'

interface Props {
  isLoading: boolean
  disabled?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits(['send', 'new-chat', 'clear-chat', 'upload-image', 'upload-audio', 'upload-file'])

const input = ref('')

const hasChineseCharacters = computed(() => {
  return /[\u4e00-\u9fa5]/.test(input.value);
})

const textareaRef = ref<HTMLTextAreaElement | null>(null)

const autoResize = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  target.style.height = 'auto'
  target.style.height = target.scrollHeight + 'px'
}

const resetTextareaHeight = async () => {
  await nextTick()
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = '48px'
  }
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
  resetTextareaHeight()
}

const handleNewChat = () => {
  emit('new-chat')
  input.value = ''
  resetTextareaHeight()
}

const handleClearChat = () => {
  emit('clear-chat')
  input.value = ''
  resetTextareaHeight()
}

const handleImageUpload = (imageData: string) => {
  emit('upload-image', imageData)
}

const handleAudioUpload = (audioData: { data: string; type: string; isRecording?: boolean }) => {
  emit('upload-audio', audioData)
}

const handleFileUpload = (fileData: { data: string; type: string; name: string }) => {
  emit('upload-file', fileData)
}
</script>

<template>
  <div class="border-t-4 border-gray-700 bg-gray-800 p-4">
    <div class="flex items-center space-x-3">
      <!-- Media Upload Buttons on the left of input -->
      <MediaUploader
        @upload-image="handleImageUpload"
        @upload-audio="handleAudioUpload"
        @upload-file="handleFileUpload"
      />

      <!-- Text Input -->
      <form id="message-form" @submit.prevent="sendMessage" class="flex-1 flex space-x-2">
        <textarea
          ref="textareaRef"
          v-model="input"
          :placeholder="props.disabled ? 'Please connect WebSocket first' : 'Type a message...'"
          class="flex-1 border-2 border-gray-600 rounded shadow-[inset_2px_2px_4px_rgba(0,0,0,0.3)] px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-700 disabled:text-gray-500 resize-none min-h-[48px] max-h-[200px] overflow-y-auto nes-input text-xs pixel-font"
          :class="{ 'zh': hasChineseCharacters }"
          :disabled="isLoading || props.disabled"
          rows="1"
          @input="autoResize"
          @keydown="handleKeydown"
        />
      </form>

      <!-- Action Buttons -->
      <div class="flex items-center space-x-2">
        <button
          type="submit"
          form="message-form"
          class="nes-btn is-primary px-4 py-2 rounded text-xs font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed uppercase"
          :disabled="isLoading || !input.trim() || props.disabled"
        >
          SEND
        </button>
        <button
          @click="handleNewChat"
          class="nes-btn is-success text-xs px-3 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="props.disabled"
          title="Start New Chat"
        >
          NEW
        </button>
        <button
          @click="handleClearChat"
          class="nes-btn is-error text-xs px-3 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="props.disabled"
          title="Clear Chat History"
        >
          CLEAR
        </button>
      </div>
    </div>
  </div>
</template>
