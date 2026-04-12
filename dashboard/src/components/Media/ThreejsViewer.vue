<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'

interface Props {
  visible: boolean
  messageData: any
}

const props = defineProps<Props>()
const emit = defineEmits(['close'])

const containerRef = ref<HTMLDivElement | null>(null)
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let controls: OrbitControls | null = null
let currentModel: THREE.Mesh | null = null
let animationId: number | null = null

const isLoading = ref(false)
const errorMessage = ref('')
const modelInfo = ref({
  vertices: 0,
  fileType: ''
})

// Initialize Three.js scene
const initScene = () => {
  if (!containerRef.value) return

  // Scene setup
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1a1a2e)
  scene.fog = new THREE.Fog(0x1a1a2e, 20, 100)

  // Camera
  camera = new THREE.PerspectiveCamera(
    75,
    containerRef.value.clientWidth / containerRef.value.clientHeight,
    0.1,
    1000
  )
  camera.position.set(5, 5, 5)
  camera.lookAt(0, 0, 0)

  // Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(containerRef.value.clientWidth, containerRef.value.clientHeight)
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  containerRef.value.appendChild(renderer.domElement)

  // Controls
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05
  controls.minDistance = 1
  controls.maxDistance = 50

  // Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
  scene.add(ambientLight)

  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
  directionalLight.position.set(10, 10, 5)
  directionalLight.castShadow = true
  scene.add(directionalLight)

  // Start animation loop
  animate()
}

// Animation loop
const animate = () => {
  animationId = requestAnimationFrame(animate)
  if (controls) {
    controls.update()
  }
  if (renderer && scene && camera) {
    renderer.render(scene, camera)
  }
}

// Load and render model
const loadModel = async (data: any) => {
  if (!scene || !data?.media || data.media.length === 0) return

  isLoading.value = true
  errorMessage.value = ''

  try {
    const msgType = data.metadata?.msg_type
    const fileType = data.metadata?.file_type || ''

    modelInfo.value.fileType = fileType

    // Clear previous model
    if (currentModel) {
      scene.remove(currentModel)
      currentModel.geometry.dispose()
      if (Array.isArray(currentModel.material)) {
        currentModel.material.forEach((m: any) => m.dispose())
      } else {
        currentModel.material.dispose()
      }
      currentModel = null
    }

    // Get base64 data
    const mediaItem = data.media[0]
    let base64Data = ''

    if (typeof mediaItem === 'object' && mediaItem.data) {
      base64Data = mediaItem.data
    } else if (typeof mediaItem === 'string') {
      base64Data = mediaItem
    }

    if (!base64Data) {
      throw new Error('No model data found')
    }

    // Convert base64 to binary
    const binaryString = atob(base64Data)
    const len = binaryString.length
    const bytes = new Uint8Array(len)
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }

    let geometry: THREE.BufferGeometry | null = null

    // Load based on file type
    if (fileType.includes('stl') || msgType === 'stl') {
      const loader = new STLLoader()
      geometry = loader.parse(bytes.buffer)
    } else if (fileType.includes('obj') || msgType === 'obj') {
      const loader = new OBJLoader()
      const textDecoder = new TextDecoder()
      const objText = textDecoder.decode(bytes)
      const object = loader.parse(objText)

      // OBJLoader returns a Group, get the first mesh
      object.traverse((child: any) => {
        if (child.isMesh && !geometry) {
          geometry = child.geometry
        }
      })

      if (!geometry) {
        throw new Error('No mesh found in OBJ file')
      }
    } else {
      throw new Error(`Unsupported file type: ${fileType}`)
    }

    if (!geometry) {
      throw new Error('Failed to parse geometry')
    }

    // Compute bounding box and center
    geometry.computeBoundingBox()
    const center = new THREE.Vector3()
    if (geometry.boundingBox) {
      geometry.boundingBox.getCenter(center)
    }

    // Calculate scale to fit view
    const size = new THREE.Vector3()
    if (geometry.boundingBox) {
      geometry.boundingBox.getSize(size)
    }
    const maxDim = Math.max(size.x, size.y, size.z)
    const scale = 3.0 / maxDim

    // Create material
    const material = new THREE.MeshPhongMaterial({
      color: 0x4ECDC4,
      specular: 0x111111,
      shininess: 200,
      flatShading: true
    })

    // Create mesh
    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.sub(center.multiplyScalar(scale))
    mesh.scale.set(scale, scale, scale)
    mesh.rotation.set(0, 0, 0)
    mesh.castShadow = true
    mesh.receiveShadow = true

    // Add to scene
    scene.add(mesh)
    currentModel = mesh

    // Update model info
    modelInfo.value.vertices = geometry.attributes.position.count

    isLoading.value = false
    console.log('✅ Model loaded successfully:', modelInfo.value)
  } catch (error: any) {
    console.error('❌ Failed to load model:', error)
    errorMessage.value = error.message || 'Failed to load model'
    isLoading.value = false
  }
}

// Handle window resize
const handleResize = () => {
  if (!containerRef.value || !camera || !renderer) return

  camera.aspect = containerRef.value.clientWidth / containerRef.value.clientHeight
  camera.updateProjectionMatrix()
  renderer.setSize(containerRef.value.clientWidth, containerRef.value.clientHeight)
}

// Close viewer
const close = () => {
  emit('close')
}

// Watch for visibility changes
watch(() => props.visible, (newVal) => {
  if (newVal && props.messageData) {
    setTimeout(() => {
      if (!scene) {
        initScene()
      }
      loadModel(props.messageData)
    }, 100)
  }
})

// Watch for message data changes
watch(() => props.messageData, (newData) => {
  if (props.visible && newData) {
    loadModel(newData)
  }
})

onMounted(() => {
  window.addEventListener('resize', handleResize)

  if (props.visible && props.messageData) {
    setTimeout(() => {
      initScene()
      loadModel(props.messageData)
    }, 100)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)

  if (animationId) {
    cancelAnimationFrame(animationId)
  }

  if (renderer) {
    renderer.dispose()
    if (containerRef.value && renderer.domElement) {
      containerRef.value.removeChild(renderer.domElement)
    }
  }

  if (controls) {
    controls.dispose()
  }
})
</script>

<template>
  <div v-if="visible" class="threejs-viewer-overlay" @click="close">
    <div class="threejs-viewer-content" @click.stop>
      <div class="viewer-header">
        <span class="viewer-title">🎨 3D Model Viewer</span>
        <div class="viewer-info" v-if="modelInfo.fileType">
          <span class="info-item">Type: {{ modelInfo.fileType }}</span>
          <span class="info-item" v-if="modelInfo.vertices > 0">Vertices: {{ modelInfo.vertices }}</span>
        </div>
        <button class="viewer-close" @click="close" title="Close">✕</button>
      </div>

      <div class="viewer-body">
        <div ref="containerRef" class="viewer-canvas"></div>

        <div v-if="isLoading" class="viewer-loading">
          <div class="loading-spinner"></div>
          <p>Loading model...</p>
        </div>

        <div v-if="errorMessage" class="viewer-error">
          <p>❌ {{ errorMessage }}</p>
        </div>

        <div class="viewer-controls-hint">
          <p>🖱️ Drag to rotate • Scroll to zoom • Right-click to pan</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.threejs-viewer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.threejs-viewer-content {
  background: #1a1a2e;
  border-radius: 12px;
  width: 90vw;
  height: 90vh;
  max-width: 1600px;
  max-height: 900px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  animation: viewerSlideIn 0.3s ease-out;
  border: 2px solid #374151;
}

@keyframes viewerSlideIn {
  from {
    opacity: 0;
    transform: scale(0.9) translateY(20px);
  }

  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 2px solid #374151;
  background: linear-gradient(to right, #1f2937, #111827);
  border-radius: 12px 12px 0 0;
}

.viewer-title {
  font-size: 16px;
  font-weight: 600;
  color: #e5e7eb;
  font-family: 'Press Start 2P', 'Noto Sans SC', monospace;
}

.viewer-info {
  display: flex;
  gap: 16px;
  flex: 1;
  margin-left: 20px;
}

.info-item {
  font-size: 12px;
  color: #9ca3af;
  font-family: monospace;
}

.viewer-close {
  background: #dc2626;
  border: 2px solid #b91c1c;
  font-size: 20px;
  color: white;
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 6px;
  transition: all 0.2s;
  line-height: 1;
  font-family: monospace;
}

.viewer-close:hover {
  background: #ef4444;
  transform: translate(-1px, -1px);
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.3);
}

.viewer-close:active {
  transform: translate(1px, 1px);
  box-shadow: none;
}

.viewer-body {
  flex: 1;
  position: relative;
  overflow: hidden;
  border-radius: 0 0 12px 12px;
}

.viewer-canvas {
  width: 100%;
  height: 100%;
  background: linear-gradient(to bottom, #1a1a2e 0%, #16213e 100%);
}

.viewer-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #e5e7eb;
}

.loading-spinner {
  width: 50px;
  height: 50px;
  border: 4px solid #374151;
  border-top-color: #4ECDC4;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.viewer-error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #ef4444;
  background: rgba(0, 0, 0, 0.8);
  padding: 20px;
  border-radius: 8px;
  border: 2px solid #dc2626;
}

.viewer-controls-hint {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.7);
  padding: 10px 20px;
  border-radius: 8px;
  color: #9ca3af;
  font-size: 12px;
  font-family: monospace;
  border: 1px solid #374151;
}
</style>
