import { dateLabel, type Report, type DemoSession } from '../api';
import EvidencePanel from './EvidencePanel';
import GmailPanel from './GmailPanel';

export default function ReportWorkspace({ report, loading, session, refresh, onUploaded, onError }: { report: Report | null; loading: boolean; session: DemoSession; refresh: number; onUploaded: () => void; onError: (error: unknown) => void }) {
  return <section className="w-report-workspace" aria-label="Selected report">
    {loading ? <p role="status">Opening report…</p> : report ? <>
      <div className="w-paper-title"><span className="w-draft-badge">Employee draft</span><h2>{report.name}</h2><p>{dateLabel(report.startDate)} – {dateLabel(report.endDate)}</p></div>
      <dl className="w-saved-details"><div><dt>Business purpose</dt><dd>{report.businessPurpose}</dd></div><div><dt>Report currency</dt><dd>GBP</dd></div><div><dt>Visibility</dt><dd>Private to Employee mode</dd></div></dl>
      <div className="w-expense-empty"><h3>No expenses yet</h3><p>Your report header is saved. Upload and validate your evidence below. Expense extraction is not available yet.</p></div>
      <EvidencePanel key={report.id} report={report} session={session} source="workspace" refresh={refresh} onUploaded={onUploaded} onError={onError}/>
      <GmailPanel key={`gmail:${report.id}`} report={report} session={session} onImported={onUploaded} onError={onError}/>
      <p className="w-saved-note">Saved in this demo session. You can reopen it from Your reports.</p>
    </> : <div className="w-workspace-empty"><div className="w-paper-symbol" aria-hidden="true"><span/><span/><span/></div>
      <h2>Your report starts here</h2><p>Describe the trip, review the details and confirm. Astra will open the saved report here.</p>
    </div>}
  </section>;
}
