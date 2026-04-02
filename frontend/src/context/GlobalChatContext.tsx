import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { useMode2Chat, type Mode2ChatState } from "../hooks/useMode2Chat";
import { getSessionMessages } from "../config/mode2Api";

export interface PageContext {
  page: string;
  ticker?: string;
  period?: string;
  previewId?: string;
  suggestions?: string[];
}

interface GlobalChatContextValue {
  /** Whether the panel is open */
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  /** Open and set page context in one call */
  openWithContext: (ctx: PageContext) => void;
  /** Current page context (set by whatever page is mounted) */
  pageContext: PageContext | undefined;
  setPageContext: (ctx: PageContext | undefined) => void;
  /** The underlying chat state — same hook as ChatPage uses */
  chat: Mode2ChatState;
  /** Load a saved conversation into the chat panel */
  loadConversation: (sessionId: string) => Promise<void>;
  /** Current pack page ID (set by PackPage, null elsewhere) */
  currentPackId: string | null;
  setActivePack: (packId: string | null) => void;
}

const Ctx = createContext<GlobalChatContextValue | null>(null);

export function GlobalChatProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [pageContext, setPageContext] = useState<PageContext | undefined>();
  const [currentPackId, setCurrentPackId] = useState<string | null>(null);
  const chat = useMode2Chat();

  // Keyboard shortcut: Cmd+/ or Ctrl+/
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        setIsOpen((p) => !p);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((p) => !p), []);

  const openWithContext = useCallback((ctx: PageContext) => {
    setPageContext(ctx);
    setIsOpen(true);
  }, []);

  const setActivePack = useCallback((packId: string | null) => {
    setCurrentPackId(packId);
  }, []);

  const loadConversation = useCallback(async (sessionId: string) => {
    try {
      const msgs = await getSessionMessages(sessionId);
      if (msgs.length === 0) return;
      chat.loadMessages(
        msgs.map((m) => ({ role: m.role, content: m.content })),
        sessionId,
      );
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  }, [chat.loadMessages]);

  return (
    <Ctx.Provider
      value={{
        isOpen,
        open,
        close,
        toggle,
        openWithContext,
        pageContext,
        setPageContext,
        chat,
        loadConversation,
        currentPackId,
        setActivePack,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useGlobalChat() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useGlobalChat must be used within GlobalChatProvider");
  return ctx;
}
