import { Card, Stat, Empty } from '../../components/ui';
import { toBuildingSchema } from '../../api/services';
import type { C01FullDesignPackage } from '../../types';

type Props = { pkg: C01FullDesignPackage; onContinue: () => void };

function Thumb({ label, base64 }: { label: string; base64: string }) {
  if (!base64) return null;
  return (
    <figure>
      <img src={`data:image/png;base64,${base64}`} alt={label} />
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export function DesignSummary({ pkg, onContinue }: Props) {
  const v = pkg.visualization_assets;
  const schema = toBuildingSchema(pkg.building_schema_json);
  const hasAnyImage = [v.exterior_image_base64, v.interior_image_base64, v.blueprint_2d_image_base64, v.floorplan_3d_image_base64].some(Boolean);

  return (
    <div className="stack">
      <div>
        <h1>Your Design Package</h1>
        <p className="muted">
          {pkg.selected_plan.variant} plan · {pkg.selected_plan.total_built_area_sqft.toFixed(0)} sqft built
        </p>
      </div>

      <div className="grid cols-4">
        <Stat label="Floor area" value={`${(schema.footprint_sqm * schema.floors).toFixed(0)} m²`} />
        <Stat label="Floors" value={schema.floors} />
        <Stat label="Rooms" value={pkg.selected_plan.rooms.length} />
        <Stat label="District" value={schema.district ?? '—'} hint={schema.province ?? undefined} />
      </div>

      <Card title="Photorealistic Renders">
        {hasAnyImage ? (
          <div className="thumb-grid">
            <Thumb label="Exterior" base64={v.exterior_image_base64} />
            <Thumb label="Interior" base64={v.interior_image_base64} />
            <Thumb label="2D Blueprint" base64={v.blueprint_2d_image_base64} />
            <Thumb label="3D Floor Plan" base64={v.floorplan_3d_image_base64} />
          </div>
        ) : (
          <Empty>Image generation did not return any renders for this run.</Empty>
        )}
      </Card>

      {v.walkthrough_script && (
        <Card title="Walkthrough" subtitle="AI-narrated room-by-room tour">
          <p className="muted">{v.walkthrough_script}</p>
        </Card>
      )}

      {v.shopping_list.length > 0 && (
        <Card title="Suggested Shopping List">
          <div className="table-wrap">
            <table>
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
                      {item.name}
                      <div className="faint">{item.description}</div>
                    </td>
                    <td>{item.category}</td>
                    <td className="num">{item.price_range_lkr}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="footer-nav">
        <span />
        <button className="primary" onClick={onContinue}>
          Move to Estimation →
        </button>
      </div>
    </div>
  );
}
