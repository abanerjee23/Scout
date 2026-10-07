import { useEffect, useState, type FormEvent } from 'react';
import EvidencePanel from './EvidencePanel';
import { ApiError, api, type DemoSession, type Header, type Report, type Proposal } from '../api';

const EXAMPLE = 'Prepare my London expense report for 1–4 October 2026 for a client workshop.';
type Props = { session: DemoSession; onSaved: (report: Report) => void; onError: (error: unknown) => void; report: Report | null; refresh: number; onUploaded: () => void };

export default function AstraIntake({ session, onSaved, onError, report, refresh, onUploaded }: Props) {
  const [expenseQuestion, setExpenseQuestion] = useState<{ expenseId: string; message: string } | null>(null);
  useEffect(() => {
    setExpenseQuestion(null);
    function receive(event: Event) { const detail = (event as CustomEvent).detail; if (detail.reportId === report?.id) setExpenseQuestion(detail); }
    window.addEventListener('unloop-expense-question', receive); return () => window.removeEventListener('unloop-expense-question', receive);
  }, [report?.id]);
  const [message, setMessage] = useState('');
  const [description, setDescription] = useState('');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [header, setHeader] = useState<Header>({ name: '', startDate: '', endDate: '', businessPurpose: '' });
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [fields, setFields] = useState<{ field: string; message: string }[]>([]);

  async function describe(event: FormEvent) {
    event.preventDefault(); setBusy(true); setFeedback(''); setFields([]);
    try {
      const next = await api<Proposal>('/report-proposals', { method: 'POST', csrf: session.csrfToken, body: { message } });
      setDescription(message); setProposal(next); setHeader(next.header);
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault(); if (!proposal) return;
    setBusy(true); setFields([]); setFeedback('');
    try {
      const report = await api<Report>('/reports', { method: 'POST', csrf: session.csrfToken,
        body: { proposalToken: proposal.proposalToken, confirmed: true, header } });
      onSaved(report); setProposal(null); setMessage(''); setDescription('');
      setFeedback(`Saved “${report.name}”. Your report is ready to reopen.`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) setFields(error.fields);
      else onError(error);
    } finally { setBusy(false); }
  }

  const change = (field: keyof Header, value: string) => setHeader(previous => ({ ...previous, [field]: value }));
  return <section className="w-astra" aria-label="Astra chat">
    <div className="w-astra-title"><span className="w-astra-mark" aria-hidden="true">a</span><div><h2>Astra</h2><p>Let’s prepare your report.</p></div></div>
    <div className="w-chat-intro"><h3>Start with the trip.</h3><p>Tell me the report name, dates with a year, and business purpose. You’ll review everything before it is saved.</p><button className="w-example" onClick={() => setMessage(EXAMPLE)} disabled={busy}>Use a London workshop example</button></div>
    <form onSubmit={describe} className="w-chat-composer"><label htmlFor="report-description">Describe your report</label><textarea id="report-description" value={message} onChange={event => setMessage(event.target.value)} required maxLength={2000} disabled={busy} rows={3} placeholder="London, 1–4 October 2026, for a client workshop…"/><button className="w-primary" disabled={busy || !message.trim()}>{busy ? 'Working…' : 'Propose report'}</button></form>
    {report && <EvidencePanel key={report.id} report={report} session={session} source="chat" refresh={refresh} onUploaded={onUploaded} onError={onError}/>}
    {expenseQuestion && <div className="w-astra-message"><p>{expenseQuestion.message}</p><button onClick={() => window.dispatchEvent(new CustomEvent('unloop-open-expense', { detail: { reportId: report?.id, expenseId: expenseQuestion.expenseId } }))}>Open expense</button></div>}
    {feedback && <p className="w-success" role="status">{feedback}</p>}
    {proposal && <>
      <p className="w-user-message">{description}</p><p className="w-astra-message" role="status">{proposal.message}</p>
      <form className="w-confirmation" onSubmit={confirm} aria-label="Review report header">
        <h3>Review report details</h3><p className="w-muted">Edit any field. Nothing is saved until you confirm.</p>
        <label htmlFor="report-name">Report name</label><input id="report-name" value={header.name} onChange={event => change('name', event.target.value)} minLength={3} maxLength={120} required disabled={busy}/>
        <div className="w-date-fields"><div><label htmlFor="report-start">Start date</label><input id="report-start" type="date" value={header.startDate} onChange={event => change('startDate', event.target.value)} min="2000-01-01" max="2100-12-31" required disabled={busy}/></div><div><label htmlFor="report-end">End date</label><input id="report-end" type="date" value={header.endDate} onChange={event => change('endDate', event.target.value)} min="2000-01-01" max="2100-12-31" required disabled={busy}/></div></div>
        <label htmlFor="report-purpose">Business purpose</label><input id="report-purpose" value={header.businessPurpose} onChange={event => change('businessPurpose', event.target.value)} minLength={5} maxLength={500} required disabled={busy}/>
        {fields.length > 0 && <ul className="w-field-errors" role="alert">{fields.map((field, index) => <li key={index}>{field.field}: {field.message}</li>)}</ul>}
        <button className="w-primary" disabled={busy}>Confirm and create report</button>
      </form>
    </>}
  </section>;
}
