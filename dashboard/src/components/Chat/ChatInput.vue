<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import MediaUploader from '../Media/MediaUploader.vue'
import { mdiSend, mdiMessagePlus, mdiDeleteSweep, mdiStopCircle } from '@mdi/js'

interface Props {
  isLoading: boolean
  disabled?: boolean
  isMicrophoneOn?: boolean
  messages?: Array<{ role: 'user' | 'assistant' | 'system'; content: string }>
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => []
})

const emit = defineEmits(['send', 'new-chat', 'clear-chat', 'stop-chat', 'upload-image', 'upload-audio', 'upload-file'])

interface PendingMedia {
  data: string
  type: string
  name: string
  preview?: string
}

const input = ref('')
const historyIndex = ref(-1)
const originalInput = ref('')
const pendingImages = ref<PendingMedia[]>([])
const pendingFiles = ref<PendingMedia[]>([])
const userHistoryMessages = ref<string[]>([])

const hasChineseCharacters = computed(() => {
  return /[\u4e00-\u9fa5]/.test(input.value);
})

// Use userHistoryMessages ref directly instead of computed from props
const userHistory = computed(() => {
  return userHistoryMessages.value.slice().reverse()
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

const handleUpdateUserHistory = (messages: string[]) => {
  userHistoryMessages.value = messages
}

const handleKeydown = (event: KeyboardEvent) => {
  // Handle Up Arrow - show previous message in history
  if (event.key === 'ArrowUp' && !event.ctrlKey && !event.metaKey) {
    event.preventDefault()

    // Save current input before navigating
    if (historyIndex.value === -1 && input.value.trim()) {
      originalInput.value = input.value
    }

    if (userHistory.value.length > 0) {
      const newIndex = historyIndex.value + 1
      if (newIndex < userHistory.value.length) {
        historyIndex.value = newIndex
        input.value = userHistory.value[historyIndex.value]
      }
    }
    return
  }

  // Handle Down Arrow - show next message in history
  if (event.key === 'ArrowDown' && !event.ctrlKey && !event.metaKey) {
    event.preventDefault()

    if (historyIndex.value > 0) {
      historyIndex.value--
      input.value = userHistory.value[historyIndex.value]
    } else if (historyIndex.value === 0) {
      // Reset to original input or empty
      historyIndex.value = -1
      input.value = originalInput.value || ''
      originalInput.value = ''
    }
    return
  }

  // Send on Enter, but only if Shift is NOT pressed and user is not composing text (e.g., Chinese input method)
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    sendMessage()
  }
}

const sendMessage = () => {
  if ((!input.value.trim() && pendingImages.value.length === 0 && pendingFiles.value.length === 0) || props.isLoading || props.disabled) return

  // Send text, images and files together
  emit('send', {
    text: input.value,
    images: pendingImages.value,
    files: pendingFiles.value
  })

  // Clear inputs
  input.value = ''
  pendingImages.value = []
  pendingFiles.value = []

  // Reset history navigation
  historyIndex.value = -1
  originalInput.value = ''

  // Reset height after sending
  resetTextareaHeight()
}

const handleNewChat = () => {
  emit('new-chat')
  input.value = ''
  pendingImages.value = []
  pendingFiles.value = []
  historyIndex.value = -1
  originalInput.value = ''
  resetTextareaHeight()
}

const handleClearChat = () => {
  emit('clear-chat')
  input.value = ''
  pendingImages.value = []
  pendingFiles.value = []
  historyIndex.value = -1
  originalInput.value = ''
  resetTextareaHeight()
}

const handleStopChat = () => {
  // Send /stop command to backend
  emit('send', {
    text: '/stop',
    images: [],
    files: []
  })
}

const handleImageUpload = (imageData: { data: string; type: string; name: string }) => {
  // Add to pending images instead of sending immediately
  pendingImages.value.push({
    ...imageData,
    preview: imageData.data // For base64 images, use as preview
  })
}

const handleAudioUpload = (audioData: { data: string; type: string; isRecording?: boolean }) => {
  emit('upload-audio', audioData)
}

const handleFileUpload = (fileData: { data: string; type: string; name: string }) => {
  // Add to pending files instead of sending immediately
  pendingFiles.value.push(fileData)
}

const removePendingImage = (index: number) => {
  pendingImages.value.splice(index, 1)
}

const removePendingFile = (index: number) => {
  pendingFiles.value.splice(index, 1)
}

// Expose method for updating user history and the history messages themselves
defineExpose({
  handleUpdateUserHistory,
  userHistoryMessages
})
</script>

<template>
  <div class="border-t-4 border-gray-700 bg-gray-800 p-4">
    <div class="flex items-center space-x-3">
      <!-- Media Upload Buttons on the left of input -->
      <MediaUploader :disabled="props.disabled || isLoading" :is-microphone-on="props.isMicrophoneOn"
        @upload-image="handleImageUpload" @upload-audio="handleAudioUpload" @upload-file="handleFileUpload" />

      <!-- Text Input -->
      <form id="message-form" @submit.prevent="sendMessage" class="flex-1 flex flex-col space-y-2">
        <!-- Pending Images Display -->
        <div v-if="pendingImages.length > 0" class="flex flex-wrap gap-2">
          <div v-for="(img, index) in pendingImages" :key="index" class="relative group">
            <img :src="img.preview" :alt="img.name" class="h-20 w-auto rounded border-2 border-gray-600" />
            <button type="button" @click="removePendingImage(index)"
              class="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-red-600"
              title="Remove image">
              ×
            </button>
          </div>
        </div>

        <!-- Pending Files Display -->
        <div v-if="pendingFiles.length > 0" class="flex flex-wrap gap-2">
          <div v-for="(file, index) in pendingFiles" :key="index"
            class="flex items-center gap-2 bg-gray-700 px-3 py-2 rounded border-2 border-gray-600">
            <span class="text-xs text-gray-300 truncate max-w-[150px]">{{ file.name }}</span>
            <button type="button" @click="removePendingFile(index)"
              class="bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-red-600"
              title="Remove file">
              ×
            </button>
          </div>
        </div>

        <!-- Textarea -->
        <textarea ref="textareaRef" v-model="input"
          :placeholder="props.disabled ? 'Please connect WebSocket first' : 'Type a message... (or attach images/files above)'"
          class="flex-1 border-2 border-gray-600 rounded shadow-[inset_2px_2px_4px_rgba(0,0,0,0.3)] px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-700 disabled:text-gray-500 resize-none min-h-[48px] max-h-[200px] overflow-y-auto nes-input text-xs chat-input-textarea zh"
          :disabled="isLoading || props.disabled" rows="1" @input="autoResize" @keydown="handleKeydown" />
      </form>

      <!-- Action Buttons -->
      <div class="flex items-center space-x-2">
        <button type="submit" form="message-form"
          class="nes-btn is-primary p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="isLoading || (!input.trim() && pendingImages.length === 0 && pendingFiles.length === 0) || props.disabled">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
            <path :d="mdiSend" />
          </svg>
        </button>
        <button @click="handleNewChat"
          class="nes-btn is-success p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="props.disabled || isLoading" title="Start New Chat">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
            <path :d="mdiMessagePlus" />
          </svg>
        </button>
        <button @click="handleClearChat"
          class="nes-btn is-warning p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="props.disabled || isLoading" title="Clear Chat History">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
            <path :d="mdiDeleteSweep" />
          </svg>
        </button>
        <button @click="handleStopChat"
          class="nes-btn is-error p-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="props.disabled || !isLoading" title="Stop Current Chat">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
            <path :d="mdiStopCircle" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
