import { useCallback, useState } from "react";

interface LegendPayloadItem {
  value: string;
  dataKey?: string | number;
  color?: string;
}

interface ToggleableLegendProps {
  payload?: LegendPayloadItem[];
  hiddenKeys: Set<string>;
  onToggle: (dataKey: string) => void;
  onSolo?: (dataKey: string) => void;
}

export function ToggleableLegend({
  payload,
  hiddenKeys,
  onToggle,
  onSolo,
}: ToggleableLegendProps) {
  if (!payload || payload.length === 0) return null;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        flexWrap: "wrap",
        gap: "4px 12px",
        padding: "4px 0",
        fontSize: "0.75rem",
      }}
    >
      {payload.map((entry) => {
        const key = String(entry.dataKey ?? entry.value);
        const isHidden = hiddenKeys.has(key);
        return (
          <span
            key={key}
            onClick={() => onToggle(key)}
            onDoubleClick={(e) => {
              e.stopPropagation();
              onSolo?.(key);
            }}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              cursor: "pointer",
              opacity: isHidden ? 0.35 : 1,
              textDecoration: isHidden ? "line-through" : "none",
              userSelect: "none",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 10,
                height: 10,
                borderRadius: 2,
                background: entry.color,
              }}
            />
            {entry.value}
          </span>
        );
      })}
    </div>
  );
}

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
