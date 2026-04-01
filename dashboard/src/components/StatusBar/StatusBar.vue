<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

interface Status {
  mode: string
  model: string
  history: number
  skills: number
  tools: number
  connected: boolean
  enable_asr: boolean
  enable_tts: boolean
}

const status = ref<Status>({
  mode: 'N/A',
  model: 'N/A',
  history: 0,
  skills: 0,
  tools: 0,
  connected: false,
  enable_asr: false,
  enable_tts: false
})

// Session state for displaying connection status
const sessionState = ref<string>('Disconnected')

const emit = defineEmits(['send'])

// Receive WebSocket status from parent via prop
const props = defineProps<{
  wsStatus?: {
    isConnected: boolean
    isConnecting: boolean
    url: string
  }
}>()

// Watch for WebSocket status changes from parent
watch(() => props.wsStatus?.isConnected, (newVal) => {
  console.log('🔌 WebSocket status changed from parent:', newVal)
  status.value.connected = newVal || false
})

const receiveWsStatusChange = (data: any) => {
  console.log('📡 Received WebSocket status change:', data)
  status.value.connected = data.isConnected || false
}

// Listen for status updates from parent component
const handleStatusUpdate = (data: any) => {
  console.log('📊 Received status update:', data)
  try {
    // Parse the JSON string if it's a string
    const parsedData = typeof data === 'string' ? JSON.parse(data) : data

    // Only update fields that are present in parsedData
    if (parsedData.mode !== undefined) {
      status.value.mode = parsedData.mode
    }
    if (parsedData.model !== undefined) {
      status.value.model = parsedData.model
    }
    if (parsedData.history !== undefined) {
      status.value.history = parsedData.history
    }
    if (parsedData.skills !== undefined) {
      status.value.skills = parsedData.skills
    }
    if (parsedData.tools !== undefined) {
      status.value.tools = parsedData.tools
    }
    if (parsedData.connected !== undefined) {
      status.value.connected = parsedData.connected
    }
    if (parsedData.enable_asr !== undefined) {
      status.value.enable_asr = parsedData.enable_asr
    }
    if (parsedData.enable_tts !== undefined) {
      status.value.enable_tts = parsedData.enable_tts
    }
    if (parsedData._session_state !== undefined) {
      sessionState.value = parsedData._session_state
    }
  } catch (error) {
    console.error('Failed to parse status data:', error)
    status.value.connected = false
  }
}

const fetchStatus = async () => {
  console.log('🔄 Fetching status via /inspect command...')
  emit('send', '/inspect', true)
}

// Expose handleStatusUpdate and receiveWsStatusChange to parent component
defineExpose({
  handleStatusUpdate,
  receiveWsStatusChange
})

onMounted(() => {
  fetchStatus()
})
</script>

<template>
  <footer class="bg-gray-800 text-white px-4 py-3 text-xs border-t-4 border-gray-600">
    <div class="flex items-center justify-between">
      <!-- Status info -->
      <div class="flex items-center space-x-4">
        <div class="flex items-center space-x-2">
          <span class="w-3 h-3 rounded-sm" :class="{
            'bg-green-500': status.connected && sessionState !== 'Standby',
            'bg-yellow-500': sessionState === 'Standby',
            'bg-red-500': !status.connected
          }"></span>
          <span>{{ sessionState }}</span>
        </div>

        <div class="flex items-center space-x-2 text-xs">
          <span class="text-gray-400">SKILLS </span>
          <span class="text-white-600">{{ status.skills }}</span>
          <span class="text-gray-400">TOOLS</span>
          <span class="text-white-600">{{ status.tools }}</span>
          <span class="text-gray-400">MODE </span>
          <span class="text-white-600">{{ status.mode }}</span>
          <span class="text-gray-400">MODELS </span>
          <span class="text-white-600">{{ status.model }}</span>
        </div>
      </div>

      <!-- Refresh button -->
      <div class="flex items-center space-x-2">
        <button @click="fetchStatus" class="nes-btn is-primary px-3 py-1 rounded transition-colors"
          title="Refresh Status">
          🔄
        </button>
      </div>
    </div>
  </footer>
</template>
