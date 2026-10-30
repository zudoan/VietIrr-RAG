import { Html } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useRef, useState } from 'react'
import * as THREE from 'three'

export interface HotspotInfo {
  id: 'reservoir' | 'spillway' | 'canal'
  title: string
  subtitle: string
  elevation: string
  capacity: string
  flowRate: string
  structureType: string
  description: string
  sampleQueries: string[]
  position: [number, number, number]
  cameraTarget: [number, number, number]
}

export const HYDRAULIC_HOTSPOTS: HotspotInfo[] = [
  {
    id: 'reservoir',
    title: 'Hồ chứa nước đầu mối',
    subtitle: 'Thượng lưu đập chính · Trữ lượng điều tiết',
    elevation: '+45.00 m (MNDBT)',
    capacity: '124,5 triệu m³',
    flowRate: 'Dung tích hữu ích: 98,2 triệu m³',
    structureType: 'Hồ chứa thủy lợi đa mục tiêu (cấp nước, phòng lũ)',
    description: 'Khu vực lòng hồ thượng lưu tích trữ và điều tiết dòng chảy lưu vực sông. Dữ liệu quan trắc phục vụ dự báo nguy cơ hạn hán và nguồn nước mặt.',
    sampleQueries: [
      'Theo dự báo nguồn nước phục vụ sản xuất nông nghiệp thuộc tỉnh Ninh Bình năm 2019, dung tích bình quân các hồ chứa đạt bao nhiêu %?',
      'Chỉ tiêu Dự báo vụ mùa năm 2019 — Dung tích cuối vụ so với TK (%) của Hồ Suối Mỡ là bao nhiêu?',
    ],
    position: [-2.8, 1.2, -2.5],
    cameraTarget: [-2.0, 1.0, -1.8],
  },
  {
    id: 'spillway',
    title: 'Cửa xả lũ & Thân đập bê tông',
    subtitle: 'Đập bê tông trọng lực & Cửa van cung',
    elevation: 'Cao trình đỉnh đập: +52.50 m',
    capacity: 'Khả năng xả lũ thiết kế: 1.850 m³/s',
    flowRate: 'Chiều rộng tràn xả: 3 khoang x 10 m',
    structureType: 'Bê tông cốt thép M300, cửa van cung điều khiển thủy lực',
    description: 'Thân đập chính chịu áp lực cột nước và cụm công trình xả sâu/xả tràn đảm bảo an toàn đập trong mùa mưa lũ, chống ngập lụt hạ du.',
    sampleQueries: [
      'Quy định về quy trình vận hành liên hồ chứa và xả lũ an toàn trong mùa mưa bão theo Quyết định của Thủ tướng?',
      'Bản tin dự báo nguồn nước Lưu vực sông Thương (Từ 19/7 đến 25/7/2019), tổng lượng nước mặt huyện Hữu Lũng là bao nhiêu?',
    ],
    position: [0.3, 0.4, 0.2],
    cameraTarget: [0.1, 0.2, 0.5],
  },
  {
    id: 'canal',
    title: 'Kênh dẫn hạ lưu & Trạm điều tiết',
    subtitle: 'Hệ thống kênh tưới tiêu nông nghiệp',
    elevation: 'Cao trình đáy kênh: +18.20 m',
    capacity: 'Diện tích tưới thiết kế: 45.000 ha',
    flowRate: 'Lưu lượng kênh chính: 32,5 m³/s',
    structureType: 'Kênh dẫn bê tông kiên cố hóa kèm cống đầu kênh',
    description: 'Kênh dẫn nước sau bể tiêu năng đưa nước tưới về các vùng canh tác đồng bằng, kết nối với trạm bơm và cống lấy nước phân phối.',
    sampleQueries: [
      'Tiêu chuẩn kỹ thuật thiết kế kênh mương và cống lấy nước tưới theo TCVN ngành Thủy lợi?',
      'Theo Bản tin dự báo nguồn nước Lưu vực sông Lục Nam, diện tích tưới và dung tích các hồ chứa có ghi chú ngoại lệ gì?',
    ],
    position: [2.8, -0.6, 2.8],
    cameraTarget: [2.2, -0.4, 2.2],
  },
]

interface HotspotProps {
  info: HotspotInfo
  active: boolean
  onClick: (info: HotspotInfo) => void
}

export function HotspotMarker({ info, active, onClick }: HotspotProps) {
  const ringRef = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)

  useFrame(({ clock }) => {
    if (!ringRef.current) return
    const time = clock.getElapsedTime()
    const scale = 1 + Math.sin(time * 3 + (info.id === 'reservoir' ? 0 : info.id === 'spillway' ? 2 : 4)) * 0.2
    ringRef.current.scale.set(scale, scale, scale)
  })

  return (
    <group position={info.position}>
      {/* 3D Pulse Rings */}
      <mesh
        ref={ringRef}
        onClick={(e) => {
          e.stopPropagation()
          onClick(info)
        }}
        onPointerOver={(e) => {
          e.stopPropagation()
          setHovered(true)
        }}
        onPointerOut={() => setHovered(false)}
      >
        <ringGeometry args={[0.18, 0.24, 32]} />
        <meshBasicMaterial
          color={active ? '#c9a46b' : hovered ? '#53aeb8' : '#e5eee9'}
          transparent
          opacity={active ? 0.95 : hovered ? 0.85 : 0.6}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Center point */}
      <mesh
        onClick={(e) => {
          e.stopPropagation()
          onClick(info)
        }}
      >
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshBasicMaterial color={active ? '#c9a46b' : '#53aeb8'} />
      </mesh>

      {/* HTML Overlay Marker */}
      <Html distanceFactor={12} position={[0, 0.4, 0]} center>
        <button
          type="button"
          className={`hydraulic-hotspot-label ${active ? 'active' : ''} ${hovered ? 'hovered' : ''}`}
          onClick={() => onClick(info)}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          <span className="hotspot-pin" />
          <span className="hotspot-text">
            <strong>{info.title}</strong>
            <small>{info.elevation}</small>
          </span>
        </button>
      </Html>
    </group>
  )
}
