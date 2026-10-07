import { dateLabel, type Report } from '../api';

type Props = { reports: Report[]; selectedId?: string; loading: boolean; onSelect: (id: string) => void; onNew: () => void };

export default function ReportList({ reports, selectedId, loading, onSelect, onNew }: Props) {
  return <aside className="w-report-list" aria-label="Your reports">
    <div className="w-section-title"><h2>Your reports</h2><button className="w-text-button" disabled={loading} onClick={onNew}>New report</button></div>
    <p className="w-muted">Employee drafts</p>
    {loading ? <p role="status">Loading reports…</p> : reports.length === 0 ?
      <p className="w-list-empty">No saved reports yet. Describe your trip to Astra to begin.</p> :
      <ul>{reports.map(report => <li key={report.id}><button className="w-report-link" aria-pressed={selectedId === report.id} onClick={() => onSelect(report.id)}>
        <strong>{report.name}</strong><span>{dateLabel(report.startDate)} – {dateLabel(report.endDate)}</span><small>Draft</small>
      </button></li>)}</ul>}
  </aside>;
}
