import { useState } from 'react';
import type { C01Room } from '../../types';
import { ROOM_FAMILIES, roomAreaSqm, roomFamily } from './rooms';

/* Top-down plan drawn straight from the solved room rectangles (position_x/y
 * and width_ft/length_ft share one coordinate system, so rooms the solver
 * kept apart stay apart here). Rooms are filled by family, as in the Stitch
 * plan schematic: living, bedrooms, kitchen & utility, wet rooms, other. */

const FT = 0.3048;

export function PlanSchematic({ rooms }: { rooms: C01Room[] }) {
  const floors = [...new Set(rooms.map((r) => r.floor ?? 1))].sort();
  const [active, setActive] = useState(floors[0] ?? 1);
  if (!rooms.length) return null;
  const floorRooms = rooms.filter((r) => (r.floor ?? 1) === (floors.includes(active) ? active : floors[0]));

  const xs = floorRooms.flatMap((r) => [r.position_x, r.position_x + r.width_ft]);
  const ys = floorRooms.flatMap((r) => [r.position_y, r.position_y + r.length_ft]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const rangeX = Math.max(...xs) - minX || 1;
  const rangeY = Math.max(...ys) - minY || 1;

  const W = 640;
  const H = 420;
  const pad = 46;
  const k = Math.min((W - pad * 2) / rangeX, (H - pad * 2) / rangeY);
  const ox = (W - rangeX * k) / 2;
  const oy = (H - rangeY * k) / 2;
  const X = (v: number) => ox + (v - minX) * k;
  const Y = (v: number) => oy + (v - minY) * k;
  const gross = floorRooms.reduce((a, r) => a + roomAreaSqm(r), 0);

  return (
    <div className="st-plan">
      <div className="between">
        <div className="st-legend">
          {ROOM_FAMILIES.map((f) => (
            <span key={f.key}>
              <i style={{ background: f.fill, borderColor: f.stroke }} /> {f.label}
            </span>
          ))}
        </div>
        {floors.length > 1 && (
          <div className="cs-filters" role="group" aria-label="Floor">
            {floors.map((f) => (
              <button key={f} type="button" aria-pressed={active === f} onClick={() => setActive(f)}>
                Floor {f}
              </button>
            ))}
          </div>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Floor ${active} plan`}>
        <defs>
          <pattern id="st-grid" width="16" height="16" patternUnits="userSpaceOnUse">
            <path d="M16 0H0V16" fill="none" stroke="var(--border)" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#st-grid)" />
        {/* Overall dimensions */}
        <g stroke="currentColor" strokeWidth="0.8" fill="none">
          <line x1={X(minX)} y1={oy - 18} x2={X(minX + rangeX)} y2={oy - 18} />
          <line x1={X(minX)} y1={oy - 23} x2={X(minX)} y2={oy - 13} />
          <line x1={X(minX + rangeX)} y1={oy - 23} x2={X(minX + rangeX)} y2={oy - 13} />
          <line x1={ox - 18} y1={Y(minY)} x2={ox - 18} y2={Y(minY + rangeY)} />
          <line x1={ox - 23} y1={Y(minY)} x2={ox - 13} y2={Y(minY)} />
          <line x1={ox - 23} y1={Y(minY + rangeY)} x2={ox - 13} y2={Y(minY + rangeY)} />
        </g>
        <g fontFamily="Space Grotesk, sans-serif" fontSize="10" letterSpacing="0.4" fill="var(--text-dim)">
          <text x={W / 2} y={oy - 24} textAnchor="middle">
            WIDTH {(rangeX * FT).toFixed(2)} M
          </text>
          <text x={ox - 24} y={H / 2} textAnchor="middle" transform={`rotate(-90 ${ox - 24} ${H / 2})`}>
            DEPTH {(rangeY * FT).toFixed(2)} M
          </text>
        </g>
        {floorRooms.map((r, i) => {
          const f = roomFamily(r.name);
          const x = X(r.position_x);
          const y = Y(r.position_y);
          const w = Math.max(r.width_ft * k, 2);
          const h = Math.max(r.length_ft * k, 2);
          const big = w > 70 && h > 34;
          return (
            <g key={i}>
              <rect x={x} y={y} width={w} height={h} fill={f.fill} stroke="currentColor" strokeWidth="1.6" />
              {w > 36 && h > 18 && (
                <text
                  x={x + w / 2}
                  y={y + h / 2 + (big ? -2 : 3)}
                  textAnchor="middle"
                  fontFamily="Space Grotesk, sans-serif"
                  fontSize={big ? 10 : 8}
                  fontWeight="600"
                  fill="var(--text)"
                >
                  {r.name.toUpperCase()}
                </text>
              )}
              {big && (
                <text
                  x={x + w / 2}
                  y={y + h / 2 + 12}
                  textAnchor="middle"
                  fontFamily="Space Grotesk, sans-serif"
                  fontSize="8.5"
                  fill="var(--terra)"
                >
                  {(r.width_ft * FT).toFixed(1)} × {(r.length_ft * FT).toFixed(1)} m ({roomAreaSqm(r).toFixed(1)} m²)
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="st-plan-foot">
        <span className="dot terra" />
        <span>
          Floor {active} gross area: <b>{gross.toFixed(1)} m²</b> across {floorRooms.length} rooms
        </span>
      </div>
    </div>
  );
}
