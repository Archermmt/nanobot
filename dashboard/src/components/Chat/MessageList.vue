<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'

// Configure marked options
marked.setOptions({
  breaks: true,
  gfm: true
})

interface MediaData {
  data: string
  file_name: string
}

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  imageUrl?: string
  audioUrl?: string
  media?: MediaData[]
  metadata?: {
    msg_type?: string
    file_type?: string
  }
}

interface Props {
  messages: Message[]
  isLoading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits(['play-audio', 'stop-audio'])

const messageContainer = ref<HTMLElement | null>(null)

const showThinking = computed(() => {
  // Show thinking only if loading and there are messages
  return props.isLoading && props.messages.length > 0
})

const currentAudio = ref<HTMLAudioElement | null>(null)
const expandedImages = ref<string[]>([])

// Extract image URL from media data
const getImageUrlFromMessage = (msg: Message): string | null => {
  if (msg.imageUrl) {
    return msg.imageUrl
  }
  if (msg.media && msg.media.length > 0) {
    // Check if this is an image message based on metadata
    const msgType = msg.metadata?.msg_type
    if (msgType === 'image' || msg.metadata?.file_type?.startsWith('image/')) {
      return msg.media[0]?.data || null
    }
  }
  return null
}

const toggleImageExpand = (imageUrl: string) => {
  const index = expandedImages.value.indexOf(imageUrl)
  if (index > -1) {
    expandedImages.value.splice(index, 1)
  } else {
    expandedImages.value.push(imageUrl)
  }
}

const playAudio = (audioUrl: string) => {
  if (currentAudio.value) {
    if (currentAudio.value.src === audioUrl && !currentAudio.value.paused) {
      currentAudio.value.pause()
      emit('stop-audio')
      return
    }
    currentAudio.value.pause()
  }

  currentAudio.value = new Audio(audioUrl)
  currentAudio.value.play()
  emit('play-audio', audioUrl)

  currentAudio.value.onended = () => {
    emit('stop-audio')
  }
}

const stopAudio = () => {
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value = null
  }
  emit('stop-audio')
}

const isPlaying = (audioUrl: string) => {
  return currentAudio.value?.src === audioUrl && !currentAudio.value?.paused
}

const isChineseContent = (content: string) => {
  // Check if content contains Chinese characters
  return /[\u4e00-\u9fa5]/.test(content);
}

const renderMarkdown = (content: string) => {
  return marked.parse(content)
}

// Auto scroll to bottom when messages change
const scrollToBottom = () => {
  nextTick(() => {
    if (messageContainer.value) {
      messageContainer.value.scrollTop = messageContainer.value.scrollHeight
    }
  })
}

// Watch for messages changes and scroll to bottom
watch(() => props.messages, scrollToBottom, { deep: true })
watch(() => props.isLoading, scrollToBottom)
</script>

<template>
  <div ref="messageContainer" class="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-900">
    <div v-for="(msg, index) in messages" :key="index" class="flex"
      :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
      <div class="max-w-[80%] border-2 rounded shadow-[4px_4px_0_rgba(0,0,0,0.5)] px-4 py-3" :class="{
        'bg-gradient-to-br from-blue-500 to-blue-600 border-blue-700 text-white': msg.role === 'user',
        'bg-gradient-to-br from-gray-100 to-gray-200 border-gray-300 text-gray-800': msg.role === 'assistant',
        'bg-gradient-to-br from-red-100 to-red-200 border-red-300 text-red-800': msg.role === 'system'
      }">
        <!-- Image Display -->
        <div v-if="getImageUrlFromMessage(msg)" class="mb-3">
          <!-- Collapsed state: display at actual size with max-width constraint -->
          <div v-if="!expandedImages.includes(getImageUrlFromMessage(msg)!)" 
            class="relative inline-block max-w-full">
            <img :src="getImageUrlFromMessage(msg)!" alt="Image"
              class="rounded border-2 cursor-pointer hover:opacity-90 transition-opacity max-w-full h-auto"
              style="max-width: 400px;"
              @click="toggleImageExpand(getImageUrlFromMessage(msg)!)" />
            <!-- Zoom hint -->
            <div class="absolute top-1 right-1 bg-black bg-opacity-50 text-white text-xs px-2 py-1 rounded opacity-0 hover:opacity-100 transition-opacity pointer-events-none">
              点击查看原图
            </div>
          </div>
          <!-- Expanded state: full screen overlay -->
          <div v-else class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90 p-8"
            @click="toggleImageExpand(getImageUrlFromMessage(msg)!)">
            <img :src="getImageUrlFromMessage(msg)!" alt="Image"
              class="max-w-full max-h-full object-contain cursor-pointer rounded" />
            <div class="absolute top-4 right-4 text-white text-sm bg-black bg-opacity-50 px-3 py-2 rounded">
              点击关闭
            </div>
          </div>
        </div>

        <!-- Audio Display -->
        <div v-if="msg.audioUrl" class="mb-3">
          <div class="flex items-center space-x-2">
            <button @click="isPlaying(msg.audioUrl!) ? stopAudio() : playAudio(msg.audioUrl!)"
              class="nes-btn is-primary">
              {{ isPlaying(msg.audioUrl!) ? '⏹️' : '▶️' }}
            </button>
            <span class="text-xs opacity-70">Voice message</span>
          </div>
        </div>

        <!-- Message Content -->
        <div class="prose prose-xs pixel-font markdown-content" :class="{ 'zh': isChineseContent(msg.content) }"
          v-html="renderMarkdown(msg.content)"></div>

        <!-- Timestamp -->
        <div class="text-xs mt-2 opacity-70">
          {{ new Date(msg.timestamp).toLocaleTimeString() }}
        </div>
      </div>
    </div>

    <!-- Loading Indicator -->
    <div v-if="showThinking" class="flex justify-start">
      <div
        class="bg-gradient-to-br from-gray-100 to-gray-200 border border-gray-300 rounded shadow-[4px_4px_0_rgba(0,0,0,0.5)] px-4 py-3">
        <div class="flex items-center space-x-2">
          <div class="text-xs text-gray-600">Thinking</div>
          <div class="flex space-x-1">
            <div class="w-2 h-2 bg-blue-500 rounded animate-bounce" style="animation-delay: 0ms"></div>
            <div class="w-2 h-2 bg-blue-500 rounded animate-bounce" style="animation-delay: 150ms"></div>
            <div class="w-2 h-2 bg-blue-500 rounded animate-bounce" style="animation-delay: 300ms"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
