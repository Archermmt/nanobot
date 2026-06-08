import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

interface MediaQueueItem {
  id: string;
  url: string;
}

interface MediaQueueContextValue {
  enqueue: (id: string, url: string) => void;
  remove: (id: string) => void;
  clear: () => void;
  currentId: string | null;
  onEnded: (id: string) => void;
}

const MediaQueueContext = createContext<MediaQueueContextValue>({
  enqueue: () => undefined,
  remove: () => undefined,
  clear: () => undefined,
  currentId: null,
  onEnded: () => undefined,
});

export function MediaQueueProvider({
  children,
  sessionId,
}: {
  children: ReactNode;
  sessionId?: string | null;
}) {
  const [queue, setQueue] = useState<MediaQueueItem[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const prevSessionId = useRef(sessionId);

  // Reset queue on session change
  useEffect(() => {
    if (prevSessionId.current !== sessionId) {
      prevSessionId.current = sessionId;
      setQueue([]);
      setCurrentId(null);
    }
  }, [sessionId]);

  // Advance to next item when nothing is playing
  useEffect(() => {
    if (currentId === null && queue.length > 0) {
      setCurrentId(queue[0].id);
    }
  }, [queue, currentId]);

  const enqueue = useCallback((id: string, url: string) => {
    setQueue((prev) => (prev.some((item) => item.id === id) ? prev : [...prev, { id, url }]));
  }, []);

  const remove = useCallback((id: string) => {
    setQueue((prev) => prev.filter((item) => item.id !== id));
    setCurrentId((prev) => (prev === id ? null : prev));
  }, []);

  const onEnded = useCallback((id: string) => {
    setQueue((prev) => prev.filter((item) => item.id !== id));
    setCurrentId((prev) => (prev === id ? null : prev));
  }, []);

  const clear = useCallback(() => {
    setQueue([]);
    setCurrentId(null);
  }, []);

  return (
    <MediaQueueContext.Provider value={{ enqueue, remove, clear, currentId, onEnded }}>
      {children}
    </MediaQueueContext.Provider>
  );
}

export function useMediaQueue(): MediaQueueContextValue {
  return useContext(MediaQueueContext);
}
