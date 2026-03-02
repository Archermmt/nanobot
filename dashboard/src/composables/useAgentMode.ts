import { ref, onUnmounted } from 'vue'

interface AgentMode {
  name: string
  model: string
  description: string
}

const currentMode = ref<AgentMode | null>(null)
const modeInterval = ref<number | null>(null)

const fetchCurrentMode = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/agent-mode/current')
    const data = await response.json()
    
    currentMode.value = {
      name: data.mode || 'unknown',
      model: data.model || 'unknown',
      description: data.description || ''
    }
  } catch (error) {
    console.error('Failed to fetch agent mode:', error)
  }
}

const startAutoRefresh = () => {
  if (modeInterval.value) {
    clearInterval(modeInterval.value)
  }
  modeInterval.value = window.setInterval(fetchCurrentMode, 30000) // Update every 30s
}

const stopAutoRefresh = () => {
  if (modeInterval.value) {
    clearInterval(modeInterval.value)
    modeInterval.value = null
  }
}

onUnmounted(() => {
  stopAutoRefresh()
})

export function useAgentMode() {
  return {
    currentMode,
    fetchCurrentMode,
    startAutoRefresh,
    stopAutoRefresh
  }
}
