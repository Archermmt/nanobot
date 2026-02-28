<script setup lang="ts">
import { ref, computed } from 'vue'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  imageUrl?: string
  audioUrl?: string
}

interface Props {
  messages: Message[]
  isLoading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits(['play-audio', 'stop-audio'])

const showThinking = computed(() => {
  // Show thinking only if loading and there are messages
  return props.isLoading && props.messages.length > 0
})

const currentAudio = ref<HTMLAudioElement | null>(null)
const expandedImages = ref<string[]>([])

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
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-4">
    <div
      v-for="(msg, index) in messages"
      :key="index"
      class="flex"
      :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
    >
      <div
        class="max-w-[80%] rounded-2xl px-4 py-3"
        :class="{
          'bg-blue-500 text-white': msg.role === 'user',
          'bg-white border border-gray-200 text-gray-800': msg.role === 'assistant',
          'bg-red-50 border border-red-200 text-red-800': msg.role === 'system'
        }"
      >
        <!-- Image Display -->
        <div v-if="msg.imageUrl" class="mb-3">
          <img
            :src="msg.imageUrl"
            alt="Generated image"
            class="max-w-full rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
            :class="expandedImages.includes(msg.imageUrl) ? 'fixed inset-0 w-full h-full object-contain bg-black bg-opacity-90 z-50 p-8' : ''"
            @click="toggleImageExpand(msg.imageUrl)"
          />
        </div>

        <!-- Audio Display -->
        <div v-if="msg.audioUrl" class="mb-3">
          <div class="flex items-center space-x-2">
            <button
              @click="isPlaying(msg.audioUrl!) ? stopAudio() : playAudio(msg.audioUrl!)"
              class="p-2 bg-blue-500 text-white rounded-full hover:bg-blue-600 transition-colors"
            >
              {{ isPlaying(msg.audioUrl!) ? '⏹️' : '▶️' }}
            </button>
            <span class="text-sm opacity-70">Voice Message</span>
          </div>
        </div>

        <!-- Message Content -->
        <div class="prose prose-sm" v-html="msg.content"></div>

        <!-- Timestamp -->
        <div class="text-xs mt-2 opacity-70">
          {{ new Date(msg.timestamp).toLocaleTimeString() }}
        </div>
      </div>
    </div>

    <!-- Loading Indicator -->
    <div v-if="showThinking" class="flex justify-start">
      <div class="bg-white border border-gray-200 rounded-2xl px-4 py-3">
        <div class="flex items-center space-x-2">
          <div class="text-sm text-gray-500">Thinking</div>
          <div class="flex space-x-1">
            <div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
            <div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
            <div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
