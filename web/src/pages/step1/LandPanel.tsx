import type { C01BuildableZone, C01CadastralData } from '../../types';

/* The left column of the C01 screen: what was read off the deed, and the
 * envelope NBC rules leave to build in. Everything here comes from C01's
 * process-cadastral response; setbacks arrive in feet and are shown in
 * metres, the unit the regulations are written in. */

const FT = 0.3048;
const SQFT = 0.092903;

type Pt = [number, number];

/** Plot boundary with the buildable polygon inset, both scaled to one box.
 *  C01 returns them in the same plan coordinate system. */
function EnvelopeFigure({ plot, buildable }: { plot: Pt[]; buildable: Pt[] }) {
  const pts = [...plot, ...buildable];
  if (plot.length < 3) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const w = Math.max(...xs) - minX || 1;
  const h = Math.max(...ys) - minY || 1;
  const W = 300;
  const H = 190;
  const pad = 16;
  const k = Math.min((W - pad * 2) / w, (H - pad * 2) / h);
  const ox = (W - w * k) / 2;
  const oy = (H - h * k) / 2;
  // Plan y grows north; SVG y grows down.
  const map = (p: Pt) => `${(ox + (p[0] - minX) * k).toFixed(1)},${(H - oy - (p[1] - minY) * k).toFixed(1)}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Plot boundary and buildable area">
      <polygon points={plot.map(map).join(' ')} fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="4 3" />
      {buildable.length >= 3 && (
        <polygon points={buildable.map(map).join(' ')} fill="var(--terra-soft)" stroke="var(--terra)" strokeWidth="1.5" />
      )}
    </svg>
  );
}

export function LandPanel({ cadastral, zone }: { cadastral: C01CadastralData; zone: C01BuildableZone }) {
  const lotSqm = cadastral.land_area_sqft * SQFT;
  const buildableSqm = zone.buildable_area_sqm ?? zone.buildable_area_sqft * SQFT;
  const side = zone.side_setbacks_ft.length ? Math.min(...zone.side_setbacks_ft) : null;
  const coverageSqm = lotSqm * zone.bcr_value;

  return (
    <aside className="cs">
      <section className="cs-panel">
        <div className="between">
          <span className="eyebrow dim">Cadastral deed input</span>
          <span className="chip">{cadastral.district}</span>
        </div>
        <div className="st-figure">
          <EnvelopeFigure plot={cadastral.plot_boundary_polygon} buildable={zone.buildable_polygon} />
          <div className="st-legend">
            <span>
              <i className="dash" /> Lot boundary
            </span>
            <span>
              <i className="fill" /> Buildable area
            </span>
          </div>
        </div>
        <div className="st-facts">
          <div>
            <span className="eyebrow dim">Total lot area</span>
            <b>{lotSqm.toFixed(1)} m²</b>
            <small>{cadastral.land_area_perches.toFixed(2)} perches</small>
          </div>
          <div>
            <span className="eyebrow dim">District</span>
            <b>{cadastral.district}</b>
            <small>{cadastral.orientation ? `Faces ${cadastral.orientation}` : '—'}</small>
          </div>
          <div>
            <span className="eyebrow dim">Road access</span>
            <b style={{ textTransform: 'capitalize' }}>{cadastral.road_access_type}</b>
            <small>Sets the front setback</small>
          </div>
          <div>
            <span className="eyebrow dim">Buildable area</span>
            <b>{buildableSqm.toFixed(1)} m²</b>
            <small>After setbacks</small>
          </div>
        </div>
      </section>

      <section className="cs-panel">
        <div className="between">
          <span className="eyebrow dim">Buildable envelope metrics</span>
          <span className="chip nominal">NBC Sri Lanka</span>
        </div>
        <div className="st-kv">
          <span>Max building coverage ({Math.round(zone.bcr_value * 100)}%)</span>
          <b>{coverageSqm.toFixed(1)} m²</b>
        </div>
        {zone.max_floors != null && (
          <div className="st-kv">
            <span>Recommended max floors</span>
            <b>{zone.max_floors}</b>
          </div>
        )}
        <span className="eyebrow dim" style={{ display: 'block', margin: '1rem 0 0.5rem' }}>
          Statutory setback buffer
        </span>
        <div className="st-setbacks">
          <div>
            <span>Front</span>
            <b>{(zone.front_setback_ft * FT).toFixed(2)} m</b>
            <small>Road reserve</small>
          </div>
          <div>
            <span>Rear</span>
            <b>{(zone.rear_setback_ft * FT).toFixed(2)} m</b>
            <small>Back boundary</small>
          </div>
          <div>
            <span>Side</span>
            <b>{side != null ? `${(side * FT).toFixed(2)} m` : '—'}</b>
            <small>Minimum gap</small>
          </div>
        </div>
        {zone.constraints_summary && (
          <div className="cs-notice" style={{ marginTop: '1rem' }}>
            <svg viewBox="0 0 20 20" aria-hidden>
              <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="m6.3 10.2 2.5 2.5 4.9-5.1" fill="none" stroke="currentColor" strokeWidth="1.6" />
            </svg>
            <div>
              <b>Regulatory summary</b>
              <p>{zone.constraints_summary}</p>
            </div>
          </div>
        )}
      </section>
    </aside>
  );
}
