import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from "react";
import type { IDoesFilterPassParams, IFilterParams } from "ag-grid-community";

/**
 * Custom multi-select "set" filter for AG Grid Community edition.
 *
 * Displays checkboxes for each unique value in the column,
 * with a search box and Select All / Deselect All controls.
 *
 * Usage: `{ filter: SetFilter }` on any ColDef.
 */
export const SetFilter = forwardRef(function SetFilter(
  props: IFilterParams,
  ref: React.Ref<unknown>
) {
  const field = props.colDef.field!;
  const [allValues, setAllValues] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  const computeUniqueValues = useCallback(() => {
    const set = new Set<string>();
    props.api.forEachNode((node) => {
      if (!node.data) return;
      const raw = node.data[field];
      if (raw != null && raw !== "") set.add(String(raw));
    });
    return Array.from(set).sort();
  }, [props.api, field]);

  // Initialise on mount
  useEffect(() => {
    const init = computeUniqueValues();
    setAllValues(init);
    setSelected(new Set(init));
  }, [computeUniqueValues]);

  // Refresh when row data changes
  useEffect(() => {
    const onData = () => {
      const vals = computeUniqueValues();
      setAllValues(vals);
      setSelected((prev) => {
        if (prev.size === 0) return new Set(vals);
        const next = new Set(prev);
        for (const v of vals) {
          if (!prev.has(v)) next.add(v);
        }
        return next;
      });
    };
    props.api.addEventListener("rowDataUpdated", onData);
    return () => props.api.removeEventListener("rowDataUpdated", onData);
  }, [props.api, computeUniqueValues]);

  // Tell AG Grid when the filter state changes
  useEffect(() => {
    props.filterChangedCallback();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const displayed = useMemo(() => {
    if (!search) return allValues;
    const q = search.toLowerCase();
    return allValues.filter((v) => v.toLowerCase().includes(q));
  }, [allValues, search]);

  const toggle = useCallback((val: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(val)) next.delete(val);
      else next.add(val);
      return next;
    });
  }, []);

  const selectAll = useCallback(
    () => setSelected(new Set(allValues)),
    [allValues]
  );
  const deselectAll = useCallback(() => setSelected(new Set()), []);

  // Imperative API that AG Grid calls
  useImperativeHandle(
    ref,
    () => ({
      isFilterActive: () => selected.size !== allValues.length,

      doesFilterPass: (params: IDoesFilterPassParams) => {
        const raw = params.data[field];
        if (raw == null || raw === "") return false;
        return selected.has(String(raw));
      },

      getModel: () =>
        selected.size === allValues.length
          ? null
          : { values: Array.from(selected) },

      setModel: (model: { values: string[] } | null) => {
        if (!model) setSelected(new Set(allValues));
        else setSelected(new Set(model.values));
      },

      getModelAsString: () => {
        if (selected.size === allValues.length) return "";
        if (selected.size === 0) return "(none)";
        if (selected.size <= 2) return Array.from(selected).join(", ");
        return `${selected.size} of ${allValues.length}`;
      },
    }),
    [selected, allValues, field]
  );

  return (
    <div style={{ padding: 8, minWidth: 200 }}>
      <div style={{ marginBottom: 6 }}>
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: "100%",
            padding: "4px 8px",
            boxSizing: "border-box",
            border: "1px solid #cbd5e1",
            borderRadius: 3,
            fontSize: 12,
          }}
        />
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
        <button
          type="button"
          onClick={selectAll}
          style={{
            cursor: "pointer",
            border: "none",
            background: "none",
            padding: 0,
            color: "#2563eb",
            fontSize: 11,
          }}
        >
          Select All
        </button>
        <button
          type="button"
          onClick={deselectAll}
          style={{
            cursor: "pointer",
            border: "none",
            background: "none",
            padding: 0,
            color: "#2563eb",
            fontSize: 11,
          }}
        >
          Deselect All
        </button>
      </div>
      <div style={{ maxHeight: 240, overflowY: "auto" }}>
        {displayed.map((val) => (
          <label
            key={val}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            <input
              type="checkbox"
              checked={selected.has(val)}
              onChange={() => toggle(val)}
            />
            {val}
          </label>
        ))}
        {displayed.length === 0 && (
          <div style={{ color: "#94a3b8", fontSize: 12, padding: "4px 0" }}>
            No matches
          </div>
        )}
      </div>
    </div>
  );
});
