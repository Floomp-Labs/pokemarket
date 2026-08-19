import { Link } from "react-router-dom";
import { api } from "../api";
import { useStore } from "../store";
import { timeAgo } from "../util";

export default function AlertsFeed() {
  const alerts = useStore((s) => s.alerts);
  const setAlerts = useStore((s) => s.setAlerts);

  const ack = (id: number) => {
    api
      .ackAlert(id)
      .then(() =>
        setAlerts(alerts.map((a) => (a.id === id ? { ...a, acknowledged: true } : a)))
      )
      .catch(console.error);
  };

  return (
    <div className="alerts-feed">
      <h2>Anomaly Alerts</h2>
      {alerts.length === 0 && <p className="empty">No anomalies detected yet.</p>}
      {alerts.map((a) => (
        <div key={a.id} className={`alert-item ${a.severity} ${a.acknowledged ? "acked" : ""}`}>
          <div className="alert-top">
            {a.image_small && <img src={a.image_small} alt="" />}
            <div className="alert-top-text">
              <Link
                to={a.subject_type === "product" ? `/product/${a.subject_id}` : `/card/${a.subject_id}`}
                className="alert-card"
              >
                {a.name}
              </Link>
              <div className="alert-meta">
                {a.kind.replace("_", " ")} · {timeAgo(a.ts)}
              </div>
            </div>
            <span className={`sev ${a.severity}`}>{a.severity}</span>
          </div>
          <div className="alert-msg">{a.message}</div>
          {!a.acknowledged && (
            <button className="ack-btn" onClick={() => ack(a.id)}>
              acknowledge
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
