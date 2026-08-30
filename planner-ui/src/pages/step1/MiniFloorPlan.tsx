import { useState } from 'react';
import type { C01Room } from '../../types';

const SIZE = 220;
const PAD = 10;

function roomColor(name: string): { fill: string; stroke: string } {
  const n = name.toLowerCase();
  if (n.includes('master') || n.includes('bedroom')) return { fill: 'rgba(99,102,241,0.18)', stroke: '#6366f1' };
  if (n.includes('living')) return { fill: 'rgba(34,197,94,0.18)', stroke: '#22c55e' };
  if (n.includes('kitchen')) return { fill: 'rgba(234,179,8,0.22)', stroke: '#eab308' };
  if (n.includes('dining')) return { fill: 'rgba(251,146,60,0.22)', stroke: '#fb923c' };
  if (n.includes('bath') || n.includes('toilet')) return { fill: 'rgba(14,165,233,0.18)', stroke: '#0ea5e9' };
  if (n.includes('garage')) return { fill: 'rgba(100,116,139,0.18)', stroke: '#64748b' };
  if (n.includes('stair')) return { fill: 'rgba(148,163,184,0.22)', stroke: '#94a3b8' };
  return { fill: 'rgba(249,115,22,0.12)', stroke: '#f97316' };
}

/** Isometric-free top-down mini floor plan, drawn straight from the solved
 *  room rectangles (position_x/y, width_ft/length_ft share one coordinate
 *  system, so non-overlapping rooms from the solver stay non-overlapping
 *  here too). Ported from Architecture/frontend's FloorPlanCard.tsx. */
export function MiniFloorPlan({ rooms }: { rooms: C01Room[] }) {
  const inner = SIZE - PAD * 2;
  const allFloors = [...new Set(rooms.map((r) => r.floor ?? 1))].sort();
  const [activeFloor, setActiveFloor] = useState(allFloors[0] ?? 1);
  const multiFloor = allFloors.length > 1;

  if (!rooms.length) return null;
  const floorRooms = rooms.filter((r) => (r.floor ?? 1) === activeFloor);

  const allX = floorRooms.flatMap((r) => [r.position_x, r.position_x + r.width_ft]);
  const allY = floorRooms.flatMap((r) => [r.position_y, r.position_y + r.length_ft]);
  const minX = Math.min(...allX);
  const maxX = Math.max(...allX);
  const minY = Math.min(...allY);
  const maxY = Math.max(...allY);
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;

  const aspect = rangeX / rangeY;
  let drawW = inner;
  let drawH = inner;
  if (aspect > 1) drawH = inner / aspect;
  else drawW = inner * aspect;
  const offX = PAD + (inner - drawW) / 2;
  const offY = PAD + (inner - drawH) / 2;

  const toX = (v: number) => offX + ((v - minX) / rangeX) * drawW;
  const toY = (v: number) => offY + ((v - minY) / rangeY) * drawH;
  const toW = (v: number) => (v / rangeX) * drawW;
  const toH = (v: number) => (v / rangeY) * drawH;

  return (
    <div>
      {multiFloor && (
        <div className="floor-tabs">
          {allFloors.map((f) => (
            <button
              key={f}
              type="button"
              className={activeFloor === f ? 'active' : ''}
              onClick={(e) => {
                e.stopPropagation();
                setActiveFloor(f);
              }}
            >
              Floor {f}
            </button>
          ))}
        </div>
      )}
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ width: '100%', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)' }}
      >
        <rect x={offX} y={offY} width={drawW} height={drawH} fill="none" stroke="var(--border-strong)" strokeWidth={1} strokeDasharray="4 2" rx={1} />
        {floorRooms.map((r, i) => {
          const x = toX(r.position_x);
          const y = toY(r.position_y);
          const w = Math.max(toW(r.width_ft), 2);
          const h = Math.max(toH(r.length_ft), 2);
          const { fill, stroke } = roomColor(r.name);
          const label = r.name.replace(/(master |ensuite |common )/i, '').split(' ')[0];
          return (
            <g key={i}>
              <rect x={x} y={y} width={w} height={h} fill={fill} stroke={stroke} strokeWidth={1.2} rx={1.5} />
              {w > 18 && h > 10 && (
                <text x={x + w / 2} y={y + h / 2 + 3} textAnchor="middle" fontSize={5.5} fill="var(--text-dim)">
                  {label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
