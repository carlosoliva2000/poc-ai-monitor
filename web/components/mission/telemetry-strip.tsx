import type { ActiveFault, PlanFile } from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import { crossTrack, distance } from '@/lib/format'
import { cn } from '@/lib/utils'

type Props = { data: Derived; plan: PlanFile | null; faults: ActiveFault[] }

/** Telemetría: lo último que dice cada fuente. Una fuente silenciada se atenúa. */
export function TelemetryStrip({ data, plan, faults }: Props) {
  const gps = data.gps[data.gps.length - 1] ?? null
  const radar = data.radar[data.radar.length - 1] ?? null
  const muted = (s: string) => faults.some((f) => f.source === s && f.mode === 'mute')
  const gpsRadar = gps && radar ? distance(gps, radar) : null
  const dev = gps && plan ? crossTrack(gps, plan.waypoints) : null
  const wind = data.wind?.payload
  const link = data.link?.payload
  const battery = data.battery?.payload

  const items: { label: string; value: string; unit?: string; alert?: boolean; dim?: boolean }[] = [
    { label: 'X', value: gps ? gps.x.toFixed(0) : '—', unit: 'm', dim: muted('gps') },
    { label: 'Y', value: gps ? gps.y.toFixed(0) : '—', unit: 'm', dim: muted('gps') },
    { label: 'VEL', value: gps ? gps.speed.toFixed(1) : '—', unit: 'm/s', dim: muted('gps') },
    { label: 'RUMBO', value: gps ? String(Math.round(gps.heading)).padStart(3, '0') : '—', unit: '°', dim: muted('gps') },
    { label: 'FIX', value: gps ? `${gps.fix} · ${gps.sats} sat` : '—', alert: gps ? gps.fix !== '3d' : false, dim: muted('gps') },
    { label: 'DESV. RUTA', value: dev !== null ? dev.toFixed(1) : '—', unit: 'm', alert: (dev ?? 0) > 30 },
    { label: 'GPS–RADAR', value: gpsRadar !== null ? gpsRadar.toFixed(1) : '—', unit: 'm', alert: (gpsRadar ?? 0) > 25, dim: muted('radar') },
    { label: 'VIENTO', value: wind ? `${wind.speed_mps.toFixed(1)} · ${wind.from_deg.toFixed(0)}°` : '—', unit: 'm/s', dim: muted('meteo') },
    { label: 'ENLACE', value: link ? link.controller_id : '—', dim: muted('link') },
    { label: 'BAT', value: battery ? battery.battery_pct.toFixed(0) : '—', unit: '%', alert: (battery?.battery_pct ?? 100) < 45, dim: muted('battery') },
  ]

  return (
    <dl className="grid grid-cols-3 border-t border-border bg-card sm:grid-cols-5 xl:grid-cols-10">
      {items.map((item) => (
        <div key={item.label} className={cn('flex flex-col gap-0.5 border-b border-r border-border px-3 py-2 transition-opacity xl:border-b-0', item.dim && 'opacity-35')}>
          <dt className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{item.label}</dt>
          <dd className={cn('truncate font-mono text-sm tabular-nums', item.alert ? 'font-medium text-accent' : 'text-foreground')}>
            {item.value}
            {item.unit && <span className="ml-0.5 text-xs text-muted-foreground">{item.unit}</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}
