<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'

// Configure marked options
marked.setOptions({
  breaks: true,
  gfm: true
})

interface MediaData {
  data?: string
  file_name?: string
  file_path?: string
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
    _progress?: boolean
    _response_for?: string
    mode_hint?: string
  }
}

interface Props {
  messages: Message[]
  isLoading: boolean
  showProgressMessages?: boolean
  playingAudioUrl?: string | null
}

const props = defineProps<Props>()
const emit = defineEmits(['play-audio', 'stop-audio'])

const messageContainer = ref<HTMLElement | null>(null)

const showThinking = computed(() => {
  // Show thinking if isLoading is true and there are messages
  // OR if the last message has _progress: true in metadata
  if (props.messages.length === 0) return false

  const lastMessage = props.messages[props.messages.length - 1]
  const hasProgressFlag = lastMessage.metadata?._progress === true

  // Always show thinking when loading
  if (props.isLoading && props.messages.length > 0) return true

  // When not loading, only show progress messages if showProgressMessages is enabled
  if (hasProgressFlag) {
    return props.showProgressMessages !== false
  }

  return false
})

const currentAudio = ref<HTMLAudioElement | null>(null)
const expandedImages = ref<string[]>([])
const currentModeHint = ref<string | null>(null)
const imageZoomLevels = ref<Record<string, number>>({})
const imagePositions = ref<Record<string, { x: number; y: number }>>({})
const isDragging = ref(false)
const dragStart = ref<{ x: number; y: number } | null>(null)
const lastTouchDistance = ref<number | null>(null)

// Extract image URL from media data
const getImageUrlFromMessage = (msg: Message): string | null => {
  if (msg.imageUrl) {
    return msg.imageUrl
  }
  if (msg.media && msg.media.length > 0) {
    // Check if this is an image message based on metadata
    const msgType = msg.metadata?.msg_type
    if (msgType === 'image' || msg.metadata?.file_type?.startsWith('image/')) {
      // For SVG files, use file_path directly
      if ('file_path' in msg.media[0] && msg.media[0].file_path) {
        return msg.media[0].file_path as string
      }
      // For other images, use data
      return msg.media[0]?.data || null
    }
  }
  return null
}

const toggleImageExpand = (imageUrl: string) => {
  const index = expandedImages.value.indexOf(imageUrl)
  if (index > -1) {
    expandedImages.value.splice(index, 1)
    // Reset zoom level when collapsing
    delete imageZoomLevels.value[imageUrl]
  } else {
    expandedImages.value.push(imageUrl)
    // Initialize zoom level to 1 when expanding
    imageZoomLevels.value[imageUrl] = 1
  }
}

const zoomImageIn = (imageUrl: string, event: Event) => {
  event.stopPropagation()
  if (!imageZoomLevels.value[imageUrl]) {
    imageZoomLevels.value[imageUrl] = 1
  }
  imageZoomLevels.value[imageUrl] = Math.min(imageZoomLevels.value[imageUrl] + 0.25, 3)
}

const zoomImageOut = (imageUrl: string, event: Event) => {
  event.stopPropagation()
  if (!imageZoomLevels.value[imageUrl]) {
    imageZoomLevels.value[imageUrl] = 1
  }
  imageZoomLevels.value[imageUrl] = Math.max(imageZoomLevels.value[imageUrl] - 0.25, 0.5)
}

const resetImageZoom = (imageUrl: string, event: Event) => {
  event.stopPropagation()
  imageZoomLevels.value[imageUrl] = 1
}

const getImageZoom = (imageUrl: string) => {
  return imageZoomLevels.value[imageUrl] || 1
}

const getImagePosition = (imageUrl: string) => {
  return imagePositions.value[imageUrl] || { x: 0, y: 0 }
}

// Mouse wheel zoom
const handleWheel = (imageUrl: string, event: WheelEvent) => {
  event.stopPropagation()
  event.preventDefault()

  if (!imageZoomLevels.value[imageUrl]) {
    imageZoomLevels.value[imageUrl] = 1
  }

  // Scroll up (negative deltaY) zooms in, scroll down (positive deltaY) zooms out
  const delta = event.deltaY > 0 ? 0.05 : -0.05
  const newZoom = Math.min(Math.max(imageZoomLevels.value[imageUrl] + delta, 0.5), 3)
  imageZoomLevels.value[imageUrl] = newZoom
}

// Mouse drag start
const handleDragStart = (imageUrl: string, event: MouseEvent) => {
  if (event.button !== 0) return // Only left click
  event.stopPropagation()
  event.preventDefault()

  isDragging.value = true
  dragStart.value = { x: event.clientX, y: event.clientY }

  if (!imagePositions.value[imageUrl]) {
    imagePositions.value[imageUrl] = { x: 0, y: 0 }
  }

  document.addEventListener('mousemove', handleDragMove)
  document.addEventListener('mouseup', handleDragEnd)
}

// Mouse drag move
const handleDragMove = (event: MouseEvent) => {
  if (!isDragging.value || !dragStart.value) return

  const dx = event.clientX - dragStart.value.x
  const dy = event.clientY - dragStart.value.y

  const imageUrl = expandedImages.value[expandedImages.value.length - 1]
  if (imageUrl && imagePositions.value[imageUrl]) {
    imagePositions.value[imageUrl].x += dx
    imagePositions.value[imageUrl].y += dy
  }

  dragStart.value = { x: event.clientX, y: event.clientY }
}

// Mouse drag end
const handleDragEnd = () => {
  isDragging.value = false
  dragStart.value = null
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
}

// Touch events for pinch-to-zoom
const handleTouchStart = (imageUrl: string, event: TouchEvent) => {
  if (event.touches.length === 2) {
    event.stopPropagation()
    lastTouchDistance.value = getTouchDistance(event.touches)
  }
}

const handleTouchMove = (imageUrl: string, event: TouchEvent) => {
  if (event.touches.length === 2 && lastTouchDistance.value !== null) {
    event.stopPropagation()
    event.preventDefault()

    const distance = getTouchDistance(event.touches)
    const delta = distance - lastTouchDistance.value

    if (!imageZoomLevels.value[imageUrl]) {
      imageZoomLevels.value[imageUrl] = 1
    }

    // Pinch out (increasing distance) zooms in, pinch in (decreasing distance) zooms out
    const zoomSensitivity = 0.005
    const newZoom = Math.min(Math.max(imageZoomLevels.value[imageUrl] + delta * zoomSensitivity, 0.5), 3)
    imageZoomLevels.value[imageUrl] = newZoom
    lastTouchDistance.value = distance
  }
}

const handleTouchEnd = (imageUrl: string, event: TouchEvent) => {
  lastTouchDistance.value = null
}

const getTouchDistance = (touches: TouchList) => {
  const dx = touches[0].clientX - touches[1].clientX
  const dy = touches[0].clientY - touches[1].clientY
  return Math.sqrt(dx * dx + dy * dy)
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
  return props.playingAudioUrl === audioUrl
}

const isChineseContent = (content: string) => {
  // Check if content contains Chinese characters
  return /[\u4e00-\u9fa5]/.test(content);
}

const renderMarkdown = (content: string) => {
  return marked.parse(content)
}

// Filter messages based on showProgressMessages prop
const visibleMessages = computed(() => {
  // Filter messages based on showProgressMessages prop
  if (props.showProgressMessages !== false) {
    // Show all messages including_progress messages
    props.messages.forEach(msg => {
      // Cache mode_hint from messages
      if (msg.metadata?.mode_hint) {
        currentModeHint.value = msg.metadata.mode_hint
      }
    })
    return props.messages.filter(msg => !msg.metadata?.mode_hint)
  } else {
    // Hide messages with _progress: true in metadata
    props.messages.forEach(msg => {
      // Cache mode_hint from messages (even progress messages)
      if (msg.metadata?.mode_hint) {
        currentModeHint.value = msg.metadata.mode_hint
      }
    })
    return props.messages.filter(msg => !msg.metadata?._progress && !msg.metadata?.mode_hint)
  }
})

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
watch(() => props.showProgressMessages, scrollToBottom)
</script>

<template>
  <div ref="messageContainer" class="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-900">
    <div v-for="(msg, index) in visibleMessages" :key="index" class="flex"
      :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
      <div class="border-2 rounded shadow-[4px_4px_0_rgba(0,0,0,0.5)] px-4 py-3 flex flex-col" :class="{
        'bg-gradient-to-br from-blue-500 to-blue-600 border-blue-700 text-white max-w-[80%]': msg.role === 'user',
        'bg-gradient-to-br from-gray-100 to-gray-200 border-gray-300 text-gray-800 max-w-[80%]': msg.role === 'assistant' && !msg.metadata?._progress && msg.metadata?._response_for !== 'status',
        'bg-gradient-to-br from-green-100 to-green-200 border-green-300 text-gray-700 max-w-[80%]': msg.role === 'assistant' && msg.metadata?._progress,
        'bg-gradient-to-br from-red-100 to-red-200 border-red-300 text-red-800 max-w-[80%]': msg.role === 'system',
        'bg-gradient-to-br from-yellow-100 to-yellow-200 border-yellow-300 text-gray-700 max-w-[80%]': msg.metadata?._response_for === 'status'
      }">
        <!-- Image Display -->
        <div v-if="getImageUrlFromMessage(msg)" class="mb-3 w-full">
          <!-- Collapsed state: display at actual size with max-width constraint -->
          <div v-if="!expandedImages.includes(getImageUrlFromMessage(msg)!)" class="relative inline-block max-w-full">
            <img :src="getImageUrlFromMessage(msg)!" alt="Image"
              class="rounded border-2 cursor-pointer hover:opacity-90 transition-opacity max-w-full h-auto"
              style="max-width: 400px;" @click="toggleImageExpand(getImageUrlFromMessage(msg)!)" />
            <!-- Zoom hint -->
            <div
              class="absolute top-1 right-1 bg-black bg-opacity-50 text-white text-xs px-2 py-1 rounded opacity-0 hover:opacity-100 transition-opacity pointer-events-none">
              点击查看原图
            </div>
          </div>
          <!-- Expanded state: full screen overlay with zoom controls -->
          <div v-else class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90 p-8"
            @click="toggleImageExpand(getImageUrlFromMessage(msg)!)"
            @wheel="handleWheel(getImageUrlFromMessage(msg)!, $event)">
            <div class="relative flex items-center justify-center max-w-full max-h-full">
              <img :src="getImageUrlFromMessage(msg)!" alt="Image"
                class="max-w-full max-h-full cursor-grab rounded transition-transform duration-200 ease-out"
                :class="{ 'cursor-grabbing': isDragging }" :style="{
                  transform: `scale(${getImageZoom(getImageUrlFromMessage(msg)!)}) translate(${getImagePosition(getImageUrlFromMessage(msg)!).x}px, ${getImagePosition(getImageUrlFromMessage(msg)!).y}px)`
                }" @mousedown="handleDragStart(getImageUrlFromMessage(msg)!, $event)"
                @touchstart="handleTouchStart(getImageUrlFromMessage(msg)!, $event)"
                @touchmove="handleTouchMove(getImageUrlFromMessage(msg)!, $event)"
                @touchend="handleTouchEnd(getImageUrlFromMessage(msg)!, $event)" @click.stop />
              <!-- Zoom controls -->
              <div
                class="absolute bottom-4 left-1/2 transform -translate-x-1/2 flex items-center space-x-2 bg-black bg-opacity-70 px-4 py-2 rounded-lg"
                @click.stop>
                <button @click="zoomImageOut(getImageUrlFromMessage(msg)!, $event)"
                  class="nes-btn is-primary text-white bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded" title="缩小 (-)">
                  🔍−
                </button>
                <span class="text-white text-sm min-w-[60px] text-center">
                  {{ Math.round(getImageZoom(getImageUrlFromMessage(msg)!) * 100) }}%
                </span>
                <button @click="zoomImageIn(getImageUrlFromMessage(msg)!, $event)"
                  class="nes-btn is-primary text-white bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded" title="放大 (+)">
                  🔍+
                </button>
                <button @click="resetImageZoom(getImageUrlFromMessage(msg)!, $event)"
                  class="nes-btn text-white bg-gray-600 hover:bg-gray-700 px-3 py-1 rounded ml-2" title="重置 (R)">
                  🔄
                </button>
              </div>
              <!-- Close hint -->
              <div class="absolute top-4 right-4 text-white text-sm bg-black bg-opacity-50 px-3 py-2 rounded">
                点击背景关闭 · 滚轮/双指缩放 · 拖拽移动
              </div>
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
            <span class="text-xs opacity-70">{{ isPlaying(msg.audioUrl!) ? '播放中...' : '语音消息' }}</span>
          </div>
        </div>

        <!-- Message Content -->
        <div class="prose prose-xs markdown-content" :class="isChineseContent(msg.content) ? 'zh' : 'pixel-font'"
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
        class="bg-gradient-to-br from-yellow-100 to-yellow-200 border border-yellow-300 rounded shadow-[4px_4px_0_rgba(0,0,0,0.5)] px-4 py-3">
        <div class="flex items-center space-x-2">
          <div class="text-xs text-yellow-800">
            Thinking<span v-if="currentModeHint">({{ currentModeHint }})</span>
          </div>
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
