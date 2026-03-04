import { useCallback, useState } from "react";

export function useToggleableLegend() {
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());

  const handleToggle = useCallback((dataKey: string) => {
    setHiddenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(dataKey)) next.delete(dataKey);
      else next.add(dataKey);
      return next;
    });
  }, []);

  const handleSolo = useCallback((dataKey: string, allKeys: string[]) => {
    setHiddenKeys((prev) => {
      const othersAllHidden = allKeys.every(
        (k) => k === dataKey || prev.has(k)
      );
      if (othersAllHidden) {
        // Already solo'd — restore all
        return new Set();
      }
      // Hide everything except the clicked key
      return new Set(allKeys.filter((k) => k !== dataKey));
    });
  }, []);

  return { hiddenKeys, handleToggle, handleSolo };
}
