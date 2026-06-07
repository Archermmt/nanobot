import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { Grip, X } from "lucide-react";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { useNanobotStream, type SendImage, type SendOptions } from "@/hooks/useNanobotStream";
import { useSessionHistory } from "@/hooks/useSessions";
import { fetchCliApps, fetchMcpPresets, fetchSettings, listSlashCommands } from "@/lib/api";
import { MediaQueueProvider } from "@/providers/MediaQueueProvider";
import {
  CLI_APPS_CHANGED_EVENT,
  installedCliAppsFromPayload,
  isCliAppsPayload,
} from "@/lib/cli-app-events";
import {
  MCP_PRESETS_CHANGED_EVENT,
  installedMcpPresetsFromPayload,
  isMcpPresetsPayload,
} from "@/lib/mcp-preset-events";
import { inferProviderFromModelName, providerDisplayLabel } from "@/lib/provider-brand";
import type {
  ChatSummary,
  CliAppInfo,
  McpPresetInfo,
  SettingsPayload,
  SlashCommand,
  UIMessage,
  WorkspaceScopePayload,
  WorkspacesPayload,
} from "@/lib/types";
import { normalizeLegacyLongTaskMessages } from "@/lib/thread-display-compat";
import { scrubSubagentUiMessages } from "@/lib/subagent-channel-display";
import { useClient } from "@/providers/ClientProvider";

function projectWebuiThreadMessages(messages: UIMessage[]): UIMessage[] {
  return scrubSubagentUiMessages(normalizeLegacyLongTaskMessages(messages));
}

function sameMessageShape(a: UIMessage, b: UIMessage): boolean {
  return (
    a.role === b.role
    && (a.kind ?? "") === (b.kind ?? "")
    && a.content === b.content
  );
}

function isStaleThreadSnapshot(current: UIMessage[], snapshot: UIMessage[]): boolean {
  if (current.length === 0 || snapshot.length >= current.length) return false;
  if (snapshot.length === 0) return true;
  return snapshot.every((message, index) => sameMessageShape(current[index], message));
}

interface ThreadShellProps {
  session: ChatSummary | null;
  title: string;
  onToggleSidebar: () => void;
  onGoHome?: () => void;
  onNewChat?: () => void;
  onCreateChat?: (workspaceScope?: WorkspaceScopePayload | null) => Promise<string | null>;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hideSidebarToggleForHostChrome?: boolean;
  hideHeader?: boolean;
  workspaceScope?: WorkspaceScopePayload | null;
  workspaceDefaultScope?: WorkspaceScopePayload | null;
  workspaceControls?: WorkspacesPayload["controls"] | null;
  workspaceScopeDisabled?: boolean;
  workspaceError?: string | null;
  onWorkspaceScopeChange?: (scope: WorkspaceScopePayload) => void;
  settingsSnapshot?: SettingsPayload | null;
}

function toModelBadgeLabel(modelName: string | null): string | null {
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  return leaf || trimmed;
}

interface ModelBadgeInfo {
  label: string | null;
  provider: string | null;
  providerLabel: string | null;
}

function activeModelPreset(settings: SettingsPayload | null): SettingsPayload["model_presets"][number] | null {
  if (!settings) return null;
  const configured = settings.agent.model_preset || "default";
  return (
    settings.model_presets.find((preset) => preset.name === configured)
    ?? settings.model_presets.find((preset) => preset.active)
    ?? null
  );
}

function resolvedModelProvider(settings: SettingsPayload | null, modelName: string | null): string | null {
  const preset = activeModelPreset(settings);
  const rawProvider = preset?.provider || settings?.agent.provider || null;
  if (rawProvider === "auto") {
    return settings?.agent.resolved_provider || inferProviderFromModelName(modelName) || null;
  }
  return rawProvider || inferProviderFromModelName(modelName);
}

function toModelBadgeInfo(modelName: string | null, settings: SettingsPayload | null): ModelBadgeInfo {
  const label = toModelBadgeLabel(modelName || settings?.agent.model || null);
  const provider = resolvedModelProvider(settings, modelName || settings?.agent.model || null);
  return {
    label,
    provider,
    providerLabel: provider ? providerDisplayLabel(settings?.providers ?? [], provider) : null,
  };
}

const HERO_GREETING_KEYS = [
  "thread.empty.greetings.workOn",
  "thread.empty.greetings.start",
  "thread.empty.greetings.build",
  "thread.empty.greetings.tackle",
] as const;

function randomHeroGreetingKey(): (typeof HERO_GREETING_KEYS)[number] {
  const index = Math.floor(Math.random() * HERO_GREETING_KEYS.length);
  return HERO_GREETING_KEYS[index] ?? HERO_GREETING_KEYS[0];
}

interface PendingFirstMessage {
  content: string;
  images?: SendImage[];
  options?: SendOptions;
}

const CAMERA_PREVIEW_DEFAULT_SIZE = { width: 320, height: 200 };
const CAMERA_PREVIEW_MIN_SIZE = { width: 220, height: 140 };
const CAMERA_PREVIEW_MARGIN = 16;

interface CameraPreviewPosition {
  x: number;
  y: number;
}

interface CameraPreviewSize {
  width: number;
  height: number;
}

interface CameraPreviewInteraction {
  mode: "drag" | "resize";
  pointerX: number;
  pointerY: number;
  position: CameraPreviewPosition;
  size: CameraPreviewSize;
}

function clampCameraPreviewPosition(
  position: CameraPreviewPosition,
  size: CameraPreviewSize,
): CameraPreviewPosition {
  if (typeof window === "undefined") return position;
  const maxX = Math.max(CAMERA_PREVIEW_MARGIN, window.innerWidth - size.width - CAMERA_PREVIEW_MARGIN);
  const maxY = Math.max(CAMERA_PREVIEW_MARGIN, window.innerHeight - size.height - CAMERA_PREVIEW_MARGIN);
  return {
    x: Math.min(Math.max(CAMERA_PREVIEW_MARGIN, position.x), maxX),
    y: Math.min(Math.max(CAMERA_PREVIEW_MARGIN, position.y), maxY),
  };
}

function FloatingCameraPreview({
  stream,
  onClose,
}: {
  stream: MediaStream;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const interactionRef = useRef<CameraPreviewInteraction | null>(null);
  const [position, setPosition] = useState<CameraPreviewPosition>(() => {
    if (typeof window === "undefined") {
      return { x: CAMERA_PREVIEW_MARGIN, y: CAMERA_PREVIEW_MARGIN };
    }
    return {
      x: Math.max(
        CAMERA_PREVIEW_MARGIN,
        window.innerWidth - CAMERA_PREVIEW_DEFAULT_SIZE.width - 24,
      ),
      y: Math.max(
        CAMERA_PREVIEW_MARGIN,
        window.innerHeight - CAMERA_PREVIEW_DEFAULT_SIZE.height - 112,
      ),
    };
  });
  const [size, setSize] = useState<CameraPreviewSize>(CAMERA_PREVIEW_DEFAULT_SIZE);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      const interaction = interactionRef.current;
      if (!interaction) return;
      const deltaX = event.clientX - interaction.pointerX;
      const deltaY = event.clientY - interaction.pointerY;
      if (interaction.mode === "drag") {
        setPosition(clampCameraPreviewPosition({
          x: interaction.position.x + deltaX,
          y: interaction.position.y + deltaY,
        }, size));
        return;
      }

      const nextSize = {
        width: Math.max(CAMERA_PREVIEW_MIN_SIZE.width, interaction.size.width + deltaX),
        height: Math.max(CAMERA_PREVIEW_MIN_SIZE.height, interaction.size.height + deltaY),
      };
      setSize(nextSize);
      setPosition((current) => clampCameraPreviewPosition(current, nextSize));
    };
    const handlePointerUp = () => {
      interactionRef.current = null;
    };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [size]);

  useEffect(() => {
    const handleResize = () => {
      setPosition((current) => clampCameraPreviewPosition(current, size));
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [size]);

  const startInteraction = (
    event: ReactPointerEvent,
    mode: CameraPreviewInteraction["mode"],
  ) => {
    event.preventDefault();
    interactionRef.current = {
      mode,
      pointerX: event.clientX,
      pointerY: event.clientY,
      position,
      size,
    };
  };

  const style = {
    left: position.x,
    top: position.y,
    width: size.width,
    height: size.height,
  } satisfies CSSProperties;

  return (
    <div
      className="fixed z-50 overflow-hidden rounded-lg border border-border/70 bg-background/95 shadow-2xl shadow-black/25 backdrop-blur"
      style={style}
      aria-label={t("thread.composer.camera.preview", { defaultValue: "Camera preview" })}
    >
      <div
        className="absolute inset-x-0 top-0 z-10 flex h-9 cursor-move items-center justify-between bg-black/55 px-2 text-white"
        onPointerDown={(event) => startInteraction(event, "drag")}
      >
        <div className="flex min-w-0 items-center gap-1.5 text-[12px] font-medium">
          <Grip className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">
            {t("thread.composer.camera.preview", { defaultValue: "Camera preview" })}
          </span>
        </div>
        <button
          type="button"
          className="flex h-6 w-6 items-center justify-center rounded-full text-white/80 hover:bg-white/15 hover:text-white"
          aria-label={t("thread.composer.camera.stopCamera")}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={onClose}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <video
        ref={videoRef}
        className="h-full w-full bg-black object-cover"
        autoPlay
        muted
        playsInline
      />
      <button
        type="button"
        className="absolute bottom-1.5 right-1.5 z-10 h-5 w-5 cursor-nwse-resize rounded-sm border border-white/30 bg-black/45"
        aria-label={t("thread.composer.camera.resize", { defaultValue: "Resize camera preview" })}
        onPointerDown={(event) => startInteraction(event, "resize")}
      >
        <span className="absolute bottom-1 right-1 h-2.5 w-2.5 border-b-2 border-r-2 border-white/80" />
      </button>
    </div>
  );
}

export function ThreadShell({
  session,
  title,
  onToggleSidebar,
  onCreateChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => {},
  hideSidebarToggleForHostChrome = false,
  hideHeader = false,
  workspaceScope = null,
  workspaceDefaultScope = null,
  workspaceControls = null,
  workspaceScopeDisabled = false,
  workspaceError = null,
  onWorkspaceScopeChange,
  settingsSnapshot = null,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const chatId = session?.chatId ?? null;
  const historyKey = session?.key ?? null;
  const {
    messages: historical,
    loading,
    hasPendingToolCalls,
    refresh: refreshHistory,
    version: historyVersion,
  } = useSessionHistory(historyKey);
  const { client, modelName, token } = useClient();
  const [booting, setBooting] = useState(false);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);
  const [cliApps, setCliApps] = useState<CliAppInfo[]>([]);
  const [mcpPresets, setMcpPresets] = useState<McpPresetInfo[]>([]);
  const [settings, setSettings] = useState<SettingsPayload | null>(settingsSnapshot);
  const [heroGreetingKey, setHeroGreetingKey] = useState(randomHeroGreetingKey);
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0);
  const [enableTts, setEnableTts] = useState(false);
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const pendingFirstRef = useRef<PendingFirstMessage | null>(null);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  /** Last chatId we associated with the in-memory thread (for cache-on-switch). */
  const prevChatIdForCacheRef = useRef<string | null>(null);
  /** Skip one message-cache write right after chatId changes (messages may not match yet). */
  const skipLayoutCacheRef = useRef(false);
  const appliedHistoryVersionRef = useRef<Map<string, number>>(new Map());
  const pendingCanonicalHydrateRef = useRef<Set<string>>(new Set());
  const sessionKeyByChatIdRef = useRef<Map<string, string>>(new Map());

  const initial = useMemo(() => {
    if (!chatId) return historical;
    return messageCacheRef.current.get(chatId) ?? historical;
  }, [chatId, historical]);
  const handleTurnEnd = useCallback(() => {
    onTurnEnd?.();
  }, [onTurnEnd]);
  const {
    messages,
    isStreaming,
    runStartedAt,
    goalState,
    send,
    stop,
    setMessages,
    transcribeAudio,
    sendRawMessage,
    ttsToggle,
    streamError,
    dismissStreamError,
  } = useNanobotStream(chatId, initial, hasPendingToolCalls, handleTurnEnd);

  useEffect(() => {
    if (chatId && historyKey) sessionKeyByChatIdRef.current.set(chatId, historyKey);
  }, [chatId, historyKey]);

  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);

  const showHeroComposer = messages.length === 0 && !loading;
  const wasShowingHeroComposerRef = useRef(showHeroComposer);
  const modelBadge = useMemo(
    () => toModelBadgeInfo(modelName, settings),
    [modelName, settings],
  );
  useEffect(() => {
    if (showHeroComposer && !wasShowingHeroComposerRef.current) {
      setHeroGreetingKey(randomHeroGreetingKey());
    }
    wasShowingHeroComposerRef.current = showHeroComposer;
  }, [showHeroComposer]);

  const withWorkspaceScope = useCallback(
    (options?: SendOptions): SendOptions | undefined => {
      if (!workspaceScope) return options;
      return {
        ...(options ?? {}),
        workspaceScope,
      };
    },
    [workspaceScope],
  );

  const refreshModelSettings = useCallback(async () => {
    try {
      setSettings(await fetchSettings(token));
    } catch {
      if (!settingsSnapshot) setSettings(null);
    }
  }, [settingsSnapshot, token]);

  useEffect(() => {
    if (settingsSnapshot) {
      setSettings(settingsSnapshot);
      return;
    }
    void refreshModelSettings();
  }, [refreshModelSettings, settingsSnapshot]);

  useEffect(() => {
    return client.onRuntimeModelUpdate(() => {
      void refreshModelSettings();
    });
  }, [client, refreshModelSettings]);

  useEffect(() => {
    if (!chatId || loading) return;
    const cached = messageCacheRef.current.get(chatId);
    const appliedVersion = appliedHistoryVersionRef.current.get(chatId) ?? 0;
    const hasPendingCanonicalHydrate = pendingCanonicalHydrateRef.current.has(chatId);
    const hasNewCanonicalHistory = hasPendingCanonicalHydrate && historyVersion > appliedVersion;
    // When the user switches away and back, keep the local in-memory thread
    // state (including not-yet-persisted messages) instead of replacing it with
    // whatever the history endpoint currently knows about. Once a fresh
    // canonical replay arrives (e.g. after ``session_updated`` refresh), prefer it
    // so rendering converges to the same shape as a manual refresh.
    setMessages((prev) => {
      const normalizedHistory = projectWebuiThreadMessages(historical);
      const keepLiveMessages = (messagesToKeep: UIMessage[]) => {
        const projected = projectWebuiThreadMessages(messagesToKeep);
        messageCacheRef.current.set(chatId, projected);
        return projected;
      };
      if (hasNewCanonicalHistory && historical.length > 0) {
        if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
        pendingCanonicalHydrateRef.current.delete(chatId);
        appliedHistoryVersionRef.current.set(chatId, historyVersion);
        messageCacheRef.current.set(chatId, normalizedHistory);
        return normalizedHistory;
      }
      if (cached && cached.length > 0) {
        const normalizedCached = projectWebuiThreadMessages(cached);
        if (isStaleThreadSnapshot(prev, normalizedCached)) return keepLiveMessages(prev);
        return normalizedCached;
      }
      if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
      appliedHistoryVersionRef.current.set(chatId, historyVersion);
      if (normalizedHistory.length > 0) messageCacheRef.current.set(chatId, normalizedHistory);
      return normalizedHistory;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, chatId, historical, historyVersion]);

  useEffect(() => {
    if (!chatId) return;
    return client.onSessionUpdate((updatedChatId, scope) => {
      if (updatedChatId !== chatId) return;
      if (scope === "metadata") return;
      pendingCanonicalHydrateRef.current.add(chatId);
      refreshHistory();
    });
  }, [chatId, client, refreshHistory]);

  useEffect(() => {
    if (!chatId || loading) return;
    setScrollToBottomSignal((value) => value + 1);
  }, [chatId, loading, historical]);

  useEffect(() => {
    if (chatId) return;
    setMessages(projectWebuiThreadMessages(historical));
  }, [chatId, historical, setMessages]);

  useLayoutEffect(() => {
    if (chatId) {
      const prev = prevChatIdForCacheRef.current;
      if (prev && prev !== chatId) {
        messageCacheRef.current.set(prev, projectWebuiThreadMessages(messages));
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = chatId;
    } else {
      if (prevChatIdForCacheRef.current) {
        messageCacheRef.current.set(
          prevChatIdForCacheRef.current,
          projectWebuiThreadMessages(messages),
        );
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = null;
    }
  }, [chatId, messages]);

  // Persist thread to in-memory cache after paint so ``useNanobotStream``'s chat switch
  // ``useEffect`` reset has flushed; ``skipLayoutCacheRef`` drops the first run that still
  // sees the *previous* chat's ``messages`` (avoids stale rows leaking across sessions).
  useEffect(() => {
    if (!chatId) {
      return;
    }
    if (skipLayoutCacheRef.current) {
      skipLayoutCacheRef.current = false;
      return;
    }
    if (loading) {
      return;
    }
    messageCacheRef.current.set(chatId, projectWebuiThreadMessages(messages));
  }, [chatId, loading, messages]);

  useEffect(() => {
    if (!chatId) return;
    const pending = pendingFirstRef.current;
    if (!pending) return;
    pendingFirstRef.current = null;
    setScrollToBottomSignal((value) => value + 1);
    send(pending.content, pending.images, pending.options);
    setBooting(false);
  }, [chatId, send]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const commands = await listSlashCommands(token);
        if (!cancelled) setSlashCommands(commands);
      } catch {
        if (!cancelled) setSlashCommands([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const refreshCliApps = useCallback(async () => {
    try {
      const payload = await fetchCliApps(token);
      setCliApps(installedCliAppsFromPayload(payload));
    } catch {
      setCliApps([]);
    }
  }, [token]);

  const refreshMcpPresets = useCallback(async () => {
    try {
      const payload = await fetchMcpPresets(token);
      setMcpPresets(installedMcpPresetsFromPayload(payload));
    } catch {
      setMcpPresets([]);
    }
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await fetchCliApps(token);
        if (!cancelled) setCliApps(installedCliAppsFromPayload(payload));
      } catch {
        if (!cancelled) setCliApps([]);
      }
    };
    load();

    const refreshOnFocus = () => {
      if (document.visibilityState === "hidden") return;
      void refreshCliApps();
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    const refreshOnCliAppsChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isCliAppsPayload(payload)) {
        setCliApps(installedCliAppsFromPayload(payload));
        return;
      }
      void refreshCliApps();
    };
    window.addEventListener(CLI_APPS_CHANGED_EVENT, refreshOnCliAppsChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
      window.removeEventListener(CLI_APPS_CHANGED_EVENT, refreshOnCliAppsChanged);
    };
  }, [refreshCliApps, token]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await fetchMcpPresets(token);
        if (!cancelled) setMcpPresets(installedMcpPresetsFromPayload(payload));
      } catch {
        if (!cancelled) setMcpPresets([]);
      }
    };
    load();

    const refreshOnFocus = () => {
      if (document.visibilityState === "hidden") return;
      void refreshMcpPresets();
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    const refreshOnMcpPresetsChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isMcpPresetsPayload(payload)) {
        setMcpPresets(installedMcpPresetsFromPayload(payload));
        return;
      }
      void refreshMcpPresets();
    };
    window.addEventListener(MCP_PRESETS_CHANGED_EVENT, refreshOnMcpPresetsChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
      window.removeEventListener(MCP_PRESETS_CHANGED_EVENT, refreshOnMcpPresetsChanged);
    };
  }, [refreshMcpPresets, token]);

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendImage[], options?: SendOptions) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = { content, images, options: withWorkspaceScope(options) };
      const newId = await onCreateChat?.(workspaceScope);
      if (!newId) {
        pendingFirstRef.current = null;
        setBooting(false);
      }
    },
    [booting, onCreateChat, withWorkspaceScope, workspaceScope],
  );

  const handleThreadSend = useCallback(
    (content: string, images?: SendImage[], options?: SendOptions) => {
      setScrollToBottomSignal((value) => value + 1);
      send(content, images, withWorkspaceScope(options));
    },
    [send, withWorkspaceScope],
  );

  const stopCamera = useCallback(() => {
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }
    setCameraStream(null);
    setIsCameraOn(false);
  }, []);

  const toggleCamera = useCallback(async () => {
    if (isCameraOn) {
      stopCamera();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      cameraStreamRef.current = stream;
      setCameraStream(stream);
      setIsCameraOn(true);
    } catch (error) {
      console.error("Failed to access camera:", error);
    }
  }, [isCameraOn, stopCamera]);

  useEffect(() => stopCamera, [stopCamera]);

  const composer = (
    <>
      {streamError ? (
        <StreamErrorNotice
          error={streamError}
          onDismiss={dismissStreamError}
        />
      ) : null}
      {session ? (
        <ThreadComposer
          onSend={handleThreadSend}
          disabled={!chatId}
          isStreaming={isStreaming}
          placeholder={
            showHeroComposer
              ? t("thread.composer.placeholderHero")
              : t("thread.composer.placeholderThread")
          }
          modelLabel={modelBadge.label}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          variant={showHeroComposer ? "hero" : "thread"}
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          onStop={stop}
          runStartedAt={runStartedAt}
          goalState={goalState}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
          pendingQueueKey={chatId}
          token={token}
          onTranscribe={transcribeAudio}
          onSendStreamAudio={sendRawMessage}
        />
      ) : (
        <ThreadComposer
          onSend={handleWelcomeSend}
          disabled={booting}
          isStreaming={isStreaming}
          placeholder={
            booting
              ? t("thread.composer.placeholderOpening")
              : t("thread.composer.placeholderHero")
          }
          modelLabel={modelBadge.label}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          variant="hero"
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          runStartedAt={runStartedAt}
          goalState={goalState}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
          onTranscribe={transcribeAudio}
        />
      )}
    </>
  );

  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <h1 className="text-balance text-[40px] font-normal leading-tight tracking-[-0.045em] text-foreground sm:text-[48px]">
        {t(heroGreetingKey)}
      </h1>
    </div>
  );

  return (
    <MediaQueueProvider sessionId={session?.key}>
      <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        {!hideHeader ? (
          <ThreadHeader
            title={title}
            onToggleSidebar={onToggleSidebar}
            theme={theme}
            onToggleTheme={onToggleTheme}
            hideSidebarToggleForHostChrome={hideSidebarToggleForHostChrome}
            minimal={!session && !loading}
            isCameraOn={isCameraOn}
            onToggleCamera={toggleCamera}
            enableTts={enableTts}
            onToggleTts={() => {
              setEnableTts(prev => {
                const newValue = !prev;
                ttsToggle(newValue);
                return newValue;
              });
            }}
          />
        ) : null}
        {cameraStream ? (
          <FloatingCameraPreview
            stream={cameraStream}
            onClose={stopCamera}
          />
        ) : null}
        <ThreadViewport
          messages={displayMessages}
          isStreaming={isStreaming}
          emptyState={emptyState}
          composer={composer}
          scrollToBottomSignal={scrollToBottomSignal}
          conversationKey={historyKey}
          showScrollToBottomButton={!!session}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
        />
      </section>
    </MediaQueueProvider>
  );
}
