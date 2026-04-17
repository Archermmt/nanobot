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
  videoUrl?: string
  htmlContent?: string
  media?: MediaData[]
  metadata?: {
    msg_type?: string
    file_type?: string
    _progress?: boolean
    _cmd_ref?: string
    _mode_hint?: string
    _tool_hint?: string
    isPlayingOpus?: boolean
    isVideoPlaying?: boolean
    _as_input?: boolean
    _warning_msg?: string
  }
}

interface Props {
  messages: Message[]
  chatState: string
  showProgressMessages?: boolean
  playingAudioUrl?: string | null
}

const props = defineProps<Props>()
const emit = defineEmits(['play-audio', 'stop-audio', 'play-video', 'stop-video', 'show-html'])

// Expose method to expand image programmatically
const expandImage = (imageUrl: string) => {
  if (!expandedImages.value.includes(imageUrl)) {
    expandedImages.value.push(imageUrl)
    // Initialize zoom level to 1
    imageZoomLevels.value[imageUrl] = 1
  }
}

// Expose methods to parent component
defineExpose({
  expandImage
})

const messageContainer = ref<HTMLElement | null>(null)
const currentAudio = ref<HTMLAudioElement | null>(null)
const expandedImages = ref<string[]>([])
const expandedVideos = ref<string[]>([])
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

// Extract video URL from media data
const getVideoUrlFromMessage = (msg: Message): string | null => {
  if (msg.videoUrl) {
    return msg.videoUrl
  }
  if (msg.media && msg.media.length > 0) {
    const msgType = msg.metadata?.msg_type
    if (msgType === 'video' || msg.metadata?.file_type?.startsWith('video/')) {
      // Use data or file_path for video
      if ('file_path' in msg.media[0] && msg.media[0].file_path) {
        return msg.media[0].file_path as string
      }
      return msg.media[0]?.data || null
    }
  }
  return null
}

const toggleVideoExpand = (videoUrl: string) => {
  const index = expandedVideos.value.indexOf(videoUrl)
  if (index > -1) {
    expandedVideos.value.splice(index, 1)
    // Stop video when collapsing
    emit('stop-video')
  } else {
    expandedVideos.value.push(videoUrl)
    // Play video when expanding
    emit('play-video', videoUrl)
  }
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
  // Clear the playing audio URL state to update UI
  emit('stop-audio')
}

const isPlaying = (audioUrl: string) => {
  return props.playingAudioUrl === audioUrl
}

const renderMarkdown = (content: string) => {
  return marked.parse(content)
}

// Filter messages based on showProgressMessages prop
const visibleMessages = computed(() => {
  const filterMessages = (messages: Message[]) => {
    // Find the first message without _tool_hint in metadata
    let firstNonToolHintIndex = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (!messages[i].metadata?._tool_hint) {
        firstNonToolHintIndex = i
        break
      }
    }

    return messages.filter((msg, index) => {
      // Skip duplicate warning messages with same _warning_msg
      if (msg.metadata?._warning_msg && index > 0) {
        const prevMsg = messages[index - 1]
        if (prevMsg?.metadata?._warning_msg === msg.metadata._warning_msg) {
          return false
        }
      }

      // If we found a message without _tool_hint, remove all previous messages with _tool_hint
      if (firstNonToolHintIndex !== -1 && index < firstNonToolHintIndex) {
        if (msg.metadata?._tool_hint) {
          return false
        }
      }

      return true
    })
  }

  // Cache _mode_hint from messages
  props.messages.forEach(msg => {
    if (msg.metadata?._mode_hint) {
      currentModeHint.value = msg.metadata._mode_hint
    }
  })

  if (props.showProgressMessages !== false) {
    // Show all messages including progress messages
    return filterMessages(props.messages)
  } else {
    // Hide messages with _progress: true in metadata
    const filteredMessages = props.messages.filter(msg => !msg.metadata?._progress)
    return filterMessages(filteredMessages)
  }
})

// Check if message should be displayed as user message
const isUserMessage = (msg: Message): boolean => {
  // If metadata has _as_input set to true, display as user message
  if (msg.metadata?._as_input === true) {
    return true
  }
  return msg.role === 'user'
}

// Get CSS class for message based on role and metadata
const getMessageClass = (msg: Message): string => {
  if (isUserMessage(msg)) {
    return 'justify-end'
  }
  return 'justify-start'
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
watch(() => props.chatState, scrollToBottom)
watch(() => props.showProgressMessages, scrollToBottom)
</script>

<template>
  <div ref="messageContainer" class="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-900">
    <div v-for="(msg, index) in visibleMessages" :key="index" class="flex" :class="getMessageClass(msg)">
      <div class="border-2 rounded shadow-[4px_4px_0_rgba(0,0,0,0.5)] px-4 py-3 flex flex-col" :class="{
        'bg-gradient-to-br from-blue-500 to-blue-600 border-blue-700 text-white max-w-[80%]': isUserMessage(msg),
        'bg-gradient-to-br from-gray-100 to-gray-200 border-gray-300 text-gray-800 max-w-[80%]': !isUserMessage(msg) && msg.role === 'assistant' && !msg.metadata?._progress && !msg.metadata?._warning_msg,
        'bg-gradient-to-br from-yellow-100 to-yellow-200 border-yellow-100 text-yellow-800 max-w-[80%]': !isUserMessage(msg) && msg.role === 'assistant' && msg.metadata?._tool_hint,
        'bg-gradient-to-br from-green-100 to-green-200 border-green-300 text-gray-700 max-w-[80%]': !isUserMessage(msg) && msg.role === 'assistant' && msg.metadata?._progress && !msg.metadata?._tool_hint,
        'bg-gradient-to-br from-red-100 to-red-200 border-red-300 text-red-800 max-w-[80%]': msg.role === 'system',
        'bg-gradient-to-br from-pink-100 to-pink-200 border-pink-300 text-gray-700 max-w-[80%]': msg.metadata?._warning_msg
      }">
        <!-- Video Display -->
        <div v-if="getVideoUrlFromMessage(msg)" class="mb-3 w-full">
          <!-- Collapsed state: thumbnail with play button -->
          <div v-if="!expandedVideos.includes(getVideoUrlFromMessage(msg)!)" class="relative inline-block max-w-full">
            <video :src="getVideoUrlFromMessage(msg)!"
              class="rounded border-2 cursor-pointer hover:opacity-90 transition-opacity max-w-full h-auto bg-black"
              style="max-width: 400px;" @click="toggleVideoExpand(getVideoUrlFromMessage(msg)!)">
            </video>
            <!-- Play overlay -->
            <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div class="bg-black bg-opacity-50 rounded-full p-4">
                <svg class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                </svg>
              </div>
            </div>
            <!-- Zoom hint -->
            <div
              class="absolute top-1 right-1 bg-black bg-opacity-50 text-white text-xs px-2 py-1 rounded opacity-0 hover:opacity-100 transition-opacity pointer-events-none">
              点击查看原视频
            </div>
          </div>
          <!-- Expanded state: full screen overlay with video player -->
          <div v-else class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90 p-8"
            @click="toggleVideoExpand(getVideoUrlFromMessage(msg)!)">
            <div class="relative max-w-full max-h-full">
              <video :src="getVideoUrlFromMessage(msg)!" controls autoplay class="max-w-full max-h-full rounded"
                @click.stop />
              <!-- Close hint -->
              <div class="absolute top-4 right-4 text-white text-sm bg-black bg-opacity-50 px-3 py-2 rounded">
                点击背景关闭
              </div>
            </div>
          </div>
        </div>

        <!-- Audio Display -->
        <div v-if="msg.audioUrl" class="mb-3">
          <div class="flex items-center space-x-2">
            <button @click="isPlaying(msg.audioUrl!) ? emit('stop-audio') : emit('play-audio', msg.audioUrl!)"
              class="nes-btn is-primary">
              {{ isPlaying(msg.audioUrl!) ? '⏹️' : '▶️' }}
            </button>
            <span class="text-xs opacity-70">{{ isPlaying(msg.audioUrl!) ? '播放中...' : '已停止' }}</span>
          </div>
        </div>

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
            <span class="text-xs opacity-70">{{ isPlaying(msg.audioUrl!) ? '播放中...' : '已停止' }}</span>
          </div>
        </div>

        <!-- Opus Audio Stop Button -->
        <div v-if="msg.metadata?.isPlayingOpus !== undefined" class="mb-3">
          <div class="flex items-center space-x-2">
            <button @click="emit('stop-audio')" class="nes-btn is-primary">
              {{ msg.metadata.isPlayingOpus ? '⏹️' : '✅' }}
            </button>
            <span class="text-xs opacity-70">{{ msg.metadata.isPlayingOpus ? '（流）播放中...' : '（流）已停止' }}</span>
          </div>
        </div>

        <!-- HTML Link Display -->
        <div v-if="msg.htmlContent" class="mb-3">
          <div class="flex items-center space-x-2">
            <button @click="emit('show-html', msg.htmlContent)" class="nes-btn is-primary">
              🌐 点击预览
            </button>
          </div>
        </div>

        <!-- Message Content -->
        <div class="prose prose-xs markdown-content zh" v-html="renderMarkdown(msg.content)"></div>

        <!-- Timestamp -->
        <div class="text-xs mt-2 opacity-70">
          {{ new Date(msg.timestamp).toLocaleTimeString() }}
        </div>
      </div>
    </div>

    <!-- Loading Indicator -->
    <div v-if="props.chatState && props.chatState !== 'Waiting'" class="flex justify-start">
      <div
        class="bg-gradient-to-br from-yellow-200 to-yellow-300 border border-yellow-100 rounded shadow-[4px_4px_0_rgba(0,0,0,0.5)] px-4 py-3">
        <div class="flex items-center space-x-2">
          <div class="text-xs text-yellow-900">
            {{ props.chatState }}<span v-if="props.chatState === 'Thinking' && currentModeHint">({{ currentModeHint
              }})</span>
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
