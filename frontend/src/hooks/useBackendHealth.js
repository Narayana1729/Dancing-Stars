import { useEffect, useState } from 'react';
import { getHealth } from '../services/api.js';

/** Returns 'loading' | 'ok' | 'error'. */
export function useBackendHealth() {
  const [state, setState] = useState('loading');
  useEffect(() => {
    let live = true;
    getHealth().then(() => live && setState('ok')).catch(() => live && setState('error'));
    return () => { live = false; };
  }, []);
  return state;
}
