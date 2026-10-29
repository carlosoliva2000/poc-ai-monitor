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
  coordinates: boolean
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
  truthDrone: false, // solo para la demo; independiente de la traza de la verdad
  wind: true,
  highlight: true,
  coordinates: false,
}

const STORAGE_KEY = 'poc-layers-v2'

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

type Item = { id: keyof Layers; label: string; swatch: string; title?: string }

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: 'Plan',
    items: [
      { id: 'plan', label: 'Planned route', swatch: 'border-t-2 border-dashed border-primary w-5' },
      { id: 'waypoints', label: 'Waypoints', swatch: 'size-2.5 rotate-45 border-2 border-primary bg-card' },
    ],
  },
  {
    title: 'Tracks',
    items: [
      { id: 'gpsTrail', label: 'GPS trail', swatch: 'h-1 w-5 rounded-full bg-accent' },
      { id: 'radarTrail', label: 'Radar trail', swatch: 'h-1 w-5 rounded-full bg-[oklch(0.55_0.12_195)]' },
      { id: 'truth', label: 'Truth trail', swatch: 'h-1 w-5 rounded-full bg-foreground/70', title: 'Show truth: the real trajectory (demo only)' },
    ],
  },
  {
    title: 'Points',
    items: [
      { id: 'gpsPoints', label: 'GPS points', swatch: 'size-2 rounded-full bg-accent' },
      { id: 'radarPoints', label: 'Radar points', swatch: 'size-2 rounded-full bg-[oklch(0.55_0.12_195)]' },
    ],
  },
  {
    title: 'Drone',
    items: [
      { id: 'drone', label: 'Known position', swatch: 'size-2.5 rounded-[2px] bg-accent', title: 'Known position · GPS course over ground' },
      { id: 'truthDrone', label: 'True position', swatch: 'size-2.5 rounded-[2px] border-2 border-dashed border-foreground/70', title: 'True position · nose heading' },
    ],
  },
  {
    title: 'Overlays',
    items: [
      { id: 'wind', label: 'Wind', swatch: 'size-2 rounded-full bg-muted-foreground' },
      { id: 'highlight', label: 'Detection highlight', swatch: 'h-1 w-5 rounded-full bg-destructive/60' },
      { id: 'coordinates', label: 'Coordinates', swatch: 'size-2.5 border border-muted-foreground/70' },
    ],
  },
]

export function LayersPanel({ layers, onChange }: { layers: Layers; onChange: (l: Layers) => void }) {
  return (
    <div className="flex flex-wrap items-stretch gap-1.5 text-xs text-muted-foreground" role="group" aria-label="Map layers">
      {GROUPS.map((group) => (
        <fieldset key={group.title} className="m-0 min-w-0 rounded-md border border-border/70 px-2 pb-1 pt-0">
          <legend className="px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/80">{group.title}</legend>
          <ul className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
            {group.items.map((item) => (
              <li key={item.id}>
                <label className="flex cursor-pointer items-center gap-1.5" title={item.title}>
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
        </fieldset>
      ))}
    </div>
  )
}
