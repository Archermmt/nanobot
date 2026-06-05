import { Menu, Moon, Sun, Video, Volume2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ThreadHeaderProps {
  title: string;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleForHostChrome?: boolean;
  minimal?: boolean;
  isCameraOn?: boolean;
  onToggleCamera?: () => void;
  enableTts?: boolean;
  onToggleTts?: () => void;
}

export function ThreadHeader({
  title,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideSidebarToggleForHostChrome = false,
  minimal = false,
  isCameraOn = false,
  onToggleCamera,
  enableTts = false,
  onToggleTts,
}: ThreadHeaderProps) {
  const { t } = useTranslation();
  if (minimal) {
    return (
      <div className="relative z-10 flex h-11 items-center justify-between gap-3 px-3 py-2">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          onClick={onToggleSidebar}
          className={cn(
            "h-7 w-7 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            hideSidebarToggleForHostChrome && "lg:hidden",
          )}
        >
          <Menu className="h-3.5 w-3.5" />
        </Button>
        <div className="ml-auto flex items-center gap-1.5">
          {onToggleCamera && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={isCameraOn ? t("thread.composer.camera.stopCamera") : t("thread.composer.camera.startCamera")}
              onClick={onToggleCamera}
              className={cn(
                "h-7 w-7 rounded-full text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-all",
                isCameraOn && "bg-green-500/10 text-green-500 hover:bg-green-500/15 hover:text-green-600 dark:bg-green-500/15 dark:hover:bg-green-500/20",
              )}
            >
              <Video className="h-3.5 w-3.5" />
            </Button>
          )}
          {onToggleTts && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={enableTts ? t("thread.composer.tts.disableTts") : t("thread.composer.tts.enableTts")}
              onClick={onToggleTts}
              className={cn(
                "h-7 w-7 rounded-full text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-all",
                enableTts && "bg-blue-500/10 text-blue-500 hover:bg-blue-500/15 hover:text-blue-600 dark:bg-blue-500/15 dark:hover:bg-blue-500/20",
              )}
            >
              <Volume2 className="h-3.5 w-3.5" />
            </Button>
          )}
          <ThemeButton
            theme={theme}
            onToggleTheme={onToggleTheme}
            label={t("thread.header.toggleTheme")}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="relative z-10 flex items-center justify-between gap-3 px-3 py-2">
      <div className="relative flex min-w-0 items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          onClick={onToggleSidebar}
          className={cn(
            "h-7 w-7 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            hideSidebarToggleForHostChrome && "lg:hidden",
          )}
        >
          <Menu className="h-3.5 w-3.5" />
        </Button>
        <div className="flex min-w-0 items-center rounded-md px-1.5 py-1 text-[12px] font-medium text-muted-foreground">
          <span className="max-w-[min(60vw,32rem)] truncate">{title}</span>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        {onToggleCamera && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label={isCameraOn ? t("thread.composer.camera.stopCamera") : t("thread.composer.camera.startCamera")}
            onClick={onToggleCamera}
            className={cn(
              "h-8 w-8 rounded-full text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-all",
              isCameraOn && "bg-green-500/10 text-green-500 hover:bg-green-500/15 hover:text-green-600 dark:bg-green-500/15 dark:hover:bg-green-500/20",
            )}
          >
            <Video className="h-4 w-4" />
          </Button>
        )}
        {onToggleTts && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label={enableTts ? t("thread.composer.tts.disableTts") : t("thread.composer.tts.enableTts")}
            onClick={onToggleTts}
            className={cn(
              "h-8 w-8 rounded-full text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-all",
              enableTts && "bg-blue-500/10 text-blue-500 hover:bg-blue-500/15 hover:text-blue-600 dark:bg-blue-500/15 dark:hover:bg-blue-500/20",
            )}
          >
            <Volume2 className="h-4 w-4" />
          </Button>
        )}
        <ThemeButton
          theme={theme}
          onToggleTheme={onToggleTheme}
          label={t("thread.header.toggleTheme")}
        />
      </div>

      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-full h-4" />
    </div>
  );
}

function ThemeButton({
  theme,
  onToggleTheme,
  label,
  className,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  label: string;
  className?: string;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      onClick={onToggleTheme}
      className={cn(
        "h-8 w-8 rounded-full text-muted-foreground/85 hover:bg-accent/40 hover:text-foreground",
        className,
      )}
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </Button>
  );
}
