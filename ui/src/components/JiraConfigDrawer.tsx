import { useState } from "react";
import { CheckCircle2, ChevronDown, KeyRound } from "lucide-react";
import type { JiraConfig } from "../lib/api";
import { setJiraConfigField } from "../lib/api";
import { cn } from "../lib/utils";

type Props = {
  config: JiraConfig;
  onChange: (next: JiraConfig) => void;
};

export default function JiraConfigDrawer({ config, onChange }: Props) {
  const [open, setOpen] = useState(!config.url_set || !config.email_set || !config.token_set || !config.project_set);
  const [urlDraft, setUrlDraft] = useState(config.url);
  const [emailDraft, setEmailDraft] = useState("");
  const [tokenDraft, setTokenDraft] = useState("");
  const [projectDraft, setProjectDraft] = useState(config.project);
  const [saving, setSaving] = useState<string | null>(null);

  const fullyConfigured =
    config.url_set && config.email_set && config.token_set && config.project_set;

  const save = async (
    field: "url" | "email" | "token" | "project",
    value: string,
  ) => {
    setSaving(field);
    try {
      const next = await setJiraConfigField(field, value);
      onChange(next);
      if (field === "email") setEmailDraft("");
      if (field === "token") setTokenDraft("");
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-[11px] uppercase tracking-wider"
      >
        <span className="flex items-center gap-2 text-white/60">
          <KeyRound className="w-3.5 h-3.5" /> Jira connection
          {fullyConfigured ? (
            <span className="flex items-center gap-1 text-neon-green normal-case tracking-normal text-[10px]">
              <CheckCircle2 className="w-3 h-3" /> configured ({config.project})
            </span>
          ) : (
            <span className="text-neon-amber normal-case tracking-normal text-[10px]">
              not configured
            </span>
          )}
        </span>
        <ChevronDown
          className={cn("w-3.5 h-3.5 text-white/40 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 flex flex-col gap-2 border-t border-white/5">
          <p className="text-[11px] text-white/40 leading-snug">
            Held in memory only. Env vars <span className="font-mono">JIRA_URL</span>,
            <span className="font-mono"> JIRA_EMAIL</span>,
            <span className="font-mono"> JIRA_API_TOKEN</span>,
            <span className="font-mono"> JIRA_PROJECT</span> are loaded on startup.
          </p>
          <Field
            label="Site URL"
            placeholder="https://your-org.atlassian.net"
            value={urlDraft}
            onChange={setUrlDraft}
            onSave={() => save("url", urlDraft)}
            isSet={config.url_set}
            saving={saving === "url"}
          />
          <Field
            label="Email"
            placeholder="you@example.com"
            type="email"
            value={emailDraft}
            onChange={setEmailDraft}
            onSave={() => save("email", emailDraft)}
            isSet={config.email_set}
            saving={saving === "email"}
            secret
          />
          <Field
            label="API token"
            placeholder="…"
            type="password"
            value={tokenDraft}
            onChange={setTokenDraft}
            onSave={() => save("token", tokenDraft)}
            isSet={config.token_set}
            saving={saving === "token"}
            secret
          />
          <Field
            label="Project key"
            placeholder="DOINGS"
            value={projectDraft}
            onChange={(v) => setProjectDraft(v.toUpperCase())}
            onSave={() => save("project", projectDraft)}
            isSet={config.project_set}
            saving={saving === "project"}
          />
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  placeholder,
  value,
  onChange,
  onSave,
  isSet,
  saving,
  type = "text",
  secret = false,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  onSave: () => void;
  isSet: boolean;
  saving: boolean;
  type?: string;
  secret?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-white/50">{label}</span>
        <span
          className={cn(
            "text-[10px] uppercase tracking-wider",
            isSet ? "text-neon-green" : "text-white/30",
          )}
        >
          {isSet ? (secret ? "set" : "saved") : "not set"}
        </span>
      </div>
      <div className="flex gap-1.5">
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 text-[11px] bg-black/40 border border-white/10 rounded-md px-2 py-1 text-white placeholder:text-white/25 focus:outline-none focus:border-neon-cyan/60 font-mono"
        />
        <button
          onClick={onSave}
          disabled={saving || (secret && !value.trim())}
          className="px-2.5 py-1 rounded-md text-[10px] font-medium text-neon-cyan bg-neon-cyan/10 border border-neon-cyan/40 hover:bg-neon-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? "…" : "Save"}
        </button>
        {isSet && (
          <button
            onClick={() => {
              onChange("");
              onSave();
            }}
            disabled={saving}
            className="px-2.5 py-1 rounded-md text-[10px] text-white/60 hover:text-white hover:bg-white/5 disabled:opacity-40"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
