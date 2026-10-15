import type { C01Room } from '../../types';

/* Room families shared by the plan schematic and the room tables: living,
 * bedrooms, kitchen & utility, wet rooms, other. */

export const ROOM_FAMILIES = [
  { key: 'living', label: 'Living / dining', fill: 'var(--accent-soft)', stroke: 'var(--accent)' },
  { key: 'bed', label: 'Bedrooms', fill: 'var(--terra-soft)', stroke: 'var(--terra)' },
  { key: 'kitchen', label: 'Kitchen & utility', fill: 'var(--warn-soft)', stroke: 'var(--ochre)' },
  { key: 'wet', label: 'Bath & wet rooms', fill: 'var(--surface-3)', stroke: 'var(--text-dim)' },
  { key: 'other', label: 'Other', fill: 'var(--surface-2)', stroke: 'var(--border-strong)' },
] as const;

export function roomFamily(name: string) {
  const n = name.toLowerCase();
  if (n.includes('bed') || n.includes('master')) return ROOM_FAMILIES[1];
  if (n.includes('living') || n.includes('dining') || n.includes('lounge')) return ROOM_FAMILIES[0];
  if (n.includes('kitchen') || n.includes('pantry') || n.includes('utility') || n.includes('store')) return ROOM_FAMILIES[2];
  if (n.includes('bath') || n.includes('toilet') || n.includes('wash')) return ROOM_FAMILIES[3];
  return ROOM_FAMILIES[4];
}

export const roomAreaSqm = (r: C01Room) => r.area_sqft * 0.092903;
