import { Canvas, useFrame } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { HYDRAULIC_HOTSPOTS, HotspotInfo, HotspotMarker } from './HydraulicHotspots'
import { WaterSurface } from './WaterSurface'

interface HydraulicSceneProps {
  activeHotspot: HotspotInfo | null
  onSelectHotspot: (hotspot: HotspotInfo) => void
  cameraMode?: 'overview' | 'reservoir' | 'spillway' | 'canal'
}

function ConcreteDam() {
  const concreteColor = '#3a4e57'
  const darkConcrete = '#28373e'
  const accentConcrete = '#516773'

  return (
    <group position={[0, 0, 0]}>
      {/* Main Dam Body - Triangular gravity section */}
      {/* Central Dam Block */}
      <mesh position={[0, 0.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[4.2, 1.8, 1.2]} />
        <meshStandardMaterial color={concreteColor} roughness={0.88} metalness={0.12} />
      </mesh>

      {/* Sloped Downstream Face */}
      <mesh position={[0, -0.15, 0.9]} rotation={[0.42, 0, 0]} castShadow receiveShadow>
        <boxGeometry args={[4.2, 1.6, 0.6]} />
        <meshStandardMaterial color={darkConcrete} roughness={0.92} metalness={0.08} />
      </mesh>

      {/* Crest Roadway (Đỉnh đập) */}
      <mesh position={[0, 1.35, 0]} castShadow>
        <boxGeometry args={[4.4, 0.12, 1.4]} />
        <meshStandardMaterial color={accentConcrete} roughness={0.75} metalness={0.2} />
      </mesh>

      {/* Parapet Walls / Railings */}
      <mesh position={[0, 1.45, -0.65]}>
        <boxGeometry args={[4.4, 0.12, 0.08]} />
        <meshStandardMaterial color="#8ca4af" roughness={0.5} metalness={0.4} />
      </mesh>
      <mesh position={[0, 1.45, 0.65]}>
        <boxGeometry args={[4.4, 0.12, 0.08]} />
        <meshStandardMaterial color="#8ca4af" roughness={0.5} metalness={0.4} />
      </mesh>

      {/* Spillway Piers (Trụ pin phân khoang tràn) */}
      {[-1.0, 0, 1.0].map((x, i) => (
        <group key={`pier-${i}`} position={[x, 0.8, 0.1]}>
          <mesh castShadow>
            <boxGeometry args={[0.22, 1.2, 1.5]} />
            <meshStandardMaterial color={accentConcrete} roughness={0.8} />
          </mesh>
          {/* Radial Gate Pivot Hub (Trục cửa van cung) */}
          <mesh position={[0, 0.2, 0.5]}>
            <cylinderGeometry args={[0.08, 0.08, 0.26, 12]} />
            <meshStandardMaterial color="#c9a46b" roughness={0.3} metalness={0.7} />
          </mesh>
        </group>
      ))}

      {/* Spillway Chute (Mặt tràn xả lũ dốc nước) */}
      <mesh position={[0, -0.2, 1.1]} rotation={[0.46, 0, 0]} receiveShadow>
        <boxGeometry args={[2.8, 1.7, 0.15]} />
        <meshStandardMaterial color="#21323a" roughness={0.95} />
      </mesh>

      {/* Stilling Basin (Bể tiêu năng) */}
      <mesh position={[0, -0.95, 2.2]} receiveShadow>
        <boxGeometry args={[3.2, 0.25, 1.6]} />
        <meshStandardMaterial color={darkConcrete} roughness={0.9} />
      </mesh>

      {/* Energy Dissipation Chute Blocks (Răng cản tiêu năng) */}
      {[-0.8, -0.3, 0.2, 0.7].map((bx, bi) => (
        <mesh key={`block-${bi}`} position={[bx, -0.75, 2.3]} castShadow>
          <boxGeometry args={[0.22, 0.22, 0.25]} />
          <meshStandardMaterial color="#1a252b" roughness={0.9} />
        </mesh>
      ))}
    </group>
  )
}

function FlowingSpillwayWater() {
  const waterRef = useRef<THREE.Mesh>(null)

  useFrame(({ clock }) => {
    if (!waterRef.current) return
    const mat = waterRef.current.material as THREE.MeshStandardMaterial
    // Pulsing foam shimmer
    mat.opacity = 0.82 + Math.sin(clock.getElapsedTime() * 5.0) * 0.08
  })

  return (
    <group>
      {/* Water rushing down spillway chute */}
      <mesh ref={waterRef} position={[0, -0.15, 1.12]} rotation={[0.46, 0, 0]}>
        <planeGeometry args={[2.2, 1.7]} />
        <meshStandardMaterial
          color="#6ed2db"
          roughness={0.1}
          metalness={0.3}
          transparent
          opacity={0.85}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Turbulent foam in stilling basin */}
      <mesh position={[0, -0.78, 2.2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[2.4, 1.3]} />
        <meshStandardMaterial
          color="#8fe5ed"
          roughness={0.2}
          metalness={0.1}
          transparent
          opacity={0.9}
        />
      </mesh>
    </group>
  )
}

function AbutmentTerrain() {
  // Left and Right valley walls holding the dam
  const leftTerrain = useMemo(() => {
    const geo = new THREE.ConeGeometry(3.5, 3.2, 5)
    return geo
  }, [])

  const rightTerrain = useMemo(() => {
    const geo = new THREE.ConeGeometry(3.2, 3.0, 5)
    return geo
  }, [])

  return (
    <group>
      {/* Left Valley Abutment */}
      <mesh
        geometry={leftTerrain}
        position={[-3.8, 0.8, 0]}
        rotation={[0.1, 0.4, -0.2]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color="#1e343d" roughness={0.95} metalness={0.05} />
      </mesh>

      {/* Right Valley Abutment */}
      <mesh
        geometry={rightTerrain}
        position={[3.8, 0.7, 0]}
        rotation={[-0.1, -0.3, 0.2]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color="#1c3038" roughness={0.95} metalness={0.05} />
      </mesh>

      {/* Riverbed ground plane */}
      <mesh position={[0, -1.05, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[16, 16]} />
        <meshStandardMaterial color="#0e1a22" roughness={0.98} />
      </mesh>
    </group>
  )
}

function CameraRig({ activeHotspot }: { activeHotspot: HotspotInfo | null }) {
  const defaultPos = useMemo(() => new THREE.Vector3(0, 3.8, 6.2), [])
  const defaultTarget = useMemo(() => new THREE.Vector3(0, 0.2, 0.6), [])

  useFrame(({ camera, pointer }) => {
    let targetPos = defaultPos
    let lookTarget = defaultTarget

    if (activeHotspot) {
      targetPos = new THREE.Vector3(...activeHotspot.position).add(new THREE.Vector3(1.2, 1.4, 2.2))
      lookTarget = new THREE.Vector3(...activeHotspot.cameraTarget)
    } else {
      // Gentle mouse parallax in overview mode
      targetPos = defaultPos.clone().add(new THREE.Vector3(pointer.x * 0.8, pointer.y * 0.4, 0))
    }

    camera.position.lerp(targetPos, 0.045)
    const currentTarget = new THREE.Vector3(0, 0, 0)
    camera.getWorldDirection(currentTarget)
    camera.lookAt(lookTarget)
  })

  return null
}

export function HydraulicScene({ activeHotspot, onSelectHotspot }: HydraulicSceneProps) {
  return (
    <div className="hydraulic-canvas-container">
      <Canvas
        camera={{ position: [0, 3.8, 6.2], fov: 42 }}
        shadows
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      >
        <color attach="background" args={['#081621']} />
        <fog attach="fog" args={['#081621', 8, 22]} />

        {/* Ambient & Technical Directional Lighting */}
        <ambientLight intensity={0.45} />
        <directionalLight
          position={[6, 8, 4]}
          intensity={1.25}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
          shadow-camera-near={1}
          shadow-camera-far={25}
          shadow-camera-left={-6}
          shadow-camera-right={6}
          shadow-camera-top={6}
          shadow-camera-bottom={-6}
          color="#f4f8fa"
        />
        <directionalLight position={[-5, 4, -5]} intensity={0.5} color="#53aeb8" />
        <pointLight position={[0, 1.8, 1]} intensity={0.8} color="#9decf5" distance={6} />

        <Suspense fallback={null}>
          <group position={[0, 0, 0]}>
            {/* Dam Structure */}
            <ConcreteDam />

            {/* Spillway Flowing Water */}
            <FlowingSpillwayWater />

            {/* Upstream Water Reservoir */}
            <WaterSurface
              width={8.5}
              length={5.5}
              position={[0, 0.85, -2.4]}
              color="#226a76"
              flowSpeed={0.5}
              waveHeight={0.06}
            />

            {/* Downstream Canal Water */}
            <WaterSurface
              width={3.0}
              length={5.2}
              position={[0, -0.88, 4.4]}
              color="#2d7c88"
              flowSpeed={1.0}
              waveHeight={0.04}
            />

            {/* Valley Abutment Landscape */}
            <AbutmentTerrain />

            {/* 3D Interactive Hotspot Markers */}
            {HYDRAULIC_HOTSPOTS.map((hotspot) => (
              <HotspotMarker
                key={hotspot.id}
                info={hotspot}
                active={activeHotspot?.id === hotspot.id}
                onClick={onSelectHotspot}
              />
            ))}
          </group>

          <CameraRig activeHotspot={activeHotspot} />
        </Suspense>
      </Canvas>
    </div>
  )
}
