import type { ReactNode } from 'react'

export interface Point { text: string; support: Record<string, unknown>[] }

/** Observations (what the records show) kept visibly apart from suggestions (what you could try). */
export function ObservationsAndSuggestions({ observations, suggestions, renderSupport }: {
  observations: Point[]; suggestions: Point[]; renderSupport: (s: Record<string, unknown>) => ReactNode
}) {
  return (
    <div className="flex flex-col gap-3">
      <section>
        <h4 className="font-semibold">Observations <span className="font-normal text-muted">(from your records)</span></h4>
        <ul className="mt-1 flex flex-col gap-2">
          {observations.map((o, i) => (
            <li key={i}>
              <p>{o.text}</p>
              <details className="text-xs text-muted">
                <summary className="cursor-pointer">Based on {o.support.length} record{o.support.length === 1 ? '' : 's'}</summary>
                <ul className="mt-1 list-inside list-disc">{o.support.map((s, j) => <li key={j}>{renderSupport(s)}</li>)}</ul>
              </details>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h4 className="font-semibold">Suggestions <span className="font-normal text-muted">(ideas to try; nothing is changed)</span></h4>
        {suggestions.length === 0 ? <p className="text-muted">No suggestions passed the checks this time.</p> : (
          <ul className="mt-1 list-inside list-disc">{suggestions.map((s, i) => <li key={i}>{s.text}</li>)}</ul>
        )}
      </section>
    </div>
  )
}
