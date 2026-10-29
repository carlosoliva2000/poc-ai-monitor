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

  type Item = { label: string; value: string; unit?: string; suffix?: string; title: string; alert?: boolean; dim?: boolean }
  const items: Item[] = [
    { label: 'X', value: gps ? gps.x.toFixed(0) : '—', unit: 'm', title: 'Known position, x (m)', dim: muted('gps') },
    { label: 'Y', value: gps ? gps.y.toFixed(0) : '—', unit: 'm', title: 'Known position, y (m)', dim: muted('gps') },
    { label: 'SPEED', value: gps ? gps.speed.toFixed(1) : '—', unit: 'm/s', title: 'GPS ground speed (m/s)', dim: muted('gps') },
    { label: 'HEADING', value: gps ? String(Math.round(gps.heading)).padStart(3, '0') : '—', unit: '°', title: 'GPS course over ground (°)', dim: muted('gps') },
    {
      label: 'FIX',
      value: gps ? `${gps.fix} · ${gps.sats}` : '—',
      unit: gps ? 'sat' : undefined,
      title: gps ? `GPS fix: ${gps.fix}, ${gps.sats} satellites` : 'GPS fix: no data',
      alert: gps ? gps.fix !== '3d' : false,
      dim: muted('gps'),
    },
    { label: 'ROUTE DEV.', value: dev !== null ? dev.toFixed(1) : '—', unit: 'm', title: 'Distance from the planned route (m)', alert: (dev ?? 0) > 30 },
    { label: 'GPS–RADAR', value: gpsRadar !== null ? gpsRadar.toFixed(1) : '—', unit: 'm', title: 'Distance between the GPS and the radar positions (m)', alert: (gpsRadar ?? 0) > 25, dim: muted('radar') },
    {
      label: 'WIND',
      value: wind ? wind.speed_mps.toFixed(1) : '—',
      unit: wind ? 'm/s' : undefined,
      suffix: wind ? ` · ${wind.from_deg.toFixed(0)}°` : undefined,
      title: wind ? `Wind: ${wind.speed_mps.toFixed(1)} m/s from ${wind.from_deg.toFixed(0)}° (gust ${wind.gust_mps.toFixed(1)} m/s)` : 'Wind: no data',
      dim: muted('meteo'),
    },
    { label: 'LINK', value: link ? link.controller_id : '—', title: link ? `Link: controlled by ${link.controller_id}` : 'Link: no data', dim: muted('link') },
    { label: 'BATT', value: battery ? battery.battery_pct.toFixed(0) : '—', unit: '%', title: 'Battery (%)', alert: (battery?.battery_pct ?? 100) < 45, dim: muted('battery') },
  ]

  // Celdas con el ancho de su contenido (sin recortar nada): si no caben en una fila, la barra pasa
  // a dos y las celdas se reparten el ancho sobrante.
  return (
    <dl className="flex flex-wrap gap-px border-t border-border bg-border">
      {items.map((item) => (
        <div key={item.label} title={item.title} className={cn('flex flex-auto flex-col gap-0.5 bg-card px-3 py-2 transition-opacity', item.dim && 'opacity-35')}>
          <dt className="whitespace-nowrap text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{item.label}</dt>
          <dd className={cn('whitespace-nowrap font-mono text-sm tabular-nums', item.alert ? 'font-medium text-accent' : 'text-foreground')}>
            {item.value}
            {item.unit && <span className="ml-0.5 text-xs text-muted-foreground">{item.unit}</span>}
            {item.suffix}
          </dd>
        </div>
      ))}
    </dl>
  )
}
