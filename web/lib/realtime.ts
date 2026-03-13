import { useEffect, useRef, useCallback, useState } from "react";

type WSMessage = {
  type: string;
  data: any;
};

type UseWebSocketOptions = {
  url: string;
  onMessage?: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  enabled?: boolean;
  reconnectInterval?: number;
  maxReconnects?: number;
};

/**
 * React hook for WebSocket connections with auto-reconnect.
 *
 * Usage:
 *   const { lastMessage, isConnected, send } = useWebSocket({
 *     url: `ws://localhost:8000/ws/eval/${taskId}`,
 *     enabled: !!taskId,
 *   });
 */
export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  enabled = true,
  reconnectInterval = 3000,
  maxReconnects = 5,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCount = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  const connect = useCallback(() => {
    if (!enabled || !url) return;

    try {
      // Enforce wss:// in production (when page is served over https)
      let safeUrl = url;
      if (
        typeof window !== "undefined" &&
        window.location.protocol === "https:"
      ) {
        safeUrl = url.replace(/^ws:\/\//, "wss://");
      }
      const ws = new WebSocket(safeUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectCount.current = 0;
        onOpen?.();
      };

      ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          setLastMessage(msg);
          onMessage?.(msg);
        } catch {
          // Non-JSON message
          setLastMessage({ type: "raw", data: event.data });
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        onClose?.();

        // Auto-reconnect
        if (reconnectCount.current < maxReconnects && enabled) {
          reconnectTimer.current = setTimeout(() => {
            reconnectCount.current += 1;
            connect();
          }, reconnectInterval);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // Connection failed
    }
  }, [
    url,
    enabled,
    onMessage,
    onOpen,
    onClose,
    reconnectInterval,
    maxReconnects,
  ]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        typeof data === "string" ? data : JSON.stringify(data),
      );
    }
  }, []);

  return { isConnected, lastMessage, send };
}

/**
 * Hook for Server-Sent Events (SSE) streams.
 */
export function useSSE(url: string, enabled: boolean = true) {
  const [data, setData] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!enabled || !url) return;

    const source = new EventSource(url);

    source.onopen = () => setIsConnected(true);

    source.onmessage = (event) => {
      try {
        setData(JSON.parse(event.data));
      } catch {
        setData(event.data);
      }
    };

    source.onerror = () => {
      setIsConnected(false);
      source.close();
    };

    return () => {
      source.close();
      setIsConnected(false);
    };
  }, [url, enabled]);

  return { data, isConnected };
}

/**
 * Hook for real-time proof job status updates via SSE.
 *
 * Connects to `GET /proofs/jobs/{taskId}/stream` and returns the latest
 * job status.  Falls back to the `useSSE` generic hook under the hood.
 * The stream auto-closes when the job reaches a terminal status.
 *
 * Usage:
 *   const { job, isConnected, isDone } = useProofJobSSE(taskId);
 */
export function useProofJobSSE(taskId: string | undefined) {
  const baseUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/api/proofs/jobs`
      : "";
  const url = taskId ? `${baseUrl}/${taskId}/stream` : "";

  const [job, setJob] = useState<any>(null);
  const [isDone, setIsDone] = useState(false);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!taskId || !url) return;

    const source = new EventSource(url);

    source.onopen = () => setIsConnected(true);

    source.onmessage = (event) => {
      try {
        setJob(JSON.parse(event.data));
      } catch {
        // ignore non-JSON
      }
    };

    source.addEventListener("done", (event: MessageEvent) => {
      try {
        setJob(JSON.parse(event.data));
      } catch {
        // ignore
      }
      setIsDone(true);
      source.close();
    });

    source.addEventListener("timeout", () => {
      setIsDone(true);
      source.close();
    });

    source.addEventListener("error", () => {
      setIsConnected(false);
      source.close();
    });

    source.onerror = () => {
      setIsConnected(false);
      source.close();
    };

    return () => {
      source.close();
      setIsConnected(false);
    };
  }, [taskId, url]);

  return { job, isConnected, isDone };
}
