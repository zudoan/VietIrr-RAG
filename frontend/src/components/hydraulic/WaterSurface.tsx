import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

interface WaterSurfaceProps {
  width?: number
  length?: number
  position?: [number, number, number]
  rotation?: [number, number, number]
  color?: string
  flowSpeed?: number
  waveHeight?: number
}

export function WaterSurface({
  width = 14,
  length = 10,
  position = [0, 0, 0],
  rotation = [-Math.PI / 2, 0, 0],
  color = '#2d7a86',
  flowSpeed = 0.8,
  waveHeight = 0.08,
}: WaterSurfaceProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const materialRef = useRef<THREE.MeshStandardMaterial>(null)

  const geometry = useMemo(() => {
    return new THREE.PlaneGeometry(width, length, 48, 36)
  }, [width, length])

  const originalPositions = useMemo(() => {
    return geometry.attributes.position.array.slice()
  }, [geometry])

  useEffect(() => {
    return () => {
      geometry.dispose()
    }
  }, [geometry])

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const time = clock.getElapsedTime() * flowSpeed
    const pos = geometry.attributes.position
    const orig = originalPositions

    for (let i = 0; i < pos.count; i++) {
      const u = orig[i * 3]
      const v = orig[i * 3 + 1]
      // Wave equation combining 2 harmonic sine waves
      const wave = Math.sin(u * 1.5 + time * 2.0) * Math.cos(v * 1.2 + time * 1.5) * waveHeight
      const ripple = Math.sin((u + v) * 2.5 + time * 3.0) * (waveHeight * 0.4)
      pos.setZ(i, wave + ripple)
    }
    pos.needsUpdate = true
    geometry.computeVertexNormals()
  })

  return (
    <mesh
      ref={meshRef}
      geometry={geometry}
      position={position}
      rotation={rotation}
      receiveShadow
    >
      <meshStandardMaterial
        ref={materialRef}
        color={color}
        roughness={0.15}
        metalness={0.4}
        transparent
        opacity={0.88}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}
