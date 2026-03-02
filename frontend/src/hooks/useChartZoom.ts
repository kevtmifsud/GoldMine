import { useCallback, useMemo, useRef, useState } from "react";

export interface ChartZoom {
  /** The committed left boundary of the zoomed range */
  zoomLeft: string | null;
  /** The committed right boundary of the zoomed range */
  zoomRight: string | null;
  /** The in-progress drag selection left edge */
  selectingLeft: string | null;
  /** The in-progress drag selection right edge */
  selectingRight: string | null;
  /** Whether the chart is currently zoomed in */
  isZoomed: boolean;
  /** Attach to the chart's onMouseDown */
  handleMouseDown: (e: { activeLabel?: string }) => void;
  /** Attach to the chart's onMouseMove */
  handleMouseMove: (e: { activeLabel?: string }) => void;
  /** Attach to the chart's onMouseUp */
  handleMouseUp: () => void;
  /** Reset zoom to show the full data range */
  handleResetZoom: () => void;
  /** Slice data to the zoomed range. Pass full data array and the x-axis key. */
  zoomData: <T extends object>(data: T[], xKey: keyof T) => T[];
}

export function useChartZoom(): ChartZoom {
  const [zoomLeft, setZoomLeft] = useState<string | null>(null);
  const [zoomRight, setZoomRight] = useState<string | null>(null);
  const [selectingLeft, setSelectingLeft] = useState<string | null>(null);
  const [selectingRight, setSelectingRight] = useState<string | null>(null);
  const isDragging = useRef(false);

  const isZoomed = zoomLeft !== null && zoomRight !== null;

  const handleMouseDown = useCallback((e: { activeLabel?: string }) => {
    if (!e?.activeLabel) return;
    isDragging.current = true;
    setSelectingLeft(e.activeLabel);
    setSelectingRight(null);
  }, []);

  const handleMouseMove = useCallback((e: { activeLabel?: string }) => {
    if (!isDragging.current || !e?.activeLabel) return;
    setSelectingRight(e.activeLabel);
  }, []);

  const handleMouseUp = useCallback(() => {
    if (!isDragging.current) return;
    isDragging.current = false;
    if (selectingLeft && selectingRight && selectingLeft !== selectingRight) {
      setZoomLeft(selectingLeft);
      setZoomRight(selectingRight);
    }
    setSelectingLeft(null);
    setSelectingRight(null);
  }, [selectingLeft, selectingRight]);

  const handleResetZoom = useCallback(() => {
    setZoomLeft(null);
    setZoomRight(null);
    setSelectingLeft(null);
    setSelectingRight(null);
  }, []);

  const zoomData = useCallback(
    <T extends object>(data: T[], xKey: keyof T): T[] => {
      if (!zoomLeft || !zoomRight) return data;
      const leftIdx = data.findIndex((d) => String(d[xKey]) === zoomLeft);
      const rightIdx = data.findIndex((d) => String(d[xKey]) === zoomRight);
      if (leftIdx === -1 || rightIdx === -1) return data;
      const lo = Math.min(leftIdx, rightIdx);
      const hi = Math.max(leftIdx, rightIdx);
      return data.slice(lo, hi + 1);
    },
    [zoomLeft, zoomRight]
  );

  return useMemo(
    () => ({
      zoomLeft,
      zoomRight,
      selectingLeft,
      selectingRight,
      isZoomed,
      handleMouseDown,
      handleMouseMove,
      handleMouseUp,
      handleResetZoom,
      zoomData,
    }),
    [
      zoomLeft,
      zoomRight,
      selectingLeft,
      selectingRight,
      isZoomed,
      handleMouseDown,
      handleMouseMove,
      handleMouseUp,
      handleResetZoom,
      zoomData,
    ]
  );
}
