import { useEffect, useState } from 'react';
import { api, type DemoSession } from '../api';

type Line = { id: string; version: number; expenseId: string; state: string; needsResubmission: boolean; receiptUrl: string; questions: { id: string; question: string; response: string | null }[]; snapshot: { facts: Record<string, string | null>; calculation: { claimGbp: string; fullGbp: string; outcome: string; clauses: string[]; policyVersion: string }; supportingDocumentIds: string[] } };
type ReviewReport = { reportId: string; header: { name: string; businessPurpose: string }; approvedClaimGbp: string; pendingSubmittedClaimGbp: string; submissions: { id: string; version: number; lines: Line[] }[] };
type Preview = { previewToken: string; approvedClaimGbp: string; lines: { lineId: string; merchant: string; claimGbp: string }[] };
export default function ManagerWorkspace({ session, onChanged }: { session: DemoSession; onChanged: () => void }) {
  const [reports, setReports] = useState<ReviewReport[]>([]), [selected, setSelected] = useState(''), [chosen, setChosen] = useState<string[]>([]), [messages, setMessages] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null), [releaseBody, setReleaseBody] = useState<Record<string, unknown> | null>(null), [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [reload, setReload] = useState(0);
  const report = reports.find(value => value.reportId === selected), lines = report?.submissions.flatMap(value => value.lines) || [];
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    api<{ reports: ReviewReport[] }>('/review/reports', { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setReports(value.reports); setSelected(old => value.reports.some(item => item.reportId === old) ? old : value.reports[0]?.reportId || ''); } }).catch(value => { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : 'Review unavailable.'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);
  async function decision(line: Line, action: 'hold' | 'return' | 'question') {
    setBusy(true); setError('');
    try { await api(`/review/lines/${line.id}/decisions`, { method: 'POST', csrf: session.csrfToken, body: { requestId: crypto.randomUUID(), version: line.version, action, message: messages[line.id] || 'Please review the evidence for this line.' } }); setChosen(value => value.filter(id => id !== line.id)); setPreview(null); setReload(value => value + 1); onChanged(); }
    catch (value) { setError(value instanceof Error ? value.message : 'Decision failed. Reload submitted snapshots.'); }
    finally { setBusy(false); }
  }
  async function prepare() {
    setBusy(true); setError(''); setConfirmed(false);
    const lineVersions = Object.fromEntries(lines.filter(line => chosen.includes(line.id)).map(line => [line.id, line.version]));
    try { const value = await api<Preview>('/review/release-preview', { method: 'POST', csrf: session.csrfToken, body: { lineVersions } }); setPreview(value); setReleaseBody({ requestId: crypto.randomUUID(), previewToken: value.previewToken, lineVersions, confirmed: true }); }
    catch (value) { setError(value instanceof Error ? value.message : 'Release preview unavailable.'); setPreview(null); }
    finally { setBusy(false); }
  }
  async function release() {
    if (!confirmed || !releaseBody) return; setBusy(true); setError('');
    try { const value = await api<{ approvedTotalGbp: string; releaseId: string }>('/review/releases', { method: 'POST', csrf: session.csrfToken, body: releaseBody }); setNotice(`Approved £${value.approvedTotalGbp}. Release ${value.releaseId} is processing ready. Review any remaining lines below; no payment has occurred.`); setChosen([]); setPreview(null); setReleaseBody(null); setConfirmed(false); setReload(value => value + 1); onChanged(); }
    catch (value) { setError(value instanceof Error ? value.message : 'Approval failed. Refresh the exact preview.'); }
    finally { setBusy(false); }
  }
  return <section className="w-review" aria-label="Manager review">{loading && <p role="status">Loading submitted snapshots…</p>}{error && <p role="alert">{error} <button onClick={() => setReload(value => value + 1)}>Reload review</button></p>}{notice && <p role="status">{notice}</p>}
    {!loading && !reports.length ? <div className="w-manager-empty"><span className="w-draft-badge">Manager inbox</span><h2>No submitted reports</h2><p>Employee drafts stay private. Reports appear here only after explicit submission.</p></div> : <><h2>Review submitted claims</h2><p>Review the exact submitted versions. Holding or returning one line does not block other eligible lines. You cannot waive a policy rule or change an amount.</p>
      <label htmlFor="review-report">Submitted report</label><select id="review-report" value={selected} onChange={event => { setSelected(event.target.value); setChosen([]); setPreview(null); }} disabled={busy}>{reports.map(value => <option key={value.reportId} value={value.reportId}>{value.header.name}</option>)}</select>
      {report && <><h3>{report.header.name}</h3><p>{report.header.businessPurpose}</p><p>Approved: £{report.approvedClaimGbp} · Pending submitted: £{report.pendingSubmittedClaimGbp}</p>
        <button disabled={busy} onClick={() => { setChosen(lines.filter(line => line.state === 'pending' && !line.needsResubmission).map(line => line.id)); setPreview(null); }}>Select pending lines</button>
        {report.submissions.map(submission => <section key={submission.id} aria-label={`Submission ${submission.version}`}><h4>Submission {submission.version}</h4>{submission.lines.map(line => <article key={line.id} className="w-review-line"><label><input type="checkbox" checked={chosen.includes(line.id)} disabled={busy || !['pending', 'held'].includes(line.state) || line.needsResubmission} onChange={event => { setChosen(value => event.target.checked ? [...value, line.id] : value.filter(id => id !== line.id)); setPreview(null); setConfirmed(false); }}/>{line.snapshot.facts.merchant} · £{line.snapshot.calculation.claimGbp} · {line.state}</label>
          <p>{line.snapshot.facts.category} · {line.snapshot.facts.receiptDate} · Original {line.snapshot.facts.transactionCurrency} {line.snapshot.facts.originalAmount} · Full GBP £{line.snapshot.calculation.fullGbp}</p><p>{line.snapshot.calculation.outcome} · {line.snapshot.calculation.policyVersion} · {line.snapshot.calculation.clauses.join(', ')}</p>
          {line.needsResubmission && <p>Facts changed after submission. These are the previous submitted facts; employee resubmission is required.</p>}<a href={line.receiptUrl}>Inspect submitted receipt</a>{line.snapshot.supportingDocumentIds.map(id => <a key={id} href={`${line.receiptUrl}?documentId=${encodeURIComponent(id)}`}>Inspect submitted supporting document</a>)}
          {line.questions.map(question => <div key={question.id}><p>Manager: {question.question}</p><p>Employee: {question.response || 'Awaiting response'}</p></div>)}
          {['pending', 'held', 'returned'].includes(line.state) && <><label htmlFor={`review-message-${line.id}`}>Question or decision context</label><textarea id={`review-message-${line.id}`} maxLength={1000} value={messages[line.id] || ''} placeholder="Please confirm the amount against the original receipt." onChange={event => setMessages(value => ({ ...value, [line.id]: event.target.value }))}/><button disabled={busy} onClick={() => void decision(line, 'question')}>Ask employee and hold line</button><button disabled={busy} onClick={() => void decision(line, 'hold')}>Hold line</button><button disabled={busy} onClick={() => void decision(line, 'return')}>Return for correction</button>
          <button onClick={() => { const context = `Unloop review · ${report.header.name}\n${line.snapshot.facts.merchant} · claimed GBP ${line.snapshot.calculation.claimGbp}\n${messages[line.id] || 'Please review this submitted line.'}\nDiscussion cannot approve or change the claim. Record the resolution in Unloop.`; void navigator.clipboard.writeText(context).then(() => setNotice('Review context copied. Teams is not configured; no external message was sent.')).catch(() => setNotice(context)); }}>Copy review context</button></>}
        </article>)}</section>)}
        <button disabled={busy || !chosen.length} onClick={() => void prepare()}>Preview selected release</button>
        {preview && <fieldset><legend>Exact approval release · £{preview.approvedClaimGbp}</legend>{preview.lines.map(line => <p key={line.lineId}>{line.merchant} · £{line.claimGbp}</p>)}<label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)}/>I approve these exact submitted lines and GBP amounts.</label><button disabled={busy || !confirmed} onClick={() => void release()}>Confirm approval release</button><button disabled={busy} onClick={() => { setPreview(null); setConfirmed(false); }}>Cancel release preview</button></fieldset>}
      </>}
    </>}
  </section>;
}
