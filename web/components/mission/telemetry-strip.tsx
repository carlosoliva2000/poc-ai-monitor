import type { ActiveFault, PlanFile } from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import { crossTrack, distance } from '@/lib/format'
import { cn } from '@/lib/utils'

type Props = { data: Derived; plan: PlanFile | null; faults: ActiveFault[]; simTime?: number }

/** La telemetría del dron llega por el enlace: sin mensajes durante tanto tiempo, sus celdas se atenúan. */
const TELEMETRY_STALE_S = 5

/** Telemetría: lo último que dice cada fuente. Una fuente silenciada se atenúa. */
export function TelemetryStrip({ data, plan, faults, simTime = 0 }: Props) {
  const gps = data.gps[data.gps.length - 1] ?? null
  const radar = data.radar[data.radar.length - 1] ?? null
  const muted = (s: string) => faults.some((f) => f.source === s && f.mode === 'mute')
  const gpsRadar = gps && radar ? distance(gps, radar) : null
  const dev = gps && plan ? crossTrack(gps, plan.waypoints) : null
  const wind = data.wind?.payload
  const link = data.link?.payload
  const battery = data.battery?.payload
  const autopilot = data.autopilot?.payload
  const age = data.lastTelemetry !== null ? simTime - data.lastTelemetry : null
  const stale = age !== null && age > TELEMETRY_STALE_S
  const noTelemetry = stale ? ` · no telemetry for ${Math.round(age ?? 0)} s (the link is down or the packets are lost)` : ''
  const noFix = data.gpsStatus?.fix === 'none'
  const linkText = data.linkState === 'lost' ? 'LOST' : data.linkState && link?.rssi_dbm != null ? `${link.rssi_dbm.toFixed(0)}` : '—'

  type Item = { label: string; value: string; unit?: string; suffix?: string; title: string; alert?: boolean; dim?: boolean }
  const items: Item[] = [
    { label: 'X', value: gps && !noFix ? gps.x.toFixed(0) : '—', unit: 'm', title: 'Known position, x (m)' + noTelemetry, dim: muted('gps') || stale },
    { label: 'Y', value: gps && !noFix ? gps.y.toFixed(0) : '—', unit: 'm', title: 'Known position, y (m)' + noTelemetry, dim: muted('gps') || stale },
    { label: 'SPEED', value: gps && !noFix ? gps.speed.toFixed(1) : '—', unit: 'm/s', title: 'GPS ground speed (m/s)' + noTelemetry, dim: muted('gps') || stale },
    { label: 'HEADING', value: gps && !noFix ? String(Math.round(gps.heading)).padStart(3, '0') : '—', unit: '°', title: 'GPS course over ground (°)' + noTelemetry, dim: muted('gps') || stale },
    {
      label: 'FIX',
      value: data.gpsStatus ? `${data.gpsStatus.fix} · ${data.gpsStatus.sats}` : '—',
      unit: data.gpsStatus ? 'sat' : undefined,
      title: (data.gpsStatus ? `GPS fix: ${data.gpsStatus.fix}, ${data.gpsStatus.sats} satellites` : 'GPS fix: no data') + noTelemetry,
      alert: data.gpsStatus ? data.gpsStatus.fix !== '3d' : false,
      dim: muted('gps') || stale,
    },
    { label: 'ROUTE DEV.', value: dev !== null ? dev.toFixed(1) : '—', unit: 'm', title: 'Distance from the planned route (m)', alert: (dev ?? 0) > 30 },
    { label: 'GPS–RADAR', value: gpsRadar !== null ? gpsRadar.toFixed(1) : '—', unit: 'm', title: 'Distance between the GPS and the radar positions (m)', alert: (gpsRadar ?? 0) > 25, dim: muted('radar') },
    {
      label: 'WIND',
      value: wind ? wind.speed_mps.toFixed(1) : '—',
      unit: wind ? 'm/s' : undefined,
      suffix: wind ? ` · ${wind.from_deg.toFixed(0)}°` : undefined,
      title: wind ? `Wind: ${wind.speed_mps.toFixed(1)} m/s from ${wind.from_deg.toFixed(0)}°` : 'Wind: no data',
      dim: muted('meteo'),
    },
    {
      label: 'LINK',
      value: linkText,
      unit: data.linkState && data.linkState !== 'lost' ? 'dBm' : undefined,
      title: link
        ? data.linkState === 'lost'
          ? 'Command link lost: our station receives nothing from the drone'
          : `Command link (our station): ${link.rssi_dbm} dBm, ${link.latency_ms} ms, ${link.packet_loss_pct ?? 0} % packets lost`
        : 'Link: no data',
      alert: data.linkState === 'lost' || data.linkState === 'degraded',
    },
    ...(autopilot ? [{ label: 'MODE', value: autopilot.mode.replace('failsafe_', 'failsafe ').replace('_', ' '), title: 'Autopilot mode' + noTelemetry, alert: autopilot.mode !== 'mission', dim: stale }] : []),
    {
      label: 'BATT',
      value: battery ? battery.battery_pct.toFixed(0) : '—',
      unit: '%',
      suffix: battery?.time_remaining_s != null ? ` · ${Math.round(battery.time_remaining_s / 60)} min` : undefined,
      title: 'Battery (%)' + (battery?.time_remaining_s != null ? `, ${Math.round(battery.time_remaining_s / 60)} min left at the current power` : '') + noTelemetry,
      alert: (battery?.battery_pct ?? 100) < 15,
      dim: muted('battery') || stale,
    },
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
