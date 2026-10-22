# Phase 4 integration config snapshot (2026-10-22)

Copies of the live, non-git config files the integration changed (no secrets). Live files win; this is the versioned record for ops/hq.

## `Editing Plugin\.claude\settings.json`
```json
{
  "permissions": {
    "deny": [
      "mcp__magnific",
      "mcp__f581ba42-e37e-4c5f-8831-25a90a44f80e",
      "mcp__0f592bed-db3f-401e-9980-fec370dba26f",
      "mcp__plugin_oh-my-claudecode_t",
      "Skill(gstack-ship)",
      "Skill(gstack-land-and-deploy)",
      "Skill(gstack-setup-deploy)",
      "Skill(gstack-canary)",
      "Skill(gstack-landing-report)",
      "Skill(gstack-codex)",
      "Skill(gstack-setup-gbrain)",
      "Skill(gstack-sync-gbrain)",
      "Skill(gstack-pair-agent)",
      "Skill(gstack-setup-browser-cookies)",
      "Skill(gstack-connect-chrome)",
      "Skill(gstack-open-gstack-browser)",
      "Skill(gstack-scrape)",
      "Skill(gstack-skillify)",
      "Skill(gstack-eval-plan)",
      "Skill(gstack-benchmark-models)",
      "Skill(gstack-upgrade)",
      "Skill(gstack-plan-tune)",
      "Skill(gstack-design-shotgun)",
      "Skill(gstack-design-consultation)",
      "Skill(oh-my-claudecode:autopilot)",
      "Skill(oh-my-claudecode:ralph)",
      "Skill(oh-my-claudecode:ultragoal)",
      "Skill(oh-my-claudecode:ralplan)",
      "Skill(oh-my-claudecode:team)",
      "Skill(oh-my-claudecode:ask)",
      "Skill(oh-my-claudecode:self-improve)",
      "Skill(oh-my-claudecode:autoresearch)",
      "Skill(oh-my-claudecode:release)",
      "Skill(oh-my-claudecode:pr)",
      "Skill(oh-my-claudecode:launch)",
      "Skill(oh-my-claudecode:harbor)",
      "Skill(oh-my-claudecode:configure-notifications)",
      "Skill(oh-my-claudecode:hud)",
      "Skill(oh-my-claudecode:omc-setup)",
      "Skill(oh-my-claudecode:skillify)",
      "Skill(oh-my-claudecode:drydock)",
      "Skill(oh-my-claudecode:deepinit)",
      "Skill(oh-my-claudecode:project-session-manager)",
      "Skill(oh-my-claudecode:graph)",
      "Skill(oh-my-claudecode:wiki)",
      "Skill(oh-my-claudecode:trace)"
    ]
  },
  "enabledPlugins": {
    "plugin-dev@claude-plugins-official": true,
    "windsor-ai@synced": false,
    "oh-my-claudecode@omc": true
  },
  "extraKnownMarketplaces": {
    "claude-plugins-official": {
      "source": {
        "source": "github",
        "repo": "anthropics/claude-plugins-official"
      }
    },
    "omc": {
      "source": {
        "source": "git",
        "url": "https://github.com/Yeachan-Heo/oh-my-claudecode.git",
        "ref": "v5.7.6"
      }
    }
  },
  "env": {
    "OMC_SKIP_HOOKS": "keyword-detector,skill-injector,persistent-mode,workflow-drift-guard",
    "OMC_READ_BUDGET": "off",
    "OMC_UPDATE_REGISTRY_BASE": "http://127.0.0.1:9",
    "OMC_NOTIFY": "0",
    "OMC_JEV": "off",
    "OMC_BUDGET_ENFORCE": "off",
    "OMC_CONTEXT_GUARD_THRESHOLD": "94"
  }
}
```

## `Editing Plugin\.claude\omc.jsonc`
```jsonc
// AI-infra restart Phase 4 (2026-10-22): OMC is the execution layer only. No keyword auto-activation
// (belt and braces with OMC_SKIP_HOOKS=keyword-detector in settings.json). Rules: 00-HQ/AGENT_ROUTING_RULES.md.
{"keywordDetector":{"disabled":["ralph","autopilot","ultragoal","ralplan","deep-interview","ai-slop-cleaner","tdd","code-review","security-review","ultrathink","deepsearch","analyze","wiki"]}}
```

## `~/.claude/.omc-config.json`
```json
{
  "claudeMdEnabled": false
}
```

## `WhyNotCut/.git/info/exclude` (added lines)
```
# OMC runtime state (AI-infra restart Phase 4, local only)
.omc/
```
