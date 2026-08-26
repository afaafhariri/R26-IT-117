/** The frontend is the orchestrator AND the store.
 *
 *  C02 and C03 persist nothing — they compute a response and forget it. Only C04
 *  keeps state. So everything the review page shows has to be kept here, in the
 *  browser, as the user moves through the wizard. */

import { useCallback, useEffect, useState } from 'react';
import type { RunState } from '../types';

const KEY = 'r26.run';

function newRun(): RunState {
  return {
    runId:
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `run-${Date.now()}`,
    updatedAt: new Date().toISOString(),
    projectName: 'My House',
  };
}

export function loadRun(): RunState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return newRun();
    const parsed = JSON.parse(raw) as RunState;
    if (!parsed || typeof parsed !== 'object' || !parsed.runId) return newRun();
    return parsed;
  } catch {
    // Private browsing, cleared storage, or a corrupt value — start clean.
    return newRun();
  }
}

function persist(run: RunState) {
  try {
    localStorage.setItem(KEY, JSON.stringify(run));
  } catch {
    // Storage unavailable or full. The wizard still works for this session;
    // only reload-survival is lost, so fail quietly rather than blocking.
  }
}

/** Cross-component sync without a full state library. */
const listeners = new Set<(r: RunState) => void>();
let current: RunState | null = null;

function snapshot(): RunState {
  if (!current) current = loadRun();
  return current;
}

function commit(next: RunState) {
  current = { ...next, updatedAt: new Date().toISOString() };
  persist(current);
  listeners.forEach((l) => l(current as RunState));
}

export function useRun() {
  const [run, setRunState] = useState<RunState>(snapshot);

  useEffect(() => {
    const l = (r: RunState) => setRunState(r);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);

  const update = useCallback((patch: Partial<RunState>) => {
    commit({ ...snapshot(), ...patch });
  }, []);

  const reset = useCallback(() => {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
    commit(newRun());
  }, []);

  return { run, update, reset };
}

/** Highest step whose prerequisites are met (1-4); 5 means review is reachable. */
export function furthestStep(run: RunState): number {
  if (run.step4?.c04ProjectId) return 5;
  if (run.step3?.schedulePayload) return 4;
  if (run.step2?.estimate) return 3;
  if (run.step1?.buildingSchema) return 2;
  return 1;
}

export function isStepUnlocked(run: RunState, step: number): boolean {
  return step <= furthestStep(run);
}
