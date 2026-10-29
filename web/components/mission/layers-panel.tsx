'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export type Layers = {
  plan: boolean
  waypoints: boolean
  gpsTrail: boolean
  radarTrail: boolean
  gpsPoints: boolean
  radarPoints: boolean
  drone: boolean
  truth: boolean
  truthDrone: boolean
  wind: boolean
  highlight: boolean
}

export const DEFAULT_LAYERS: Layers = {
  plan: true,
  waypoints: true,
  gpsTrail: true,
  radarTrail: true,
  gpsPoints: false,
  radarPoints: true,
  drone: true,
  truth: false, // solo para la demo
  truthDrone: true, // solo se pinta con la verdad activa
  wind: true,
  highlight: true,
}

const STORAGE_KEY = 'poc-layers-v1'

/** Casillas de capas; se recuerdan en `localStorage` (que puede fallar: se ignora). */
export function useLayers() {
  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS)
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (raw) setLayers({ ...DEFAULT_LAYERS, ...(JSON.parse(raw) as Partial<Layers>) })
    } catch {
      /* sin almacenamiento: se usan los valores por defecto */
    }
  }, [])
  const update = (next: Layers) => {
    setLayers(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* ídem */
    }
  }
  return [layers, update] as const
}

const ITEMS: { id: keyof Layers; label: string; swatch: string; needs?: keyof Layers }[] = [
  { id: 'plan', label: 'Planned route', swatch: 'border-t-2 border-dashed border-primary w-5' },
  { id: 'waypoints', label: 'Waypoints', swatch: 'size-2.5 rotate-45 border-2 border-primary bg-card' },
  { id: 'gpsTrail', label: 'GPS trail', swatch: 'h-1 w-5 rounded-full bg-accent' },
  { id: 'radarTrail', label: 'Radar trail', swatch: 'h-1 w-5 rounded-full bg-[oklch(0.55_0.12_195)]' },
  { id: 'gpsPoints', label: 'GPS points', swatch: 'size-2 rounded-full bg-accent' },
  { id: 'radarPoints', label: 'Radar points', swatch: 'size-2 rounded-full bg-[oklch(0.55_0.12_195)]' },
  { id: 'drone', label: 'Drone (known position)', swatch: 'size-2.5 rounded-[2px] bg-accent' },
  { id: 'truth', label: 'Show truth', swatch: 'h-1 w-5 rounded-full bg-foreground/70' },
  { id: 'truthDrone', label: 'Drone (true position)', swatch: 'size-2.5 rounded-[2px] border-2 border-dashed border-foreground/70', needs: 'truth' },
  { id: 'wind', label: 'Wind', swatch: 'size-2 rounded-full bg-muted-foreground' },
  { id: 'highlight', label: 'Detection highlight', swatch: 'h-1 w-5 rounded-full bg-destructive/60' },
]

export function LayersPanel({ layers, onChange }: { layers: Layers; onChange: (l: Layers) => void }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Map layers">
      {ITEMS.map((item) => (
        <li key={item.id}>
          <label className={cn('flex cursor-pointer items-center gap-1.5', item.needs && !layers[item.needs] && 'opacity-50')}>
            <input
              type="checkbox"
              checked={layers[item.id]}
              onChange={(e) => onChange({ ...layers, [item.id]: e.target.checked })}
              className="size-3.5 accent-primary"
            />
            <span className={cn('inline-block shrink-0', item.swatch)} aria-hidden="true" />
            <span className={cn(layers[item.id] && 'text-foreground')}>{item.label}</span>
          </label>
        </li>
      ))}
    </ul>
  )
}
