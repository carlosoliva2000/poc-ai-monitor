import type { Connection } from '@/hooks/use-platform'
import type { PlayerState, PlayerStatus } from '@/lib/contracts'
import { cn } from '@/lib/utils'
import { VIEWS, type View } from '@/lib/view'

const STATUS_LABEL: Record<PlayerStatus, string> = {
  idle: 'Idle',
  running: 'Running',
  paused: 'Paused',
  finished: 'Finished',
}

type Props = {
  missionId: string
  state: PlayerState | null
  connection: Connection
  agentBusy: boolean
  view: View
  onView: (view: View) => void
}

export function MissionHeader({ missionId, state, connection, agentBusy, view, onView }: Props) {
  const status = state?.status ?? 'idle'
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border bg-card px-4 py-3">
      <div className="flex items-center gap-3">
        <h1 className="text-base font-semibold tracking-tight text-foreground">Mission console</h1>
        <span className="font-mono text-sm text-muted-foreground">{missionId}</span>
        <span
          className={cn(
            'flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
            status === 'running' ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground',
          )}
        >
          <span className={cn('size-1.5 rounded-full', status === 'running' ? 'animate-pulse bg-accent-foreground' : 'bg-muted-foreground')} aria-hidden="true" />
          {STATUS_LABEL[status]}
        </span>
        {state?.scenario && <span className="font-mono text-xs text-muted-foreground">{state.scenario} · {state.run_id}</span>}
      </div>

      <div className="flex items-center gap-5">
        <ViewSwitch view={view} onView={onView} />
        <dl className="flex items-center gap-5 text-xs">
          <ModuleStatus label="Platform" value={connection === 'open' ? 'connected' : connection === 'connecting' ? 'connecting…' : 'disconnected'} ok={connection === 'open'} />
          <ModuleStatus label="AI module" value={agentBusy ? 'reasoning' : 'ready'} ok />
        </dl>
      </div>
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

/** Conmutador de vista: la del alumno enseña incidentes, evidencias y explicaciones; la del
 *  instructor, además, lo inyectado y la verdad del ejercicio. */
function ViewSwitch({ view, onView }: { view: View; onView: (view: View) => void }) {
  return (
    <div role="radiogroup" aria-label="View" className="flex rounded-md border border-border bg-background p-0.5 text-xs" data-testid="view-switch">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          type="button"
          role="radio"
          aria-checked={view === v.id}
          onClick={() => onView(v.id)}
          title={v.id === 'student' ? 'Student view: incidents, evidence and explanations' : 'Instructor view: also what was injected and the truth of the exercise'}
          className={cn('rounded px-2.5 py-1 font-medium transition-colors', view === v.id ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground')}
        >
          {v.label}
        </button>
      ))}
    </div>
  )
}
