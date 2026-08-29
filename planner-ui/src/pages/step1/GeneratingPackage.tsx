import { Loading } from '../../components/ui';

/** Stage 5 (image + text generation) runs for ~30-90s server-side — this is
 *  just a holding screen, there's no meaningful per-step progress to report
 *  since the backend returns one response when everything (or whatever
 *  partially succeeded) is done. */
export function GeneratingPackage() {
  return (
    <div className="stack" style={{ minHeight: '50vh', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
      <Loading what="Building your full design package" />
      <p className="faint">Rendering exterior, interior, 2D blueprint and 3D floor plan — usually 30–90 seconds.</p>
    </div>
  );
}
