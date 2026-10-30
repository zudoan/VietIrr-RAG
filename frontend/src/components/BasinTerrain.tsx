import { Canvas, useFrame } from '@react-three/fiber'
import { useReducedMotion } from 'motion/react'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'

function elevation(x: number, y: number) {
  const ridgeA = Math.exp(-((x + 1.8) ** 2 * 0.18 + (y - 0.6) ** 2 * 0.45)) * 1.65
  const ridgeB = Math.exp(-((x - 2.2) ** 2 * 0.22 + (y + 0.8) ** 2 * 0.38)) * 1.25
  const valley = Math.exp(-(x ** 2 * 0.32 + y ** 2 * 0.16)) * 0.9
  return ridgeA + ridgeB - valley + Math.sin(x * 1.3 + y * 0.7) * 0.13
}

function Terrain({ animate }: { animate: boolean }) {
  const group = useRef<THREE.Group>(null)
  const geometry = useMemo(() => {
    const next = new THREE.PlaneGeometry(10, 7.4, 72, 52)
    const positions = next.attributes.position
    for (let index = 0; index < positions.count; index += 1) {
      positions.setZ(index, elevation(positions.getX(index), positions.getY(index)))
    }
    positions.needsUpdate = true
    next.computeVertexNormals()
    return next
  }, [])
  const river = useMemo(() => Array.from({ length: 55 }, (_, index) => {
    const y = -3.3 + index * 0.125
    const x = Math.sin(y * 0.95) * 0.52 + Math.sin(y * 2.2) * 0.12
    return new THREE.Vector3(x, y, elevation(x, y) + 0.12)
  }), [])
  const tributary = useMemo(() => Array.from({ length: 28 }, (_, index) => {
    const x = -4 + index * 0.13
    const y = 1.2 - (x + 0.45) * 0.45 + Math.sin(x * 1.4) * 0.12
    return new THREE.Vector3(x, y, elevation(x, y) + 0.1)
  }), [])
  const riverLine = useMemo(() => {
    const lineGeometry = new THREE.BufferGeometry().setFromPoints(river)
    return new THREE.Line(lineGeometry, new THREE.LineBasicMaterial({ color: '#3c8791', transparent: true, opacity: 0.95 }))
  }, [river])
  const tributaryLine = useMemo(() => {
    const lineGeometry = new THREE.BufferGeometry().setFromPoints(tributary)
    return new THREE.Line(lineGeometry, new THREE.LineBasicMaterial({ color: '#6aa0a6', transparent: true, opacity: 0.75 }))
  }, [tributary])

  useEffect(() => () => {
    geometry.dispose()
    riverLine.geometry.dispose()
    tributaryLine.geometry.dispose()
    ;(riverLine.material as THREE.Material).dispose()
    ;(tributaryLine.material as THREE.Material).dispose()
  }, [geometry, riverLine, tributaryLine])
  useFrame(({ pointer }) => {
    if (!group.current || !animate) return
    group.current.rotation.z = THREE.MathUtils.lerp(group.current.rotation.z, pointer.x * 0.035, 0.025)
    group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, -1.03 + pointer.y * 0.025, 0.025)
  })

  return (
    <group ref={group} rotation={[-1.03, 0, -0.08]} position={[0, -0.45, 0]}>
      <mesh geometry={geometry}>
        <meshStandardMaterial color="#cfd2c5" roughness={0.93} metalness={0.02} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={geometry} position={[0, 0, 0.018]}>
        <meshBasicMaterial color="#1b4248" wireframe transparent opacity={0.22} />
      </mesh>
      <primitive object={riverLine} />
      <primitive object={tributaryLine} />
    </group>
  )
}

export function BasinTerrain() {
  const reducedMotion = useReducedMotion()
  const [visible, setVisible] = useState(!document.hidden)

  useEffect(() => {
    const update = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])

  return (
    <div className="basin-scene" role="img" aria-label="Mô hình địa hình lưu vực và mạng sông cách điệu">
      <Suspense fallback={<div className="terrain-fallback" />}>
        <Canvas
          dpr={[1, 1.5]}
          frameloop={reducedMotion || !visible ? 'demand' : 'always'}
          camera={{ position: [0, 2.7, 7.7], fov: 38 }}
          gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        >
          <color attach="background" args={['#e5e4da']} />
          <fog attach="fog" args={['#e5e4da', 7, 13]} />
          <ambientLight intensity={1.5} />
          <directionalLight position={[-3, 5, 4]} intensity={2.4} color="#fff8df" />
          <directionalLight position={[4, 1, 2]} intensity={0.65} color="#6da5aa" />
          <Terrain animate={!reducedMotion && visible} />
        </Canvas>
      </Suspense>
      <div className="terrain-north">BẮC <span /></div>
      <div className="terrain-scale"><span /> 0&nbsp;&nbsp;&nbsp;25&nbsp;&nbsp;&nbsp;50 km</div>
      <div className="terrain-legend"><i /> Mạng sông <b /> Địa hình chỉ thị</div>
    </div>
  )
}
