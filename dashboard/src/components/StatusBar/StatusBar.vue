<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Status {
  mode: string
  price: string
  model: string
  history: number
  skills: number
  tools: number
  connected: boolean
}

const status = ref<Status>({
  mode: 'N/A',
  price: 'N/A',
  model: 'N/A',
  history: 0,
  skills: 0,
  tools: 0,
  connected: false
})

const emit = defineEmits(['send-status'])
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

    status.value = {
      mode: parsedData.mode || 'N/A',
      price: parsedData.price || 'N/A',
      model: parsedData.model || 'N/A',
      history: parsedData.history || 0,
      skills: parsedData.skills || 0,
      tools: parsedData.tools || 0,
      connected: true
    }
  } catch (error) {
    console.error('Failed to parse status data:', error)
    status.value.connected = false
  }
}

const fetchStatus = async () => {
  console.log('🔄 Fetching status via /status command...')
  emit('send-status')
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
          <span class="w-3 h-3 rounded-sm" :class="status.connected ? 'bg-green-500' : 'bg-red-500'"></span>
          <span>{{ status.connected ? 'Connected' : 'Disconnected' }}</span>
        </div>

        <div class="flex items-center space-x-2 text-xs">
          <span class="text-gray-400">MODE </span>
          <span class="text-white-600">{{ status.mode }}</span>
          <span class="text-gray-400">PRICE </span>
          <span class="text-white-600">{{ status.price }}</span>
          <span class="text-gray-400">MODEL </span>
          <span class="text-white-600">{{ status.model }}</span>
          <span class="text-gray-400">SKILLS </span>
          <span class="text-white-600">{{ status.skills }}</span>
          <span class="text-gray-400">TOOLS</span>
          <span class="text-white-600">{{ status.tools }}</span>
        </div>
      </div>

      <!-- Refresh button -->
      <div class="flex items-center space-x-2">
        <button
          @click="fetchStatus"
          class="nes-btn is-primary px-3 py-1 rounded transition-colors"
          title="Refresh Status"
        >
          🔄
        </button>
      </div>
    </div>
  </footer>
</template>
