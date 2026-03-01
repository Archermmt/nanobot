<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAgentMode } from '@/composables/useAgentMode'

interface Status {
  connected: boolean
  agent: string
  llm_provider: string
  llm_model: string
  memory_loaded: boolean
  skills_loaded: number
}

const status = ref<Status>({
  connected: false,
  agent: 'Unknown',
  llm_provider: '-',
  llm_model: '-',
  memory_loaded: false,
  skills_loaded: 0
})

const logs = ref<string[]>([])
const showLogs = ref(false)
const showLLMSettings = ref(false)

const { currentMode, fetchCurrentMode, startAutoRefresh } = useAgentMode()

const fetchStatus = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/status')
    const data = await response.json()
    
    status.value = {
      connected: true,
      agent: data.soul_loaded ? 'SoulAgent' : 'Not Loaded',
      llm_provider: data.llm_providers?.[0] || '-',
      llm_model: '-',
      memory_loaded: data.memory_dir_exists,
      skills_loaded: data.skills_loaded?.length || 0
    }
    
    logs.value.unshift(`[${new Date().toLocaleTimeString()}] Status updated`)
  } catch (error) {
    status.value.connected = false
    logs.value.unshift(`[${new Date().toLocaleTimeString()}] Connection failed`)
  }
}

const fetchCurrentLLM = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/llm/current')
    const data = await response.json()
    status.value.llm_provider = data.provider
    status.value.llm_model = data.model
  } catch (error) {
    console.error('Failed to fetch LLM info:', error)
  }
}

let statusInterval: number | null = null

onMounted(() => {
  fetchStatus()
  fetchCurrentLLM()
  fetchCurrentMode()
  statusInterval = window.setInterval(fetchStatus, 30000) // Update every 30s
  startAutoRefresh()
})

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval)
  }
})
</script>

<template>
  <footer class="bg-gray-800 text-white px-4 py-3 text-xs border-t-4 border-gray-600">
    <div class="flex items-center justify-between">
      <!-- Left: Status indicators -->
      <div class="flex items-center space-x-4">
        <div class="flex items-center space-x-2">
          <span class="w-3 h-3 rounded-sm" :class="status.connected ? 'bg-green-500' : 'bg-red-500'"></span>
          <span>{{ status.connected ? 'Connected' : 'Disconnected' }}</span>
        </div>
        
        <div class="hidden md:flex items-center space-x-2 text-gray-400">
          <span>🤖 {{ status.agent }}</span>
        </div>
        
        <div class="hidden md:flex items-center space-x-2 text-gray-400">
          <span>🧠 {{ status.llm_provider }} / {{ status.llm_model }}</span>
        </div>
        
        <div class="hidden md:flex items-center space-x-2 text-gray-400">
          <span>📦 {{ status.skills_loaded }} skills</span>
        </div>
        
        <div class="hidden md:flex items-center space-x-2 text-blue-400">
          <span>⚙️ {{ currentMode?.name || 'N/A' }}</span>
        </div>
      </div>

      <!-- Right: Action buttons -->
      <div class="flex items-center space-x-2">
        <button
          @click="showLogs = !showLogs"
          class="nes-btn is-primary px-3 py-1 rounded transition-colors"
          title="View Logs"
        >
          📋
        </button>
        
        <button
          @click="showLLMSettings = !showLLMSettings"
          class="nes-btn is-primary px-3 py-1 rounded transition-colors"
          title="LLM Settings"
        >
          ⚙️
        </button>
      </div>
    </div>

    <!-- Logs Panel -->
    <div v-if="showLogs" class="mt-2 bg-black rounded p-3 max-h-48 overflow-y-auto font-mono text-xs border border-gray-600 shadow-[4px_4px_0_rgba(0,0,0,0.5)]">
      <div v-for="(log, index) in logs.slice(0, 20)" :key="index" class="text-gray-300">
        {{ log }}
      </div>
    </div>

    <!-- LLM Settings Panel -->
    <div v-if="showLLMSettings" class="mt-2 bg-gray-700 rounded p-3 border border-gray-600 shadow-[4px_4px_0_rgba(0,0,0,0.5)]">
      <h4 class="font-semibold mb-2">LLM Configuration</h4>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between">
          <span class="text-gray-400">Provider:</span>
          <span>{{ status.llm_provider }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-gray-400">Model:</span>
          <span>{{ status.llm_model }}</span>
        </div>
        <button
          @click="$emit('open-llm-settings')"
          class="nes-btn is-primary mt-2 w-full"
        >
          Change Provider
        </button>
      </div>
    </div>
  </footer>
</template>
