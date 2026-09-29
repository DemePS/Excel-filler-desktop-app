// A change the agent is about to make: workbook cells, a text file diff, or another action.

import type { Item } from '../types'

export function Change({ item }: { item: Extract<Item, { kind: 'change' }> }) {
  const event = item.event
  if (event.type === 'cells') {
    return (
      <div className="change">
        <div className="change-title">{event.title}</div>
        <table className="cells">
          <thead>
            <tr><th>Cell</th><th>Now</th><th>New value</th><th>Format</th></tr>
          </thead>
          <tbody>
            {(event.rows ?? []).map((row, i) => (
              <tr key={i}>
                <td className="mono">{row.cell}</td>
                <td className={row.old ? 'old' : 'empty'}>{row.old || 'empty'}</td>
                <td className={row.new ? 'new' : 'empty'}>{row.new || 'empty'}</td>
                <td className="mono muted">{row.format ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {event.more > 0 && <div className="muted">… and {event.more} more cell(s)</div>}
      </div>
    )
  }
  if (event.type === 'diff') {
    return (
      <div className="change">
        <div className="change-title">{event.action} {event.name}</div>
        <pre className="diff">
          {(event.lines ?? []).map((line, i) => (
            <div key={i} className={line.startsWith('+') && !line.startsWith('+++') ? 'add' : line.startsWith('-') && !line.startsWith('---') ? 'del' : line.startsWith('@@') ? 'hunk' : ''}>{line || ' '}</div>
          ))}
        </pre>
      </div>
    )
  }
  return (
    <div className={`change tone-${event.tone}`}>
      <div className="change-title">{event.title}</div>
      {event.lines?.length > 0 && <pre className="panel-lines">{event.lines.join('\n')}</pre>}
    </div>
  )
}
