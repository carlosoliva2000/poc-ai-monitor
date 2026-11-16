'use client'

import { Check, Pencil, X } from 'lucide-react'
import type { Proposal } from '@/lib/contracts'
import { describeWind } from '@/lib/instructor'

export type Decision = 'confirmed' | 'discarded'

type Props = {
  proposal: Proposal
  decision?: Decision
  /** Sin modo interactivo la plataforma rechazaría el comando. */
  canConfirm: boolean
  onConfirm: () => void
  onEdit: () => void
  onDiscard: () => void
}

/** Propuesta del agente del instructor: no se aplica hasta «Confirm». «Edit» abre el panel con
 *  esos valores. */
export function ProposalCard({ proposal, decision, canConfirm, onConfirm, onEdit, onDiscard }: Props) {
  const title = proposal.command === 'cancel_wind' || !proposal.params ? 'Cancel the instructor wind' : describeWind(proposal.params)
  const defaults = proposal.defaults_used.length > 0 ? `Filled in by default: ${proposal.defaults_used.join(', ')}` : null
  return (
    <div className="flex flex-col gap-2 rounded-md border border-warning/50 bg-warning/10 px-3 py-2" data-testid="proposal-card" data-decision={decision ?? 'pending'}>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {defaults && <p className="text-xs text-muted-foreground">{defaults}</p>}
      {decision ? (
        <p className="text-xs text-muted-foreground" role="status">
          {decision === 'confirmed' ? 'Confirmed: sent to the simulation.' : 'Discarded.'}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" disabled={!canConfirm} onClick={onConfirm} className="flex items-center gap-1 rounded-md border border-primary bg-primary px-2.5 py-1 text-xs text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-45">
            <Check className="size-3.5" aria-hidden="true" /> Confirm
          </button>
          {proposal.params && (
            <button type="button" onClick={onEdit} className="flex items-center gap-1 rounded-md border border-border bg-background px-2.5 py-1 text-xs hover:bg-muted">
              <Pencil className="size-3.5" aria-hidden="true" /> Edit
            </button>
          )}
          <button type="button" onClick={onDiscard} className="flex items-center gap-1 rounded-md border border-border bg-background px-2.5 py-1 text-xs hover:bg-muted">
            <X className="size-3.5" aria-hidden="true" /> Discard
          </button>
          {!canConfirm && <span className="text-xs text-muted-foreground">Turn on interactive mode to confirm.</span>}
        </div>
      )}
    </div>
  )
}
