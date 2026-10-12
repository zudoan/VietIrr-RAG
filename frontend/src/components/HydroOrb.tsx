import { Canvas, useFrame } from '@react-three/fiber'
import { Float, MeshDistortMaterial } from '@react-three/drei'
import { useReducedMotion } from 'motion/react'
import { Suspense, useMemo, useRef, useState } from 'react'
import type { Group } from 'three'

function OrbModel() {
  const group = useRef<Group>(null)
  const points = useMemo(() => Array.from({ length: 18 }, (_, index) => {
    const angle = index * 2.399
    const y = 1 - (index / 17) * 2
    const radius = Math.sqrt(1 - y * y)
    return [Math.cos(angle) * radius * 1.48, y * 1.48, Math.sin(angle) * radius * 1.48] as const
  }), [])

  useFrame((state, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * 0.08
      group.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.25) * 0.06
    }
  })

  return (
    <Float speed={0.8} rotationIntensity={0.15} floatIntensity={0.28}>
      <group ref={group}>
        <mesh>
          <icosahedronGeometry args={[1.26, 12]} />
          <MeshDistortMaterial color="#0dc9aa" roughness={0.2} metalness={0.25}
            distort={0.24} speed={1.4} transparent opacity={0.38} />
        </mesh>
        <mesh scale={1.035}>
          <icosahedronGeometry args={[1.28, 3]} />
          <meshBasicMaterial color="#85fff0" wireframe transparent opacity={0.13} />
        </mesh>
        <mesh rotation={[1.15, 0.3, 0.2]}>
          <torusGeometry args={[1.66, 0.006, 8, 180]} />
          <meshBasicMaterial color="#3cefd1" transparent opacity={0.65} />
        </mesh>
        <mesh rotation={[0.2, 1.2, -0.4]}>
          <torusGeometry args={[1.82, 0.004, 8, 180]} />
          <meshBasicMaterial color="#1f9fcd" transparent opacity={0.4} />
        </mesh>
        {points.map((point, index) => (
          <mesh key={index} position={point}>
            <sphereGeometry args={[index % 5 === 0 ? 0.04 : 0.023, 8, 8]} />
            <meshBasicMaterial color={index % 3 === 0 ? '#d7fff8' : '#42d9bd'} />
          </mesh>
        ))}
      </group>
    </Float>
  )
}

function canUseWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

export function HydroOrb() {
  const reducedMotion = useReducedMotion()
  const [failed, setFailed] = useState(false)
  const available = useMemo(canUseWebGL, [])

  if (!available || failed || reducedMotion) {
    return <div className="orb-fallback" role="img" aria-label="Quả cầu tri thức thủy văn" />
  }

  return (
    <div className="orb-canvas" aria-label="Mô hình 3D mạng tri thức thủy văn">
      <Canvas dpr={[1, 1.5]} camera={{ position: [0, 0, 5.2], fov: 42 }}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => gl.domElement.addEventListener('webglcontextlost', () => setFailed(true), { once: true })}>
        <ambientLight intensity={0.55} />
        <pointLight position={[4, 3, 4]} intensity={12} color="#79ffe7" />
        <pointLight position={[-4, -2, 2]} intensity={8} color="#087ea4" />
        <Suspense fallback={null}><OrbModel /></Suspense>
      </Canvas>
    </div>
  )
}
