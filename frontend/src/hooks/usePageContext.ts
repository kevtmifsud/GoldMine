import { useEffect } from "react";
import { useGlobalChat, type PageContext } from "../context/GlobalChatContext";

/**
 * Pages call this hook to inject context into the global chat panel.
 * Updates the global chat context when the page mounts; clears it on unmount.
 */
export function usePageContext(context: PageContext) {
  const { setPageContext } = useGlobalChat();

  useEffect(() => {
    setPageContext(context);
    return () => setPageContext(undefined);
    // Only re-set when the key fields change, not on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.page, context.ticker, context.period, context.previewId, setPageContext]);
}
