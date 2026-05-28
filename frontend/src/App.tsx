import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  ToolOutlined
} from "@ant-design/icons";
import { Alert, App as AntApp, Button } from "antd";
import { useEffect, useRef, useState } from "react";
import { ChatComposer } from "./components/ChatComposer";
import { ConversationThread } from "./components/ConversationThread";
import type { ChatTurn } from "./components/ConversationThread";
import { API_BASE_URL, WS_BASE_URL } from "./lib/config";
import { useDeepAgentSession } from "./hooks/useDeepAgentSession";
import type { ConnectionState, SocketMessage, UploadedItem } from "./types";

const TURN_STORAGE_PREFIX = "medireg-agents:turns:";
const SESSION_HISTORY_KEY = "medireg-agents:session-history";
const MAX_SESSION_HISTORY = 30;
const AUTO_SCROLL_BOTTOM_THRESHOLD = 96;
const MAX_STORED_EVENTS = 120;

interface SessionSummary {
  threadId: string;
  title: string;
  updatedAt: string;
  turnCount: number;
}

function connectionLabel(state: ConnectionState): string {
  const labels: Record<ConnectionState, string> = {
    connecting: "连接中",
    connected: "已连接",
    reconnecting: "重连中",
    closed: "已关闭"
  };
  return labels[state];
}

function createTurn(content: string): ChatTurn {
  return {
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`,
    content,
    events: [],
    files: [],
    isRunning: true,
    result: "",
    timestamp: new Date().toISOString()
  };
}

function getTurnsStorageKey(threadId: string): string {
  return `${TURN_STORAGE_PREFIX}${threadId}`;
}

function removeStoredTurns(threadId: string): void {
  try {
    window.localStorage.removeItem(getTurnsStorageKey(threadId));
  } catch {
    // Ignore local storage failures.
  }
}

function isChatTurn(value: unknown): value is ChatTurn {
  if (!value || typeof value !== "object") {
    return false;
  }

  const item = value as Partial<ChatTurn>;
  return (
    typeof item.id === "string" &&
    typeof item.content === "string" &&
    Array.isArray(item.events) &&
    Array.isArray(item.files) &&
    typeof item.result === "string" &&
    typeof item.timestamp === "string"
  );
}

function readStoredTurns(threadId: string, options: { markIdle?: boolean } = {}): ChatTurn[] {
  try {
    const rawValue = window.localStorage.getItem(getTurnsStorageKey(threadId));
    if (!rawValue) {
      return [];
    }

    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return [];
    }

    const storedTurns = parsed.filter(isChatTurn);
    if (!options.markIdle) {
      return storedTurns;
    }

    return storedTurns.map((turn) => ({
      ...turn,
      isRunning: false
    }));
  } catch {
    return [];
  }
}

function storeTurns(threadId: string, turns: ChatTurn[]): void {
  try {
    window.localStorage.setItem(getTurnsStorageKey(threadId), JSON.stringify(turns));
  } catch {
    // Ignore local storage quota or private-mode errors; chat still works in memory.
  }
}

function isSessionSummary(value: unknown): value is SessionSummary {
  if (!value || typeof value !== "object") {
    return false;
  }

  const item = value as Partial<SessionSummary>;
  return (
    typeof item.threadId === "string" &&
    typeof item.title === "string" &&
    typeof item.updatedAt === "string" &&
    typeof item.turnCount === "number"
  );
}

function readSessionHistory(): SessionSummary[] {
  try {
    const rawValue = window.localStorage.getItem(SESSION_HISTORY_KEY);
    if (!rawValue) {
      return [];
    }

    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter(isSessionSummary);
  } catch {
    return [];
  }
}

function storeSessionHistory(history: SessionSummary[]): void {
  try {
    window.localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(history.slice(0, MAX_SESSION_HISTORY)));
  } catch {
    // History is a convenience layer; ignore storage failures.
  }
}

function buildSessionSummary(threadId: string, turns: ChatTurn[], existing?: SessionSummary): SessionSummary {
  const firstUserTurn = turns.find((turn) => turn.content.trim());
  const title = firstUserTurn?.content.trim().slice(0, 32) || existing?.title || "新会话";
  const lastTurn = turns[turns.length - 1];

  return {
    threadId,
    title,
    updatedAt: lastTurn?.timestamp || existing?.updatedAt || new Date().toISOString(),
    turnCount: turns.length
  };
}

function extractPayloadString(data: Record<string, unknown>, key: string): string {
  const value = data[key];
  return typeof value === "string" ? value : "";
}

function applySocketMessageToTurns(turns: ChatTurn[], payload: SocketMessage): ChatTurn[] {
  if (payload.type !== "monitor_event" || turns.length === 0) {
    return turns;
  }

  const latestTurn = turns[turns.length - 1];
  const nextLatestTurn: ChatTurn = {
    ...latestTurn,
    events: [...latestTurn.events, payload].slice(-MAX_STORED_EVENTS)
  };

  if (payload.event === "task_result") {
    nextLatestTurn.result = extractPayloadString(payload.data, "result") || payload.message;
    nextLatestTurn.isRunning = false;
  }

  if (payload.event === "task_cancelled") {
    nextLatestTurn.result = nextLatestTurn.result || payload.message;
    nextLatestTurn.isRunning = false;
  }

  if (payload.event === "error") {
    nextLatestTurn.result = nextLatestTurn.result || payload.message;
    nextLatestTurn.isRunning = false;
  }

  return [...turns.slice(0, -1), nextLatestTurn];
}

function hasRunningTurn(threadId: string): boolean {
  const storedTurns = readStoredTurns(threadId);
  return Boolean(storedTurns[storedTurns.length - 1]?.isRunning);
}

function formatSessionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default function App() {
  const { message } = AntApp.useApp();
  const [query, setQuery] = useState("");
  const [stagedItems, setStagedItems] = useState<UploadedItem[]>([]);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionHistory, setSessionHistory] = useState<SessionSummary[]>(readSessionHistory);
  const hydratedThreadRef = useRef("");
  const streamRef = useRef<HTMLElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const backgroundSocketsRef = useRef<Map<string, WebSocket>>(new Map());
  const session = useDeepAgentSession();

  useEffect(() => {
    if (hydratedThreadRef.current === session.threadId) {
      return;
    }

    hydratedThreadRef.current = session.threadId;
    setTurns(readStoredTurns(session.threadId));
  }, [session.threadId]);

  useEffect(() => {
    if (hydratedThreadRef.current !== session.threadId) {
      return;
    }

    storeTurns(session.threadId, turns);

    setSessionHistory((previous) => {
      const existing = previous.find((item) => item.threadId === session.threadId);
      const nextSummary = buildSessionSummary(session.threadId, turns, existing);
      const next = [
        nextSummary,
        ...previous.filter((item) => item.threadId !== session.threadId)
      ].slice(0, MAX_SESSION_HISTORY);
      storeSessionHistory(next);
      return next;
    });
  }, [session.threadId, turns]);

  useEffect(() => {
    const sockets = backgroundSocketsRef.current;
    const runningThreadIds = new Set(
      sessionHistory
        .map((item) => item.threadId)
        .filter((threadId) => threadId !== session.threadId && hasRunningTurn(threadId))
    );

    for (const [threadId, socket] of sockets) {
      if (!runningThreadIds.has(threadId)) {
        socket.close();
        sockets.delete(threadId);
      }
    }

    runningThreadIds.forEach((threadId) => {
      if (sockets.has(threadId)) {
        return;
      }

      const socket = new WebSocket(`${WS_BASE_URL}/ws/${encodeURIComponent(threadId)}`);
      sockets.set(threadId, socket);

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as SocketMessage;
          if (payload.type === "pong") {
            return;
          }

          const nextTurns = applySocketMessageToTurns(readStoredTurns(threadId), payload);
          storeTurns(threadId, nextTurns);

          setSessionHistory((previous) => {
            const existing = previous.find((item) => item.threadId === threadId);
            const nextSummary = buildSessionSummary(threadId, nextTurns, existing);
            const next = [
              nextSummary,
              ...previous.filter((item) => item.threadId !== threadId)
            ].slice(0, MAX_SESSION_HISTORY);
            storeSessionHistory(next);
            return next;
          });

          if (
            payload.type === "monitor_event" &&
            ["task_result", "task_cancelled", "error"].includes(payload.event)
          ) {
            socket.close();
            sockets.delete(threadId);
          }
        } catch {
          // Background session updates are best-effort; the active session remains unaffected.
        }
      };

      socket.onclose = () => {
        if (sockets.get(threadId) === socket) {
          sockets.delete(threadId);
        }
      };
    });
  }, [session.threadId, sessionHistory]);

  useEffect(() => {
    return () => {
      backgroundSocketsRef.current.forEach((socket) => socket.close());
      backgroundSocketsRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const hasSessionUpdate =
      session.isRunning ||
      session.events.length > 0 ||
      session.files.length > 0 ||
      Boolean(session.result);

    if (!hasSessionUpdate) {
      return;
    }

    setTurns((previous) => {
      if (previous.length === 0) {
        return previous;
      }

      const latestTurn = previous[previous.length - 1];
      const nextLatestTurn = {
        ...latestTurn,
        events: session.events,
        files: session.files,
        isRunning: session.isRunning,
        result: session.result
      };

      return [...previous.slice(0, -1), nextLatestTurn];
    });
  }, [session.events, session.files, session.isRunning, session.result]);

  useEffect(() => {
    const streamNode = streamRef.current;
    if (!streamNode) {
      return;
    }

    const distanceFromBottom = streamNode.scrollHeight - streamNode.scrollTop - streamNode.clientHeight;
    if (distanceFromBottom > AUTO_SCROLL_BOTTOM_THRESHOLD && !shouldAutoScrollRef.current) {
      return;
    }

    window.requestAnimationFrame(() => {
      streamNode.scrollTo({
        top: streamNode.scrollHeight,
        behavior: "smooth"
      });
      shouldAutoScrollRef.current = false;
    });
  }, [turns]);

  async function handleSubmit() {
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      message.warning("请输入注册知识库任务");
      return;
    }

    const nextTurn = createTurn(cleanQuery);
    shouldAutoScrollRef.current = true;
    setTurns((previous) => [...previous, nextTurn]);
    setQuery("");

    try {
      await session.submitTask(cleanQuery);
      message.success("任务已启动，检索和分析过程会显示在对话中");
    } catch (error) {
      setTurns((previous) =>
        previous.map((turn) =>
          turn.id === nextTurn.id
            ? {
                ...turn,
                isRunning: false,
                result: error instanceof Error ? error.message : "任务启动失败"
              }
            : turn
        )
      );
      message.error(error instanceof Error ? error.message : "任务启动失败");
    }
  }

  async function handleCancel() {
    try {
      const response = await session.cancelCurrentTask();
      message.info(response.status === "cancelling" ? "取消请求已发送，正在等待当前调用结束" : "任务已取消");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "取消任务失败");
    }
  }

  async function handleUpload(items: UploadedItem[]) {
    try {
      const response = await session.uploadFiles(items);
      setStagedItems([]);
      message.success(`已上传 ${response.files.length} 个文件`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "上传失败");
    }
  }

  function handleNewSession() {
    session.resetSession();
    setTurns([]);
    setQuery("");
    setStagedItems([]);
  }

  function handleSelectSession(threadId: string) {
    if (threadId === session.threadId) {
      return;
    }

    session.switchSession(threadId);
    setQuery("");
    setStagedItems([]);
  }

  function handleDeleteSession(threadId: string) {
    removeStoredTurns(threadId);

    const nextHistory = sessionHistory.filter((item) => item.threadId !== threadId);
    setSessionHistory(nextHistory);
    storeSessionHistory(nextHistory);

    if (threadId !== session.threadId) {
      return;
    }

    const nextSession = nextHistory[0];
    if (nextSession) {
      session.switchSession(nextSession.threadId);
    } else {
      session.resetSession();
      setTurns([]);
    }
    setQuery("");
    setStagedItems([]);
  }

  const online = session.connectionState === "connected";

  return (
    <div className="chat-app-shell min-h-dvh">
      <aside className="chat-sidebar" aria-label="会话信息">
        <div className="sidebar-brand">
          <span className="panel-kicker">MEDIREG AGENTS</span>
          <h1>知识库</h1>
          <p>医疗器械注册问答与证据追溯工作台</p>
        </div>

        <Button className="new-chat-button" block onClick={handleNewSession}>
          新建分析
        </Button>

        <div className="sidebar-section conversation-history">
          <div className="history-heading">
            <span className="sidebar-label">HISTORY</span>
            <span>{sessionHistory.length} 个会话</span>
          </div>
          <div className="history-list">
            {sessionHistory.length === 0 ? (
              <p className="history-empty">暂无历史会话</p>
            ) : (
              sessionHistory.map((item) => (
                <div
                  className={item.threadId === session.threadId ? "history-item history-item--active" : "history-item"}
                  key={item.threadId}
                >
                  <button
                    className="history-select"
                    onClick={() => handleSelectSession(item.threadId)}
                    type="button"
                  >
                  <span className="history-title">{item.title}</span>
                  <span className="history-meta">
                    {formatSessionTime(item.updatedAt)} · {item.turnCount} 轮
                  </span>
                  </button>
                  <button
                    aria-label="删除会话"
                    className="history-delete"
                    onClick={() => handleDeleteSession(item.threadId)}
                    title="删除会话"
                    type="button"
                  >
                    <DeleteOutlined aria-hidden />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="sidebar-section">
          <span className="sidebar-label">THREAD</span>
          <strong className="thread-id" title={session.threadId}>
            {session.threadId.slice(0, 8)}
          </strong>
        </div>

        <div className="sidebar-status-list">
          <div className={`sidebar-status ${online ? "sidebar-status--online" : "sidebar-status--warn"}`}>
            <ApiOutlined aria-hidden />
            <span>WebSocket</span>
            <strong>{connectionLabel(session.connectionState)}</strong>
          </div>
          <div className="sidebar-status">
            <BranchesOutlined aria-hidden />
            <span>助手调度</span>
            <strong>{session.stats.assistantEvents}</strong>
          </div>
          <div className="sidebar-status">
            <ToolOutlined aria-hidden />
            <span>工具调用</span>
            <strong>{session.stats.toolEvents}</strong>
          </div>
          <div className={session.stats.errorEvents > 0 ? "sidebar-status sidebar-status--error" : "sidebar-status"}>
            <CloseCircleOutlined aria-hidden />
            <span>异常</span>
            <strong>{session.stats.errorEvents}</strong>
          </div>
        </div>

        <div className="sidebar-section">
          <span className="sidebar-label">AGENTS</span>
          <ul className="agent-mini-list">
            <li>
              <CloudServerOutlined aria-hidden />
              网络搜索助手
            </li>
            <li>
              <DatabaseOutlined aria-hidden />
              数据库查询助手
            </li>
            <li>
              <FileSearchOutlined aria-hidden />
              RAGFlow 助手
            </li>
          </ul>
        </div>

        <div className="sidebar-section sidebar-endpoints">
          <span className="sidebar-label">ENDPOINTS</span>
          <code>{API_BASE_URL}</code>
          <code>{WS_BASE_URL}</code>
        </div>
      </aside>

      <main className="chat-main">
        <header className="chat-topbar">
          <div>
            <span className="panel-kicker">CHAT WORKSPACE</span>
            <h2>医疗器械注册问答</h2>
          </div>
          <div className={`run-indicator ${session.isRunning ? "run-indicator--live" : ""}`}>
            {session.isRunning ? <BranchesOutlined aria-hidden /> : <CheckCircleOutlined aria-hidden />}
            {session.isRunning ? "分析中" : "待命"}
          </div>
        </header>

        {session.lastError ? (
          <Alert
            className="chat-alert"
            message={session.lastError}
            showIcon
            type="error"
          />
        ) : null}

        <section className="chat-stream-panel" ref={streamRef}>
          <ConversationThread
            onUseExample={setQuery}
            turns={turns}
          />
        </section>

        <ChatComposer
          isCancelling={session.isCancelling}
          isRunning={session.isRunning}
          isUploading={session.isUploading}
          onCancel={handleCancel}
          onNewSession={handleNewSession}
          onQueryChange={setQuery}
          onStagedItemsChange={setStagedItems}
          onSubmit={handleSubmit}
          onUpload={handleUpload}
          query={query}
          stagedItems={stagedItems}
          uploadedItems={session.uploadedItems}
        />
      </main>
    </div>
  );
}
