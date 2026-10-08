import { useEffect, useRef, useState } from 'react';
import { api, type DemoSession, type Report } from '../api';

type Line = { expenseId: string; merchant: string; claimGbp: string };
type Preview = { previewToken: string; eligibleLines: Line[]; blockedLines: { expenseId: string; state: string }[]; eligibleClaimGbp: string };
type Discussion = { lineId: string; expenseId: string; state: string; questions: { id: string; version: number; question: string; response: string | null }[] };
type Status = { approvedClaimGbp: string; pendingSubmittedClaimGbp: string; submissions: { id: string; version: number; claimGbp: string; lines: { state: string; expenseId: string; snapshot: { calculation: { claimGbp: string } } }[] }[] };
export default function SubmissionPanel({ report, session, refresh, onChanged }: { report: Report; session: DemoSession; refresh: number; onChanged: () => void }) {
  const [preview, setPreview] = useState<Preview | null>(null), [chosen, setChosen] = useState<string[]>([]), [confirmed, setConfirmed] = useState(false);
  const [status, setStatus] = useState<Status | null>(null), [discussions, setDiscussions] = useState<Discussion[]>([]), [replies, setReplies] = useState<Record<string, string>>({});
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [reload, setReload] = useState(0);
  const requestId = useRef('');
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api<Status>(`/reports/${report.id}/submissions`, { signal: controller.signal }), api<{ lines: Discussion[] }>(`/reports/${report.id}/review-questions`, { signal: controller.signal })]).then(([value, questions]) => { if (!controller.signal.aborted) { setStatus(value); setDiscussions(questions.lines); } }).catch(value => { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : 'Review status unavailable.'); });
    return () => controller.abort();
  }, [report.id, refresh, reload]);
  async function prepare() {
    setBusy(true); setError(''); setConfirmed(false);
    try { const value = await api<Preview>(`/reports/${report.id}/submission-preview`, { method: 'POST', csrf: session.csrfToken, body: {} }); setPreview(value); setChosen(value.eligibleLines.map(line => line.expenseId)); requestId.current = crypto.randomUUID(); }
    catch (value) { setError(value instanceof Error ? value.message : 'Submission preview unavailable.'); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!preview || !confirmed || !chosen.length) return;
    setBusy(true); setError('');
    try { await api(`/reports/${report.id}/submissions`, { method: 'POST', csrf: session.csrfToken, body: { requestId: requestId.current, previewToken: preview.previewToken, expenseIds: chosen, confirmed: true } }); setPreview(null); setConfirmed(false); setReload(value => value + 1); onChanged(); }
    catch (value) { setError(value instanceof Error ? value.message : 'Submission failed. Refresh the preview.'); }
    finally { setBusy(false); }
  }
  async function reply(id: string, version: number) {
    setBusy(true); setError('');
    try { await api(`/review-questions/${id}/responses`, { method: 'POST', csrf: session.csrfToken, body: { version, response: replies[id] } }); setReload(value => value + 1); onChanged(); }
    catch (value) { setError(value instanceof Error ? value.message : 'Response failed.'); }
    finally { setBusy(false); }
  }
  return <section className="w-evidence" aria-label="Submission and review"><h3>Submit for manager review</h3><p>Only explicitly submitted snapshots enter Manager mode. Remaining draft lines stay private. Approved amounts are processing ready; no payment is performed.</p>
    <p>Approved: £{status?.approvedClaimGbp || '0.00'} · Pending submitted: £{status?.pendingSubmittedClaimGbp || '0.00'}</p>
    {error && <p role="alert">{error}</p>}<button disabled={busy} onClick={() => void prepare()}>Preview eligible submission</button>
    {preview && <fieldset><legend>Exact lines for submission</legend>{preview.eligibleLines.length ? preview.eligibleLines.map(line => <label key={line.expenseId}><input type="checkbox" checked={chosen.includes(line.expenseId)} disabled={busy} onChange={event => { setChosen(value => event.target.checked ? [...value, line.expenseId] : value.filter(id => id !== line.expenseId)); setConfirmed(false); }}/>{line.merchant} · £{line.claimGbp}</label>) : <p>No eligible lines. Resolve evidence, conversion and policy checks first.</p>}
      {preview.blockedLines.length > 0 && <p>{preview.blockedLines.length} unresolved line(s) remain private. You can submit the selected eligible subset or wait.</p>}
      <label><input type="checkbox" checked={confirmed} disabled={busy || !chosen.length} onChange={event => setConfirmed(event.target.checked)}/>I reviewed these selected GBP claims and want to submit their exact saved versions.</label>
      <button disabled={busy || !confirmed || !chosen.length} onClick={() => void submit()}>Confirm and submit selected lines</button><button disabled={busy} onClick={() => setPreview(null)}>Wait and resolve remaining lines</button></fieldset>}
    {status?.submissions.map(value => <p key={value.id}>Submission {value.version} · £{value.claimGbp} · {value.lines.map(line => line.state).join(', ')}</p>)}
    {discussions.filter(line => line.questions.length).map(line => <article key={line.lineId}><h4>Manager discussion · {line.state}</h4><button onClick={() => window.dispatchEvent(new CustomEvent('unloop-open-expense', { detail: { reportId: report.id, expenseId: line.expenseId } }))}>Open affected expense</button>{line.questions.map(question => <div key={question.id}><p>{question.question}</p>{question.response && <p>Your response: {question.response}</p>}{!['approved', 'superseded'].includes(line.state) && <><label htmlFor={`reply-${question.id}`}>Response to manager</label><textarea id={`reply-${question.id}`} maxLength={1500} value={replies[question.id] || ''} onChange={event => setReplies(value => ({ ...value, [question.id]: event.target.value }))}/><button disabled={busy || !replies[question.id]?.trim()} onClick={() => void reply(question.id, question.version)}>Send in-app response</button></>}</div>)}<p>Material corrections require a new preview and explicit resubmission. A response alone does not replace submitted facts.</p></article>)}
  </section>;
}
