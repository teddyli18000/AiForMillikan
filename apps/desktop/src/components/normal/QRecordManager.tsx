import type { NormalRecord, NormalSession } from "../../types";

type Props = {
  session: NormalSession | null;
  activeRecord: NormalRecord | null;
  onSelectRecord: (record: NormalRecord) => void;
  onToggleSelected: (record: NormalRecord, selected: boolean) => void;
  onMeasureAnother: () => void;
  onImportNew: () => void;
  onRunInversion: () => void;
};

export function QRecordManager({ session, activeRecord, onSelectRecord, onToggleSelected, onMeasureAnother, onImportNew, onRunInversion }: Props) {
  const records = session?.records ?? [];
  if (records.length === 0) return null;
  return (
    <section className="normal-step-card record-manager">
      <div className="normal-step-heading">
        <span>记录</span>
        <div>
          <h3>已保存 q 记录</h3>
          <p>{session?.counts.valid ?? 0} 条有效，{session?.counts.selected_valid ?? 0} 条已选；只有有效记录可参与反演。</p>
        </div>
      </div>
      <div className="record-table">
        {records.map((record) => (
          <button key={record.record_id} className={activeRecord?.record_id === record.record_id ? "record-row active" : "record-row"} onClick={() => onSelectRecord(record)}>
            <span>{record.record_id}</span>
            <strong>{record.status === "valid" ? "有效 q" : "诊断记录"}</strong>
            <small>{formatQ(record.q?.charge_abs_C)} C</small>
            <label onClick={(event) => event.stopPropagation()}>
              <input type="checkbox" disabled={record.status !== "valid"} checked={Boolean(record.selected)} onChange={(event) => onToggleSelected(record, event.currentTarget.checked)} />
              参与反演
            </label>
          </button>
        ))}
      </div>
      <div className="three-entrances">
        <button className="primary-button" onClick={onMeasureAnother}>测量另一颗</button>
        <button className="ghost-button" onClick={onImportNew}>导入新视频</button>
        <button className="ghost-button" onClick={() => activeRecord && onSelectRecord(activeRecord)}>查看记录</button>
      </div>
      {session?.eligible_for_inversion && <button className="primary-button full" onClick={onRunInversion}>运行双盲反演</button>}
    </section>
  );
}

function formatQ(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toExponential(3) : "-";
}

