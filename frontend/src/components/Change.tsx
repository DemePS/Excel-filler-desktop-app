// A change the agent is about to make: workbook cells, a text file diff, or another action.

import { useT } from '../i18n'
import type { Item } from '../types'

export function Change({ item }: { item: Extract<Item, { kind: 'change' }> }) {
  const t = useT()
  const event = item.event
  if (event.type === 'cells') {
    return (
      <div className="change">
        <div className="change-title">{t(event.title)}</div>
        <table className="cells">
          <thead>
            <tr><th>{t('Cell')}</th><th>{t('Now')}</th><th>{t('New value')}</th><th>{t('Format')}</th></tr>
          </thead>
          <tbody>
            {(event.rows ?? []).map((row, i) => (
              <tr key={i}>
                <td className="mono">{row.cell}</td>
                <td className={row.old ? 'old' : 'empty'}>{row.old || t('empty')}</td>
                <td className={row.new ? 'new' : 'empty'}>{row.new || t('empty')}</td>
                <td className="mono muted">{row.format ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {event.more > 0 && <div className="muted">{t('… and {n} more cell(s)', { n: event.more })}</div>}
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
