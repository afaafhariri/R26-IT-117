import { useState } from 'react';
import { Empty, titleCase } from '../../components/ui';
import { toBuildingSchema } from '../../api/services';
import type { C01FullDesignPackage } from '../../types';
import { ImageModal } from './ImageModal';
import { PlanSchematic } from './PlanSchematic';

type Props = { pkg: C01FullDesignPackage; onContinue: () => void };
type PreviewTarget = { label: string; base64: string };

const SQFT = 0.092903;

function Render({ label, base64, onOpen }: { label: string; base64: string; onOpen: (t: PreviewTarget) => void }) {
  if (!base64) return null;
  return (
    <figure className="st-render" onClick={() => onOpen({ label, base64 })}>
      <figcaption>
        <span className="eyebrow dim">{label}</span>
        <span className="eyebrow">Synthesised render</span>
      </figcaption>
      <img src={`data:image/png;base64,${base64}`} alt={label} />
      <span className="st-render-tag">Click to preview &amp; download</span>
    </figure>
  );
}

export function DesignSummary({ pkg, onContinue }: Props) {
  const v = pkg.visualization_assets;
  const plan = pkg.selected_plan;
  const schema = toBuildingSchema(pkg.building_schema_json);
  const renders = [
    { label: 'Exterior', b: v.exterior_image_base64 },
    { label: 'Interior', b: v.interior_image_base64 },
    { label: '2D blueprint', b: v.blueprint_2d_image_base64 },
    { label: '3D floor plan', b: v.floorplan_3d_image_base64 },
  ];
  const hasAnyImage = renders.some((r) => r.b);
  const [preview, setPreview] = useState<PreviewTarget | null>(null);

  return (
    <>
      <div className="cs-layers" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="cs-layer">
          <span className="eyebrow dim">Selected option</span>
          <h3 style={{ textTransform: 'capitalize' }}>{plan.variant}</h3>
          <p>Overall score {plan.scores.overall.toFixed(1)} / 10</p>
        </div>
        <div className="cs-layer">
          <span className="eyebrow dim">Floor area</span>
          <h3>{(schema.footprint_sqm * schema.floors).toFixed(0)} m²</h3>
          <p>
            {schema.floors} floor{schema.floors === 1 ? '' : 's'} · {(plan.total_built_area_sqft * SQFT).toFixed(0)} m² built
          </p>
        </div>
        <div className="cs-layer">
          <span className="eyebrow dim">Rooms</span>
          <h3>{plan.rooms.length}</h3>
          <p>{schema.bathroom_count} bathroom{schema.bathroom_count === 1 ? '' : 's'}</p>
        </div>
        <div className="cs-layer">
          <span className="eyebrow dim">Location</span>
          <h3>{schema.district ?? '—'}</h3>
          <p>{schema.province ?? ''}{schema.is_coastal ? ' · coastal' : ''}</p>
        </div>
      </div>

      <section className="cs-panel">
        <div className="between" style={{ marginBottom: '0.75rem' }}>
          <span className="eyebrow dim">Plan schematic — approved layout</span>
          <span className="chip nominal">{titleCase(schema.roof_type)} roof · {titleCase(schema.finish_grade)} grade</span>
        </div>
        <PlanSchematic rooms={plan.rooms} />
      </section>

      <section className="cs-panel">
        <span className="eyebrow dim">Photorealistic renders</span>
        {hasAnyImage ? (
          <div className="st-renders">
            {renders.map((r) => (
              <Render key={r.label} label={r.label} base64={r.b} onOpen={setPreview} />
            ))}
          </div>
        ) : (
          <Empty>Image generation did not return any renders for this design.</Empty>
        )}
      </section>

      {v.walkthrough_script && (
        <section className="cs-panel">
          <span className="eyebrow dim">Walkthrough</span>
          <h2 style={{ margin: '0.4rem 0 0.6rem' }}>A room-by-room tour</h2>
          <p className="muted" style={{ margin: 0 }}>
            {v.walkthrough_script}
          </p>
        </section>
      )}

      {v.shopping_list.length > 0 && (
        <section className="cs-panel">
          <span className="eyebrow dim">Suggested fit-out list</span>
          <div className="table-wrap" style={{ marginTop: '0.75rem' }}>
            <table className="st-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Category</th>
                  <th className="num">Price range (LKR)</th>
                </tr>
              </thead>
              <tbody>
                {v.shopping_list.map((item, i) => (
                  <tr key={i}>
                    <td>
                      <b>{item.name}</b>
                      <div className="faint">{item.description}</div>
                    </td>
                    <td>
                      <span className="chip">{item.category}</span>
                    </td>
                    <td className="num">{item.price_range_lkr}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="cs-status">
        <div>
          <span className="eyebrow">{plan.variant} option ready for costing</span>
          <p className="faint" style={{ margin: '0.25rem 0 0' }}>
            Validated against NBC Sri Lanka setback and coverage rules for {schema.district ?? 'the district'}.
          </p>
        </div>
        <button className="accent" onClick={onContinue}>
          Approve plan &amp; send to cost estimation (C02) →
        </button>
      </div>

      {preview && <ImageModal label={preview.label} base64={preview.base64} onClose={() => setPreview(null)} />}
    </>
  );
}
