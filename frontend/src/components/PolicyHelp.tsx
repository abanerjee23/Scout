import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, type DemoSession, type Report } from '../api';

type Question = { id: string; state: string; question: string; policyVersion: string; expenseId: string | null; failureCode: string | null; message: string | null; result: { state: string; answer: string; citations: { clauseId: string; quote: string }[]; passages: { id: string; title: string; text: string }[] } | null };
export default function PolicyHelp({ report, session }: { report: Report; session: DemoSession }) {
  const [question, setQuestion] = useState(''), [expenseId, setExpenseId] = useState<string | null>(null);
  const [rows, setRows] = useState<Question[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  const pending = useRef<{ fingerprint: string; id: string } | null>(null);
  useEffect(() => {
    function opened(event: Event) { const value = (event as CustomEvent).detail; if (value.reportId === report.id) setExpenseId(value.expenseId); }
    window.addEventListener('unloop-open-expense', opened); return () => window.removeEventListener('unloop-open-expense', opened);
  }, [report.id]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try { const data = await api<{ questions: Question[] }>(`/reports/${report.id}/policy-questions`, { signal: controller.signal }); if (controller.signal.aborted) return; setRows(data.questions); if (data.questions.some(value => ['queued', 'processing'].includes(value.state))) timer = setTimeout(() => void read(), 1500); }
      catch (value) { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : 'Saved guidance unavailable.'); }
    }
    void read(); return () => { controller.abort(); clearTimeout(timer); };
  }, [report.id, refresh]);
  async function ask(event: FormEvent) {
    event.preventDefault(); if (!question.trim() || busy) return;
    setBusy(true); setError(''); const fingerprint = JSON.stringify([question.trim(), expenseId]);
    if (pending.current?.fingerprint !== fingerprint) pending.current = { fingerprint, id: crypto.randomUUID() };
    try { await api(`/reports/${report.id}/policy-questions`, { method: 'POST', csrf: session.csrfToken, body: { requestId: pending.current.id, question: question.trim(), expenseId } }); pending.current = null; setQuestion(''); setRefresh(value => value + 1); }
    catch (value) { setError(value instanceof Error ? value.message : 'Guidance unavailable. Inspect the policy sources and retry.'); }
    finally { setBusy(false); }
  }
  return <section className="w-evidence" aria-label="Policy help"><h3>Ask about policy</h3><p>Answers explain approved sources. They cannot change facts, claim amounts or approval decisions.</p>
    <form onSubmit={event => void ask(event)}><label htmlFor="policy-question">Your policy question</label><textarea id="policy-question" maxLength={800} value={question} onChange={event => setQuestion(event.target.value)} disabled={busy}/>{expenseId && <p>Linked to the expense opened from Astra. <button type="button" onClick={() => setExpenseId(null)}>Ask about the report instead</button></p>}<button disabled={busy || !question.trim()}>{busy ? 'Saving question…' : 'Ask policy'}</button></form>
    {error && <p role="alert">{error}</p>}
    {rows.map(value => <article key={value.id}><h4>{value.question}</h4><p className="w-muted">{value.policyVersion} · {value.state}</p>{value.expenseId && <button onClick={() => window.dispatchEvent(new CustomEvent('unloop-open-expense', { detail: { reportId: report.id, expenseId: value.expenseId } }))}>Open linked expense</button>}{value.result ? <><p>{value.result.answer}</p>{value.result.citations.map((citation, index) => <details key={index}><summary>{citation.clauseId} · inspect passage</summary><blockquote>{citation.quote}</blockquote><p style={{ whiteSpace: 'pre-wrap' }}>{value.result?.passages.find(source => source.id === citation.clauseId)?.text}</p><small>{value.policyVersion}</small></details>)}</> : value.message ? <p>{value.message} {value.failureCode}</p> : <p role="status">Preparing guidance…</p>}</article>)}
  </section>;
}
