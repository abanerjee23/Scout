import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, ApiError, type DemoSession, type Report } from '../api';

type Expense = { id: string; reportId: string; documentId: string; version: number; state: string; facts: Record<string, string | null>; lockedFields: string[]; confirmed: boolean; failureCode: string | null; originalUrl: string; question: { field: string; message: string } | null; calculation: { fullGbp: string; claimGbp: string; excessGbp: string; limitGbp: string; outcome: string; policyVersion: string; clauses: string[]; fx: { rate: string; provider: string; date: string } } | null };
type Evidence = { id: string; filename: string; mimeType: string; state: string };
const labels: Record<string, string> = { queued: 'Queued', processing: 'Reading evidence', needs_information: 'Needs information', policy_inactive: 'Policy inactive — awaiting owner decision', conversion_pending: 'Conversion pending', review: 'Prepared for employee review', failed: 'Processing stopped', unsupported: 'Category unsupported in this increment', unreadable: 'Receipt unreadable', excluded: 'Excluded from claim', conflict: 'Choose one receipt for this Meal' };
const fieldNames: Record<string, string> = { merchant: 'Merchant', receiptDate: 'Receipt date', originalAmount: 'Full receipt total', transactionCurrency: 'Original currency', vatAmount: 'VAT (optional)', category: 'Category', mealType: 'Meal type' };

type Props = { report: Report; session: DemoSession; refresh: number; onError: (error: unknown) => void };
export default function ExpensePanel({ report, session, refresh, onError }: Props) {
  const [rows, setRows] = useState<Expense[]>([]), [documents, setDocuments] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState<string | null>(null), [document, setDocument] = useState('');
  const [facts, setFacts] = useState<Record<string, string | null>>({}), [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [reload, setReload] = useState(0), [total, setTotal] = useState('0.00');
  const editor = useRef<HTMLDivElement>(null), announced = useRef('');
  const active = rows.find(row => row.id === selected);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const [data, evidence] = await Promise.all([api<{ expenses: Expense[]; preparedClaimGbp: string }>(`/reports/${report.id}/expenses`, { signal: controller.signal }), api<{ documents: Evidence[] }>(`/reports/${report.id}/evidence`, { signal: controller.signal })]);
        if (controller.signal.aborted) return;
        setRows(data.expenses); setTotal(data.preparedClaimGbp); setDocuments(evidence.documents); setError('');
        const affected = data.expenses.find(row => row.question && !['queued', 'processing', 'excluded'].includes(row.state));
        if (affected && announced.current !== `${affected.id}:${affected.version}:${affected.state}`) {
          announced.current = `${affected.id}:${affected.version}:${affected.state}`; setSelected(affected.id);
          window.dispatchEvent(new CustomEvent('unloop-expense-question', { detail: { reportId: report.id, expenseId: affected.id, ...affected.question } }));
        }
        if (data.expenses.some(row => ['queued', 'processing'].includes(row.state)) || evidence.documents.some(row => ['queued', 'processing'].includes(row.state))) timer = setTimeout(() => void read(), 1500);
      } catch (problem) { if (!controller.signal.aborted) { setError(problem instanceof Error ? problem.message : 'Expenses unavailable.'); if (problem instanceof ApiError && [401, 403].includes(problem.status)) onError(problem); } }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void read(); return () => { controller.abort(); clearTimeout(timer); };
  }, [report.id, refresh, reload]);
  useEffect(() => {
    if (active) { setFacts(active.facts); setConfirmed(active.confirmed); }
  }, [active?.id, active?.version, active?.state]);
  useEffect(() => {
    function open(event: Event) { const value = (event as CustomEvent).detail; if (value.reportId === report.id) { setSelected(value.expenseId); editor.current?.scrollIntoView({ block: 'nearest' }); } }
    window.addEventListener('unloop-open-expense', open); return () => window.removeEventListener('unloop-open-expense', open);
  }, [report.id]);
  useEffect(() => { if (active?.question) documentElementFocus(active.question.field); }, [active?.id, active?.version, active?.state]);
  function documentElementFocus(field: string) { window.document.getElementById(`expense-${field}`)?.focus({ preventScroll: true }); }
  async function action(path: string, body: unknown, method = 'POST') {
    setBusy(true); setError('');
    try { const result = await api<{ expense?: Expense } & Partial<Expense>>(path, { method, csrf: session.csrfToken, body }); if (result.expense) { setSelected(result.expense.id); if (result.expense.reportId !== report.id) setError('This original already has an expense in another report. No second claim was created.'); } setReload(value => value + 1); }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Expense update failed.'); if (problem instanceof ApiError && [401, 403].includes(problem.status)) onError(problem); }
    finally { setBusy(false); }
  }
  function save(event: FormEvent) { event.preventDefault(); if (active) void action(`/expenses/${active.id}`, { version: active.version, facts, confirmed }, 'PATCH'); }
  const receipt = documents.find(item => item.id === active?.documentId);
  return <section className="w-expenses" aria-label="Expense workspace">
    <h3>Expenses</h3><p className="w-muted">Evidence validation is not extraction. Select a retained receipt to prepare one expense. Model processing requires privately configured, reviewed budgets.</p>
    {loading && <p role="status">Loading saved expenses…</p>}
    {error && <p role="alert">{error} <button onClick={() => setReload(value => value + 1)}>Reload saved data</button></p>}
    <label htmlFor="expense-receipt-select">Selected receipt</label><select id="expense-receipt-select" value={document} onChange={event => setDocument(event.target.value)} disabled={busy}><option value="">Choose validated evidence</option>{documents.filter(item => item.state === 'validated').map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}</select>
    <button disabled={busy || !document} onClick={() => void action(`/reports/${report.id}/expenses`, { documentId: document })}>Prepare selected receipt</button>
    {!loading && !rows.length && <p>No expenses yet. Originals remain private and retained.</p>}
    <ul className="w-expense-lines">{rows.map(row => <li key={row.id}><button onClick={() => setSelected(row.id)} aria-pressed={row.id === selected}>{row.facts.merchant || 'Receipt awaiting facts'} · {labels[row.state] || row.state}</button>{row.calculation && <span> Claim £{row.calculation.claimGbp}</span>}</li>)}</ul>
    <p>Prepared draft total: £{total} — not submitted or approved.</p>
    {active && <div className="w-expense-editor" ref={editor}>
      <div className="w-receipt-view"><h4>Original receipt</h4>{receipt?.mimeType.startsWith('image/') ? <img src={active.originalUrl.replace('/original', '/preview')} alt="Selected original receipt"/> : receipt?.mimeType === 'application/pdf' ? <iframe sandbox="" src={active.originalUrl.replace('/original', '/preview')} title="Selected original PDF receipt"/> : <p>Original retained.</p>}<a href={active.originalUrl}>Download original receipt</a></div>
      <form onSubmit={save} aria-label="Correct expense facts"><h4>{labels[active.state] || active.state}</h4>{active.question && <p className="w-astra-message">Astra: {active.question.message}</p>}{active.failureCode && <p role="status">{active.failureCode}. Your original and saved corrections are retained.</p>}
        {Object.entries(fieldNames).map(([key, label]) => <div key={key}><label htmlFor={`expense-${key}`}>{label}{active.lockedFields.includes(key) ? ' · human locked' : ''}</label>{['category', 'mealType'].includes(key) ? <select id={`expense-${key}`} value={facts[key] ?? ''} onChange={event => { setFacts(previous => ({ ...previous, [key]: event.target.value || null })); setConfirmed(false); }} disabled={busy || (key === 'mealType' && facts.category !== 'meals')}><option value="">Confirm from receipt</option>{(key === 'category' ? ['meals', 'air', 'groundTransport'] : ['breakfast', 'lunch', 'dinner']).map(option => <option key={option} value={option}>{option}</option>)}</select> : <input id={`expense-${key}`} type={key === 'receiptDate' ? 'date' : 'text'} value={facts[key] ?? ''} maxLength={200} onChange={event => { setFacts(previous => ({ ...previous, [key]: event.target.value || null })); setConfirmed(false); }} disabled={busy}/>}</div>)}
        <label><input id="expense-confirm-facts" type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy}/>I checked these facts against the original receipt, including uncertainty, and this is one final restaurant receipt.</label>
        <button disabled={busy}>Save corrections</button><button type="button" disabled={busy} onClick={() => void action(`/expenses/${active.id}/recheck`, { version: active.version })}>Recheck saved facts</button><button type="button" disabled={busy} onClick={() => void action(`/expenses/${active.id}/extract`, { version: active.version })}>Retry extraction</button>
        <button type="button" disabled={busy} onClick={() => void action(`/expenses/${active.id}`, { version: active.version, facts: {}, confirmed: active.confirmed, excluded: active.state !== 'excluded' }, 'PATCH')}>{active.state === 'excluded' ? 'Restore candidate' : 'Exclude from claim'}</button>
        {active.state === 'conflict' && <button type="button" disabled={busy} onClick={() => void action(`/expenses/${active.id}/choose`, { version: active.version })}>Choose this receipt and exclude conflicting Meals</button>}
        {active.calculation && <dl><dt>Full receipt GBP</dt><dd>£{active.calculation.fullGbp}</dd><dt>Claim</dt><dd>£{active.calculation.claimGbp}</dd><dt>Excess</dt><dd>£{active.calculation.excessGbp}</dd><dt>Outcome</dt><dd>{active.calculation.outcome} · {active.calculation.clauses.join(', ')}</dd><dt>FX</dt><dd>{active.calculation.fx.provider} · {active.calculation.fx.rate} · {active.calculation.fx.date}</dd><dt>Policy version</dt><dd>{active.calculation.policyVersion}</dd></dl>}
      </form></div>}
  </section>;
}
