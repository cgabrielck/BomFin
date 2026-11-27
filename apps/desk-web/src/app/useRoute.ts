import { useEffect, useState } from 'react';

function currentRoute() {
  return location.hash.startsWith('#stock/') ? location.hash.slice(7) : null;
}
export function useRoute() {
  const [symbol, setSymbol] = useState(currentRoute);
  useEffect(() => {
    const change = () => setSymbol(currentRoute());
    addEventListener('hashchange', change);
    return () => removeEventListener('hashchange', change);
  }, []);
  return {
    symbol,
    navigate: (value: string | null) => {
      location.hash = value ? `stock/${value}` : 'home';
    },
  };
}
