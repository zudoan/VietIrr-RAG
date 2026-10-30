import { motion, useReducedMotion } from 'motion/react'
import type { PropsWithChildren } from 'react'

export function SectionReveal({ children, className = '', delay = 0 }: PropsWithChildren<{ className?: string; delay?: number }>) {
  const reducedMotion = useReducedMotion()
  return (
    <motion.div
      className={className}
      initial={reducedMotion ? false : { opacity: 0, y: 24 }}
      whileInView={reducedMotion ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.18 }}
      transition={{ duration: 0.65, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}
