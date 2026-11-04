import { Activity, CheckCircle2 } from 'lucide-react';
export default function PlaceholderPage({
  title,
  eyebrow,
  description,
  bullets,
  icon: Icon,
}: {
  title: string;
  eyebrow: string;
  description: string;
  bullets: string[];
  icon: any;
}) {
  return (
    <>
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h1>{title}</h1>
          <p className="page-subtitle">{description}</p>
        </div>
      </div>
      <div className="coming-card">
        <div className="coming-icon">
          <Icon size={28} />
        </div>
        <div className="coming-pill">
          <span />
          FOUNDATION READY · MODULE IN PROGRESS
        </div>
        <h2>Built for the way BRIGHT SCAFF. works.</h2>
        <p>This module will be connected to the API and database in the next development stage.</p>
        <div className="coming-list">
          {bullets.map((b) => (
            <div key={b}>
              <CheckCircle2 size={19} />
              {b}
            </div>
          ))}
        </div>
        <div className="coming-note">
          <Activity size={18} />
          <span>
            We will confirm rental date boundaries and billing rules against the company's delivery
            challan, return records and ledger samples before implementing calculations.
          </span>
        </div>
      </div>
    </>
  );
}
