import type { Connection } from '@/hooks/use-platform'
import type { PlayerState, PlayerStatus } from '@/lib/contracts'
import { cn } from '@/lib/utils'

const STATUS_LABEL: Record<PlayerStatus, string> = {
  idle: 'En espera',
  running: 'En ejecución',
  paused: 'En pausa',
  finished: 'Finalizada',
}

type Props = {
  missionId: string
  state: PlayerState | null
  connection: Connection
  waiting: boolean
  agentBusy: boolean
}

export function MissionHeader({ missionId, state, connection, waiting, agentBusy }: Props) {
  const status = state?.status ?? 'idle'
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border bg-card px-4 py-3">
      <div className="flex items-center gap-3">
        <h1 className="text-base font-semibold tracking-tight text-foreground">Consola de misión</h1>
        <span className="font-mono text-sm text-muted-foreground">{missionId}</span>
        <span
          className={cn(
            'flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
            status === 'running' ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground',
          )}
        >
          <span className={cn('size-1.5 rounded-full', status === 'running' ? 'animate-pulse bg-accent-foreground' : 'bg-muted-foreground')} aria-hidden="true" />
          {waiting ? 'Esperando al monitor' : STATUS_LABEL[status]}
        </span>
        {state?.scenario && <span className="font-mono text-xs text-muted-foreground">{state.scenario} · {state.run_id}</span>}
      </div>

      <dl className="flex items-center gap-5 text-xs">
        <ModuleStatus label="Plataforma" value={connection === 'open' ? 'conectada' : connection === 'connecting' ? 'conectando…' : 'sin conexión'} ok={connection === 'open'} />
        <ModuleStatus label="Módulo de IA" value={agentBusy ? 'razonando' : 'listo'} ok />
      </dl>
    </header>
  )
}

function ModuleStatus({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn('size-2 rounded-full', ok ? 'bg-primary' : 'bg-destructive')} aria-hidden="true" />
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-foreground">{value}</dd>
    </div>
  )
}
