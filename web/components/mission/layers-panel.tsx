'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export type Layers = {
  plan: boolean
  waypoints: boolean
  gpsTrail: boolean
  gpsPoints: boolean
  radarPoints: boolean
  truth: boolean
  wind: boolean
  highlight: boolean
}

export const DEFAULT_LAYERS: Layers = {
  plan: true,
  waypoints: true,
  gpsTrail: true,
  gpsPoints: false,
  radarPoints: true,
  truth: false, // solo para la demo: el agente no la ve
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

const ITEMS: { id: keyof Layers; label: string; swatch: string; note?: string }[] = [
  { id: 'plan', label: 'Ruta planificada', swatch: 'border-t-2 border-dashed border-primary w-5' },
  { id: 'waypoints', label: 'Waypoints', swatch: 'size-2.5 rotate-45 border-2 border-primary bg-card' },
  { id: 'gpsTrail', label: 'Estela del GPS', swatch: 'h-1 w-5 rounded-full bg-accent' },
  { id: 'gpsPoints', label: 'Puntos del GPS', swatch: 'size-2 rounded-full bg-accent' },
  { id: 'radarPoints', label: 'Puntos del radar', swatch: 'size-2 rounded-full bg-[oklch(0.55_0.12_195)]' },
  { id: 'truth', label: 'Mostrar verdad', swatch: 'h-1 w-5 rounded-full bg-foreground/70', note: 'solo simulador, el agente no la ve' },
  { id: 'wind', label: 'Viento', swatch: 'size-2 rounded-full bg-muted-foreground' },
  { id: 'highlight', label: 'Resalte de detecciones', swatch: 'h-1 w-5 rounded-full bg-destructive/60' },
]

export function LayersPanel({ layers, onChange }: { layers: Layers; onChange: (l: Layers) => void }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Capas del mapa">
      {ITEMS.map((item) => (
        <li key={item.id}>
          <label className="flex cursor-pointer items-center gap-1.5" title={item.note}>
            <input
              type="checkbox"
              checked={layers[item.id]}
              onChange={(e) => onChange({ ...layers, [item.id]: e.target.checked })}
              className="size-3.5 accent-primary"
            />
            <span className={cn('inline-block shrink-0', item.swatch)} aria-hidden="true" />
            <span className={cn(layers[item.id] && 'text-foreground')}>{item.label}</span>
            {item.note && <span className="text-[10px] italic">({item.note})</span>}
          </label>
        </li>
      ))}
    </ul>
  )
}
