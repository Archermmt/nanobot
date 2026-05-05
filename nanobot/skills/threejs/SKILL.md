---
name: threejs
description: Master guide for Three.js 3D graphics development. Provides unified access to all Three.js sub-skills including fundamentals, geometry, materials, lighting, textures, loaders, animation, interaction, shaders, and post-processing. Use when creating 3D scenes, working with WebGL, or building interactive 3D experiences.
metadata: {"nanobot":{"emoji":"🎨"}}
---

# Three.js Skill - Master Guide

This is the master guide for all Three.js-related operations in nanobot. It provides a unified interface for working with 3D graphics through specialized sub-skills covering different aspects of Three.js development.

## Overview

Three.js is a powerful JavaScript library for creating 3D graphics in web browsers. The system is organized into specialized sub-skills:

- **Fundamentals** 🏗️ - Scene setup, cameras, renderer, Object3D hierarchy
- **Geometry** 📐 - Built-in shapes, BufferGeometry, custom geometry, instancing
- **Materials** 🎨 - PBR materials, shaders, texture mapping
- **Lighting** 💡 - Light types, shadows, environment lighting
- **Textures** 🖼️ - Texture loading, UV mapping, environment maps
- **Loaders** 📦 - GLTF, models, async patterns, asset management
- **Animation** 🎬 - Keyframe animation, morph targets, skeletal animation
- **Interaction** 🖱️ - Raycasting, controls, mouse/touch input
- **Shaders** ⚡ - Custom GLSL shaders, ShaderMaterial
- **Post-processing** ✨ - Bloom, DOF, screen effects

## Quick Decision Guide

When you need to work with Three.js, follow this decision tree:

### 1. What aspect of Three.js?

- **Setting up scenes, cameras, renderers** → See [threejs-fundamentals](./threejs-fundamentals/SKILL.md)
- **Creating 3D shapes and meshes** → See [threejs-geometry](./threejs-geometry/SKILL.md)
- **Styling surfaces and appearances** → See [threejs-materials](./threejs-materials/SKILL.md)
- **Adding lights and shadows** → See [threejs-lighting](./threejs-lighting/SKILL.md)
- **Working with images and textures** → See [threejs-textures](./threejs-textures/SKILL.md)
- **Loading models and assets** → See [threejs-loaders](./threejs-loaders/SKILL.md)
- **Animating objects and scenes** → See [threejs-animation](./threejs-animation/SKILL.md)
- **Handling user input and interaction** → See [threejs-interaction](./threejs-interaction/SKILL.md)
- **Writing custom shaders** → See [threejs-shaders](./threejs-shaders/SKILL.md)
- **Adding screen effects** → See [threejs-postprocessing](./threejs-postprocessing/SKILL.md)

### 2. Common Development Workflows

#### Workflow 1: Basic Scene Setup
```javascript
// 1. Read threejs-fundamentals for scene/camera/renderer setup
// 2. Create basic scene structure
import * as THREE from 'three';

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });

renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// 3. Add content using appropriate sub-skills
```

#### Workflow 2: Loading and Displaying Models
```javascript
// 1. Read threejs-loaders for model loading
// 2. Read threejs-fundamentals for scene setup
// 3. Load and display model
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const loader = new GLTFLoader();
loader.load('model.glb', (gltf) => {
    scene.add(gltf.scene);
});
```

#### Workflow 3: Creating Interactive 3D Experiences
```javascript
// 1. Read threejs-fundamentals for basics
// 2. Read threejs-interaction for raycasting and controls
// 3. Read threejs-animation for animations
// 4. Implement interaction logic
```

## Important Rules

1. **Always use the correct sub-skill**:
   - Each sub-skill covers specific aspects of Three.js
   - Don't mix concepts between unrelated sub-skills
   - Refer to the appropriate sub-skill for detailed implementation

2. **HTML Output Configuration**:
   - When generating HTML files for Three.js demos, save them to: `~/.nanobot/media/html/`
   - Use absolute paths when referencing the saved file
   - Example: `const outputPath = Path.home() / '.nanobot' / 'media' / 'html' / 'demo.html';`

3. **Use proper import statements**:
   - Always import Three.js modules correctly
   - Use ES6 imports for modern Three.js versions
   - Include necessary addons from `three/examples/jsm/`

4. **Follow Three.js best practices**:
   - Dispose of geometries, materials, and textures when no longer needed
   - Use efficient rendering techniques (instancing, LOD, etc.)
   - Optimize performance for web deployment

5. **Read detailed documentation**:
   - For specific parameter details and advanced usage, read the individual sub-skill files
   - Each sub-skill contains comprehensive examples and best practices

## Examples by Use Case

### "Create a rotating cube"
→ Use threejs-fundamentals + threejs-geometry + threejs-materials
```javascript
// Basic scene setup from fundamentals
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer();

// Geometry from geometry skill
const geometry = new THREE.BoxGeometry(1, 1, 1);

// Material from materials skill
const material = new THREE.MeshStandardMaterial({ color: 0x00ff00 });

// Combine into mesh
const cube = new THREE.Mesh(geometry, material);
scene.add(cube);

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    cube.rotation.x += 0.01;
    cube.rotation.y += 0.01;
    renderer.render(scene, camera);
}
animate();
```

### "Load a 3D model"
→ Use threejs-loaders + threejs-fundamentals
```javascript
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const loader = new GLTFLoader();
loader.load('path/to/model.glb', (gltf) => {
    scene.add(gltf.scene);
});
```

### "Add realistic lighting"
→ Use threejs-lighting + threejs-materials
```javascript
// Ambient light
const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
scene.add(ambientLight);

// Directional light with shadows
const dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(5, 5, 5);
dirLight.castShadow = true;
scene.add(dirLight);

// Enable shadows on renderer
renderer.shadowMap.enabled = true;
```

### "Create custom shader effect"
→ Use threejs-shaders + threejs-materials
```javascript
const shaderMaterial = new THREE.ShaderMaterial({
    uniforms: {
        time: { value: 0 },
        resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) }
    },
    vertexShader: `
        varying vec2 vUv;
        void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
    `,
    fragmentShader: `
        uniform float time;
        varying vec2 vUv;
        void main() {
            gl_FragColor = vec4(vUv, sin(time) * 0.5 + 0.5, 1.0);
        }
    `
});
```

## When to Read Detailed Documentation

Read the specific sub-skill documentation when you need:
- Advanced parameters and configurations
- Specific implementation patterns
- Performance optimization techniques
- Complex feature implementations
- Detailed API references

**Remember**: This master guide helps you choose the right sub-skill. For detailed implementation, always refer to the specific sub-skill documentation.

## Sub-Skill Relationships

The sub-skills are designed to work together:

- **Fundamentals** is the foundation - always start here for basic setup
- **Geometry** and **Materials** work together to create visual objects
- **Lighting** affects how **Materials** appear
- **Textures** enhance **Materials** and can be loaded via **Loaders**
- **Animation** brings static scenes to life
- **Interaction** adds user engagement
- **Shaders** provide ultimate customization
- **Post-processing** adds final visual polish

## Getting Started Checklist

1. ✅ Read [threejs-fundamentals](./threejs-fundamentals/SKILL.md) for basic setup
2. ✅ Choose appropriate sub-skills based on your needs
3. ✅ Follow the examples in each sub-skill
4. ✅ Test your implementation incrementally
5. ✅ Optimize performance for web deployment

## Additional Resources

- Official Three.js documentation: https://threejs.org/docs/
- Three.js examples: https://threejs.org/examples/
- Community forums and tutorials
- WebGL fundamentals for deeper understanding

For any Three.js development task, start with this master guide to identify the relevant sub-skills, then dive into the specific documentation for detailed implementation guidance.

## Important Rules

1. **ALWAYS save HTML files to the correct directory** - When generating HTML files for Three.js demos, save them to `~/.nanobot/media/html/`.
2. **Use absolute paths** - Convert all paths to absolute before referencing saved HTML files.
3. **Display generated HTML files** - After generating an HTML file, always call the `media` tool in `display` mode with `media_type="html"` to display the HTML content to the user.
