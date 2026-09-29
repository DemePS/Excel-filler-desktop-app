// Approvals and Claude's questions: the agent waits until you answer.

import { useEffect, useRef, useState } from 'react'
import type { Question } from '../types'
import { Change } from './Change'
import { Markdown } from './Markdown'

const LABELS: Record<string, string> = { yes: 'Approve', no: 'Reject', 'always for this session': 'Always' }

export function QuestionDialog({ question, onAnswer }: { question: Question; onAnswer: (value: string | null) => void }) {
  const [text, setText] = useState('')
  const first = useRef<HTMLButtonElement & HTMLTextAreaElement>(null)
  useEffect(() => {
    setText('')
    first.current?.focus()
  }, [question.id])

  return (
    <div className="backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="question-title">
        {question.kind === 'confirm' ? (
          <>
            {question.context?.kind === 'change' && <Change item={question.context} />}
            <h2 id="question-title">{question.question}</h2>
            <div className="actions">
              {question.choices.map((choice, i) => (
                <button key={choice} ref={i === 0 ? first : undefined} className={choice === 'yes' ? 'primary' : choice === 'no' ? 'danger' : ''}
                  onClick={() => onAnswer(choice)}>
                  {LABELS[choice] ?? choice}
                </button>
              ))}
            </div>
          </>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); onAnswer(text) }}>
            {question.context && <div className="asked"><Markdown text={question.context} /></div>}
            <label id="question-title" htmlFor="answer">{question.context ? 'Your answer' : question.prompt.replace(/\s*\(.*\)\s*:?\s*$/, '')}</label>
            <textarea id="answer" ref={first} rows={question.multiline ? 5 : 2} value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) onAnswer(text) }} />
            <div className="actions">
              <button type="button" onClick={() => onAnswer('')}>Skip</button>
              <button type="submit" className="primary">Send</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
