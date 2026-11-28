pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Io
import AnoShell.Config
import qs.components
import qs.components.effects
import qs.services

// AGENT OS — Cockpit multi-agents Liquid Glass façon Katana (Super + Maj + A).
// Goutte de verre réfractive qui sort de la Dynamic Island :
//  - Canvas spatial déplaçable (nœud Orchestrateur + liaisons Bézier + cartes agents draggables)
//  - Cockpit & Inspecteur live (timeline outils/étapes, Git status, CHAT DIRECT vers l'agent dans son terminal)
//  - Commandant IA (« Katana AI » propulsé par Gemini qui comprend tes ordres et pilote réellement tous tes agents)
//  - Escouade (Swarm Dispatch multi-moteurs sur tous tes projets auto-découverts)
Item {
    id: root

    required property ShellScreen screen
    required property ScreenState screenState
    property Item island

    readonly property bool shown: screenState?.agentos ?? false

    // ── Ouverture : la goutte de verre part de l'île et se déploie au centre ──
    property real morph: shown ? 1 : 0
    readonly property real offsetScale: 1 - morph
    property real fromX
    property real fromW: 220
    property real fromBottom: 38
    property real fromR: 19
    readonly property real fromTop: -70
    readonly property real hMorph: Math.min(1, morph)
    readonly property real curX: fromX + (x - fromX) * hMorph
    readonly property real curW: fromW + (width - fromW) * hMorph
    readonly property real curTop: fromTop + (y - fromTop) * morph
    readonly property real curBottom: fromBottom + (y + height - fromBottom) * morph
    readonly property real curR: fromR + (30 - fromR) * hMorph
    readonly property real reveal: Math.max(0, Math.min(1, (morph - 0.4) / 0.6))

    // ── Palette Liquid Glass ──
    readonly property color fg: Colours.palette.m3onSurface
    readonly property color fgDim: Qt.alpha(fg, 0.58)
    readonly property color fgMute: Qt.alpha(fg, 0.36)
    readonly property color fgFaint: Qt.alpha(fg, 0.08)
    readonly property color accent: Colours.palette.m3primary
    readonly property color leadTint: Agents.waiting > 0 ? "#ff9f0a" : (Agents.lead ? Agents.kindColour(Agents.lead.kind) : accent)
    readonly property color aiTint: "#a78bfa"
    readonly property color green: "#32d74b"
    readonly property color orange: "#ff9f0a"
    readonly property color red: "#ff453a"
    readonly property string agentsBin: "ano-agents"
    readonly property string dictateBin: "ano-dictate"

    // ── État de l'application ──
    property int viewTab: 0 // 0 = Canvas, 1 = Cockpit & Chat agent, 2 = Commandant IA, 3 = Escouade
    property string selectedId: ""
    property string kindFilter: "all"
    property var cardOffsets: ({})
    property var projects: []
    property int projectIdx: 0
    property string dockTarget: "ai" // "ai" (Commandant IA) ou un moteur ("agy", "claude", "codex", "copilot", "opencode", "antigravity")
    property var swarmKinds: ({ claude: true, codex: true, copilot: false, opencode: false, agy: true, antigravity: false })
    property var detailData: ({ id: "", events: [], steps: [], gitStatus: [], gitFiles: [] })
    property int inspectorTab: 0 // 0 = Journal, 1 = Terminal Live, 2 = Diff Git
    property int expandedEventIdx: -1
    property var screenData: ({ ok: false, text: "", lineCount: 0, kittyWin: null, detail: "" })
    property bool screenLoading: false
    property string diffFile: ""
    property var diffData: ({ ok: true, file: "", added: 0, removed: 0, truncated: false, stat: "", lines: [], raw: "", detail: "" })
    property bool diffLoading: false
    property bool modelPickerOpen: false
    property var modelPickerAgent: null
    property var modelCatalog: ({ kind: "", canApplyLive: false, efforts: [], groups: [], models: [] })
    property var modelCatalogCache: ({})
    property bool modelCatalogLoading: false
    property bool applyingModel: false
    property string pickedEffort: ""
    property string modelFilterText: ""
    property var chatHistory: [] // [{ role: "user"|"ai", text: "", executed: [] }]
    property bool aiThinking: false
    property string aiStreamStatus: ""
    property var aiStreamBadges: []
    property bool aiDoneReceived: false
    property bool sendingDirect: false
    property bool dictating: false
    property string toastMsg: ""

    // ── Canvas Pan/Zoom, Conflits & Persistance ──
    property real canvasPanX: 0
    property real canvasPanY: 0
    property real canvasZoom: 1.0
    property real wirePulse: 0
    property bool layoutLoaded: false

    // ── Escouade Pro (worktrees + rôles + filtre projets) ──
    property bool swarmWorktree: true
    property string swarmPreset: "shared" // "shared" | "impl_review" | "audit_perf" | "duel"
    property bool swarmDeploying: false
    property string swarmProjectFilter: ""

    // ── Navigation clavier, Palette projets, Aide, Worktrees & Broadcast ──
    property int permIdx: 0
    property bool projectPickerOpen: false
    property string projectPickerQuery: ""
    property int projectPickerCursor: 0
    property bool helpOpen: false
    property var worktrees: []
    property bool broadcasting: false
    property string fleetFilter: ""
    property var dockHistory: []
    property int dockHistIdx: -1

    readonly property int conflictRepoCount: {
        let n = 0;
        for (const k in repoAgentCounts)
            if (repoAgentCounts[k] > 1)
                n += 1;
        return n;
    }

    readonly property int liveCliCount: Agents.shown.filter(a => a.alive && a.surface === "cli").length

    readonly property var filteredFleet: {
        const q = (fleetFilter || "").trim().toLowerCase();
        if (!q)
            return Agents.shown;
        return Agents.shown.filter(a => (a.project || "").toLowerCase().indexOf(q) >= 0
            || (a.kind || "").toLowerCase().indexOf(q) >= 0
            || (a.branch || "").toLowerCase().indexOf(q) >= 0
            || (a.model || "").toLowerCase().indexOf(q) >= 0);
    }

    readonly property var repoAgentCounts: {
        const counts = {};
        for (const a of Agents.shown) {
            const p = String(a.cwd || "").replace(/\/+$/, "");
            if (p)
                counts[p] = (counts[p] || 0) + 1;
        }
        return counts;
    }

    readonly property var dynamicSuggestions: {
        const out = [];
        const projName = currentProject?.name ?? "";
        if (Agents.perms.length > 0)
            out.push(I18n.tr("Inspecte et explique la permission demandée par %1").arg(Agents.perms[0].project || "l'agent"));
        if (Agents.working > 0)
            out.push(I18n.tr("Fais-moi un bilan détaillé de mes %1 agent(s) actifs").arg(Agents.working));
        else
            out.push(I18n.tr("Fais-moi un bilan de tous mes agents et projets récents"));
        if (projName) {
            out.push(I18n.tr("Résume l'état git et les derniers changements de %1").arg(projName));
            out.push(I18n.tr("Déploie Claude et Codex sur %1 pour auditer les bugs").arg(projName));
        }
        if (Agents.shown.length >= 2)
            out.push(I18n.tr("Compare ce que font mes agents en cours et signale les conflits"));
        else if (Agents.shown.length === 1)
            out.push(I18n.tr("Inspecte %1 (%2) et propose la prochaine étape").arg(Agents.kindName(Agents.shown[0].kind)).arg(Agents.shown[0].project));
        if (Agents.working > 0)
            out.push(I18n.tr("Stoppe les agents CLI qui tournent"));
        else if (projName)
            out.push(I18n.tr("Lance AGY CLI sur %1 pour vérifier lint et tests").arg(projName));
        return out.slice(0, 6);
    }

    readonly property var activePerm: {
        if (Agents.perms.length === 0)
            return null;
        const idx = Math.max(0, Math.min(permIdx, Agents.perms.length - 1));
        return Agents.perms[idx];
    }

    readonly property var visibleAgents: {
        const src = Agents.shown;
        if (kindFilter === "all")
            return src;
        if (kindFilter === "active")
            return src.filter(a => a.status !== "idle");
        return src.filter(a => a.kind === kindFilter);
    }

    readonly property var selectedAgent: {
        if (selectedId) {
            const found = Agents.shown.find(a => a.id === selectedId);
            if (found)
                return found;
        }
        return Agents.shown[0] ?? null;
    }

    // Agent déjà ouvert correspondant au moteur choisi dans le Command Dock
    readonly property var dockExistingAgent: {
        if (dockTarget === "ai" || dockTarget === "all")
            return null;
        return Agents.shown.find(a => a.kind === dockTarget && a.alive) ?? Agents.shown.find(a => a.kind === dockTarget) ?? null;
    }

    readonly property color dockTint: dockTarget === "ai" ? aiTint : (dockTarget === "all" ? orange : Agents.kindColour(dockTarget))

    readonly property var currentProject: projects.length > 0 ? projects[Math.max(0, Math.min(projectIdx, projects.length - 1))] : null

    readonly property int swarmCount: {
        let n = 0;
        for (const k of Agents.launchKinds)
            if (swarmKinds[k])
                n += 1;
        return n;
    }

    function close(): void {
        screenState.agentos = false;
    }

    function flashToast(msg: string): void {
        toastMsg = msg;
        toastTimer.restart();
    }

    function refreshProjects(): void {
        if (!projProc.running)
            projProc.running = true;
    }

    function refreshHistory(): void {
        if (!histProc.running)
            histProc.running = true;
    }

    function clearHistory(): void {
        chatHistory = [];
        Quickshell.execDetached([root.agentsBin, "history-clear"]);
    }

    function toggleDictation(): void {
        if (dictating) {
            if (dictProc.running)
                dictProc.write('{"stop":true}\n');
            dictating = false;
            return;
        }
        dictating = true;
        flashToast(I18n.tr("Écoute micro… reclique pour valider"));
        dictProc.running = true;
    }

    function refreshDetail(): void {
        const ag = selectedAgent;
        if (!ag || !ag.id) {
            detailData = { id: "", events: [], steps: [], gitStatus: [], gitFiles: [] };
            return;
        }
        if (detailProc.running)
            return;
        const cmd = [root.agentsBin, "detail", ag.id];
        if (ag.kind)
            cmd.push("--kind", String(ag.kind));
        if (ag.cwd)
            cmd.push("--cwd", String(ag.cwd));
        if (ag.pid)
            cmd.push("--pid", String(ag.pid));
        detailProc.command = cmd;
        detailProc.running = true;
    }

    function copyText(txt: string, label: string): void {
        const s = String(txt || "");
        if (!s)
            return;
        Quickshell.execDetached(["wl-copy", "--", s]);
        flashToast(label || I18n.tr("Copié dans le presse-papiers ✓"));
    }

    function refreshScreen(): void {
        const ag = selectedAgent;
        if (!ag || !ag.id) {
            screenData = { ok: false, text: "", lineCount: 0, kittyWin: null, detail: "" };
            return;
        }
        if (screenProc.running)
            return;
        screenLoading = true;
        const cmd = [root.agentsBin, "screen", ag.id];
        if (ag.pid)
            cmd.push("--pid", String(ag.pid));
        screenProc.command = cmd;
        screenProc.running = true;
    }

    function refreshDiff(filePath: string): void {
        const ag = selectedAgent;
        const fp = filePath !== undefined ? String(filePath) : diffFile;
        diffFile = fp;
        if (!ag || !ag.cwd) {
            diffData = { ok: false, file: fp, added: 0, removed: 0, truncated: false, stat: "", lines: [], raw: "", detail: I18n.tr("Aucun dépôt Git détecté pour cet agent.") };
            return;
        }
        if (diffProc.running)
            return;
        diffLoading = true;
        const cmd = [root.agentsBin, "diff", String(ag.cwd)];
        if (fp)
            cmd.push(fp);
        diffProc.command = cmd;
        diffProc.running = true;
    }

    function openDiffFile(filePath: string): void {
        inspectorTab = 2;
        refreshDiff(filePath || "");
    }

    function detectEffortFromModel(raw: string): string {
        const low = String(raw || "").toLowerCase();
        if (low.indexOf("xhigh") >= 0)
            return "xhigh";
        if (low.indexOf("max") >= 0)
            return "max";
        if (low.indexOf("high") >= 0)
            return "high";
        if (low.indexOf("medium") >= 0 || low.indexOf("moyen") >= 0)
            return "medium";
        if (low.indexOf("low") >= 0 || low.indexOf("faible") >= 0)
            return "low";
        return "";
    }

    function openModelPicker(agent: var): void {
        if (!agent?.kind)
            return;
        modelPickerAgent = agent;
        modelPickerOpen = true;
        modelFilterText = "";
        pickedEffort = detectEffortFromModel(agent.model || "");
        const k = String(agent.kind).toLowerCase();
        if (modelCatalogCache[k]) {
            modelCatalog = modelCatalogCache[k];
            modelCatalogLoading = false;
            return;
        }
        modelCatalog = { kind: k, canApplyLive: k !== "antigravity", efforts: [], groups: [], models: [] };
        modelCatalogLoading = true;
        if (modelsProc.running)
            modelsProc.running = false;
        modelsProc.command = [root.agentsBin, "models", k, "--catalog"];
        modelsProc.running = true;
    }

    function closeModelPicker(): void {
        modelPickerOpen = false;
    }

    function applyPickedModel(group: var): void {
        const ag = modelPickerAgent;
        if (!ag || !group || applyingModel)
            return;
        let targetModel = group.slug || group.base || "";
        let targetEff = pickedEffort;
        if (group.variants && targetEff && group.variants[targetEff]) {
            targetModel = group.variants[targetEff].display || group.variants[targetEff].slug || targetModel;
        } else if (group.display && (!group.efforts || group.efforts.length === 0)) {
            targetModel = group.display;
        }
        applyingModel = true;
        const cmd = [root.agentsBin, "set-model", targetModel];
        if (targetEff)
            cmd.push("--effort", targetEff);
        if (ag.id)
            cmd.push("--agent", String(ag.id));
        if (ag.kind)
            cmd.push("--kind", String(ag.kind));
        setModelProc.command = cmd;
        setModelProc.running = true;
    }

    function applyEffortOnly(eff: string): void {
        pickedEffort = pickedEffort === eff ? "" : eff;
    }

    function filteredModelGroups(): var {
        const groups = modelCatalog?.groups ?? [];
        const q = (modelFilterText || "").trim().toLowerCase();
        if (!q)
            return groups;
        return groups.filter(g => (g.base || "").toLowerCase().indexOf(q) >= 0 || (g.slug || "").toLowerCase().indexOf(q) >= 0);
    }

    function inspectAgent(agent: var, focusChat: bool): void {
        if (!agent?.id)
            return;
        selectedId = agent.id;
        viewTab = 1;
        expandedEventIdx = -1;
        refreshDetail();
        if (inspectorTab === 1)
            refreshScreen();
        else if (inspectorTab === 2)
            refreshDiff("");
        if (focusChat)
            directFocusTimer.restart();
    }

    function resetCanvasLayout(): void {
        cardOffsets = ({});
        canvasPanX = 0;
        canvasPanY = 0;
        canvasZoom = 1.0;
        canvasWires.requestPaint();
        scheduleLayoutSave();
        flashToast(I18n.tr("Canvas réaligné"));
    }

    function setCardOffset(id: string, dx: real, dy: real): void {
        const next = Object.assign({}, cardOffsets);
        next[id] = { dx: dx, dy: dy };
        cardOffsets = next;
        canvasWires.requestPaint();
        scheduleLayoutSave();
    }

    function setCanvasZoom(nextZ: real): void {
        canvasZoom = Math.max(0.65, Math.min(1.35, Math.round(nextZ * 20) / 20));
        canvasWires.requestPaint();
        scheduleLayoutSave();
    }

    function scheduleLayoutSave(): void {
        layoutSaveTimer.restart();
    }

    function saveLayoutNow(): void {
        const payload = JSON.stringify({
            offsets: cardOffsets,
            panX: canvasPanX,
            panY: canvasPanY,
            zoom: canvasZoom
        });
        Quickshell.execDetached([root.agentsBin, "layout-set", payload]);
    }

    function loadLayout(): void {
        if (layoutLoaded || layoutLoadProc.running)
            return;
        layoutLoadProc.running = true;
    }

    function cardPermFor(agent: var): var {
        if (!agent)
            return null;
        return Agents.perms.find(p => (agent.pid && p.agentPid === agent.pid) || (agent.project && p.project === agent.project)) ?? null;
    }

    function repoConflictCount(agent: var): int {
        const p = String(agent?.cwd || "").replace(/\/+$/, "");
        return p ? (repoAgentCounts[p] ?? 0) : 0;
    }

    function filteredProjectsList(query: string): var {
        const q = (query || "").trim().toLowerCase();
        if (!q)
            return projects;
        return projects.filter(p => (p.name || "").toLowerCase().indexOf(q) >= 0
            || (p.cwd || "").toLowerCase().indexOf(q) >= 0
            || (p.branch || "").toLowerCase().indexOf(q) >= 0);
    }

    function selectProjectByCwd(cwd: string): void {
        const idx = projects.findIndex(p => p.cwd === cwd);
        if (idx >= 0)
            projectIdx = idx;
    }

    function refreshWorktrees(): void {
        const cwd = currentProject?.cwd ?? "";
        if (!cwd) {
            worktrees = [];
            return;
        }
        if (wtListProc.running)
            wtListProc.running = false;
        wtListProc.command = [root.agentsBin, "worktrees", cwd];
        wtListProc.running = true;
    }

    function removeWorktree(wtPath: string): void {
        const cwd = currentProject?.cwd ?? "";
        if (!cwd || !wtPath || wtRemoveProc.running)
            return;
        wtRemoveProc.command = [root.agentsBin, "worktree-remove", cwd, wtPath];
        wtRemoveProc.running = true;
    }

    function openWorktreeDiff(wtPath: string): void {
        if (!wtPath)
            return;
        diffFile = "";
        viewTab = 1;
        inspectorTab = 2;
        diffLoading = true;
        if (diffProc.running)
            diffProc.running = false;
        diffProc.command = [root.agentsBin, "diff", wtPath];
        diffProc.running = true;
    }

    function broadcastToAll(msg: string): void {
        const txt = (msg || "").trim();
        if (!txt || broadcasting)
            return;
        broadcasting = true;
        broadcastProc.command = [root.agentsBin, "broadcast", txt];
        broadcastProc.running = true;
    }

    function stopAllWorking(): void {
        if (stopAllProc.running)
            return;
        stopAllProc.running = true;
    }

    function stepFleet(delta: int): void {
        const arr = Agents.shown;
        if (arr.length === 0)
            return;
        const curIdx = arr.findIndex(a => a.id === selectedAgent?.id);
        const nextIdx = curIdx < 0 ? 0 : (curIdx + delta + arr.length) % arr.length;
        selectedId = arr[nextIdx].id;
        if (viewTab !== 1)
            viewTab = 1;
    }

    function copyChatTranscript(): void {
        if (chatHistory.length === 0)
            return;
        const lines = [];
        for (const m of chatHistory) {
            lines.push(m.role === "user" ? `### Moi\n${m.text}` : `### Katana AI\n${m.text}`);
            if (m.executed && m.executed.length > 0)
                lines.push(m.executed.map(e => `- [${e.ok ? "OK" : "ERR"}] ${e.label}`).join("\n"));
        }
        copyText(lines.join("\n\n"), I18n.tr("Conversation Katana copiée ✓"));
    }

    function closeTopOverlayOrStudio(): void {
        if (helpOpen)
            helpOpen = false;
        else if (projectPickerOpen)
            closeProjectPicker();
        else if (modelPickerOpen)
            closeModelPicker();
        else
            close();
    }

    function openProjectPicker(): void {
        projectPickerOpen = true;
        projectPickerQuery = "";
        projectPickerCursor = 0;
        projectPickerFocusTimer.restart();
    }

    function closeProjectPicker(): void {
        projectPickerOpen = false;
    }

    function swarmRoleFor(kind: string): string {
        if (swarmPreset === "shared")
            return "";
        const chosen = Agents.launchKinds.filter(k => !!swarmKinds[k]);
        const pos = chosen.indexOf(kind);
        if (pos < 0)
            return "";
        if (swarmPreset === "impl_review") {
            const roles = [I18n.tr("Implémentation"), I18n.tr("Revue & Tests"), I18n.tr("Lint & Sécu")];
            return roles[pos % roles.length];
        }
        if (swarmPreset === "audit_perf") {
            const roles = [I18n.tr("Audit Bugs & Sécu"), I18n.tr("Perf & Mémoire"), I18n.tr("Architecture")];
            return roles[pos % roles.length];
        }
        if (swarmPreset === "duel") {
            return I18n.tr("Variante #%1").arg(pos + 1);
        }
        return "";
    }

    function toggleSwarmKind(k: string): void {
        const next = Object.assign({}, swarmKinds);
        next[k] = !next[k];
        swarmKinds = next;
    }

    // Parler directement à un agent précis (via Kitty remote ou reprise de session)
    function sendDirectToAgent(agent: var, text: string): void {
        const msg = (text || "").trim();
        if (!agent?.id || !msg)
            return;
        if (sendProc.running)
            return;
        sendingDirect = true;
        sendProc.command = [root.agentsBin, "send", agent.id, msg];
        sendProc.running = true;
    }

    // Parler au Commandant IA (Katana AI) en streaming JSONL
    function askCommander(text: string): void {
        const msg = (text || "").trim();
        if (!msg || aiThinking)
            return;
        const next = chatHistory.slice(-18);
        next.push({ role: "user", text: msg, executed: [] });
        chatHistory = next;
        viewTab = 2;
        aiThinking = true;
        aiDoneReceived = false;
        aiStreamStatus = I18n.tr("Analyse de ta flotte…");
        aiStreamBadges = [];
        const cwd = currentProject?.cwd ?? "";
        commanderProc.command = cwd
            ? [root.agentsBin, "commander", "--stream", "--cwd", cwd, msg]
            : [root.agentsBin, "commander", "--stream", msg];
        commanderProc.running = true;
    }

    function cancelCommander(): void {
        if (!aiThinking)
            return;
        if (commanderProc.running)
            commanderProc.running = false;
        aiThinking = false;
        aiDoneReceived = true;
        const next = chatHistory.slice(-18);
        next.push({
            role: "ai",
            text: I18n.tr("Ordre interrompu par l'utilisateur."),
            executed: aiStreamBadges
        });
        chatHistory = next;
        aiStreamStatus = "";
        aiStreamBadges = [];
        flashToast(I18n.tr("Ordre Katana AI annulé"));
    }

    function badgeClickable(badge: var): bool {
        if (!badge)
            return false;
        return Boolean(badge.agent_id || badge.kind || badge.cwd);
    }

    function openExecutedBadge(badge: var): void {
        if (!badge)
            return;
        if (badge.agent_id) {
            const exact = Agents.shown.find(a => a.id === badge.agent_id);
            if (exact) {
                inspectAgent(exact, false);
                return;
            }
        }
        if (badge.kind) {
            const byKind = Agents.shown.find(a => a.kind === badge.kind && a.alive) ?? Agents.shown.find(a => a.kind === badge.kind);
            if (byKind) {
                inspectAgent(byKind, false);
                return;
            }
        }
        if (badge.cwd) {
            selectProjectByCwd(badge.cwd);
            viewTab = 0;
            flashToast(I18n.tr("Projet sélectionné : %1").arg(currentProject?.name ?? badge.cwd));
        }
    }

    // Exécution depuis la barre inférieure (Command Dock)
    function submitDock(promptText: string): void {
        const msg = (promptText || "").trim();
        if (msg) {
            const nextH = dockHistory.filter(h => h !== msg).slice(-24);
            nextH.push(msg);
            dockHistory = nextH;
            dockHistIdx = -1;
        }
        if (dockTarget === "ai") {
            if (!msg) {
                viewTab = 2;
                return;
            }
            askCommander(msg);
            return;
        }
        if (dockTarget === "all") {
            if (!msg) {
                flashToast(I18n.tr("Écris un ordre à diffuser à tous les agents CLI"));
                return;
            }
            broadcastToAll(msg);
            return;
        }
        // Si une session de ce moteur existe déjà et qu'on écrit un ordre, on lui parle en direct !
        if (msg && dockExistingAgent) {
            sendDirectToAgent(dockExistingAgent, msg);
            return;
        }
        const cwd = currentProject?.cwd ?? "";
        Agents.dispatch(dockTarget, cwd, msg);
        flashToast(I18n.tr("%1 lancé sur %2").arg(Agents.kindName(dockTarget)).arg(currentProject?.name ?? "~"));
    }

    function launchSwarm(promptText: string): void {
        const cwd = currentProject?.cwd ?? "";
        const chosen = Agents.launchKinds.filter(k => !!swarmKinds[k]);
        if (chosen.length === 0) {
            flashToast(I18n.tr("Sélectionne au moins un agent"));
            return;
        }
        const basePrompt = (promptText || "").trim();
        const plan = chosen.map(k => {
            const role = swarmRoleFor(k);
            let finalPrompt = basePrompt;
            if (role) {
                if (swarmPreset === "impl_review") {
                    finalPrompt = `[Rôle : ${role}] ` + (basePrompt || "Travaille sur la tâche en cours selon ton rôle.");
                } else if (swarmPreset === "audit_perf") {
                    finalPrompt = `[Rôle : ${role}] ` + (basePrompt || "Audite le dépôt sur cet axe précis et liste les actions prioritaires.");
                } else if (swarmPreset === "duel") {
                    finalPrompt = `[Mode Duel · ${role}] Propose ta meilleure approche indépendante : ` + (basePrompt || "Améliore ce projet.");
                }
            }
            return { kind: k, role: role, prompt: finalPrompt };
        });
        if (swarmProc.running)
            return;
        swarmDeploying = true;
        const cmd = [root.agentsBin, "swarm-dispatch", "--cwd", cwd];
        if (swarmWorktree)
            cmd.push("--worktree");
        cmd.push("--plan", JSON.stringify(plan));
        swarmProc.command = cmd;
        swarmProc.running = true;
    }

    visible: morph > 0.001
    implicitWidth: Math.min(1160, Math.max(900, Math.round((screen?.width ?? 1920) * 0.63)))
    implicitHeight: Math.min(700, Math.max(570, Math.round((screen?.height ?? 1080) * 0.66)))

    Behavior on morph {
        NumberAnimation {
            duration: root.shown ? 560 : 340
            easing.type: root.shown ? Easing.OutBack : Easing.InOutCubic
            easing.overshoot: 0.65
        }
    }

    onShownChanged: {
        if (shown) {
            if (island && island.h > 1) {
                fromX = island.x;
                fromW = island.w;
                fromBottom = island.y + island.h;
                fromR = island.radius;
            } else {
                fromX = island ? island.x + island.width / 2 - 110 : x;
                fromW = 220;
                fromBottom = island ? island.y + 38 : 38;
                fromR = 19;
            }
            refreshProjects();
            refreshHistory();
            loadLayout();
            if (!selectedId && Agents.shown.length > 0)
                selectedId = Agents.shown[0].id;
            refreshDetail();
            canvasWires.requestPaint();
            dockInput.forceActiveFocus();
            openFocusTimer.restart();
        } else {
            helpOpen = false;
            modelPickerOpen = false;
            projectPickerOpen = false;
            if (dictating && dictProc.running) {
                dictProc.write('{"cancel":true}\n');
                dictating = false;
            }
        }
    }

    onProjectIdxChanged: {
        if (shown && viewTab === 3)
            refreshWorktrees();
    }

    onSelectedIdChanged: {
        expandedEventIdx = -1;
        diffFile = "";
        if (shown && viewTab === 1) {
            refreshDetail();
            if (inspectorTab === 1)
                refreshScreen();
            else if (inspectorTab === 2)
                refreshDiff("");
        }
    }

    onInspectorTabChanged: {
        if (!shown || viewTab !== 1)
            return;
        if (inspectorTab === 0)
            refreshDetail();
        else if (inspectorTab === 1)
            refreshScreen();
        else if (inspectorTab === 2)
            refreshDiff(diffFile);
    }

    onViewTabChanged: {
        if (viewTab === 1) {
            refreshDetail();
            if (inspectorTab === 1)
                refreshScreen();
            else if (inspectorTab === 2)
                refreshDiff(diffFile);
        }
        if (viewTab === 0)
            canvasWires.requestPaint();
        if (viewTab === 2)
            openFocusTimer.restart();
        if (viewTab === 3)
            refreshWorktrees();
    }

    Connections {
        target: Agents

        function onListChanged(): void {
            if (root.shown && root.viewTab === 0)
                canvasWires.requestPaint();
        }
    }

    Timer {
        id: openFocusTimer

        interval: 120
        onTriggered: {
            if (root.shown)
                dockInput.forceActiveFocus();
        }
    }

    Timer {
        id: directFocusTimer

        interval: 90
        onTriggered: {
            if (root.shown && root.viewTab === 1)
                directReplyInput.forceActiveFocus();
        }
    }

    Timer {
        id: toastTimer

        interval: 3200
        onTriggered: root.toastMsg = ""
    }

    Timer {
        interval: 2800
        repeat: true
        running: root.shown && root.viewTab === 1 && root.inspectorTab !== 1 && !!root.selectedAgent
        onTriggered: root.refreshDetail()
    }

    Timer {
        interval: 1800
        repeat: true
        running: root.shown && root.viewTab === 1 && root.inspectorTab === 1 && !!root.selectedAgent
        onTriggered: root.refreshScreen()
    }

    Process {
        id: projProc

        command: [root.agentsBin, "projects"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const arr = JSON.parse(text);
                    if (Array.isArray(arr)) {
                        root.projects = arr;
                        if (root.projectIdx >= arr.length)
                            root.projectIdx = 0;
                    }
                } catch (e) {}
            }
        }
    }

    Process {
        id: histProc

        command: [root.agentsBin, "history"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const arr = JSON.parse(text);
                    if (Array.isArray(arr) && arr.length > 0 && !root.aiThinking)
                        root.chatHistory = arr;
                } catch (e) {}
            }
        }
    }

    Process {
        id: dictProc

        command: [root.dictateBin, "--stdout-only"]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                let m;
                try {
                    m = JSON.parse(data);
                } catch (e) {
                    return;
                }
                if (m.stage === "text" && m.text) {
                    if (root.viewTab === 1)
                        directReplyInput.text = m.text;
                    else if (root.viewTab === 3)
                        swarmInput.text = m.text;
                    else
                        dockInput.text = m.text;
                } else if (m.stage === "state" && m.state === "erreur") {
                    root.dictating = false;
                    root.flashToast("✕ " + (m.detail || I18n.tr("Erreur micro")));
                } else if (m.stage === "done") {
                    root.dictating = false;
                    if (m.text) {
                        if (root.viewTab === 1) {
                            directReplyInput.text = m.text;
                            directReplyInput.forceActiveFocus();
                        } else if (root.viewTab === 3) {
                            swarmInput.text = m.text;
                            swarmInput.forceActiveFocus();
                        } else {
                            dockInput.text = m.text;
                            dockInput.forceActiveFocus();
                        }
                    }
                }
            }
        }
        onExited: root.dictating = false
    }

    Process {
        id: detailProc

        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const d = JSON.parse(text);
                    if (d && typeof d === "object")
                        root.detailData = d;
                } catch (e) {}
            }
        }
    }

    Process {
        id: screenProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.screenLoading = false;
                try {
                    const d = JSON.parse(text);
                    if (d && typeof d === "object")
                        root.screenData = d;
                } catch (e) {}
            }
        }
        onExited: root.screenLoading = false
    }

    Process {
        id: diffProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.diffLoading = false;
                try {
                    const d = JSON.parse(text);
                    if (d && typeof d === "object")
                        root.diffData = d;
                } catch (e) {}
            }
        }
        onExited: root.diffLoading = false
    }

    Process {
        id: modelsProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.modelCatalogLoading = false;
                try {
                    const d = JSON.parse(text);
                    if (d && typeof d === "object" && d.kind) {
                        root.modelCatalog = d;
                        const next = Object.assign({}, root.modelCatalogCache);
                        next[d.kind] = d;
                        root.modelCatalogCache = next;
                    }
                } catch (e) {}
            }
        }
        onExited: root.modelCatalogLoading = false
    }

    Process {
        id: setModelProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.applyingModel = false;
                try {
                    const r = JSON.parse(text);
                    root.flashToast((r.ok ? "✓ " : "✕ ") + (r.detail || (r.ok ? I18n.tr("Modèle appliqué") : I18n.tr("Échec changement modèle"))));
                    if (r.ok) {
                        root.modelPickerOpen = false;
                        if (root.viewTab === 1) {
                            root.refreshDetail();
                            if (root.inspectorTab === 1)
                                root.refreshScreen();
                        }
                    }
                } catch (e) {
                    root.flashToast(I18n.tr("Modèle mis à jour"));
                    root.modelPickerOpen = false;
                }
            }
        }
        onExited: root.applyingModel = false
    }

    Process {
        id: sendProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.sendingDirect = false;
                try {
                    const r = JSON.parse(text);
                    root.flashToast((r.ok ? "✓ " : "✕ ") + (r.detail || ""));
                } catch (e) {
                    root.flashToast(I18n.tr("Message envoyé"));
                }
                if (root.viewTab === 1)
                    root.refreshDetail();
            }
        }
        onExited: root.sendingDirect = false
    }

    Process {
        id: commanderProc

        stdout: SplitParser {
            onRead: line => {
                const raw = (line || "").trim();
                if (!raw)
                    return;
                let ev;
                try {
                    ev = JSON.parse(raw);
                } catch (e) {
                    return;
                }
                if (ev.event === "status") {
                    root.aiStreamStatus = ev.text || "";
                } else if (ev.event === "tool_start") {
                    root.aiStreamStatus = ev.label || ev.name || "";
                } else if (ev.event === "tool_done") {
                    const nextB = root.aiStreamBadges.slice();
                    nextB.push({
                        type: ev.type || "",
                        ok: !!ev.ok,
                        label: ev.label || "",
                        agent_id: ev.agent_id || "",
                        kind: ev.kind || "",
                        cwd: ev.cwd || ""
                    });
                    root.aiStreamBadges = nextB;
                } else if (ev.event === "done") {
                    root.aiDoneReceived = true;
                    root.aiThinking = false;
                    root.aiStreamStatus = "";
                    const next = root.chatHistory.slice(-18);
                    next.push({
                        role: "ai",
                        text: ev.reply || I18n.tr("Réponse reçue."),
                        executed: ev.executed ?? root.aiStreamBadges
                    });
                    root.chatHistory = next;
                    root.aiStreamBadges = [];
                }
            }
        }
        onExited: {
            if (root.aiThinking && !root.aiDoneReceived) {
                root.aiThinking = false;
                root.aiStreamStatus = "";
                const next = root.chatHistory.slice(-18);
                next.push({
                    role: "ai",
                    text: I18n.tr("Erreur de réponse du Commandant IA."),
                    executed: root.aiStreamBadges
                });
                root.chatHistory = next;
                root.aiStreamBadges = [];
            }
        }
    }

    Process {
        id: layoutLoadProc

        command: [root.agentsBin, "layout-get"]
        stdout: StdioCollector {
            onStreamFinished: {
                root.layoutLoaded = true;
                try {
                    const d = JSON.parse(text);
                    if (d && typeof d === "object") {
                        if (d.offsets && typeof d.offsets === "object")
                            root.cardOffsets = d.offsets;
                        if (typeof d.panX === "number")
                            root.canvasPanX = d.panX;
                        if (typeof d.panY === "number")
                            root.canvasPanY = d.panY;
                        if (typeof d.zoom === "number")
                            root.canvasZoom = Math.max(0.65, Math.min(1.35, d.zoom));
                        canvasWires.requestPaint();
                    }
                } catch (e) {}
            }
        }
    }

    Process {
        id: swarmProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.swarmDeploying = false;
                try {
                    const r = JSON.parse(text);
                    if (r.ok) {
                        const isoTxt = (r.isolated ?? 0) > 0
                            ? I18n.tr(" (%1 worktree(s) isolé(s))").arg(r.isolated)
                            : "";
                        root.flashToast(I18n.tr("Escouade de %1 agent(s) déployée%2").arg(r.count ?? 0).arg(isoTxt));
                        root.viewTab = 0;
                    } else {
                        root.flashToast("✕ " + (r.detail || I18n.tr("Échec déploiement escouade")));
                    }
                } catch (e) {
                    root.flashToast(I18n.tr("Escouade déployée"));
                    root.viewTab = 0;
                }
            }
        }
        onExited: root.swarmDeploying = false
    }

    Timer {
        id: layoutSaveTimer

        interval: 600
        onTriggered: root.saveLayoutNow()
    }

    Timer {
        id: projectPickerFocusTimer

        interval: 40
        onTriggered: {
            if (root.projectPickerOpen)
                projectSearchInput.forceActiveFocus();
        }
    }

    // Légère pulsation des fils Bézier actifs (coupée en mode éco/batterie pour préserver l'iGPU)
    Timer {
        interval: 120
        repeat: true
        running: root.shown && root.viewTab === 0 && Agents.working > 0 && !Glass.ecoOnBattery
        onTriggered: {
            root.wirePulse = (root.wirePulse + 2) % 24;
            canvasWires.requestPaint();
        }
    }

    Process {
        id: wtListProc

        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const arr = JSON.parse(text);
                    if (Array.isArray(arr))
                        root.worktrees = arr;
                } catch (e) {
                    root.worktrees = [];
                }
            }
        }
    }

    Process {
        id: wtRemoveProc

        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const r = JSON.parse(text);
                    root.flashToast((r.ok ? "✓ " : "✕ ") + (r.detail || ""));
                } catch (e) {}
                root.refreshWorktrees();
            }
        }
    }

    Process {
        id: broadcastProc

        stdout: StdioCollector {
            onStreamFinished: {
                root.broadcasting = false;
                try {
                    const r = JSON.parse(text);
                    root.flashToast((r.ok ? "✓ " : "✕ ") + (r.detail || ""));
                } catch (e) {
                    root.flashToast(I18n.tr("Ordre diffusé"));
                }
            }
        }
        onExited: root.broadcasting = false
    }

    Process {
        id: stopAllProc

        command: [root.agentsBin, "stop-all"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const r = JSON.parse(text);
                    root.flashToast((r.ok ? "✓ " : "✕ ") + (r.detail || I18n.tr("Agents interrompus")));
                } catch (e) {}
            }
        }
    }

    // ── Raccourcis clavier globaux du Studio (actifs uniquement quand le Studio est ouvert) ──
    Shortcut { enabled: root.shown; sequence: "F1"; onActivated: root.helpOpen = !root.helpOpen }
    Shortcut { enabled: root.shown; sequence: "Ctrl+/"; onActivated: root.helpOpen = !root.helpOpen }
    Shortcut { enabled: root.shown; sequence: "Alt+Up"; onActivated: root.stepFleet(-1) }
    Shortcut { enabled: root.shown; sequence: "Alt+Down"; onActivated: root.stepFleet(1) }
    Shortcut { enabled: root.shown; sequence: "Ctrl+1"; onActivated: root.viewTab = 0 }
    Shortcut { enabled: root.shown; sequence: "Ctrl+2"; onActivated: root.viewTab = 1 }
    Shortcut { enabled: root.shown; sequence: "Ctrl+3"; onActivated: root.viewTab = 2 }
    Shortcut { enabled: root.shown; sequence: "Ctrl+4"; onActivated: root.viewTab = 3 }
    Shortcut { enabled: root.shown; sequence: "Ctrl+P"; onActivated: root.projectPickerOpen ? root.closeProjectPicker() : root.openProjectPicker() }
    Shortcut { enabled: root.shown; sequence: "Ctrl+Space"; onActivated: root.toggleDictation() }
    Shortcut { enabled: root.shown; sequence: "Alt+1"; onActivated: { root.dockTarget = "ai"; dockInput.forceActiveFocus(); } }
    Shortcut { enabled: root.shown; sequence: "Alt+2"; onActivated: { root.dockTarget = Agents.launchKinds[0]; dockInput.forceActiveFocus(); } }
    Shortcut { enabled: root.shown; sequence: "Alt+3"; onActivated: { root.dockTarget = Agents.launchKinds[1]; dockInput.forceActiveFocus(); } }
    Shortcut { enabled: root.shown; sequence: "Alt+4"; onActivated: { root.dockTarget = Agents.launchKinds[2]; dockInput.forceActiveFocus(); } }
    Shortcut { enabled: root.shown; sequence: "Alt+5"; onActivated: { root.dockTarget = Agents.launchKinds[3]; dockInput.forceActiveFocus(); } }
    Shortcut { enabled: root.shown; sequence: "Alt+6"; onActivated: { root.dockTarget = Agents.launchKinds[4]; dockInput.forceActiveFocus(); } }
    Shortcut { enabled: root.shown; sequence: "Alt+7"; onActivated: { root.dockTarget = Agents.launchKinds[5]; dockInput.forceActiveFocus(); } }
    Shortcut {
        enabled: root.shown && !!root.activePerm
        sequence: "Alt+A"
        onActivated: {
            if (root.activePerm)
                Agents.answer(root.activePerm.id, "allow");
        }
    }
    Shortcut {
        enabled: root.shown && !!root.activePerm
        sequence: "Alt+D"
        onActivated: {
            if (root.activePerm)
                Agents.answer(root.activePerm.id, "deny");
        }
    }

    // ════════════════════ Contenu principal ════════════════════
    Item {
        id: mainBody

        anchors.fill: parent
        opacity: root.reveal
        scale: 0.96 + 0.04 * root.reveal

        Keys.onEscapePressed: root.closeTopOverlayOrStudio()

        // Aura supérieure colorée par l'agent leader
        Rectangle {
            x: 24
            y: 10
            width: Math.round(parent.width * 0.45)
            height: 64
            radius: 32
            opacity: Colours.light ? 0.28 : 0.48
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.35; color: Qt.alpha(root.leadTint, 0.16) }
                GradientStop { position: 0.78; color: Qt.alpha(root.leadTint, 0.04) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        // Reflet spéculaire supérieur sur le bord du verre
        Rectangle {
            anchors.top: parent.top
            anchors.topMargin: 1.5
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 80
            height: 1
            opacity: Colours.light ? 0.5 : 0.24
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.25; color: "#ffffff" }
                GradientStop { position: 0.75; color: "#ffffff" }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        // ── 1. BARRE SUPÉRIEURE : Command Header ──
        Item {
            id: topBar

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 22
            anchors.rightMargin: 22
            anchors.topMargin: 14
            height: 44

            // Gauche : Identité AGENT OS + KPI temps réel
            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 34
                    height: 34
                    radius: 12
                    border.width: 0.75
                    border.color: Qt.alpha(root.leadTint, 0.46)
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.alpha(root.leadTint, 0.26) }
                        GradientStop { position: 1.0; color: Qt.alpha(root.fg, 0.05) }
                    }

                    MaterialIcon {
                        anchors.centerIn: parent
                        text: "hub"
                        color: root.leadTint
                        fontStyle: Tokens.font.icon.size(18).build()
                        fill: 1
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0

                    Row {
                        spacing: 6

                        StyledText {
                            text: I18n.tr("AGENT OS")
                            color: root.fg
                            font.pointSize: 10.5
                            font.weight: Font.Black
                            font.letterSpacing: 1.0
                        }
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: katBadge.implicitWidth + 10
                            height: 15
                            radius: 7.5
                            color: Qt.alpha(root.aiTint, 0.18)
                            border.width: 0.5
                            border.color: Qt.alpha(root.aiTint, 0.42)

                            StyledText {
                                id: katBadge

                                anchors.centerIn: parent
                                text: "KATANA AI"
                                color: root.aiTint
                                font.pointSize: 6.1
                                font.weight: Font.Black
                                font.letterSpacing: 0.7
                            }
                        }
                    }

                    StyledText {
                        text: {
                            const parts = [];
                            if (Agents.working > 0)
                                parts.push(I18n.tr("%1 actif(s)").arg(Agents.working));
                            if (Agents.waiting > 0)
                                parts.push(I18n.tr("%1 en attente").arg(Agents.waiting));
                            if (Agents.totalSubagents > 0)
                                parts.push(I18n.tr("+%1 sub").arg(Agents.totalSubagents));
                            if (parts.length === 0)
                                parts.push(Agents.shown.length > 0 ? I18n.tr("%1 session(s) prêtes").arg(Agents.shown.length) : I18n.tr("Orchestrateur prêt"));
                            if (Agents.totalTokens > 0)
                                parts.push(`${Agents.fmtTokens(Agents.totalTokens)} tok`);
                            return parts.join(" · ");
                        }
                        color: Agents.waiting > 0 ? root.orange : root.fgDim
                        font.pointSize: 7.6
                        font.weight: Font.Medium
                        font.features: { "tnum": 1 }
                    }
                }
            }

            // Centre : Switch 4 vues (Canvas · Cockpit · Commandant · Escouade)
            Rectangle {
                anchors.centerIn: parent
                width: tabRow.implicitWidth + 8
                height: 34
                radius: 17
                color: Qt.alpha(root.fg, 0.07)
                border.width: 0.5
                border.color: Qt.alpha(root.fg, 0.14)

                Row {
                    id: tabRow

                    anchors.centerIn: parent
                    spacing: 3

                    Repeater {
                        model: [
                            { idx: 0, icon: "hub", label: I18n.tr("Canvas") },
                            { idx: 1, icon: "terminal", label: I18n.tr("Cockpit") },
                            { idx: 2, icon: "auto_awesome", label: I18n.tr("Commandant") },
                            { idx: 3, icon: "groups", label: I18n.tr("Escouade") }
                        ]

                        Rectangle {
                            id: vTab

                            required property var modelData
                            readonly property bool active: root.viewTab === modelData.idx
                            readonly property color tCol: modelData.idx === 2 ? root.aiTint : root.leadTint

                            width: vTabRow.implicitWidth + 18
                            height: 26
                            radius: 13
                            color: active ? Qt.alpha(tCol, 0.24) : (vTabArea.containsMouse ? Qt.alpha(root.fg, 0.08) : "transparent")
                            border.width: active ? 0.5 : 0
                            border.color: Qt.alpha(tCol, 0.54)

                            Behavior on color { ColorAnimation { duration: 140 } }

                            Row {
                                id: vTabRow

                                anchors.centerIn: parent
                                spacing: 5

                                MaterialIcon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: vTab.modelData.icon
                                    color: vTab.active ? vTab.tCol : root.fgDim
                                    fontStyle: Tokens.font.icon.size(14).build()
                                    fill: vTab.active ? 1 : 0
                                }
                                StyledText {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: vTab.modelData.label
                                    color: vTab.active ? root.fg : root.fgDim
                                    font.pointSize: 8.1
                                    font.weight: vTab.active ? Font.Bold : Font.Medium
                                }
                            }

                            MouseArea {
                                id: vTabArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.viewTab = vTab.modelData.idx
                            }
                        }
                    }
                }
            }

            // Droite : Stop tout (urgence), Nettoyer, Aide raccourcis, Dictée vocale, Fermer
            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7

                Rectangle {
                    visible: Agents.working >= 2
                    anchors.verticalCenter: parent.verticalCenter
                    width: stopAllRow.implicitWidth + 14
                    height: 28
                    radius: 14
                    color: Qt.alpha(root.red, stopAllArea.containsMouse ? 0.28 : 0.16)
                    border.width: 0.6
                    border.color: Qt.alpha(root.red, 0.56)

                    Row {
                        id: stopAllRow

                        anchors.centerIn: parent
                        spacing: 4

                        MaterialIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "stop_circle"
                            color: root.red
                            fontStyle: Tokens.font.icon.size(13).build()
                            fill: 1
                        }
                        StyledText {
                            anchors.verticalCenter: parent.verticalCenter
                            text: I18n.tr("Stop tout")
                            color: root.red
                            font.pointSize: 7.5
                            font.weight: Font.Black
                        }
                    }

                    MouseArea {
                        id: stopAllArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.stopAllWorking()
                    }
                }

                Rectangle {
                    visible: Agents.doneShown > 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: hdrCleanRow.implicitWidth + 16
                    height: 28
                    radius: 14
                    color: Qt.alpha(root.fg, hdrCleanArea.containsMouse ? 0.14 : 0.07)
                    border.width: 0.5
                    border.color: Qt.alpha(root.fg, 0.16)

                    Row {
                        id: hdrCleanRow

                        anchors.centerIn: parent
                        spacing: 4

                        MaterialIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "cleaning_services"
                            color: root.fgDim
                            fontStyle: Tokens.font.icon.size(13).build()
                        }
                        StyledText {
                            anchors.verticalCenter: parent.verticalCenter
                            text: I18n.tr("Nettoyer")
                            color: root.fg
                            font.pointSize: 7.8
                            font.weight: Font.DemiBold
                        }
                    }

                    MouseArea {
                        id: hdrCleanArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: Agents.clean()
                    }
                }

                // Aide raccourcis clavier (F1 / Ctrl+/)
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30
                    height: 30
                    radius: 15
                    color: root.helpOpen ? Qt.alpha(root.leadTint, 0.28) : Qt.alpha(root.fg, helpArea.containsMouse ? 0.16 : 0.07)
                    border.width: 0.5
                    border.color: root.helpOpen ? Qt.alpha(root.leadTint, 0.62) : Qt.alpha(root.fg, 0.16)

                    MaterialIcon {
                        anchors.centerIn: parent
                        text: "keyboard"
                        color: root.helpOpen ? root.leadTint : root.fgDim
                        fontStyle: Tokens.font.icon.size(14).build()
                    }

                    MouseArea {
                        id: helpArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.helpOpen = !root.helpOpen
                    }
                }

                // Bouton Dictée vocale intégrée dans Agent OS (Voice-First façon Katana)
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30
                    height: 30
                    radius: 15
                    color: root.dictating ? Qt.alpha(root.red, 0.34) : Qt.alpha(root.aiTint, voiceArea.containsMouse ? 0.26 : 0.14)
                    border.width: root.dictating ? 1 : 0.5
                    border.color: root.dictating ? Qt.alpha(root.red, 0.8) : Qt.alpha(root.aiTint, 0.44)

                    MaterialIcon {
                        anchors.centerIn: parent
                        text: root.dictating ? "stop" : "mic"
                        color: root.dictating ? root.red : root.aiTint
                        fontStyle: Tokens.font.icon.size(15).build()
                        fill: 1
                    }

                    MouseArea {
                        id: voiceArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.toggleDictation()
                    }
                }

                // Bouton Fermer
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30
                    height: 30
                    radius: 15
                    color: Qt.alpha(root.fg, closeArea.containsMouse ? 0.18 : 0.08)
                    border.width: 0.5
                    border.color: Qt.alpha(root.fg, 0.18)

                    MaterialIcon {
                        anchors.centerIn: parent
                        text: "close"
                        color: root.fg
                        fontStyle: Tokens.font.icon.size(15).build()
                    }

                    MouseArea {
                        id: closeArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }
        }

        // Séparateur optique
        Rectangle {
            id: topSep

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: topBar.bottom
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.topMargin: 8
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.15; color: Qt.alpha(root.fg, 0.14) }
                GradientStop { position: 0.85; color: Qt.alpha(root.fg, 0.14) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        // ── 2. BANDEAU PERMISSION PRIORITAIRE (file complète multi-permissions) ──
        Rectangle {
            id: permBanner

            readonly property var perm: root.activePerm
            readonly property int totalPerms: Agents.perms.length
            readonly property int safeIdx: totalPerms > 0 ? Math.max(0, Math.min(root.permIdx, totalPerms - 1)) : 0
            visible: !!perm
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: topSep.bottom
            anchors.leftMargin: 22
            anchors.rightMargin: 22
            anchors.topMargin: visible ? 10 : 0
            height: visible ? 54 : 0
            radius: 16
            color: Qt.alpha(root.orange, 0.14)
            border.width: 0.75
            border.color: Qt.alpha(root.orange, 0.45)

            Row {
                anchors.left: parent.left
                anchors.right: permBtns.left
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10

                MaterialIcon {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "gpp_maybe"
                    color: root.orange
                    fontStyle: Tokens.font.icon.size(20).build()
                    fill: 1
                }

                // Navigation file multi-permissions (1/N)
                Rectangle {
                    visible: permBanner.totalPerms > 1
                    anchors.verticalCenter: parent.verticalCenter
                    width: pNavRow.implicitWidth + 10
                    height: 24
                    radius: 12
                    color: Qt.alpha(root.orange, 0.22)
                    border.width: 0.5
                    border.color: Qt.alpha(root.orange, 0.52)

                    Row {
                        id: pNavRow

                        anchors.centerIn: parent
                        spacing: 3

                        StyledText {
                            text: "‹"
                            color: root.fg
                            font.pointSize: 9
                            font.weight: Font.Black

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.permIdx = (permBanner.safeIdx - 1 + permBanner.totalPerms) % permBanner.totalPerms
                            }
                        }
                        StyledText {
                            text: `${permBanner.safeIdx + 1}/${permBanner.totalPerms}`
                            color: root.orange
                            font.pointSize: 7.4
                            font.weight: Font.Black
                            font.features: { "tnum": 1 }
                        }
                        StyledText {
                            text: "›"
                            color: root.fg
                            font.pointSize: 9
                            font.weight: Font.Black

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.permIdx = (permBanner.safeIdx + 1) % permBanner.totalPerms
                            }
                        }
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - (permBanner.totalPerms > 1 ? 96 : 34)
                    spacing: 1

                    StyledText {
                        width: parent.width
                        elide: Text.ElideRight
                        text: `${permBanner.perm?.label ?? ""} · ${permBanner.perm?.project ?? ""}`
                        color: root.fg
                        font.pointSize: 8.8
                        font.weight: Font.Bold
                    }
                    StyledText {
                        width: parent.width
                        elide: Text.ElideRight
                        text: permBanner.perm?.detail ?? ""
                        color: root.fgDim
                        font.family: "monospace"
                        font.pointSize: 7.6
                    }
                }
            }

            Row {
                id: permBtns

                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                ActionChip {
                    label: I18n.tr("Terminal")
                    tint: root.fg
                    onClicked: {
                        const p = permBanner.perm;
                        Agents.answer(p.id, "terminal");
                        Agents.focusPid(p.agentPid);
                    }
                }
                ActionChip {
                    label: I18n.tr("Refuser")
                    tint: root.red
                    onClicked: Agents.answer(permBanner.perm.id, "deny")
                }
                ActionChip {
                    label: I18n.tr("Autoriser")
                    tint: root.green
                    filled: true
                    onClicked: Agents.answer(permBanner.perm.id, "allow")
                }
            }
        }

        // ── 3. ZONE CENTRALE (Canvas / Cockpit / Commandant / Escouade) ──
        Item {
            id: workArea

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: permBanner.bottom
            anchors.bottom: commandDock.top
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            anchors.topMargin: 10
            anchors.bottomMargin: 10

            // ════════════════ VUE 0 : CANVAS SPATIAL KATANA ════════════════
            Item {
                id: canvasView

                anchors.fill: parent
                visible: root.viewTab === 0

                Rectangle {
                    anchors.fill: parent
                    radius: 20
                    color: Qt.alpha(root.fg, Colours.light ? 0.03 : 0.04)
                    border.width: 0.5
                    border.color: Qt.alpha(root.fg, 0.12)
                    clip: true

                    // Grille de points statique séparée (évite de repeindre des centaines de points pendant le drag)
                    Canvas {
                        id: canvasGrid

                        anchors.fill: parent
                        property bool isLight: Colours.light
                        onIsLightChanged: requestPaint()
                        onPaint: {
                            const ctx = getContext("2d");
                            ctx.clearRect(0, 0, width, height);
                            ctx.fillStyle = isLight ? "rgba(0,0,0,0.08)" : "rgba(255,255,255,0.08)";
                            const step = 28;
                            for (let gx = 18; gx < width; gx += step) {
                                for (let gy = 18; gy < height; gy += step) {
                                    ctx.fillRect(gx, gy, 1.5, 1.5);
                                }
                            }
                        }
                    }

                    // Pan (glisser le fond) & Zoom (molette) du Canvas Spatial
                    MouseArea {
                        id: canvasPanArea

                        property real startX
                        property real startY
                        property real initPanX
                        property real initPanY

                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.ArrowCursor
                        onPressed: mouse => {
                            startX = mouse.x;
                            startY = mouse.y;
                            initPanX = root.canvasPanX;
                            initPanY = root.canvasPanY;
                        }
                        onPositionChanged: mouse => {
                            if (!pressed)
                                return;
                            root.canvasPanX = Math.max(-600, Math.min(600, initPanX + (mouse.x - startX)));
                            root.canvasPanY = Math.max(-500, Math.min(500, initPanY + (mouse.y - startY)));
                            canvasWires.requestPaint();
                            root.scheduleLayoutSave();
                        }
                        onDoubleClicked: root.resetCanvasLayout()
                        onWheel: wheel => {
                            const delta = wheel.angleDelta.y > 0 ? 0.08 : -0.08;
                            root.setCanvasZoom(root.canvasZoom + delta);
                        }
                    }

                    Canvas {
                        id: canvasWires

                        anchors.fill: parent
                        onPaint: {
                            const ctx = getContext("2d");
                            ctx.clearRect(0, 0, width, height);

                            const list = root.visibleAgents;
                            if (list.length === 0)
                                return;

                            const z = root.canvasZoom;
                            const px = root.canvasPanX;
                            const py = root.canvasPanY;
                            const hubX = width / 2;
                            const hubY = 44;
                            const centers = [];

                            for (let i = 0; i < list.length; i++) {
                                const a = list[i];
                                const col = i % 3;
                                const row = Math.floor(i / 3);
                                const colsInRow = Math.min(3, list.length - row * 3);
                                const cardW = 328;
                                const cardH = 194;
                                const gapX = 18;
                                const totalW = colsInRow * cardW + (colsInRow - 1) * gapX;
                                const baseX = Math.round((width - totalW) / 2) + col * (cardW + gapX);
                                const baseY = 92 + row * (cardH + 18);
                                const off = root.cardOffsets[a.id] ?? { dx: 0, dy: 0 };
                                const wx = baseX + off.dx;
                                const wy = baseY + off.dy;
                                const cx = width / 2 + (wx + cardW / 2 - width / 2) * z + px;
                                const cy = 66 + (wy - 66) * z + py;
                                centers.push({ x: cx, y: cy + (cardH * z) / 2, topY: cy, cwd: String(a.cwd || "").replace(/\/+$/, "") });

                                const isWait = a.status === "waiting";
                                const isWork = a.status === "working";
                                const cHex = isWait ? "#ff9f0a" : (isWork ? String(Agents.kindColour(a.kind)) : "#32d74b");

                                ctx.save();
                                ctx.beginPath();
                                ctx.moveTo(hubX, hubY + 18);
                                const midY = (hubY + 18 + cy) / 2;
                                ctx.bezierCurveTo(hubX, midY, cx, midY, cx, cy + 4);
                                ctx.strokeStyle = cHex;
                                ctx.globalAlpha = isWork || isWait ? 0.56 : 0.24;
                                ctx.lineWidth = isWork || isWait ? 2.1 : 1.25;
                                if (isWork) {
                                    ctx.setLineDash([8, 6]);
                                    ctx.lineDashOffset = -root.wirePulse;
                                }
                                ctx.stroke();

                                ctx.setLineDash([]);
                                ctx.beginPath();
                                ctx.arc(cx, cy + 4, 3.5, 0, Math.PI * 2);
                                ctx.fillStyle = cHex;
                                ctx.globalAlpha = 0.88;
                                ctx.fill();
                                ctx.restore();
                            }

                            // Liaisons pointillées ambre entre agents partageant le même dossier (alerte conflit multi-agents)
                            for (let i = 0; i < centers.length; i++) {
                                if (!centers[i].cwd)
                                    continue;
                                for (let j = i + 1; j < centers.length; j++) {
                                    if (centers[i].cwd !== centers[j].cwd)
                                        continue;
                                    ctx.save();
                                    ctx.beginPath();
                                    ctx.moveTo(centers[i].x, centers[i].y);
                                    const mx = (centers[i].x + centers[j].x) / 2;
                                    const my = Math.min(centers[i].y, centers[j].y) - 28;
                                    ctx.quadraticCurveTo(mx, my, centers[j].x, centers[j].y);
                                    ctx.strokeStyle = "#ff9f0a";
                                    ctx.globalAlpha = 0.62;
                                    ctx.lineWidth = 1.6;
                                    ctx.setLineDash([5, 5]);
                                    ctx.stroke();
                                    ctx.restore();
                                }
                            }
                        }
                    }

                    // Nœud central Orchestrateur (clic = ouvre Commandant IA)
                    Rectangle {
                        id: hubNode

                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 20
                        width: hubRow.implicitWidth + 26
                        height: 36
                        radius: 18
                        border.width: 0.75
                        border.color: Qt.alpha(root.aiTint, hubArea.containsMouse ? 0.72 : 0.48)
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Qt.alpha(root.aiTint, 0.24) }
                            GradientStop { position: 1.0; color: Qt.alpha(root.fg, 0.05) }
                        }

                        Row {
                            id: hubRow

                            anchors.centerIn: parent
                            spacing: 8

                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 7
                                height: 7
                                radius: 3.5
                                color: Agents.activeCount > 0 ? root.leadTint : root.green
                            }

                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: I18n.tr("KATANA AI · ORCHESTRATEUR")
                                color: root.fg
                                font.pointSize: 7.5
                                font.weight: Font.Black
                                font.letterSpacing: 0.75
                            }

                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: `${Agents.shown.length} ${Agents.shown.length > 1 ? I18n.tr("agents") : I18n.tr("agent")}`
                                color: root.fgDim
                                font.pointSize: 7.4
                                font.weight: Font.DemiBold
                                font.features: { "tnum": 1 }
                            }
                        }

                        MouseArea {
                            id: hubArea

                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.viewTab = 2
                        }
                    }

                    // Filtres moteurs
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 14
                        y: 24
                        spacing: 5

                        FilterChip {
                            label: I18n.tr("Tous")
                            count: Agents.shown.length
                            selected: root.kindFilter === "all"
                            tint: root.fg
                            onClicked: {
                                root.kindFilter = "all";
                                canvasWires.requestPaint();
                            }
                        }

                        Repeater {
                            model: Agents.presentKinds

                            FilterChip {
                                required property var modelData
                                label: Agents.kindName(modelData.kind)
                                count: modelData.total
                                selected: root.kindFilter === modelData.kind
                                tint: Agents.kindColour(modelData.kind)
                                onClicked: {
                                    root.kindFilter = root.kindFilter === modelData.kind ? "all" : modelData.kind;
                                    canvasWires.requestPaint();
                                }
                            }
                        }
                    }

                    // Contrôles Canvas : Zoom (- / 100% / +) + Réaligner
                    Row {
                        anchors.right: parent.right
                        anchors.rightMargin: 14
                        y: 24
                        z: 25
                        spacing: 5

                        Rectangle {
                            height: 26
                            width: zoomRow.implicitWidth + 14
                            radius: 13
                            color: Qt.alpha(root.fg, 0.08)
                            border.width: 0.5
                            border.color: Qt.alpha(root.fg, 0.18)

                            Row {
                                id: zoomRow

                                anchors.centerIn: parent
                                spacing: 7

                                StyledText {
                                    text: "−"
                                    color: root.fg
                                    font.pointSize: 8.6
                                    font.weight: Font.Black

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.setCanvasZoom(root.canvasZoom - 0.1)
                                    }
                                }
                                StyledText {
                                    text: `${Math.round(root.canvasZoom * 100)}%`
                                    color: root.fgDim
                                    font.pointSize: 7.2
                                    font.weight: Font.Bold
                                    font.features: { "tnum": 1 }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.setCanvasZoom(1.0)
                                    }
                                }
                                StyledText {
                                    text: "+"
                                    color: root.fg
                                    font.pointSize: 8.6
                                    font.weight: Font.Black

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.setCanvasZoom(root.canvasZoom + 0.1)
                                    }
                                }
                            }
                        }

                        Rectangle {
                            visible: Object.keys(root.cardOffsets).length > 0 || root.canvasPanX !== 0 || root.canvasPanY !== 0 || Math.abs(root.canvasZoom - 1.0) > 0.01
                            width: alignRow.implicitWidth + 14
                            height: 26
                            radius: 13
                            color: Qt.alpha(root.fg, alignArea.containsMouse ? 0.15 : 0.08)
                            border.width: 0.5
                            border.color: Qt.alpha(root.fg, 0.2)

                            Row {
                                id: alignRow

                                anchors.centerIn: parent
                                spacing: 4

                                MaterialIcon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "grid_view"
                                    color: root.fgDim
                                    fontStyle: Tokens.font.icon.size(12).build()
                                }
                                StyledText {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: I18n.tr("Réaligner")
                                    color: root.fg
                                    font.pointSize: 7.4
                                    font.weight: Font.DemiBold
                                }
                            }

                            MouseArea {
                                id: alignArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.resetCanvasLayout()
                            }
                        }
                    }

                    // Cartes agents draggables illimitées sur le Canvas (pan + zoom)
                    Item {
                        id: canvasWorld

                        width: parent.width
                        height: parent.height
                        x: root.canvasPanX
                        y: root.canvasPanY
                        transform: Scale {
                            origin.x: canvasView.width / 2
                            origin.y: 66
                            xScale: root.canvasZoom
                            yScale: root.canvasZoom
                        }

                        Repeater {
                            model: root.visibleAgents

                            Item {
                                id: kCard

                                required property var modelData
                                required property int index

                                readonly property bool working: modelData.status === "working"
                                readonly property bool waiting: modelData.status === "waiting"
                                readonly property bool done: !working && !waiting
                                readonly property color tint: Agents.kindColour(modelData.kind)
                                readonly property color stateCol: waiting ? root.orange : working ? tint : root.green
                                readonly property var cardPerm: root.cardPermFor(modelData)
                                readonly property bool repoConflict: root.repoConflictCount(modelData) > 1
                                readonly property int col: index % 3
                                readonly property int row: Math.floor(index / 3)
                                readonly property int colsInRow: Math.min(3, root.visibleAgents.length - row * 3)
                                readonly property real baseX: Math.round((canvasView.width - (colsInRow * width + (colsInRow - 1) * 18)) / 2) + col * (width + 18)
                                readonly property real baseY: 92 + row * (height + 18)
                                readonly property var off: root.cardOffsets[modelData.id] ?? ({ dx: 0, dy: 0 })

                                width: 328
                                height: 194
                                x: baseX + off.dx
                                y: baseY + off.dy
                                z: dragArea.pressed ? 20 : (cardHover.hovered ? 10 : 1)

                            Rectangle {
                                anchors.fill: parent
                                radius: 18
                                border.width: dragArea.pressed || cardHover.hovered ? 1 : 0.6
                                border.color: Qt.alpha(kCard.stateCol, dragArea.pressed ? 0.72 : cardHover.hovered ? 0.52 : 0.28)
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Qt.alpha(kCard.stateCol, Colours.light ? 0.14 : 0.18) }
                                    GradientStop { position: 0.45; color: Qt.alpha(Colours.palette.m3surface, Colours.light ? 0.68 : 0.44) }
                                    GradientStop { position: 1.0; color: Qt.alpha(Colours.palette.m3surface, Colours.light ? 0.78 : 0.58) }
                                }

                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.topMargin: 1
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.leftMargin: 18
                                    anchors.rightMargin: 18
                                    height: 1
                                    color: "#ffffff"
                                    opacity: Colours.light ? 0.45 : 0.22
                                }

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 7
                                    y: 18
                                    width: 3
                                    height: 44
                                    radius: 1.5
                                    color: kCard.stateCol
                                }
                            }

                            MouseArea {
                                id: dragArea

                                property real startMouseX
                                property real startMouseY
                                property real startDx
                                property real startDy

                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                height: 146
                                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                onPressed: mouse => {
                                    const pt = mapToItem(canvasView, mouse.x, mouse.y);
                                    startMouseX = pt.x;
                                    startMouseY = pt.y;
                                    startDx = kCard.off.dx;
                                    startDy = kCard.off.dy;
                                }
                                onPositionChanged: mouse => {
                                    if (!pressed)
                                        return;
                                    const pt = mapToItem(canvasView, mouse.x, mouse.y);
                                    const z = Math.max(0.5, root.canvasZoom);
                                    root.setCardOffset(kCard.modelData.id, startDx + (pt.x - startMouseX) / z, startDy + (pt.y - startMouseY) / z);
                                }
                                onDoubleClicked: root.inspectAgent(kCard.modelData, true)
                            }

                            Column {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 14
                                anchors.topMargin: 12
                                anchors.bottomMargin: 10
                                spacing: 7

                                Item {
                                    width: parent.width
                                    height: 32

                                    Row {
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 8

                                        MiniSpinner {
                                            size: 30
                                            tint: kCard.stateCol
                                            spinning: kCard.working && root.shown && root.viewTab === 0
                                            done: kCard.done
                                            letter: Agents.kindLetter(kCard.modelData.kind)
                                        }

                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 1

                                            Row {
                                                spacing: 5

                                                Rectangle {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    width: kcKindTxt.implicitWidth + 10
                                                    height: 16
                                                    radius: 8
                                                    color: Qt.alpha(kCard.tint, 0.2)
                                                    border.width: 0.5
                                                    border.color: Qt.alpha(kCard.tint, 0.45)

                                                    StyledText {
                                                        id: kcKindTxt

                                                        anchors.centerIn: parent
                                                        text: Agents.kindShort(kCard.modelData.kind)
                                                        color: kCard.tint
                                                        font.pointSize: 6.2
                                                        font.weight: Font.Black
                                                        font.letterSpacing: 0.45
                                                    }
                                                }

                                                StyledText {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    width: 140
                                                    elide: Text.ElideRight
                                                    text: kCard.modelData.project
                                                    color: root.fg
                                                    font.pointSize: 9.4
                                                    font.weight: Font.Bold
                                                }
                                            }

                                            Row {
                                                spacing: 6

                                                StyledText {
                                                    visible: Boolean(kCard.modelData.model)
                                                    text: kCard.modelData.model
                                                    color: Qt.alpha(kCard.tint, 0.92)
                                                    font.pointSize: 6.9
                                                    font.weight: Font.DemiBold
                                                }
                                                StyledText {
                                                    visible: Boolean(kCard.modelData.branch)
                                                    text: `⎇ ${kCard.modelData.branch}`
                                                    color: root.fgDim
                                                    font.pointSize: 6.9
                                                }
                                            }
                                        }
                                    }

                                    Rectangle {
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: kcTimeTxt.implicitWidth + 12
                                        height: 20
                                        radius: 10
                                        color: Qt.alpha(kCard.stateCol, 0.16)
                                        border.width: 0.5
                                        border.color: Qt.alpha(kCard.stateCol, 0.38)

                                        StyledText {
                                            id: kcTimeTxt

                                            anchors.centerIn: parent
                                            text: Agents.elapsed(kCard.modelData.since)
                                            color: kCard.stateCol
                                            font.pointSize: 7.4
                                            font.weight: Font.Bold
                                            font.features: { "tnum": 1 }
                                        }
                                    }
                                }

                                StyledText {
                                    width: parent.width
                                    elide: Text.ElideRight
                                    text: kCard.modelData.title || I18n.tr("Session active")
                                    color: root.fg
                                    font.pointSize: 8.2
                                    font.weight: Font.Medium
                                }

                                Rectangle {
                                    width: parent.width
                                    height: 44
                                    radius: 10
                                    color: Qt.alpha(root.fg, Colours.light ? 0.055 : 0.075)
                                    border.width: 0.5
                                    border.color: Qt.alpha(kCard.stateCol, 0.2)

                                    StyledText {
                                        anchors.fill: parent
                                        anchors.margins: 7
                                        verticalAlignment: Text.AlignVCenter
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                        text: kCard.waiting
                                            ? `▲ ${kCard.modelData.tool || I18n.tr("Attend ta validation")}`
                                            : kCard.working
                                                ? `❯ ${kCard.modelData.focus || kCard.modelData.tool || I18n.tr("Réfléchit…")}`
                                                : `✓ ${kCard.modelData.reply || I18n.tr("Prêt à recevoir un ordre")}`
                                        color: kCard.waiting ? root.orange : root.fg
                                        font.family: "monospace"
                                        font.pointSize: 7.3
                                    }
                                }

                                Row {
                                    width: parent.width
                                    spacing: 8

                                    Row {
                                        visible: (kCard.modelData.stepTotal ?? 0) > 0
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 5

                                        Rectangle {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 48
                                            height: 4
                                            radius: 2
                                            color: Qt.alpha(root.fg, 0.14)

                                            Rectangle {
                                                width: Math.max(4, parent.width * Math.min(1, (kCard.modelData.stepDone ?? 0) / Math.max(1, kCard.modelData.stepTotal ?? 1)))
                                                height: parent.height
                                                radius: 2
                                                color: kCard.stateCol
                                            }
                                        }
                                        StyledText {
                                            text: `${kCard.modelData.stepDone}/${kCard.modelData.stepTotal}`
                                            color: kCard.stateCol
                                            font.pointSize: 7
                                            font.weight: Font.Bold
                                            font.features: { "tnum": 1 }
                                        }
                                    }

                                    StyledText {
                                        visible: (kCard.modelData.files ?? 0) > 0
                                        text: I18n.tr("%1 fich.").arg(kCard.modelData.files)
                                        color: root.fgDim
                                        font.pointSize: 7.1
                                        font.features: { "tnum": 1 }
                                    }
                                    StyledText {
                                        visible: (kCard.modelData.tokens ?? 0) > 0
                                        text: `${Agents.fmtTokens(kCard.modelData.tokens)} tok`
                                        color: root.fgDim
                                        font.pointSize: 7.1
                                        font.features: { "tnum": 1 }
                                    }
                                    StyledText {
                                        visible: (kCard.modelData.subagents ?? 0) > 0
                                        text: I18n.tr("+%1 sub").arg(kCard.modelData.subagents)
                                        color: root.aiTint
                                        font.pointSize: 7.1
                                        font.weight: Font.Bold
                                    }
                                    Rectangle {
                                        visible: kCard.repoConflict
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: confTxt.implicitWidth + 10
                                        height: 16
                                        radius: 8
                                        color: Qt.alpha(root.orange, 0.2)
                                        border.width: 0.5
                                        border.color: Qt.alpha(root.orange, 0.52)

                                        StyledText {
                                            id: confTxt

                                            anchors.centerIn: parent
                                            text: I18n.tr("⚠ Même repo")
                                            color: root.orange
                                            font.pointSize: 6.5
                                            font.weight: Font.Black
                                        }
                                    }
                                }

                                // Pied de carte : Permission directe si en attente · sinon Parler · Ouvrir · Modèle · Stop
                                Item {
                                    width: parent.width
                                    height: 24

                                    Row {
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 5

                                        ActionChip {
                                            visible: !!kCard.cardPerm
                                            label: I18n.tr("Autoriser")
                                            icon: "check"
                                            tint: root.green
                                            filled: true
                                            onClicked: Agents.answer(kCard.cardPerm.id, "allow")
                                        }
                                        ActionChip {
                                            visible: !!kCard.cardPerm
                                            label: I18n.tr("Refuser")
                                            icon: "close"
                                            tint: root.red
                                            onClicked: Agents.answer(kCard.cardPerm.id, "deny")
                                        }
                                        ActionChip {
                                            visible: !kCard.cardPerm
                                            label: I18n.tr("Parler")
                                            icon: "chat"
                                            tint: kCard.tint
                                            filled: true
                                            onClicked: root.inspectAgent(kCard.modelData, true)
                                        }
                                        ActionChip {
                                            label: I18n.tr("Ouvrir")
                                            icon: "open_in_new"
                                            tint: root.fg
                                            onClicked: {
                                                Agents.focus(kCard.modelData);
                                                root.close();
                                            }
                                        }
                                        ActionChip {
                                            visible: !kCard.cardPerm && kCard.modelData.kind !== "antigravity"
                                            label: I18n.tr("Modèle")
                                            icon: "tune"
                                            tint: root.aiTint
                                            onClicked: root.openModelPicker(kCard.modelData)
                                        }
                                        ActionChip {
                                            visible: !kCard.cardPerm && kCard.working && kCard.modelData.canStop
                                            label: I18n.tr("Stop")
                                            icon: "stop"
                                            tint: root.red
                                            onClicked: Agents.stop(kCard.modelData)
                                        }
                                    }

                                    Rectangle {
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        visible: kCard.done
                                        width: 22
                                        height: 22
                                        radius: 11
                                        color: Qt.alpha(root.fg, kcDismissArea.containsMouse ? 0.18 : 0.08)

                                        MaterialIcon {
                                            anchors.centerIn: parent
                                            text: "close"
                                            color: root.fgDim
                                            fontStyle: Tokens.font.icon.size(12).build()
                                        }

                                        MouseArea {
                                            id: kcDismissArea

                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: Agents.dismiss(kCard.modelData)
                                        }
                                    }
                                }
                            }

                            HoverHandler {
                                id: cardHover
                            }
                        }
                        }
                    }

                    // État vide du Canvas
                    Column {
                        visible: root.visibleAgents.length === 0
                        anchors.centerIn: parent
                        spacing: 14

                        StyledText {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: I18n.tr("Déploie un agent sur ton canvas")
                            color: root.fg
                            font.pointSize: 12
                            font.weight: Font.Bold
                        }

                        StyledText {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: I18n.tr("Parle à Katana AI dans la barre du bas ou clique sur un moteur")
                            color: root.fgDim
                            font.pointSize: 8.6
                        }

                        Flow {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 680
                            spacing: 10

                            Repeater {
                                model: Agents.launchKinds

                                Rectangle {
                                    id: spawnTile

                                    required property string modelData
                                    readonly property color tint: Agents.kindColour(modelData)

                                    width: 216
                                    height: 62
                                    radius: 16
                                    scale: spawnArea.pressed ? 0.96 : 1
                                    color: Qt.alpha(tint, spawnArea.containsMouse ? 0.22 : 0.11)
                                    border.width: 0.75
                                    border.color: Qt.alpha(tint, spawnArea.containsMouse ? 0.56 : 0.28)

                                    Behavior on scale { NumberAnimation { duration: 100 } }

                                    Row {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 14
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 10

                                        MiniSpinner {
                                            size: 32
                                            tint: spawnTile.tint
                                            spinning: false
                                            done: false
                                            letter: Agents.kindLetter(spawnTile.modelData)
                                        }

                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter

                                            StyledText {
                                                text: Agents.kindName(spawnTile.modelData)
                                                color: root.fg
                                                font.pointSize: 9.4
                                                font.weight: Font.Bold
                                            }
                                            StyledText {
                                                text: I18n.tr("Lancer une session")
                                                color: root.fgDim
                                                font.pointSize: 7.4
                                            }
                                        }
                                    }

                                    MouseArea {
                                        id: spawnArea

                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: Agents.dispatch(spawnTile.modelData, root.currentProject?.cwd ?? "", "")
                                    }
                                }
                            }
                        }
                    }

                    // Rangée rapide d'invocation en bas du canvas
                    Column {
                        visible: root.visibleAgents.length > 0 && root.visibleAgents.length <= 3
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 34
                        spacing: 7

                        StyledText {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: I18n.tr("INVOQUER UN AGENT SUR LE CANVAS")
                            color: root.fgMute
                            font.pointSize: 6.8
                            font.weight: Font.Black
                            font.letterSpacing: 0.8
                        }

                        Row {
                            anchors.horizontalCenter: parent.horizontalCenter
                            spacing: 8

                            Repeater {
                                model: Agents.launchKinds

                                Rectangle {
                                    id: qSpawn

                                    required property string modelData
                                    readonly property color tint: Agents.kindColour(modelData)

                                    width: qSpawnRow.implicitWidth + 22
                                    height: 36
                                    radius: 18
                                    scale: qSpawnArea.pressed ? 0.95 : 1
                                    color: Qt.alpha(tint, qSpawnArea.containsMouse ? 0.22 : 0.1)
                                    border.width: 0.6
                                    border.color: Qt.alpha(tint, qSpawnArea.containsMouse ? 0.56 : 0.28)

                                    Behavior on scale { NumberAnimation { duration: 100 } }

                                    Row {
                                        id: qSpawnRow

                                        anchors.centerIn: parent
                                        spacing: 6

                                        StyledText {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: Agents.kindLetter(qSpawn.modelData)
                                            color: qSpawn.tint
                                            font.pointSize: 8.6
                                            font.weight: Font.Black
                                        }
                                        StyledText {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: Agents.kindName(qSpawn.modelData)
                                            color: root.fg
                                            font.pointSize: 8
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    MouseArea {
                                        id: qSpawnArea

                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: Agents.dispatch(qSpawn.modelData, root.currentProject?.cwd ?? "", "")
                                    }
                                }
                            }
                        }
                    }

                    // HUD Télémétrie temps réel (bas-gauche du Canvas)
                    Rectangle {
                        visible: root.visibleAgents.length > 0
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        anchors.margins: 12
                        z: 25
                        width: hudRow.implicitWidth + 16
                        height: 24
                        radius: 12
                        color: Qt.alpha(Colours.palette.m3surface, Colours.light ? 0.8 : 0.72)
                        border.width: 0.5
                        border.color: root.conflictRepoCount > 0 ? Qt.alpha(root.orange, 0.52) : Qt.alpha(root.fg, 0.14)

                        Row {
                            id: hudRow

                            anchors.centerIn: parent
                            spacing: 8

                            StyledText {
                                visible: Agents.totalFiles > 0
                                text: I18n.tr("%1 fich. modifiés").arg(Agents.totalFiles)
                                color: root.fgDim
                                font.pointSize: 7.1
                                font.weight: Font.DemiBold
                                font.features: { "tnum": 1 }
                            }
                            StyledText {
                                visible: Agents.totalTokens > 0
                                text: `${Agents.fmtTokens(Agents.totalTokens)} tok`
                                color: root.fgDim
                                font.pointSize: 7.1
                                font.weight: Font.DemiBold
                                font.features: { "tnum": 1 }
                            }
                            StyledText {
                                visible: root.conflictRepoCount > 0
                                text: I18n.tr("⚠ %1 conflit(s) repo").arg(root.conflictRepoCount)
                                color: root.orange
                                font.pointSize: 7.1
                                font.weight: Font.Black
                            }
                            StyledText {
                                visible: Agents.totalFiles === 0 && Agents.totalTokens === 0 && root.conflictRepoCount === 0
                                text: I18n.tr("%1 session(s) sur le canvas").arg(root.visibleAgents.length)
                                color: root.fgDim
                                font.pointSize: 7.1
                                font.weight: Font.Medium
                            }
                        }
                    }

                    StyledText {
                        visible: root.visibleAgents.length > 0
                        anchors.bottom: parent.bottom
                        anchors.right: parent.right
                        anchors.margins: 12
                        text: I18n.tr("Glisser fond = déplacer · Molette = zoom · Double-clic = réaligner")
                        color: root.fgMute
                        font.pointSize: 7.1
                    }
                }
            }

            // ════════════════ VUE 1 : COCKPIT, INSPECTEUR & CHAT DIRECT AGENT ════════════════
            Row {
                anchors.fill: parent
                visible: root.viewTab === 1
                spacing: 12

                // Flotte gauche
                Rectangle {
                    width: 320
                    height: parent.height
                    radius: 18
                    color: Qt.alpha(root.fg, 0.045)
                    border.width: 0.5
                    border.color: Qt.alpha(root.fg, 0.12)

                    Column {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8

                        StyledText {
                            text: I18n.tr("FLOTTE (%1)").arg(Agents.shown.length)
                            color: root.fgDim
                            font.pointSize: 7.5
                            font.weight: Font.Black
                            font.letterSpacing: 0.7
                        }

                        // Filtre rapide flotte (visible dès 4 sessions)
                        Rectangle {
                            visible: Agents.shown.length >= 4
                            width: parent.width
                            height: 28
                            radius: 14
                            color: Qt.alpha(root.fg, 0.06)
                            border.width: 0.5
                            border.color: fleetSearchInput.activeFocus ? Qt.alpha(root.leadTint, 0.6) : Qt.alpha(root.fg, 0.14)

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 9
                                anchors.rightMargin: 9
                                spacing: 5

                                MaterialIcon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "search"
                                    color: root.fgDim
                                    fontStyle: Tokens.font.icon.size(12).build()
                                }
                                TextInput {
                                    id: fleetSearchInput

                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 18
                                    height: 22
                                    verticalAlignment: Text.AlignVCenter
                                    color: root.fg
                                    font.pointSize: 7.6
                                    clip: true
                                    text: root.fleetFilter
                                    onTextChanged: root.fleetFilter = text

                                    StyledText {
                                        visible: fleetSearchInput.text.length === 0
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: I18n.tr("Filtrer la flotte…")
                                        color: root.fgMute
                                        font.pointSize: 7.4
                                    }
                                }
                            }
                        }

                        Flickable {
                            width: parent.width
                            height: parent.height - (Agents.shown.length >= 4 ? 62 : 26)
                            contentWidth: width
                            contentHeight: fleetCol.implicitHeight
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds

                            Column {
                                id: fleetCol

                                width: parent.width
                                spacing: 6

                                Repeater {
                                    model: root.filteredFleet

                                    Rectangle {
                                        id: fItem

                                        required property var modelData
                                        readonly property bool sel: root.selectedAgent?.id === modelData.id
                                        readonly property bool working: modelData.status === "working"
                                        readonly property bool waiting: modelData.status === "waiting"
                                        readonly property color tint: Agents.kindColour(modelData.kind)
                                        readonly property color stateCol: waiting ? root.orange : working ? tint : root.green

                                        width: fleetCol.width
                                        height: 64
                                        radius: 14
                                        color: sel ? Qt.alpha(tint, 0.18) : Qt.alpha(root.fg, fItemArea.containsMouse ? 0.09 : 0.04)
                                        border.width: sel ? 1 : 0.5
                                        border.color: sel ? Qt.alpha(tint, 0.56) : Qt.alpha(root.fg, 0.12)

                                        Row {
                                            anchors.fill: parent
                                            anchors.leftMargin: 10
                                            anchors.rightMargin: 10
                                            spacing: 9

                                            MiniSpinner {
                                                anchors.verticalCenter: parent.verticalCenter
                                                size: 28
                                                tint: fItem.stateCol
                                                spinning: fItem.working && root.shown && root.viewTab === 1
                                                done: !fItem.working && !fItem.waiting
                                                letter: Agents.kindLetter(fItem.modelData.kind)
                                            }

                                            Column {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: parent.width - 86
                                                spacing: 2

                                                Row {
                                                    spacing: 5

                                                    StyledText {
                                                        text: Agents.kindShort(fItem.modelData.kind)
                                                        color: fItem.tint
                                                        font.pointSize: 6.4
                                                        font.weight: Font.Black
                                                    }
                                                    StyledText {
                                                        width: 130
                                                        elide: Text.ElideRight
                                                        text: fItem.modelData.project
                                                        color: root.fg
                                                        font.pointSize: 8.6
                                                        font.weight: Font.Bold
                                                    }
                                                }
                                                StyledText {
                                                    width: parent.width
                                                    elide: Text.ElideRight
                                                    text: fItem.modelData.focus || fItem.modelData.tool || fItem.modelData.title || I18n.tr("Prêt")
                                                    color: root.fgDim
                                                    font.pointSize: 7.4
                                                }
                                            }

                                            StyledText {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: Agents.elapsed(fItem.modelData.since)
                                                color: fItem.stateCol
                                                font.pointSize: 7.4
                                                font.weight: Font.Bold
                                                font.features: { "tnum": 1 }
                                            }
                                        }

                                        MouseArea {
                                            id: fItemArea

                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                root.selectedId = fItem.modelData.id;
                                                directFocusTimer.restart();
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Inspecteur droite + Chat direct vers l'agent
                Rectangle {
                    id: inspectorPane

                    readonly property var ag: root.selectedAgent
                    readonly property color tint: ag ? Agents.kindColour(ag.kind) : root.accent

                    width: parent.width - 332
                    height: parent.height
                    radius: 18
                    color: Qt.alpha(root.fg, 0.045)
                    border.width: 0.5
                    border.color: Qt.alpha(tint, ag ? 0.28 : 0.12)

                    StyledText {
                        visible: !inspectorPane.ag
                        anchors.centerIn: parent
                        text: I18n.tr("Sélectionne un agent à inspecter ou commander")
                        color: root.fgDim
                        font.pointSize: 9.5
                    }

                    Column {
                        visible: !!inspectorPane.ag
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 10

                        // En-tête inspecteur (anti-chevauchement garanti)
                        Item {
                            width: parent.width
                            height: 42

                            Row {
                                anchors.left: parent.left
                                anchors.right: inspectorHdrBtns.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                clip: true
                                spacing: 10

                                MiniSpinner {
                                    size: 36
                                    tint: inspectorPane.tint
                                    spinning: (inspectorPane.ag?.status ?? "") === "working" && root.shown && root.viewTab === 1
                                    done: (inspectorPane.ag?.status ?? "") === "idle"
                                    letter: Agents.kindLetter(inspectorPane.ag?.kind ?? "")
                                }

                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 1

                                    Row {
                                        spacing: 6

                                        StyledText {
                                            text: Agents.kindName(inspectorPane.ag?.kind ?? "")
                                            color: inspectorPane.tint
                                            font.pointSize: 10
                                            font.weight: Font.Black
                                        }
                                        StyledText {
                                            text: `· ${inspectorPane.ag?.project ?? ""}`
                                            color: root.fg
                                            font.pointSize: 10
                                            font.weight: Font.Bold
                                        }
                                        // Pastille Modèle & Effort cliquable en 1 clic
                                        Rectangle {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.min(200, hdrModelRow.implicitWidth + 14)
                                            height: 22
                                            radius: 11
                                            color: Qt.alpha(inspectorPane.tint, hdrModelArea.containsMouse ? 0.28 : 0.15)
                                            border.width: 0.6
                                            border.color: Qt.alpha(inspectorPane.tint, hdrModelArea.containsMouse ? 0.68 : 0.38)

                                            Row {
                                                id: hdrModelRow

                                                anchors.centerIn: parent
                                                spacing: 4

                                                MaterialIcon {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: "tune"
                                                    color: inspectorPane.tint
                                                    fontStyle: Tokens.font.icon.size(12).build()
                                                }
                                                StyledText {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    width: Math.min(implicitWidth, 162)
                                                    elide: Text.ElideRight
                                                    text: inspectorPane.ag?.model || I18n.tr("Modèle")
                                                    color: root.fg
                                                    font.pointSize: 7.4
                                                    font.weight: Font.Bold
                                                }
                                            }

                                            MouseArea {
                                                id: hdrModelArea

                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: root.openModelPicker(inspectorPane.ag)
                                            }
                                        }
                                    }
                                    StyledText {
                                        width: 350
                                        elide: Text.ElideMiddle
                                        text: inspectorPane.ag?.cwd || inspectorPane.ag?.title || ""
                                        color: root.fgDim
                                        font.family: "monospace"
                                        font.pointSize: 7.3
                                    }
                                }
                            }

                            Row {
                                id: inspectorHdrBtns

                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 6

                                ActionChip {
                                    label: I18n.tr("Ouvrir")
                                    icon: "open_in_new"
                                    tint: inspectorPane.tint
                                    filled: true
                                    onClicked: {
                                        Agents.focus(inspectorPane.ag);
                                        root.close();
                                    }
                                }
                                ActionChip {
                                    visible: Boolean(inspectorPane.ag?.cwd)
                                    label: I18n.tr("Terminal")
                                    icon: "terminal"
                                    tint: root.fg
                                    onClicked: Agents.openTerminal(inspectorPane.ag.cwd)
                                }
                                ActionChip {
                                    visible: Boolean(inspectorPane.ag?.canStop) && (inspectorPane.ag?.status ?? "") === "working"
                                    label: I18n.tr("Stop")
                                    icon: "stop"
                                    tint: root.orange
                                    onClicked: Agents.stop(inspectorPane.ag)
                                }
                                ActionChip {
                                    visible: Boolean(inspectorPane.ag?.canStop)
                                    label: I18n.tr("Tuer")
                                    icon: "power_settings_new"
                                    tint: root.red
                                    onClicked: Agents.kill(inspectorPane.ag)
                                }
                            }
                        }

                        // 4 Tuiles KPI
                        Row {
                            width: parent.width
                            spacing: 8

                            KpiBox {
                                width: (parent.width - 24) / 4
                                label: I18n.tr("STATUT")
                                value: (inspectorPane.ag?.status ?? "") === "working" ? I18n.tr("Actif") : (inspectorPane.ag?.status ?? "") === "waiting" ? I18n.tr("Attente") : I18n.tr("Prêt")
                                sub: Agents.elapsed(inspectorPane.ag?.since ?? Agents.now)
                                tint: (inspectorPane.ag?.status ?? "") === "waiting" ? root.orange : (inspectorPane.ag?.status ?? "") === "working" ? inspectorPane.tint : root.green
                            }
                            KpiBox {
                                width: (parent.width - 24) / 4
                                label: I18n.tr("FICHIERS")
                                value: String(inspectorPane.ag?.files ?? 0)
                                sub: inspectorPane.ag?.branch ? `⎇ ${inspectorPane.ag.branch}` : "—"
                                tint: root.fg
                            }
                            KpiBox {
                                width: (parent.width - 24) / 4
                                label: I18n.tr("TOKENS")
                                value: Agents.fmtTokens(inspectorPane.ag?.tokens ?? 0) || "—"
                                sub: inspectorPane.ag?.model || "—"
                                tint: inspectorPane.tint
                            }
                            KpiBox {
                                width: (parent.width - 24) / 4
                                label: I18n.tr("SOUS-AGENTS")
                                value: String(inspectorPane.ag?.subagents ?? 0)
                                sub: (inspectorPane.ag?.stepTotal ?? 0) > 0 ? I18n.tr("Étapes %1/%2").arg(inspectorPane.ag.stepDone).arg(inspectorPane.ag.stepTotal) : I18n.tr("Flux direct")
                                tint: root.aiTint
                            }
                        }

                        // Zone Inspecteur (Journal / Terminal Live / Diff Git) + Étapes & Fichiers Git cliquables
                        Row {
                            width: parent.width
                            height: parent.height - 208
                            spacing: 10

                            readonly property bool hasSide: (root.detailData.steps?.length ?? 0) > 0 || (root.detailData.gitFiles?.length ?? root.detailData.gitStatus?.length ?? 0) > 0

                            Rectangle {
                                width: parent.hasSide ? Math.round(parent.width * 0.66) : parent.width
                                height: parent.height
                                radius: 14
                                color: Qt.alpha(root.fg, 0.04)
                                border.width: 0.5
                                border.color: Qt.alpha(root.fg, 0.1)

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 7

                                    // Barre d'onglets Inspecteur : Journal · Terminal Live · Diff Git + Actions Copier/Rafraîchir
                                    Item {
                                        width: parent.width
                                        height: 26

                                        Row {
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 4

                                            Repeater {
                                                model: [
                                                    { idx: 0, icon: "list_alt", label: I18n.tr("Journal") },
                                                    { idx: 1, icon: "terminal", label: I18n.tr("Terminal Live") },
                                                    { idx: 2, icon: "difference", label: I18n.tr("Diff Git") }
                                                ]

                                                Rectangle {
                                                    id: iTab

                                                    required property var modelData
                                                    readonly property bool sel: root.inspectorTab === modelData.idx

                                                    width: iTabRow.implicitWidth + 14
                                                    height: 24
                                                    radius: 12
                                                    color: sel ? Qt.alpha(inspectorPane.tint, 0.22) : Qt.alpha(root.fg, iTabArea.containsMouse ? 0.1 : 0.04)
                                                    border.width: sel ? 0.6 : 0.4
                                                    border.color: sel ? Qt.alpha(inspectorPane.tint, 0.55) : Qt.alpha(root.fg, 0.12)

                                                    Row {
                                                        id: iTabRow

                                                        anchors.centerIn: parent
                                                        spacing: 4

                                                        MaterialIcon {
                                                            anchors.verticalCenter: parent.verticalCenter
                                                            text: iTab.modelData.icon
                                                            color: iTab.sel ? inspectorPane.tint : root.fgDim
                                                            fontStyle: Tokens.font.icon.size(12).build()
                                                            fill: iTab.sel ? 1 : 0
                                                        }
                                                        StyledText {
                                                            anchors.verticalCenter: parent.verticalCenter
                                                            text: iTab.modelData.label
                                                            color: iTab.sel ? root.fg : root.fgDim
                                                            font.pointSize: 7.3
                                                            font.weight: iTab.sel ? Font.Bold : Font.DemiBold
                                                        }
                                                    }

                                                    MouseArea {
                                                        id: iTabArea

                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: root.inspectorTab = iTab.modelData.idx
                                                    }
                                                }
                                            }
                                        }

                                        // Actions contextuelles droite (Copier / Rafraîchir)
                                        Row {
                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 5

                                            ActionChip {
                                                visible: root.inspectorTab === 1 && root.screenData.ok && (root.screenData.text?.length ?? 0) > 0
                                                label: I18n.tr("Copier")
                                                icon: "content_copy"
                                                tint: root.fg
                                                onClicked: root.copyText(root.screenData.text, I18n.tr("Écran terminal copié ✓"))
                                            }
                                            ActionChip {
                                                visible: root.inspectorTab === 2 && (root.diffData.raw?.length ?? 0) > 0
                                                label: I18n.tr("Copier")
                                                icon: "content_copy"
                                                tint: root.fg
                                                onClicked: root.copyText(root.diffData.raw, I18n.tr("Diff Git copié ✓"))
                                            }
                                            ActionChip {
                                                visible: root.inspectorTab === 1 || root.inspectorTab === 2
                                                label: root.screenLoading || root.diffLoading ? I18n.tr("…") : I18n.tr("Actualiser")
                                                icon: "refresh"
                                                tint: inspectorPane.tint
                                                onClicked: {
                                                    if (root.inspectorTab === 1)
                                                        root.refreshScreen();
                                                    else
                                                        root.refreshDiff(root.diffFile);
                                                }
                                            }
                                        }
                                    }

                                    // ── SOUS-VUE 0 : JOURNAL D'ACTIVITÉ DÉPLIABLE ──
                                    Flickable {
                                        visible: root.inspectorTab === 0
                                        width: parent.width
                                        height: parent.height - 33
                                        contentWidth: width
                                        contentHeight: evCol.implicitHeight
                                        clip: true
                                        boundsBehavior: Flickable.StopAtBounds

                                        Column {
                                            id: evCol

                                            width: parent.width
                                            spacing: 4

                                            Repeater {
                                                model: root.detailData.events ?? []

                                                Rectangle {
                                                    id: evItem

                                                    required property var modelData
                                                    required property int index
                                                    readonly property bool expanded: root.expandedEventIdx === index
                                                    readonly property string fullStr: modelData.fullText || modelData.text || ""
                                                    readonly property bool canExpand: fullStr.length > 90 || fullStr.indexOf("\n") >= 0

                                                    width: evCol.width
                                                    height: evRow.implicitHeight + 8
                                                    radius: 8
                                                    color: expanded ? Qt.alpha(inspectorPane.tint, 0.1) : (evHover.containsMouse ? Qt.alpha(root.fg, 0.05) : "transparent")
                                                    border.width: expanded ? 0.5 : 0
                                                    border.color: Qt.alpha(inspectorPane.tint, 0.32)

                                                    Row {
                                                        id: evRow

                                                        anchors.left: parent.left
                                                        anchors.right: evCopyBtn.visible ? evCopyBtn.left : parent.right
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        anchors.leftMargin: 6
                                                        anchors.rightMargin: 6
                                                        spacing: 7

                                                        Rectangle {
                                                            y: 5
                                                            width: 6
                                                            height: 6
                                                            radius: 3
                                                            color: evItem.modelData.kind === "tool" ? inspectorPane.tint
                                                                : evItem.modelData.kind === "focus" ? root.aiTint
                                                                : evItem.modelData.kind === "reply" ? root.green
                                                                : evItem.modelData.kind === "file" ? root.orange
                                                                : root.fgDim
                                                        }

                                                        StyledText {
                                                            width: parent.width - 14
                                                            wrapMode: Text.Wrap
                                                            maximumLineCount: evItem.expanded ? 30 : 2
                                                            elide: evItem.expanded ? Text.ElideNone : Text.ElideRight
                                                            text: evItem.expanded ? evItem.fullStr : (evItem.modelData.text ?? "")
                                                            color: evItem.modelData.kind === "reply" || evItem.expanded ? root.fg : root.fgDim
                                                            font.family: evItem.modelData.kind === "tool" ? "monospace" : Tokens.font.body.medium.family
                                                            font.pointSize: evItem.modelData.kind === "tool" ? 7.4 : 7.8
                                                        }
                                                    }

                                                    MouseArea {
                                                        id: evHover

                                                        anchors.fill: parent
                                                        anchors.rightMargin: evCopyBtn.visible ? 28 : 0
                                                        hoverEnabled: true
                                                        cursorShape: evItem.canExpand ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                        onClicked: {
                                                            if (evItem.canExpand)
                                                                root.expandedEventIdx = evItem.expanded ? -1 : evItem.index;
                                                        }
                                                    }

                                                    Rectangle {
                                                        id: evCopyBtn

                                                        visible: evItem.expanded || evHover.containsMouse
                                                        anchors.right: parent.right
                                                        anchors.top: parent.top
                                                        anchors.margins: 4
                                                        width: 22
                                                        height: 22
                                                        radius: 11
                                                        color: Qt.alpha(root.fg, evCopyArea.containsMouse ? 0.18 : 0.08)

                                                        MaterialIcon {
                                                            anchors.centerIn: parent
                                                            text: "content_copy"
                                                            color: root.fgDim
                                                            fontStyle: Tokens.font.icon.size(12).build()
                                                        }

                                                        MouseArea {
                                                            id: evCopyArea

                                                            anchors.fill: parent
                                                            hoverEnabled: true
                                                            cursorShape: Qt.PointingHandCursor
                                                            onClicked: root.copyText(evItem.fullStr, I18n.tr("Entrée copiée ✓"))
                                                        }
                                                    }
                                                }
                                            }

                                            StyledText {
                                                visible: (root.detailData.events?.length ?? 0) === 0
                                                text: inspectorPane.ag?.reply || inspectorPane.ag?.tool || I18n.tr("Session prête — écris un ordre ci-dessous pour piloter cet agent en direct.")
                                                color: root.fgDim
                                                font.pointSize: 8
                                                width: parent.width
                                                wrapMode: Text.Wrap
                                            }
                                        }
                                    }

                                    // ── SOUS-VUE 1 : TERMINAL KITTY LIVE ──
                                    Rectangle {
                                        visible: root.inspectorTab === 1
                                        width: parent.width
                                        height: parent.height - 33
                                        radius: 10
                                        color: Colours.light ? Qt.rgba(0.08, 0.09, 0.12, 0.92) : Qt.rgba(0.03, 0.04, 0.06, 0.72)
                                        border.width: 0.5
                                        border.color: Qt.alpha(inspectorPane.tint, 0.25)

                                        Column {
                                            anchors.fill: parent
                                            anchors.margins: 9
                                            spacing: 5

                                            Row {
                                                width: parent.width
                                                spacing: 7

                                                Rectangle {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    width: 7
                                                    height: 7
                                                    radius: 3.5
                                                    color: root.screenData.ok ? root.green : root.orange
                                                }
                                                StyledText {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: root.screenData.ok
                                                        ? (root.screenData.detail || I18n.tr("Terminal Kitty connecté"))
                                                        : (root.screenLoading ? I18n.tr("Lecture de l'écran Kitty…") : (root.screenData.detail || I18n.tr("Aperçu terminal indisponible")))
                                                    color: Qt.rgba(0.82, 0.86, 0.92, 0.78)
                                                    font.family: "monospace"
                                                    font.pointSize: 7.1
                                                    font.weight: Font.DemiBold
                                                }
                                            }

                                            Flickable {
                                                id: termFlick

                                                width: parent.width
                                                height: parent.height - 20
                                                contentWidth: width
                                                contentHeight: Math.max(height, termTxt.implicitHeight)
                                                clip: true
                                                boundsBehavior: Flickable.StopAtBounds

                                                onContentHeightChanged: {
                                                    if (contentHeight > height)
                                                        contentY = contentHeight - height;
                                                }

                                                StyledText {
                                                    id: termTxt

                                                    width: termFlick.width
                                                    wrapMode: Text.WrapAnywhere
                                                    text: root.screenData.ok
                                                        ? (root.screenData.text || I18n.tr("(écran vide)"))
                                                        : (root.screenData.detail || I18n.tr("Cet agent ne tourne pas dans Kitty."))
                                                    color: root.screenData.ok ? "#e5edf8" : "#a8b3c4"
                                                    font.family: "monospace"
                                                    font.pointSize: 7.3
                                                }
                                            }
                                        }
                                    }

                                    // ── SOUS-VUE 2 : DIFF GIT COLORÉ ──
                                    Column {
                                        visible: root.inspectorTab === 2
                                        width: parent.width
                                        height: parent.height - 33
                                        spacing: 6

                                        // En-tête diff : fichier courant + compteur +added/-removed
                                        Row {
                                            width: parent.width
                                            spacing: 7

                                            Rectangle {
                                                visible: root.diffFile.length > 0
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: allDiffTxt.implicitWidth + 12
                                                height: 20
                                                radius: 10
                                                color: Qt.alpha(root.fg, allDiffArea.containsMouse ? 0.16 : 0.08)

                                                StyledText {
                                                    id: allDiffTxt

                                                    anchors.centerIn: parent
                                                    text: I18n.tr("← Tout")
                                                    color: root.fg
                                                    font.pointSize: 7
                                                    font.weight: Font.Bold
                                                }

                                                MouseArea {
                                                    id: allDiffArea

                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: root.refreshDiff("")
                                                }
                                            }

                                            StyledText {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: Math.min(implicitWidth, parent.width - 140)
                                                elide: Text.ElideMiddle
                                                text: root.diffFile || I18n.tr("Diff global du dépôt")
                                                color: root.fg
                                                font.family: "monospace"
                                                font.pointSize: 7.4
                                                font.weight: Font.Bold
                                            }

                                            StyledText {
                                                visible: (root.diffData.added ?? 0) > 0
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: `+${root.diffData.added ?? 0}`
                                                color: root.green
                                                font.family: "monospace"
                                                font.pointSize: 7.4
                                                font.weight: Font.Black
                                            }

                                            StyledText {
                                                visible: (root.diffData.removed ?? 0) > 0
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: `-${root.diffData.removed ?? 0}`
                                                color: root.red
                                                font.family: "monospace"
                                                font.pointSize: 7.4
                                                font.weight: Font.Black
                                            }
                                        }

                                        Rectangle {
                                            width: parent.width
                                            height: parent.height - 26
                                            radius: 10
                                            color: Colours.light ? Qt.rgba(0.08, 0.09, 0.12, 0.92) : Qt.rgba(0.03, 0.04, 0.06, 0.68)
                                            border.width: 0.5
                                            border.color: Qt.alpha(root.fg, 0.14)

                                            Flickable {
                                                anchors.fill: parent
                                                anchors.margins: 8
                                                contentWidth: width
                                                contentHeight: diffLinesCol.implicitHeight
                                                clip: true
                                                boundsBehavior: Flickable.StopAtBounds

                                                Column {
                                                    id: diffLinesCol

                                                    width: parent.width
                                                    spacing: 1

                                                    Repeater {
                                                        model: root.diffData.lines ?? []

                                                        Rectangle {
                                                            id: dLn

                                                            required property var modelData
                                                            width: diffLinesCol.width
                                                            height: dLnTxt.implicitHeight + 3
                                                            radius: 3
                                                            color: modelData.kind === "add" ? Qt.alpha(root.green, 0.16)
                                                                : modelData.kind === "del" ? Qt.alpha(root.red, 0.17)
                                                                : modelData.kind === "hunk" ? Qt.alpha(root.aiTint, 0.16)
                                                                : "transparent"

                                                            StyledText {
                                                                id: dLnTxt

                                                                anchors.left: parent.left
                                                                anchors.right: parent.right
                                                                anchors.verticalCenter: parent.verticalCenter
                                                                anchors.leftMargin: 5
                                                                anchors.rightMargin: 5
                                                                wrapMode: Text.WrapAnywhere
                                                                text: dLn.modelData.text ?? ""
                                                                color: dLn.modelData.kind === "add" ? "#6ee7b7"
                                                                    : dLn.modelData.kind === "del" ? "#fca5a5"
                                                                    : dLn.modelData.kind === "hunk" ? "#c4b5fd"
                                                                    : dLn.modelData.kind === "meta" ? "#93c5fd"
                                                                    : "#d8e1ee"
                                                                font.family: "monospace"
                                                                font.pointSize: 7.2
                                                                font.weight: dLn.modelData.kind === "meta" || dLn.modelData.kind === "hunk" ? Font.Bold : Font.Normal
                                                            }
                                                        }
                                                    }

                                                    StyledText {
                                                        visible: (root.diffData.lines?.length ?? 0) === 0
                                                        width: parent.width
                                                        wrapMode: Text.Wrap
                                                        text: root.diffLoading
                                                            ? I18n.tr("Chargement du diff Git…")
                                                            : (root.diffData.detail || I18n.tr("Aucune modification Git en cours sur ce chemin."))
                                                        color: "#a8b3c4"
                                                        font.family: "monospace"
                                                        font.pointSize: 7.6
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                visible: parent.hasSide
                                width: parent.width - Math.round(parent.width * 0.66) - 10
                                height: parent.height
                                radius: 14
                                color: Qt.alpha(root.fg, 0.04)
                                border.width: 0.5
                                border.color: Qt.alpha(root.fg, 0.1)

                                Flickable {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    contentWidth: width
                                    contentHeight: sideDetCol.implicitHeight
                                    clip: true

                                    Column {
                                        id: sideDetCol

                                        width: parent.width
                                        spacing: 7

                                        StyledText {
                                            visible: (root.detailData.steps?.length ?? 0) > 0
                                            text: I18n.tr("ÉTAPES")
                                            color: root.fgDim
                                            font.pointSize: 7.2
                                            font.weight: Font.Black
                                            font.letterSpacing: 0.65
                                        }

                                        Repeater {
                                            model: root.detailData.steps ?? []

                                            Row {
                                                required property var modelData
                                                width: sideDetCol.width
                                                spacing: 6

                                                MaterialIcon {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: modelData.status === "done" ? "check_circle" : modelData.status === "in_progress" ? "pending" : "radio_button_unchecked"
                                                    color: modelData.status === "done" ? root.green : modelData.status === "in_progress" ? inspectorPane.tint : root.fgMute
                                                    fontStyle: Tokens.font.icon.size(13).build()
                                                    fill: modelData.status === "done" ? 1 : 0
                                                }
                                                StyledText {
                                                    width: parent.width - 20
                                                    elide: Text.ElideRight
                                                    text: modelData.title ?? ""
                                                    color: modelData.status === "done" ? root.fgDim : root.fg
                                                    font.pointSize: 7.6
                                                }
                                            }
                                        }

                                        StyledText {
                                            visible: (root.detailData.gitFiles?.length ?? root.detailData.gitStatus?.length ?? 0) > 0
                                            text: I18n.tr("FICHIERS GIT (CLIC = DIFF)")
                                            color: root.fgDim
                                            font.pointSize: 7.0
                                            font.weight: Font.Black
                                            font.letterSpacing: 0.6
                                        }

                                        Repeater {
                                            model: root.detailData.gitFiles ?? []

                                            Rectangle {
                                                id: gfRow

                                                required property var modelData
                                                readonly property bool active: root.inspectorTab === 2 && root.diffFile === modelData.path
                                                readonly property color badgeCol: modelData.code === "??" || modelData.code === "A" ? root.green
                                                    : modelData.code === "D" ? root.red
                                                    : root.orange

                                                width: sideDetCol.width
                                                height: 24
                                                radius: 7
                                                color: active ? Qt.alpha(inspectorPane.tint, 0.2) : (gfArea.containsMouse ? Qt.alpha(root.fg, 0.09) : "transparent")
                                                border.width: active ? 0.5 : 0
                                                border.color: Qt.alpha(inspectorPane.tint, 0.45)

                                                Row {
                                                    anchors.fill: parent
                                                    anchors.leftMargin: 5
                                                    anchors.rightMargin: 5
                                                    spacing: 5

                                                    Rectangle {
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        width: 18
                                                        height: 15
                                                        radius: 4
                                                        color: Qt.alpha(gfRow.badgeCol, 0.2)

                                                        StyledText {
                                                            anchors.centerIn: parent
                                                            text: gfRow.modelData.code ?? "M"
                                                            color: gfRow.badgeCol
                                                            font.family: "monospace"
                                                            font.pointSize: 6.5
                                                            font.weight: Font.Black
                                                        }
                                                    }

                                                    StyledText {
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        width: parent.width - 24
                                                        elide: Text.ElideMiddle
                                                        text: gfRow.modelData.path ?? ""
                                                        color: gfRow.active ? root.fg : root.fgDim
                                                        font.family: "monospace"
                                                        font.pointSize: 7.1
                                                        font.weight: gfRow.active ? Font.Bold : Font.Normal
                                                    }
                                                }

                                                MouseArea {
                                                    id: gfArea

                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: root.openDiffFile(gfRow.modelData.path)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // PUCES D'ACTIONS RAPIDES VERS L'AGENT
                        Row {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: [
                                    { label: I18n.tr("Continuer"), icon: "fast_forward", msg: "Continue" },
                                    { label: "/compact", icon: "compress", msg: "/compact" },
                                    { label: I18n.tr("Vérif lint"), icon: "verified", msg: "Lance les vérifications lint et tests rapides sur les fichiers touchés." },
                                    { label: I18n.tr("Diff Git"), icon: "difference", msg: "__diff__" }
                                ]

                                ActionChip {
                                    required property var modelData
                                    label: modelData.label
                                    icon: modelData.icon
                                    tint: modelData.msg === "__diff__" ? root.aiTint : root.fg
                                    onClicked: {
                                        if (modelData.msg === "__diff__") {
                                            root.openDiffFile("");
                                        } else {
                                            root.sendDirectToAgent(inspectorPane.ag, modelData.msg);
                                        }
                                    }
                                }
                            }
                        }

                        // BARRE DE CHAT DIRECT VERS CET AGENT (injection Kitty / reprise session)
                        Rectangle {
                            width: parent.width
                            height: 44
                            radius: 22
                            color: Qt.alpha(inspectorPane.tint, directReplyInput.activeFocus ? 0.14 : 0.08)
                            border.width: directReplyInput.activeFocus ? 1 : 0.6
                            border.color: Qt.alpha(inspectorPane.tint, directReplyInput.activeFocus ? 0.72 : 0.34)

                            MouseArea {
                                anchors.fill: parent
                                onClicked: directReplyInput.forceActiveFocus()
                            }

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 6
                                spacing: 8

                                MaterialIcon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "send"
                                    color: inspectorPane.tint
                                    fontStyle: Tokens.font.icon.size(15).build()
                                    fill: 1
                                }

                                TextInput {
                                    id: directReplyInput

                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 118
                                    height: 32
                                    verticalAlignment: Text.AlignVCenter
                                    color: root.fg
                                    font.pointSize: 8.6
                                    clip: true
                                    selectByMouse: true
                                    activeFocusOnPress: true
                                    Keys.onEscapePressed: root.closeTopOverlayOrStudio()
                                    onAccepted: {
                                        if (text.trim()) {
                                            root.sendDirectToAgent(inspectorPane.ag, text);
                                            text = "";
                                        }
                                    }

                                    StyledText {
                                        visible: directReplyInput.text.length === 0
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: I18n.tr("Écrire directement à %1 (%2)…").arg(Agents.kindName(inspectorPane.ag?.kind ?? "")).arg(inspectorPane.ag?.project ?? "")
                                        color: root.fgMute
                                        font.pointSize: 8.3
                                    }
                                }

                                ActionChip {
                                    anchors.verticalCenter: parent.verticalCenter
                                    label: root.sendingDirect ? I18n.tr("Envoi…") : I18n.tr("Envoyer")
                                    tint: inspectorPane.tint
                                    filled: true
                                    onClicked: {
                                        if (directReplyInput.text.trim()) {
                                            root.sendDirectToAgent(inspectorPane.ag, directReplyInput.text);
                                            directReplyInput.text = "";
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ════════════════ VUE 2 : COMMANDANT IA (KATANA AI CHEF D'ORCHESTRE) ════════════════
            Rectangle {
                anchors.fill: parent
                visible: root.viewTab === 2
                radius: 20
                color: Qt.alpha(root.fg, 0.04)
                border.width: 0.6
                border.color: Qt.alpha(root.aiTint, 0.3)

                Column {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    // En-tête Commandant IA
                    Item {
                        width: parent.width
                        height: 36

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 10

                            Rectangle {
                                width: 32
                                height: 32
                                radius: 16
                                color: Qt.alpha(root.aiTint, 0.22)
                                border.width: 0.6
                                border.color: Qt.alpha(root.aiTint, 0.5)

                                MaterialIcon {
                                    anchors.centerIn: parent
                                    text: "auto_awesome"
                                    color: root.aiTint
                                    fontStyle: Tokens.font.icon.size(16).build()
                                    fill: 1
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter

                                StyledText {
                                    text: I18n.tr("KATANA AI · MÉMOIRE & ACTIONS ANO-GPT")
                                    color: root.fg
                                    font.pointSize: 9.4
                                    font.weight: Font.Black
                                    font.letterSpacing: 0.65
                                }
                                StyledText {
                                    text: I18n.tr("Pilote tous tes agents + tout ton PC (apps, réglages, musique, web, fichiers) avec la mémoire d'ANO-GPT")
                                    color: root.fgDim
                                    font.pointSize: 7.8
                                }
                            }
                        }

                        Row {
                            visible: root.chatHistory.length > 0
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6

                            ActionChip {
                                label: I18n.tr("Copier tout")
                                icon: "content_copy"
                                tint: root.aiTint
                                onClicked: root.copyChatTranscript()
                            }
                            ActionChip {
                                label: I18n.tr("Effacer")
                                icon: "delete_sweep"
                                tint: root.fg
                                onClicked: root.clearHistory()
                            }
                        }
                    }

                    // Fil de discussion ou suggestions rapides
                    Flickable {
                        id: chatFlick

                        width: parent.width
                        height: parent.height - 48
                        contentWidth: width
                        contentHeight: Math.max(height, chatCol.implicitHeight)
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds

                        onContentHeightChanged: {
                            if (contentHeight > height)
                                contentY = contentHeight - height;
                        }

                        Column {
                            id: chatCol

                            width: chatFlick.width
                            spacing: 10

                            // Accueil + Suggestions rapides quand vide
                            Column {
                                visible: root.chatHistory.length === 0 && !root.aiThinking
                                width: parent.width
                                topPadding: 44
                                spacing: 14

                                StyledText {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: I18n.tr("Que veux-tu ordonner à tes agents ?")
                                    color: root.fg
                                    font.pointSize: 13
                                    font.weight: Font.Bold
                                }

                                Flow {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: Math.min(760, parent.width - 20)
                                    spacing: 8

                                    Repeater {
                                        model: root.dynamicSuggestions

                                        Rectangle {
                                            id: sugChip

                                            required property string modelData
                                            width: sugTxt.implicitWidth + 24
                                            height: 34
                                            radius: 17
                                            scale: sugArea.pressed ? 0.96 : 1
                                            color: Qt.alpha(root.aiTint, sugArea.containsMouse ? 0.22 : 0.1)
                                            border.width: 0.6
                                            border.color: Qt.alpha(root.aiTint, sugArea.containsMouse ? 0.56 : 0.28)

                                            Behavior on scale { NumberAnimation { duration: 100 } }

                                            StyledText {
                                                id: sugTxt

                                                anchors.centerIn: parent
                                                text: sugChip.modelData
                                                color: root.fg
                                                font.pointSize: 8.1
                                                font.weight: Font.Medium
                                            }

                                            MouseArea {
                                                id: sugArea

                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: root.askCommander(sugChip.modelData)
                                            }
                                        }
                                    }
                                }
                            }

                            // Messages de la conversation (Markdown + Copier + Badges cliquables)
                            Repeater {
                                model: root.chatHistory

                                Item {
                                    id: msgWrap

                                    required property var modelData
                                    readonly property bool isUser: modelData.role === "user"

                                    width: chatCol.width
                                    height: msgBubble.implicitHeight + 4

                                    Rectangle {
                                        id: msgBubble

                                        anchors.right: msgWrap.isUser ? parent.right : undefined
                                        anchors.left: msgWrap.isUser ? undefined : parent.left
                                        width: Math.min(Math.round(parent.width * 0.8), msgCol.implicitWidth + 32)
                                        implicitHeight: msgCol.implicitHeight + 20
                                        radius: 16
                                        color: msgWrap.isUser ? Qt.alpha(root.aiTint, 0.2) : Qt.alpha(root.fg, 0.07)
                                        border.width: 0.6
                                        border.color: msgWrap.isUser ? Qt.alpha(root.aiTint, 0.48) : Qt.alpha(root.fg, 0.14)

                                        HoverHandler {
                                            id: msgHover
                                        }

                                        Column {
                                            id: msgCol

                                            anchors.fill: parent
                                            anchors.margins: 10
                                            anchors.leftMargin: 14
                                            anchors.rightMargin: msgWrap.isUser ? 14 : 30
                                            spacing: 6

                                            StyledText {
                                                width: Math.min(implicitWidth, Math.round(msgWrap.width * 0.8) - 44)
                                                wrapMode: Text.Wrap
                                                textFormat: msgWrap.isUser ? Text.PlainText : Text.MarkdownText
                                                text: msgWrap.modelData.text
                                                color: root.fg
                                                font.pointSize: 8.7
                                            }

                                            // Badges d'actions réellement exécutées par Katana AI (cliquables → Cockpit / Projet)
                                            Flow {
                                                visible: (msgWrap.modelData.executed?.length ?? 0) > 0
                                                width: Math.min(Math.round(msgWrap.width * 0.74), 680)
                                                spacing: 6

                                                Repeater {
                                                    model: msgWrap.modelData.executed ?? []

                                                    Rectangle {
                                                        id: exBadge

                                                        required property var modelData
                                                        readonly property color bCol: modelData.ok ? root.green : root.red
                                                        readonly property bool clickable: root.badgeClickable(modelData)

                                                        width: exTxt.implicitWidth + 16
                                                        height: 22
                                                        radius: 11
                                                        scale: exArea.pressed && clickable ? 0.96 : 1
                                                        color: Qt.alpha(bCol, exArea.containsMouse && clickable ? 0.28 : 0.16)
                                                        border.width: clickable ? 0.7 : 0.5
                                                        border.color: Qt.alpha(bCol, exArea.containsMouse && clickable ? 0.75 : 0.45)

                                                        StyledText {
                                                            id: exTxt

                                                            anchors.centerIn: parent
                                                            text: `${exBadge.modelData.ok ? "✓" : "✕"} ${exBadge.modelData.label}${exBadge.clickable ? " ↗" : ""}`
                                                            color: exBadge.bCol
                                                            font.pointSize: 7.3
                                                            font.weight: Font.Bold
                                                        }

                                                        MouseArea {
                                                            id: exArea

                                                            anchors.fill: parent
                                                            hoverEnabled: true
                                                            cursorShape: exBadge.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                            onClicked: {
                                                                if (exBadge.clickable)
                                                                    root.openExecutedBadge(exBadge.modelData);
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        // Bouton Copier (réponse IA) ou Réutiliser (message utilisateur)
                                        Rectangle {
                                            visible: msgHover.hovered
                                            anchors.top: parent.top
                                            anchors.right: parent.right
                                            anchors.margins: 6
                                            width: 22
                                            height: 22
                                            radius: 11
                                            color: Qt.alpha(root.fg, msgCopyArea.containsMouse ? 0.18 : 0.09)

                                            MaterialIcon {
                                                anchors.centerIn: parent
                                                text: msgWrap.isUser ? "replay" : "content_copy"
                                                color: root.fgDim
                                                fontStyle: Tokens.font.icon.size(12).build()
                                            }

                                            MouseArea {
                                                id: msgCopyArea

                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    if (msgWrap.isUser) {
                                                        root.dockTarget = "ai";
                                                        dockInput.text = msgWrap.modelData.text;
                                                        dockInput.forceActiveFocus();
                                                    } else {
                                                        root.copyText(msgWrap.modelData.text, I18n.tr("Réponse copiée ✓"));
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            // Flux temps réel Katana AI (étapes en direct + badges live + bouton Annuler)
                            Rectangle {
                                visible: root.aiThinking
                                width: Math.min(chatCol.width, 640)
                                height: liveStreamCol.implicitHeight + 18
                                radius: 14
                                color: Qt.alpha(root.aiTint, 0.1)
                                border.width: 0.6
                                border.color: Qt.alpha(root.aiTint, 0.36)

                                Column {
                                    id: liveStreamCol

                                    anchors.fill: parent
                                    anchors.margins: 9
                                    spacing: 7

                                    Item {
                                        width: parent.width
                                        height: 24

                                        Row {
                                            anchors.left: parent.left
                                            anchors.right: cancelAiBtn.left
                                            anchors.rightMargin: 8
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 8

                                            MiniSpinner {
                                                size: 22
                                                tint: root.aiTint
                                                spinning: root.aiThinking
                                                done: false
                                                letter: "✦"
                                            }
                                            StyledText {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: parent.width - 30
                                                elide: Text.ElideRight
                                                text: root.aiStreamStatus || I18n.tr("Katana AI analyse ta flotte et transmet les ordres…")
                                                color: root.aiTint
                                                font.pointSize: 8.3
                                                font.weight: Font.DemiBold
                                            }
                                        }

                                        ActionChip {
                                            id: cancelAiBtn

                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            label: I18n.tr("Annuler")
                                            icon: "stop"
                                            tint: root.red
                                            onClicked: root.cancelCommander()
                                        }
                                    }

                                    Flow {
                                        visible: root.aiStreamBadges.length > 0
                                        width: parent.width
                                        spacing: 5

                                        Repeater {
                                            model: root.aiStreamBadges

                                            Rectangle {
                                                id: liveBadge

                                                required property var modelData
                                                readonly property color bCol: modelData.ok ? root.green : root.red

                                                width: lbTxt.implicitWidth + 14
                                                height: 20
                                                radius: 10
                                                color: Qt.alpha(bCol, 0.16)
                                                border.width: 0.5
                                                border.color: Qt.alpha(bCol, 0.45)

                                                StyledText {
                                                    id: lbTxt

                                                    anchors.centerIn: parent
                                                    text: `${liveBadge.modelData.ok ? "✓" : "✕"} ${liveBadge.modelData.label}`
                                                    color: liveBadge.bCol
                                                    font.pointSize: 7.1
                                                    font.weight: Font.Bold
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ════════════════ VUE 3 : ESCOUADE (SWARM DISPATCH & PROJETS) ════════════════
            Row {
                anchors.fill: parent
                visible: root.viewTab === 3
                spacing: 12

                Rectangle {
                    width: 390
                    height: parent.height
                    radius: 18
                    color: Qt.alpha(root.fg, 0.045)
                    border.width: 0.5
                    border.color: Qt.alpha(root.fg, 0.12)

                    Column {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        StyledText {
                            text: I18n.tr("PROJETS DÉTECTÉS (%1)").arg(root.projects.length)
                            color: root.fgDim
                            font.pointSize: 7.5
                            font.weight: Font.Black
                            font.letterSpacing: 0.7
                        }

                        // Filtre rapide de projets dans l'onglet Escouade
                        Rectangle {
                            width: parent.width
                            height: 30
                            radius: 15
                            color: Qt.alpha(root.fg, 0.06)
                            border.width: 0.5
                            border.color: swarmProjInput.activeFocus ? Qt.alpha(root.leadTint, 0.6) : Qt.alpha(root.fg, 0.14)

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 6

                                MaterialIcon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "search"
                                    color: root.fgDim
                                    fontStyle: Tokens.font.icon.size(13).build()
                                }
                                TextInput {
                                    id: swarmProjInput

                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 20
                                    height: 24
                                    verticalAlignment: Text.AlignVCenter
                                    color: root.fg
                                    font.pointSize: 7.9
                                    clip: true
                                    text: root.swarmProjectFilter
                                    onTextChanged: root.swarmProjectFilter = text

                                    StyledText {
                                        visible: swarmProjInput.text.length === 0
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: I18n.tr("Filtrer les projets…")
                                        color: root.fgMute
                                        font.pointSize: 7.6
                                    }
                                }
                            }
                        }

                        Flickable {
                            width: parent.width
                            height: parent.height - 64
                            contentWidth: width
                            contentHeight: projCol.implicitHeight
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds

                            Column {
                                id: projCol

                                width: parent.width
                                spacing: 5

                                Repeater {
                                    model: root.filteredProjectsList(root.swarmProjectFilter)

                                    Rectangle {
                                        id: pRow

                                        required property var modelData
                                        readonly property bool sel: root.currentProject?.cwd === modelData.cwd

                                        width: projCol.width
                                        height: 48
                                        radius: 12
                                        color: sel ? Qt.alpha(root.leadTint, 0.18) : Qt.alpha(root.fg, pRowArea.containsMouse ? 0.09 : 0.04)
                                        border.width: sel ? 0.8 : 0.5
                                        border.color: sel ? Qt.alpha(root.leadTint, 0.52) : Qt.alpha(root.fg, 0.1)

                                        Row {
                                            anchors.fill: parent
                                            anchors.leftMargin: 12
                                            anchors.rightMargin: 12
                                            spacing: 8

                                            MaterialIcon {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: "folder_code"
                                                color: pRow.sel ? root.leadTint : root.fgDim
                                                fontStyle: Tokens.font.icon.size(16).build()
                                                fill: pRow.sel ? 1 : 0
                                            }

                                            Column {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: parent.width - 96
                                                spacing: 1

                                                StyledText {
                                                    width: parent.width
                                                    elide: Text.ElideRight
                                                    text: pRow.modelData.name
                                                    color: root.fg
                                                    font.pointSize: 8.6
                                                    font.weight: Font.Bold
                                                }
                                                StyledText {
                                                    width: parent.width
                                                    elide: Text.ElideMiddle
                                                    text: pRow.modelData.cwd
                                                    color: root.fgDim
                                                    font.family: "monospace"
                                                    font.pointSize: 6.9
                                                }
                                            }

                                            StyledText {
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: Boolean(pRow.modelData.branch)
                                                text: `⎇ ${pRow.modelData.branch}`
                                                color: pRow.modelData.active ? root.green : root.fgDim
                                                font.pointSize: 7.2
                                                font.weight: Font.DemiBold
                                            }
                                        }

                                        MouseArea {
                                            id: pRowArea

                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.selectProjectByCwd(pRow.modelData.cwd)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    width: parent.width - 402
                    height: parent.height
                    radius: 18
                    color: Qt.alpha(root.fg, 0.045)
                    border.width: 0.5
                    border.color: Qt.alpha(root.leadTint, 0.24)

                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        // En-tête + toggle Git Worktree isolé
                        Item {
                            width: parent.width
                            height: 36

                            Column {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 1

                                StyledText {
                                    text: I18n.tr("DÉPLOIEMENT ESCOUADE (MULTI-AGENTS)")
                                    color: root.fg
                                    font.pointSize: 9.0
                                    font.weight: Font.Black
                                    font.letterSpacing: 0.65
                                }
                                StyledText {
                                    text: I18n.tr("Déploie tes moteurs avec rôles et isolation sur %1").arg(root.currentProject?.name ?? "~")
                                    color: root.fgDim
                                    font.pointSize: 7.8
                                }
                            }

                            Rectangle {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                width: wtRow.implicitWidth + 16
                                height: 28
                                radius: 14
                                color: root.swarmWorktree ? Qt.alpha(root.green, 0.2) : Qt.alpha(root.fg, wtArea.containsMouse ? 0.12 : 0.06)
                                border.width: 0.7
                                border.color: root.swarmWorktree ? Qt.alpha(root.green, 0.62) : Qt.alpha(root.fg, 0.18)

                                Row {
                                    id: wtRow

                                    anchors.centerIn: parent
                                    spacing: 5

                                    MaterialIcon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "account_tree"
                                        color: root.swarmWorktree ? root.green : root.fgDim
                                        fontStyle: Tokens.font.icon.size(13).build()
                                    }
                                    StyledText {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: I18n.tr("Worktree isolé")
                                        color: root.swarmWorktree ? root.green : root.fgDim
                                        font.pointSize: 7.3
                                        font.weight: Font.Bold
                                    }
                                }

                                MouseArea {
                                    id: wtArea

                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.swarmWorktree = !root.swarmWorktree
                                }
                            }
                        }

                        // Préréglages d'équipe avec rôles distincts
                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: [
                                    { id: "shared", icon: "hub", label: I18n.tr("Mission commune") },
                                    { id: "impl_review", icon: "rate_review", label: I18n.tr("Implémentation + Revue") },
                                    { id: "audit_perf", icon: "security", label: I18n.tr("Audit Sécu + Perf") },
                                    { id: "duel", icon: "compare", label: I18n.tr("Duel comparatif") }
                                ]

                                Rectangle {
                                    id: prPill

                                    required property var modelData
                                    readonly property bool sel: root.swarmPreset === modelData.id

                                    width: prRow.implicitWidth + 16
                                    height: 26
                                    radius: 13
                                    color: sel ? Qt.alpha(root.aiTint, 0.24) : Qt.alpha(root.fg, prArea.containsMouse ? 0.1 : 0.05)
                                    border.width: sel ? 0.7 : 0.4
                                    border.color: sel ? Qt.alpha(root.aiTint, 0.62) : Qt.alpha(root.fg, 0.14)

                                    Row {
                                        id: prRow

                                        anchors.centerIn: parent
                                        spacing: 4

                                        MaterialIcon {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: prPill.modelData.icon
                                            color: prPill.sel ? root.aiTint : root.fgDim
                                            fontStyle: Tokens.font.icon.size(12).build()
                                        }
                                        StyledText {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: prPill.modelData.label
                                            color: prPill.sel ? root.fg : root.fgDim
                                            font.pointSize: 7.3
                                            font.weight: prPill.sel ? Font.Bold : Font.DemiBold
                                        }
                                    }

                                    MouseArea {
                                        id: prArea

                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.swarmPreset = prPill.modelData.id
                                    }
                                }
                            }
                        }

                        Flow {
                            width: parent.width
                            spacing: 8

                            Repeater {
                                model: Agents.launchKinds

                                Rectangle {
                                    id: swBox

                                    required property string modelData
                                    readonly property bool on: !!root.swarmKinds[modelData]
                                    readonly property color tint: Agents.kindColour(modelData)
                                    readonly property string assignedRole: on ? root.swarmRoleFor(modelData) : ""

                                    width: Math.floor((parent.width - 16) / 3)
                                    height: 52
                                    radius: 14
                                    color: on ? Qt.alpha(tint, 0.22) : Qt.alpha(root.fg, swBoxArea.containsMouse ? 0.09 : 0.04)
                                    border.width: on ? 1 : 0.5
                                    border.color: on ? Qt.alpha(tint, 0.62) : Qt.alpha(root.fg, 0.14)

                                    Row {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 11
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 8

                                        MiniSpinner {
                                            size: 26
                                            tint: swBox.tint
                                            spinning: false
                                            done: false
                                            letter: Agents.kindLetter(swBox.modelData)
                                        }
                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter

                                            StyledText {
                                                text: Agents.kindName(swBox.modelData)
                                                color: root.fg
                                                font.pointSize: 8.6
                                                font.weight: Font.Bold
                                            }
                                            StyledText {
                                                text: swBox.assignedRole
                                                    ? swBox.assignedRole
                                                    : (swBox.on ? I18n.tr("Sélectionné") : I18n.tr("Cliquer pour ajouter"))
                                                color: swBox.on ? swBox.tint : root.fgDim
                                                font.pointSize: 7.0
                                                font.weight: swBox.assignedRole ? Font.Bold : Font.Normal
                                            }
                                        }
                                    }

                                    MouseArea {
                                        id: swBoxArea

                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.toggleSwarmKind(swBox.modelData)
                                    }
                                }
                            }
                        }

                        Flow {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: [
                                    I18n.tr("Audite le projet et liste les bugs prioritaires"),
                                    I18n.tr("Vérifie le lint, les types et corrige les erreurs"),
                                    I18n.tr("Explique l'architecture et propose 3 améliorations"),
                                    I18n.tr("Prépare un résumé git des derniers changements")
                                ]

                                ActionChip {
                                    required property string modelData
                                    label: modelData
                                    tint: root.fg
                                    onClicked: {
                                        swarmInput.text = modelData;
                                        swarmInput.forceActiveFocus();
                                    }
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 82
                            radius: 14
                            color: Qt.alpha(root.fg, 0.06)
                            border.width: 0.75
                            border.color: swarmInput.activeFocus ? Qt.alpha(root.leadTint, 0.65) : Qt.alpha(root.fg, 0.14)

                            MouseArea {
                                anchors.fill: parent
                                onClicked: swarmInput.forceActiveFocus()
                            }

                            TextEdit {
                                id: swarmInput

                                anchors.fill: parent
                                anchors.margins: 10
                                color: root.fg
                                font.pointSize: 8.8
                                wrapMode: TextEdit.Wrap
                                selectByMouse: true
                                activeFocusOnPress: true
                                Keys.onEscapePressed: {
                                    if (root.projectPickerOpen)
                                        root.closeProjectPicker();
                                    else if (root.modelPickerOpen)
                                        root.closeModelPicker();
                                    else
                                        root.close();
                                }
                                Keys.onPressed: event => {
                                    if ((event.modifiers & Qt.ControlModifier) && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                                        root.launchSwarm(swarmInput.text);
                                        event.accepted = true;
                                    }
                                }

                                StyledText {
                                    visible: swarmInput.text.length === 0
                                    text: I18n.tr("Écris la mission à envoyer à l'escouade (Ctrl+Entrée pour déployer)…")
                                    color: root.fgMute
                                    font.pointSize: 8.6
                                }
                            }
                        }

                        // Worktrees isolés actifs pour ce dépôt (Diff · Terminal · Supprimer)
                        Rectangle {
                            visible: root.worktrees.length > 0
                            width: parent.width
                            height: wtListCol.implicitHeight + 14
                            radius: 12
                            color: Qt.alpha(root.green, 0.08)
                            border.width: 0.5
                            border.color: Qt.alpha(root.green, 0.3)

                            Column {
                                id: wtListCol

                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 4

                                StyledText {
                                    text: I18n.tr("WORKTREES ESCOUADE ACTIFS (%1)").arg(root.worktrees.length)
                                    color: root.green
                                    font.pointSize: 6.7
                                    font.weight: Font.Black
                                    font.letterSpacing: 0.6
                                }

                                Repeater {
                                    model: root.worktrees.slice(0, 3)

                                    Item {
                                        id: wtRowItem

                                        required property var modelData
                                        width: wtListCol.width
                                        height: 24

                                        Row {
                                            anchors.left: parent.left
                                            anchors.right: wtBtns.left
                                            anchors.rightMargin: 6
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 6

                                            StyledText {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: Math.min(implicitWidth, parent.width - 70)
                                                elide: Text.ElideRight
                                                text: `⎇ ${wtRowItem.modelData.branch}`
                                                color: root.fg
                                                font.family: "monospace"
                                                font.pointSize: 7.2
                                                font.weight: Font.Bold
                                            }
                                            StyledText {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: wtRowItem.modelData.dirty > 0
                                                    ? I18n.tr("%1 modif.").arg(wtRowItem.modelData.dirty)
                                                    : I18n.tr("propre")
                                                color: wtRowItem.modelData.dirty > 0 ? root.orange : root.fgDim
                                                font.pointSize: 6.9
                                            }
                                        }

                                        Row {
                                            id: wtBtns

                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 4

                                            ActionChip {
                                                label: I18n.tr("Diff")
                                                tint: root.aiTint
                                                onClicked: root.openWorktreeDiff(wtRowItem.modelData.path)
                                            }
                                            ActionChip {
                                                label: I18n.tr("Terminal")
                                                tint: root.fg
                                                onClicked: Agents.openTerminal(wtRowItem.modelData.path)
                                            }
                                            ActionChip {
                                                label: I18n.tr("Suppr.")
                                                tint: root.red
                                                onClicked: root.removeWorktree(wtRowItem.modelData.path)
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            anchors.right: parent.right
                            width: deployRow.implicitWidth + 28
                            height: 36
                            radius: 18
                            scale: deployArea.pressed ? 0.96 : 1
                            color: Qt.alpha(root.leadTint, deployArea.containsMouse ? 0.34 : 0.24)
                            border.width: 1
                            border.color: Qt.alpha(root.leadTint, 0.65)

                            Behavior on scale { NumberAnimation { duration: 100 } }

                            Row {
                                id: deployRow

                                anchors.centerIn: parent
                                spacing: 7

                                MaterialIcon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "rocket_launch"
                                    color: root.leadTint
                                    fontStyle: Tokens.font.icon.size(16).build()
                                    fill: 1
                                }
                                StyledText {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.swarmDeploying
                                        ? I18n.tr("Déploiement…")
                                        : I18n.tr("Déployer l'escouade (%1)").arg(root.swarmCount)
                                    color: root.fg
                                    font.pointSize: 8.6
                                    font.weight: Font.Bold
                                }
                            }

                            MouseArea {
                                id: deployArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.launchSwarm(swarmInput.text)
                            }
                        }
                    }
                }
            }

            // Toast de confirmation
            Rectangle {
                visible: root.toastMsg.length > 0
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottomMargin: 12
                z: 40
                width: toastTxt.implicitWidth + 26
                height: 30
                radius: 15
                color: Qt.alpha(Colours.palette.m3surface, 0.94)
                border.width: 0.75
                border.color: Qt.alpha(root.leadTint, 0.55)

                StyledText {
                    id: toastTxt

                    anchors.centerIn: parent
                    text: root.toastMsg
                    color: root.fg
                    font.pointSize: 8.2
                    font.weight: Font.DemiBold
                }
            }
        }

        // ── 4. BARRE INFÉRIEURE : Katana Command Dock (Katana AI ou moteur direct) ──
        Rectangle {
            id: commandDock

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            anchors.bottomMargin: 14
            height: 54
            radius: 27
            color: Qt.alpha(root.fg, Colours.light ? 0.065 : 0.085)
            border.width: dockInput.activeFocus ? 1.0 : 0.75
            border.color: dockInput.activeFocus ? Qt.alpha(root.dockTint, 0.75) : Qt.alpha(root.fg, 0.18)

            Row {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 8
                spacing: 7

                // Pilules rapides : Katana AI (par défaut) + tous les moteurs
                Row {
                    id: dockEnginesRow

                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    // Pilule Commandant IA (Katana AI)
                    Rectangle {
                        readonly property bool sel: root.dockTarget === "ai"

                        width: sel ? dAiRow.implicitWidth + 14 : 30
                        height: 30
                        radius: 15
                        color: sel ? Qt.alpha(root.aiTint, 0.28) : Qt.alpha(root.aiTint, dAiArea.containsMouse ? 0.18 : 0.1)
                        border.width: sel ? 0.9 : 0.5
                        border.color: Qt.alpha(root.aiTint, sel ? 0.72 : 0.32)

                        Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

                        Row {
                            id: dAiRow

                            anchors.centerIn: parent
                            spacing: 4

                            MaterialIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "auto_awesome"
                                color: root.aiTint
                                fontStyle: Tokens.font.icon.size(13).build()
                                fill: 1
                            }
                            StyledText {
                                visible: root.dockTarget === "ai"
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Katana AI"
                                color: root.fg
                                font.pointSize: 7.4
                                font.weight: Font.Black
                            }
                        }

                        MouseArea {
                            id: dAiArea

                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.dockTarget = "ai";
                                dockInput.forceActiveFocus();
                            }
                        }
                    }

                    // Pilule Broadcast : diffuser un ordre à tous les agents CLI actifs
                    Rectangle {
                        visible: root.liveCliCount >= 2 || root.dockTarget === "all"
                        readonly property bool sel: root.dockTarget === "all"

                        width: sel ? dAllRow.implicitWidth + 14 : 30
                        height: 30
                        radius: 15
                        anchors.verticalCenter: parent.verticalCenter
                        color: sel ? Qt.alpha(root.orange, 0.28) : Qt.alpha(root.orange, dAllArea.containsMouse ? 0.18 : 0.1)
                        border.width: sel ? 0.9 : 0.5
                        border.color: Qt.alpha(root.orange, sel ? 0.72 : 0.35)

                        Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

                        Row {
                            id: dAllRow

                            anchors.centerIn: parent
                            spacing: 4

                            MaterialIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "campaign"
                                color: root.orange
                                fontStyle: Tokens.font.icon.size(13).build()
                                fill: 1
                            }
                            StyledText {
                                visible: root.dockTarget === "all"
                                anchors.verticalCenter: parent.verticalCenter
                                text: I18n.tr("Tous (%1)").arg(root.liveCliCount)
                                color: root.fg
                                font.pointSize: 7.4
                                font.weight: Font.Black
                            }
                        }

                        MouseArea {
                            id: dAllArea

                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.dockTarget = "all";
                                dockInput.forceActiveFocus();
                            }
                        }
                    }

                    Repeater {
                        model: Agents.launchKinds

                        Rectangle {
                            id: dKind

                            required property string modelData
                            readonly property bool sel: root.dockTarget === modelData
                            readonly property bool hasLive: Agents.shown.some(a => a.kind === modelData && a.alive)
                            readonly property color tint: Agents.kindColour(modelData)

                            width: sel ? dKindRow.implicitWidth + 14 : 28
                            height: 28
                            radius: 14
                            anchors.verticalCenter: parent.verticalCenter
                            color: sel ? Qt.alpha(tint, 0.24) : Qt.alpha(tint, dKindArea.containsMouse ? 0.16 : 0.08)
                            border.width: sel ? 0.8 : 0.5
                            border.color: Qt.alpha(tint, sel ? 0.65 : 0.25)

                            Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

                            Row {
                                id: dKindRow

                                anchors.centerIn: parent
                                spacing: 4

                                StyledText {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Agents.kindLetter(dKind.modelData)
                                    color: dKind.tint
                                    font.pointSize: 8
                                    font.weight: Font.Black
                                }
                                StyledText {
                                    visible: dKind.sel
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Agents.kindName(dKind.modelData)
                                    color: root.fg
                                    font.pointSize: 7.4
                                    font.weight: Font.Bold
                                }
                            }

                            // Petit point vert si ce moteur a déjà une session vivante
                            Rectangle {
                                visible: dKind.hasLive
                                anchors.top: parent.top
                                anchors.right: parent.right
                                width: 6
                                height: 6
                                radius: 3
                                color: root.green
                            }

                            MouseArea {
                                id: dKindArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.dockTarget = dKind.modelData;
                                    dockInput.forceActiveFocus();
                                }
                            }
                        }
                    }
                }

                // Sélecteur projet rapide
                Rectangle {
                    id: projChip

                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(148, projChipRow.implicitWidth + 16)
                    height: 30
                    radius: 15
                    color: Qt.alpha(root.fg, projChipArea.containsMouse ? 0.14 : 0.07)
                    border.width: 0.5
                    border.color: Qt.alpha(root.fg, 0.16)

                    Row {
                        id: projChipRow

                        anchors.centerIn: parent
                        spacing: 4

                        MaterialIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "folder"
                            color: root.fgDim
                            fontStyle: Tokens.font.icon.size(13).build()
                        }
                        StyledText {
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, 108)
                            elide: Text.ElideRight
                            text: root.currentProject?.name ?? "~"
                            color: root.fg
                            font.pointSize: 7.6
                            font.weight: Font.DemiBold
                        }
                    }

                    MouseArea {
                        id: projChipArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.openProjectPicker()
                    }
                }

                // Champ texte principal (focus garanti + historique ↑/↓)
                Item {
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(160, commandDock.width - dockEnginesRow.width - projChip.width - goBtn.width - 42)
                    height: 36

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.IBeamCursor
                        onClicked: dockInput.forceActiveFocus()
                    }

                    TextInput {
                        id: dockInput

                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        color: root.fg
                        font.pointSize: 8.8
                        clip: true
                        selectByMouse: true
                        activeFocusOnPress: true
                        Keys.onEscapePressed: {
                            if (root.projectPickerOpen)
                                root.closeProjectPicker();
                            else if (root.modelPickerOpen)
                                root.closeModelPicker();
                            else
                                root.close();
                        }
                        Keys.onUpPressed: {
                            if (root.dockHistory.length === 0)
                                return;
                            const nextIdx = root.dockHistIdx < 0
                                ? root.dockHistory.length - 1
                                : Math.max(0, root.dockHistIdx - 1);
                            root.dockHistIdx = nextIdx;
                            dockInput.text = root.dockHistory[nextIdx] || "";
                        }
                        Keys.onDownPressed: {
                            if (root.dockHistIdx < 0)
                                return;
                            if (root.dockHistIdx >= root.dockHistory.length - 1) {
                                root.dockHistIdx = -1;
                                dockInput.text = "";
                            } else {
                                root.dockHistIdx = root.dockHistIdx + 1;
                                dockInput.text = root.dockHistory[root.dockHistIdx] || "";
                            }
                        }
                        onAccepted: {
                            root.submitDock(text);
                            text = "";
                        }

                        StyledText {
                            visible: dockInput.text.length === 0
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width
                            elide: Text.ElideRight
                            text: root.dockTarget === "ai"
                                ? I18n.tr("Parle à Katana AI : « Dis à AGY CLI de… », « Lance Codex sur… »")
                                : root.dockTarget === "all"
                                    ? I18n.tr("Diffuser un ordre à tous les %1 agent(s) CLI actifs…").arg(root.liveCliCount)
                                    : root.dockExistingAgent
                                        ? I18n.tr("Écrire en direct à %1 (%2)…").arg(Agents.kindName(root.dockTarget)).arg(root.dockExistingAgent.project)
                                        : I18n.tr("Lancer %1 sur %2 avec une mission…").arg(Agents.kindName(root.dockTarget)).arg(root.currentProject?.name ?? "~")
                            color: root.fgMute
                            font.pointSize: 8.3
                        }
                    }
                }

                // Bouton Envoyer / Lancer / Diffuser
                Rectangle {
                    id: goBtn

                    anchors.verticalCenter: parent.verticalCenter
                    width: goRow.implicitWidth + 20
                    height: 34
                    radius: 17
                    scale: goArea.pressed ? 0.94 : 1
                    color: Qt.alpha(root.dockTint, goArea.containsMouse ? 0.34 : 0.22)
                    border.width: 0.8
                    border.color: Qt.alpha(root.dockTint, 0.65)

                    Behavior on scale { NumberAnimation { duration: 100 } }

                    Row {
                        id: goRow

                        anchors.centerIn: parent
                        spacing: 5

                        MaterialIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.dockTarget === "ai" ? "auto_awesome" : (root.dockTarget === "all" ? "campaign" : (root.dockExistingAgent ? "send" : "play_arrow"))
                            color: root.dockTint
                            fontStyle: Tokens.font.icon.size(15).build()
                            fill: 1
                        }
                        StyledText {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.aiThinking || root.broadcasting
                                ? I18n.tr("…")
                                : root.dockTarget === "ai"
                                    ? I18n.tr("Ordonner")
                                    : root.dockTarget === "all"
                                        ? I18n.tr("Diffuser")
                                        : root.dockExistingAgent
                                            ? I18n.tr("Envoyer")
                                            : I18n.tr("Lancer")
                            color: root.fg
                            font.pointSize: 8.1
                            font.weight: Font.Bold
                        }
                    }

                    MouseArea {
                        id: goArea

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.submitDock(dockInput.text);
                            dockInput.text = "";
                            dockInput.forceActiveFocus();
                        }
                    }
                }
            }
        }

        // ── 5. OVERLAY SÉLECTEUR DE MODÈLE & EFFORT EN 1 CLIC ──
        Rectangle {
            id: modelPickerOverlay

            visible: root.modelPickerOpen
            anchors.fill: parent
            z: 60
            radius: 30
            color: Qt.rgba(0, 0, 0, Colours.light ? 0.28 : 0.56)

            MouseArea {
                anchors.fill: parent
                onClicked: root.closeModelPicker()
            }

            Rectangle {
                id: pickerCard

                readonly property color tint: root.modelPickerAgent ? Agents.kindColour(root.modelPickerAgent.kind) : root.aiTint

                anchors.centerIn: parent
                width: Math.min(540, parent.width - 60)
                height: Math.min(460, parent.height - 80)
                radius: 22
                color: Qt.alpha(Colours.palette.m3surface, Colours.light ? 0.96 : 0.94)
                border.width: 0.9
                border.color: Qt.alpha(tint, 0.55)

                MouseArea {
                    anchors.fill: parent
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    // En-tête du sélecteur
                    Item {
                        width: parent.width
                        height: 36

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 9

                            Rectangle {
                                width: 32
                                height: 32
                                radius: 11
                                color: Qt.alpha(pickerCard.tint, 0.2)
                                border.width: 0.6
                                border.color: Qt.alpha(pickerCard.tint, 0.5)

                                MaterialIcon {
                                    anchors.centerIn: parent
                                    text: "tune"
                                    color: pickerCard.tint
                                    fontStyle: Tokens.font.icon.size(16).build()
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 1

                                StyledText {
                                    text: I18n.tr("MODÈLE & EFFORT · %1").arg(Agents.kindName(root.modelPickerAgent?.kind ?? "").toUpperCase())
                                    color: root.fg
                                    font.pointSize: 9.2
                                    font.weight: Font.Black
                                    font.letterSpacing: 0.65
                                }
                                StyledText {
                                    text: `${root.modelPickerAgent?.project ?? ""} · ${root.modelPickerAgent?.model || I18n.tr("Modèle par défaut")}`
                                    color: root.fgDim
                                    font.pointSize: 7.5
                                }
                            }
                        }

                        Rectangle {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 28
                            height: 28
                            radius: 14
                            color: Qt.alpha(root.fg, pkCloseArea.containsMouse ? 0.16 : 0.08)

                            MaterialIcon {
                                anchors.centerIn: parent
                                text: "close"
                                color: root.fg
                                fontStyle: Tokens.font.icon.size(14).build()
                            }

                            MouseArea {
                                id: pkCloseArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.closeModelPicker()
                            }
                        }
                    }

                    // Avertissement honnête si GUI non pilotable en direct
                    Rectangle {
                        visible: !root.modelCatalogLoading && !root.modelCatalog.canApplyLive
                        width: parent.width
                        height: 36
                        radius: 10
                        color: Qt.alpha(root.orange, 0.14)
                        border.width: 0.5
                        border.color: Qt.alpha(root.orange, 0.42)

                        StyledText {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            text: I18n.tr("Fenêtre graphique : sélectionne le modèle directement dans son menu.")
                            color: root.orange
                            font.pointSize: 7.6
                            font.weight: Font.DemiBold
                        }
                    }

                    // Pilules de niveau d'effort
                    Row {
                        visible: (root.modelCatalog.efforts?.length ?? 0) > 0
                        width: parent.width
                        spacing: 6

                        StyledText {
                            anchors.verticalCenter: parent.verticalCenter
                            text: I18n.tr("EFFORT")
                            color: root.fgDim
                            font.pointSize: 7
                            font.weight: Font.Black
                            font.letterSpacing: 0.6
                        }

                        Repeater {
                            model: root.modelCatalog.efforts ?? []

                            Rectangle {
                                id: effPill

                                required property string modelData
                                readonly property bool sel: root.pickedEffort === modelData

                                width: effTxt.implicitWidth + 18
                                height: 24
                                radius: 12
                                color: sel ? Qt.alpha(pickerCard.tint, 0.28) : Qt.alpha(root.fg, effArea.containsMouse ? 0.12 : 0.06)
                                border.width: sel ? 0.8 : 0.5
                                border.color: sel ? Qt.alpha(pickerCard.tint, 0.72) : Qt.alpha(root.fg, 0.16)

                                StyledText {
                                    id: effTxt

                                    anchors.centerIn: parent
                                    text: effPill.modelData.toUpperCase()
                                    color: effPill.sel ? root.fg : root.fgDim
                                    font.pointSize: 7.1
                                    font.weight: effPill.sel ? Font.Black : Font.DemiBold
                                }

                                MouseArea {
                                    id: effArea

                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.applyEffortOnly(effPill.modelData)
                                }
                            }
                        }
                    }

                    // Champ de filtre rapide
                    Rectangle {
                        width: parent.width
                        height: 34
                        radius: 17
                        color: Qt.alpha(root.fg, 0.06)
                        border.width: 0.6
                        border.color: modelSearchInput.activeFocus ? Qt.alpha(pickerCard.tint, 0.65) : Qt.alpha(root.fg, 0.16)

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 7

                            MaterialIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "search"
                                color: root.fgDim
                                fontStyle: Tokens.font.icon.size(14).build()
                            }

                            TextInput {
                                id: modelSearchInput

                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 24
                                height: 28
                                verticalAlignment: Text.AlignVCenter
                                color: root.fg
                                font.pointSize: 8.3
                                clip: true
                                text: root.modelFilterText
                                onTextChanged: root.modelFilterText = text
                                Keys.onEscapePressed: root.closeModelPicker()

                                StyledText {
                                    visible: modelSearchInput.text.length === 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: I18n.tr("Filtrer les modèles…")
                                    color: root.fgMute
                                    font.pointSize: 8
                                }
                            }
                        }
                    }

                    // Liste des modèles disponibles
                    Flickable {
                        width: parent.width
                        height: parent.height - ((root.modelCatalog.efforts?.length ?? 0) > 0 ? 156 : 124) - (!root.modelCatalogLoading && !root.modelCatalog.canApplyLive ? 48 : 0)
                        contentWidth: width
                        contentHeight: pkListCol.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds

                        Column {
                            id: pkListCol

                            width: parent.width
                            spacing: 6

                            StyledText {
                                visible: root.modelCatalogLoading
                                text: I18n.tr("Chargement du catalogue de modèles…")
                                color: root.fgDim
                                font.pointSize: 8.2
                            }

                            Repeater {
                                model: root.modelCatalogLoading ? [] : root.filteredModelGroups()

                                Rectangle {
                                    id: mRow

                                    required property var modelData
                                    readonly property bool isCurrent: {
                                        const cur = String(root.modelPickerAgent?.model || "").toLowerCase();
                                        return cur.length > 0 && (cur.indexOf(String(modelData.base || "").toLowerCase()) >= 0 || cur === String(modelData.slug || "").toLowerCase());
                                    }

                                    width: pkListCol.width
                                    height: 44
                                    radius: 12
                                    scale: mRowArea.pressed ? 0.98 : 1
                                    color: isCurrent ? Qt.alpha(pickerCard.tint, 0.2) : Qt.alpha(root.fg, mRowArea.containsMouse ? 0.11 : 0.05)
                                    border.width: isCurrent ? 0.9 : 0.5
                                    border.color: isCurrent ? Qt.alpha(pickerCard.tint, 0.62) : Qt.alpha(root.fg, 0.12)

                                    Behavior on scale { NumberAnimation { duration: 90 } }

                                    Row {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        spacing: 8

                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: parent.width - 110
                                            spacing: 1

                                            StyledText {
                                                width: parent.width
                                                elide: Text.ElideRight
                                                text: mRow.modelData.base ?? mRow.modelData.display ?? ""
                                                color: root.fg
                                                font.pointSize: 8.5
                                                font.weight: Font.Bold
                                            }
                                            StyledText {
                                                width: parent.width
                                                elide: Text.ElideRight
                                                text: mRow.modelData.slug ?? ""
                                                color: root.fgDim
                                                font.family: "monospace"
                                                font.pointSize: 6.9
                                            }
                                        }

                                        StyledText {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 98
                                            horizontalAlignment: Text.AlignRight
                                            text: root.applyingModel
                                                ? I18n.tr("Application…")
                                                : (mRow.isCurrent ? I18n.tr("● Actif") : I18n.tr("Appliquer →"))
                                            color: mRow.isCurrent ? root.green : pickerCard.tint
                                            font.pointSize: 7.4
                                            font.weight: Font.Bold
                                        }
                                    }

                                    MouseArea {
                                        id: mRowArea

                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.applyPickedModel(mRow.modelData)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        // ── 6. OVERLAY PALETTE PROJETS RAPIDE (Ctrl+P ou clic sur projChip) ──
        Rectangle {
            id: projectPickerOverlay

            readonly property var hits: root.filteredProjectsList(root.projectPickerQuery)

            visible: root.projectPickerOpen
            anchors.fill: parent
            z: 65
            radius: 30
            color: Qt.rgba(0, 0, 0, Colours.light ? 0.28 : 0.56)

            MouseArea {
                anchors.fill: parent
                onClicked: root.closeProjectPicker()
            }

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(520, parent.width - 60)
                height: Math.min(430, parent.height - 90)
                radius: 22
                color: Qt.alpha(Colours.palette.m3surface, Colours.light ? 0.96 : 0.94)
                border.width: 0.9
                border.color: Qt.alpha(root.leadTint, 0.55)

                MouseArea {
                    anchors.fill: parent
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 10

                    Item {
                        width: parent.width
                        height: 28

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 7

                            MaterialIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "folder_code"
                                color: root.leadTint
                                fontStyle: Tokens.font.icon.size(17).build()
                                fill: 1
                            }
                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: I18n.tr("CHANGER DE PROJET (Ctrl+P)")
                                color: root.fg
                                font.pointSize: 9.0
                                font.weight: Font.Black
                                font.letterSpacing: 0.65
                            }
                        }

                        Rectangle {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 26
                            height: 26
                            radius: 13
                            color: Qt.alpha(root.fg, ppCloseArea.containsMouse ? 0.16 : 0.08)

                            MaterialIcon {
                                anchors.centerIn: parent
                                text: "close"
                                color: root.fg
                                fontStyle: Tokens.font.icon.size(14).build()
                            }

                            MouseArea {
                                id: ppCloseArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.closeProjectPicker()
                            }
                        }
                    }

                    Rectangle {
                        width: parent.width
                        height: 36
                        radius: 18
                        color: Qt.alpha(root.fg, 0.07)
                        border.width: 0.7
                        border.color: Qt.alpha(root.leadTint, 0.6)

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 7

                            MaterialIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "search"
                                color: root.leadTint
                                fontStyle: Tokens.font.icon.size(15).build()
                            }
                            TextInput {
                                id: projectSearchInput

                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 24
                                height: 28
                                verticalAlignment: Text.AlignVCenter
                                color: root.fg
                                font.pointSize: 8.6
                                clip: true
                                text: root.projectPickerQuery
                                onTextChanged: {
                                    root.projectPickerQuery = text;
                                    root.projectPickerCursor = 0;
                                }
                                Keys.onEscapePressed: root.closeProjectPicker()
                                Keys.onDownPressed: {
                                    if (projectPickerOverlay.hits.length > 0)
                                        root.projectPickerCursor = Math.min(projectPickerOverlay.hits.length - 1, root.projectPickerCursor + 1);
                                }
                                Keys.onUpPressed: {
                                    if (projectPickerOverlay.hits.length > 0)
                                        root.projectPickerCursor = Math.max(0, root.projectPickerCursor - 1);
                                }
                                onAccepted: {
                                    const hits = projectPickerOverlay.hits;
                                    if (hits.length > 0) {
                                        const chosen = hits[Math.max(0, Math.min(root.projectPickerCursor, hits.length - 1))];
                                        root.selectProjectByCwd(chosen.cwd);
                                        root.closeProjectPicker();
                                        dockInput.forceActiveFocus();
                                    }
                                }

                                StyledText {
                                    visible: projectSearchInput.text.length === 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: I18n.tr("Chercher un projet par nom, chemin ou branche…")
                                    color: root.fgMute
                                    font.pointSize: 8.2
                                }
                            }
                        }
                    }

                    Flickable {
                        width: parent.width
                        height: parent.height - 84
                        contentWidth: width
                        contentHeight: ppCol.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds

                        Column {
                            id: ppCol

                            width: parent.width
                            spacing: 5

                            Repeater {
                                model: projectPickerOverlay.hits

                                Rectangle {
                                    id: ppItem

                                    required property var modelData
                                    required property int index
                                    readonly property bool sel: root.projectPickerCursor === index || root.currentProject?.cwd === modelData.cwd

                                    width: ppCol.width
                                    height: 44
                                    radius: 12
                                    color: root.projectPickerCursor === index
                                        ? Qt.alpha(root.leadTint, 0.22)
                                        : Qt.alpha(root.fg, ppArea.containsMouse ? 0.1 : 0.04)
                                    border.width: sel ? 0.7 : 0.4
                                    border.color: sel ? Qt.alpha(root.leadTint, 0.56) : Qt.alpha(root.fg, 0.1)

                                    Row {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        spacing: 8

                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: parent.width - 94
                                            spacing: 1

                                            StyledText {
                                                width: parent.width
                                                elide: Text.ElideRight
                                                text: ppItem.modelData.name
                                                color: root.fg
                                                font.pointSize: 8.6
                                                font.weight: Font.Bold
                                            }
                                            StyledText {
                                                width: parent.width
                                                elide: Text.ElideMiddle
                                                text: ppItem.modelData.cwd
                                                color: root.fgDim
                                                font.family: "monospace"
                                                font.pointSize: 6.9
                                            }
                                        }

                                        StyledText {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 84
                                            horizontalAlignment: Text.AlignRight
                                            elide: Text.ElideRight
                                            visible: Boolean(ppItem.modelData.branch)
                                            text: `⎇ ${ppItem.modelData.branch}`
                                            color: ppItem.modelData.active ? root.green : root.fgDim
                                            font.pointSize: 7.2
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    MouseArea {
                                        id: ppArea

                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            root.selectProjectByCwd(ppItem.modelData.cwd);
                                            root.closeProjectPicker();
                                            dockInput.forceActiveFocus();
                                        }
                                    }
                                }
                            }

                            StyledText {
                                visible: projectPickerOverlay.hits.length === 0
                                text: I18n.tr("Aucun projet correspondant.")
                                color: root.fgDim
                                font.pointSize: 8.2
                            }
                        }
                    }
                }
            }
        }
        // ── 7. OVERLAY AIDE RACCOURCIS CLAVIER (F1 / Ctrl+/) ──
        Rectangle {
            id: helpOverlay

            visible: root.helpOpen
            anchors.fill: parent
            z: 70
            radius: 30
            color: Qt.rgba(0, 0, 0, Colours.light ? 0.28 : 0.56)

            MouseArea {
                anchors.fill: parent
                onClicked: root.helpOpen = false
            }

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(620, parent.width - 60)
                height: helpCol.implicitHeight + 36
                radius: 22
                color: Qt.alpha(Colours.palette.m3surface, Colours.light ? 0.97 : 0.95)
                border.width: 0.9
                border.color: Qt.alpha(root.aiTint, 0.52)

                MouseArea {
                    anchors.fill: parent
                }

                Column {
                    id: helpCol

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 18
                    spacing: 12

                    Item {
                        width: parent.width
                        height: 28

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            MaterialIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "keyboard"
                                color: root.aiTint
                                fontStyle: Tokens.font.icon.size(17).build()
                            }
                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: I18n.tr("RACCOURCIS CLAVIER · AGENT OS STUDIO")
                                color: root.fg
                                font.pointSize: 9.0
                                font.weight: Font.Black
                                font.letterSpacing: 0.65
                            }
                        }

                        Rectangle {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 26
                            height: 26
                            radius: 13
                            color: Qt.alpha(root.fg, hCloseArea.containsMouse ? 0.16 : 0.08)

                            MaterialIcon {
                                anchors.centerIn: parent
                                text: "close"
                                color: root.fg
                                fontStyle: Tokens.font.icon.size(14).build()
                            }

                            MouseArea {
                                id: hCloseArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.helpOpen = false
                            }
                        }
                    }

                    Grid {
                        width: parent.width
                        columns: 2
                        columnSpacing: 14
                        rowSpacing: 8

                        Repeater {
                            model: [
                                { k: "Ctrl + 1..4", d: I18n.tr("Changer d'onglet (Canvas / Cockpit / Katana / Escouade)") },
                                { k: "Ctrl + P", d: I18n.tr("Palette rapide de recherche de projet") },
                                { k: "Alt + 1..7", d: I18n.tr("Choisir Katana AI ou un moteur dans le Dock") },
                                { k: "Alt + ↑ / ↓", d: I18n.tr("Naviguer d'un agent à l'autre dans le Cockpit") },
                                { k: "Alt + A / D", d: I18n.tr("Autoriser / Refuser la permission active") },
                                { k: "Ctrl + Espace", d: I18n.tr("Dictée vocale dans le champ actif") },
                                { k: "↑ / ↓ (Dock)", d: I18n.tr("Historique des commandes envoyées") },
                                { k: "Ctrl + Entrée", d: I18n.tr("Déployer l'escouade immédiatement") },
                                { k: "Molette / Glisser", d: I18n.tr("Zoomer et déplacer le Canvas Spatial") },
                                { k: "F1 / Échap", d: I18n.tr("Afficher l'aide / Fermer le panneau") }
                            ]

                            Row {
                                required property var modelData
                                width: Math.floor((helpCol.width - 14) / 2)
                                spacing: 8

                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.max(82, hkTxt.implicitWidth + 12)
                                    height: 22
                                    radius: 6
                                    color: Qt.alpha(root.aiTint, 0.16)
                                    border.width: 0.5
                                    border.color: Qt.alpha(root.aiTint, 0.42)

                                    StyledText {
                                        id: hkTxt

                                        anchors.centerIn: parent
                                        text: modelData.k
                                        color: root.fg
                                        font.family: "monospace"
                                        font.pointSize: 7.0
                                        font.weight: Font.Bold
                                    }
                                }

                                StyledText {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 96
                                    wrapMode: Text.Wrap
                                    text: modelData.d
                                    color: root.fgDim
                                    font.pointSize: 7.4
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ════════════════════ Sous-composants réutilisables ════════════════════

    component MiniSpinner: Item {
        id: ms

        property color tint
        property bool spinning
        property bool done
        property string letter
        property real size: 28
        readonly property bool animOn: ms.spinning && !ms.done

        width: size
        height: size

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Qt.alpha(ms.tint, 0.16)
            border.width: 0.6
            border.color: Qt.alpha(ms.tint, 0.38)
        }

        Shape {
            anchors.fill: parent
            visible: !ms.done
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                strokeWidth: 2.4
                strokeColor: ms.tint
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap

                PathAngleArc {
                    centerX: ms.size / 2
                    centerY: ms.size / 2
                    radiusX: ms.size / 2 - 2
                    radiusY: ms.size / 2 - 2
                    startAngle: -90
                    sweepAngle: ms.animOn ? 125 : 360
                }
            }

            RotationAnimation on rotation {
                running: ms.animOn
                loops: Animation.Infinite
                from: 0
                to: 360
                duration: 1100
            }
        }

        StyledText {
            anchors.centerIn: parent
            visible: !ms.done
            text: ms.letter || "✦"
            color: ms.tint
            font.pointSize: ms.size >= 34 ? 10.5 : 8.8
            font.weight: Font.Black
        }

        MaterialIcon {
            anchors.centerIn: parent
            visible: ms.done
            text: "check"
            color: ms.tint
            fontStyle: Tokens.font.icon.size(ms.size >= 34 ? 17 : 14).build()
            fill: 1
        }
    }

    component ActionChip: Rectangle {
        id: ac

        property string label
        property string icon
        property color tint: root.fg
        property bool filled: false
        signal clicked

        width: acRow.implicitWidth + 16
        height: 24
        radius: 12
        scale: acArea.pressed ? 0.94 : 1
        color: filled
            ? Qt.alpha(tint, acArea.containsMouse ? 0.3 : 0.2)
            : Qt.alpha(tint, acArea.containsMouse ? 0.16 : 0.08)
        border.width: 0.5
        border.color: Qt.alpha(tint, filled ? 0.52 : 0.24)

        Behavior on scale { NumberAnimation { duration: 100 } }

        Row {
            id: acRow

            anchors.centerIn: parent
            spacing: 4

            MaterialIcon {
                visible: ac.icon.length > 0
                anchors.verticalCenter: parent.verticalCenter
                text: ac.icon
                color: ac.filled ? ac.tint : root.fgDim
                fontStyle: Tokens.font.icon.size(12).build()
                fill: 1
            }
            StyledText {
                anchors.verticalCenter: parent.verticalCenter
                text: ac.label
                color: ac.filled ? ac.tint : root.fg
                font.pointSize: 7.4
                font.weight: Font.Bold
            }
        }

        MouseArea {
            id: acArea

            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: ac.clicked()
        }
    }

    component FilterChip: Rectangle {
        id: fc

        property string label
        property int count: 0
        property bool selected: false
        property color tint: root.fg
        signal clicked

        width: fcTxt.implicitWidth + 16
        height: 24
        radius: 12
        color: selected ? Qt.alpha(tint, 0.22) : Qt.alpha(root.fg, fcArea.containsMouse ? 0.12 : 0.06)
        border.width: 0.5
        border.color: selected ? Qt.alpha(tint, 0.56) : Qt.alpha(root.fg, 0.14)

        StyledText {
            id: fcTxt

            anchors.centerIn: parent
            text: `${fc.label} (${fc.count})`
            color: fc.selected ? fc.tint : root.fgDim
            font.pointSize: 7.3
            font.weight: fc.selected ? Font.Bold : Font.DemiBold
            font.features: { "tnum": 1 }
        }

        MouseArea {
            id: fcArea

            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: fc.clicked()
        }
    }

    component KpiBox: Rectangle {
        id: kb

        property string label
        property string value
        property string sub
        property color tint: root.fg

        height: 60
        radius: 14
        color: Qt.alpha(kb.tint, 0.08)
        border.width: 0.5
        border.color: Qt.alpha(kb.tint, 0.22)

        Column {
            anchors.fill: parent
            anchors.margins: 9
            spacing: 1

            StyledText {
                text: kb.label
                color: root.fgDim
                font.pointSize: 6.5
                font.weight: Font.Black
                font.letterSpacing: 0.6
            }
            StyledText {
                width: parent.width
                elide: Text.ElideRight
                text: kb.value
                color: kb.tint
                font.pointSize: 11.5
                font.weight: Font.Black
                font.features: { "tnum": 1 }
            }
            StyledText {
                width: parent.width
                elide: Text.ElideRight
                text: kb.sub
                color: root.fgDim
                font.pointSize: 6.9
            }
        }
    }
}
